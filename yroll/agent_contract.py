"""YROLL Agent Contract (v0.2 §29): unified API for MCP / Agent / GUI.

Spec §29:
    get_project_state()
    get_selection()
    get_timeline()
    get_impact()
    preview_mutation()
    commit_mutation()
    undo()
    redo()
    request_edit_lease()
    release_edit_lease()
    handoff()

This module wraps the existing core APIs into a single import-friendly
interface that MCP server / GUI / external Agent can call directly
without going through HTTP. All methods respect the Mutation Gate:
session_id + base_revision are required for any mutation.

Usage:
    from yroll.agent_contract import YrollAgent
    agent = YrollAgent(core, session_id=None)
    # Read-only: always works
    state = agent.get_project_state()
    # Mutations: need session + lease
    sid = agent.request_edit_lease(actor="human", mode="edit")
    try:
        pv = agent.preview_mutation(selection, "move", {"delta_seconds": 1.0})
        if pv["summary"]["n_secondary"] < 5:
            agent.commit_mutation(selection, "move", {"delta_seconds": 1.0})
    finally:
        agent.release_edit_lease(sid)
"""
from __future__ import annotations

from typing import Optional

from yroll.core.commands import CommandError, CommandLayer
from yroll.core.history import HistoryAPI
from yroll.core.lease import (
    Actor as LeaseActor, LeaseMode, get_lease_store, require_edit_right,
    get_current_revision,
)
from yroll.core.revision import check_project_revision
from yroll.core.links import impact_preview, preview_mutation
from yroll.core.project import ProjectCore
from yroll.core.selection import Selection


class YrollAgent:
    """Single front door for any external editor (MCP, GUI, scripts)."""

    def __init__(self, core: ProjectCore, session_id: Optional[str] = None,
                 base_revision: Optional[int] = None):
        self.core = core
        self.session_id = session_id
        self.base_revision = (
            base_revision if base_revision is not None
            else get_current_revision(core))

    # ---------- Read-only ----------

    def get_project_state(self) -> dict:
        return self.core.project.model_dump()

    def get_selection(self) -> list[str]:
        """Project has no Selection field yet — return clip_ids list.
        GUI is expected to pass its current selection separately."""
        return list(self.core.project.clips.keys())

    def get_timeline(self) -> dict:
        return self.core.project.timeline.model_dump()

    def get_impact(self, clip_id: str, op: str = "remove") -> dict:
        return impact_preview(self.core.project, clip_id, op)

    def get_lease_state(self) -> dict:
        ls = get_lease_store(self.core).get(self.core.project.project_id)
        if ls is None:
            return {"held_by": None, "session_id": None, "alive": False,
                    "base_revision": get_current_revision(self.core)}
        return {"held_by": ls.actor.value, "session_id": ls.session_id,
                "alive": ls.is_alive(),
                "base_revision": ls.base_revision}

    # ---------- Mutation gate ----------

    def _gate(self) -> None:
        """Raise if gate fails. No-op when session_id is None (read-only).

        base_revision stays as caller set it; callers should manually
        advance it after successful mutation.
        """
        if self.session_id is None:
            return
        require_edit_right(self.core, self.session_id)
        check_project_revision(self.core, self.base_revision)

    # ---------- Mutations ----------

    def preview_mutation(self, selection, op: str,
                         params: Optional[dict] = None) -> dict:
        sel = (selection if isinstance(selection, Selection)
               else Selection.from_clip_or_id(selection))
        return preview_mutation(self.core.project, sel, op, params)

    def commit_mutation(self, selection, op: str,
                        params: Optional[dict] = None,
                        why: str = "") -> dict:
        """Dispatch to the right CommandLayer method based on op."""
        self._gate()
        sel = (selection if isinstance(selection, Selection)
               else Selection.from_clip_or_id(selection))
        cmd = CommandLayer(self.core, who=LeaseActor.HUMAN)
        if op == "move":
            delta = float((params or {}).get("delta_seconds", 0.0))
            res = cmd.move_selection(sel, delta_seconds=delta, why=why)
        elif op == "delete":
            res = cmd.delete_selection(
                sel, ripple=bool((params or {}).get("ripple", False)),
                why=why)
        elif op == "ripple_delete":
            res = cmd.delete_selection(sel, ripple=True, why=why)
        else:
            raise CommandError(f"unsupported op for selection: {op}")
        # Refresh base_revision after mutation
        self.base_revision = get_current_revision(self.core)
        return res.model_dump()

    def undo(self, why: str = "") -> Optional[dict]:
        self._gate()
        rev = HistoryAPI(self.core).undo(who="human", why=why)
        self.base_revision = get_current_revision(self.core)
        return rev

    def redo(self, why: str = "") -> Optional[dict]:
        self._gate()
        redone = HistoryAPI(self.core).redo(who="human", why=why)
        self.base_revision = get_current_revision(self.core)
        return redone

    # ---------- Lease ----------

    def request_edit_lease(self, actor: str = "human",
                           mode: str = "edit",
                           human_label: str = "") -> str:
        ls = get_lease_store(self.core).acquire(
            self.core.project.project_id,
            LeaseActor(actor), LeaseMode(mode),
            self.base_revision, human_label)
        self.session_id = ls.session_id
        return ls.session_id

    def release_edit_lease(self, session_id: Optional[str] = None) -> bool:
        sid = session_id or self.session_id
        if sid is None:
            return False
        ok = get_lease_store(self.core).release(
            self.core.project.project_id, sid)
        if ok and sid == self.session_id:
            self.session_id = None
        return ok

    def handoff(self, from_session_id: Optional[str] = None,
                to_actor: str = "agent", to_mode: str = "edit",
                to_label: str = "") -> str:
        sid = from_session_id or self.session_id
        if sid is None:
            raise CommandError("handoff requires active session_id")
        ls = get_lease_store(self.core).handoff(
            self.core.project.project_id, sid,
            LeaseActor(to_actor), LeaseMode(to_mode), to_label)
        self.session_id = ls.session_id
        return ls.session_id
