"""YROLL Edit Lease (P0-10) - editing-rights management.

Avoids the OpenChatCut "GUI open blocks MCP / MCP open blocks GUI" problem.
YROLL instead queues writers through a lease, with UI always showing
who currently holds the editing rights.
"""
from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from yroll.core.project import ProjectCore


class LeaseMode(str, Enum):
    EDIT = "edit"        # write rights
    PROPOSE = "propose"  # can preview/plan, but commit needs edit
    OBSERVE = "observe"  # read-only


class Actor(str, Enum):
    HUMAN = "human"
    AGENT = "agent"


class LeaseError(Exception):
    pass


class LeaseConflictError(LeaseError):
    pass


class LeaseExpiredError(LeaseError):
    pass


@dataclass
class EditLease:
    session_id: str
    project_id: str
    actor: Actor
    mode: LeaseMode
    base_revision: int
    acquired_at: float = field(default_factory=time.time)
    last_heartbeat: float = field(default_factory=time.time)
    human_label: str = ""
    # GUI-01.5: stable identity of the *peer* (e.g. "claude-code-1").
    # Used by /session/ensure to detect "same Agent reconnecting" and
    # resume their prior lease instead of clobbering the human's.
    # Empty for legacy human callers that didn't pass one.
    actor_id: str = ""

    def touch(self) -> None:
        self.last_heartbeat = time.time()

    def is_alive(self, ttl_sec: float = 300.0) -> bool:
        return (time.time() - self.last_heartbeat) < ttl_sec


class LeaseStore:
    HEARTBEAT_TTL = 300.0

    def __init__(self):
        self._lock = threading.Lock()
        self._by_project: dict[str, EditLease] = {}
        # GUI-01.5: parked sessions for actors that asked for EDIT but
        # couldn't get it because someone else holds. Keyed by actor_id.
        # A later handoff to the matching actor_id promotes this sessionId
        # to active instead of minting a new one.
        self._parked: dict[str, str] = {}

    def get(self, project_id: str) -> Optional[EditLease]:
        with self._lock:
            lease = self._by_project.get(project_id)
            if lease is None:
                return None
            if not lease.is_alive(self.HEARTBEAT_TTL):
                self._by_project.pop(project_id, None)
                return None
            return lease

    def acquire(
        self,
        project_id: str,
        actor: Actor,
        mode: LeaseMode,
        base_revision: int,
        human_label: str = "",
        actor_id: str = "",
    ) -> EditLease:
        with self._lock:
            current = self._by_project.get(project_id)
            if current and current.is_alive(self.HEARTBEAT_TTL):
                raise LeaseConflictError(
                    f"project {project_id} currently held by {current.actor.value} "
                    f"session {current.session_id[:8]} in {current.mode.value} mode; "
                    f"release or handoff first"
                )
            lease = EditLease(
                session_id=uuid.uuid4().hex,
                project_id=project_id,
                actor=actor,
                mode=mode,
                base_revision=base_revision,
                human_label=human_label,
                actor_id=actor_id,
            )
            self._by_project[project_id] = lease
            return lease

    def release(self, project_id: str, session_id: str) -> bool:
        with self._lock:
            lease = self._by_project.get(project_id)
            if lease and lease.session_id == session_id:
                self._by_project.pop(project_id, None)
                # Clear any parked sessions for the released actor.
                if lease.actor_id:
                    self._parked.pop(lease.actor_id, None)
                return True
            return False

    def heartbeat(self, project_id: str, session_id: str) -> bool:
        with self._lock:
            lease = self._by_project.get(project_id)
            if lease and lease.session_id == session_id:
                lease.touch()
                return True
            return False

    def handoff(
        self,
        project_id: str,
        from_session_id: str,
        to_actor: Actor,
        to_mode: LeaseMode,
        to_label: str = "",
        to_actor_id: str = "",
    ) -> EditLease:
        with self._lock:
            current = self._by_project.get(project_id)
            if not current or current.session_id != from_session_id:
                raise LeaseError(f"session {from_session_id[:8]} does not hold {project_id}")
            if not current.is_alive(self.HEARTBEAT_TTL):
                self._by_project.pop(project_id, None)
                raise LeaseExpiredError("current lease expired; cannot handoff")
            # If the target actor has a parked sessionId, promote it.
            promoted = (
                self._parked.pop(to_actor_id, None) if to_actor_id else None
            )
            new_lease = EditLease(
                session_id=promoted or uuid.uuid4().hex,
                project_id=project_id,
                actor=to_actor,
                mode=to_mode,
                base_revision=current.base_revision,
                human_label=to_label,
                actor_id=to_actor_id,
            )
            self._by_project[project_id] = new_lease
            return new_lease

    # ----- GUI-01.5: actor_id + parked-session registry ----------------

    def by_actor(self, actor_id: str) -> Optional[EditLease]:
        """Live lease whose actor_id matches (None if dead or absent)."""
        if not actor_id:
            return None
        with self._lock:
            for lease in self._by_project.values():
                if lease.actor_id == actor_id and lease.is_alive(self.HEARTBEAT_TTL):
                    return lease
            return None

    def park_session(self, actor_id: str, session_id: str) -> None:
        """Remember that this actor wants edit, parked behind a holder."""
        if not actor_id or not session_id:
            return
        with self._lock:
            self._parked[actor_id] = session_id

    def consume_parked(self, actor_id: str) -> Optional[str]:
        """Take and clear the parked sessionId for an actor (used on resume)."""
        if not actor_id:
            return None
        with self._lock:
            return self._parked.pop(actor_id, None)

    def parked_for(self, actor_id: str) -> Optional[str]:
        """Read-only peek at the parked sessionId, if any."""
        if not actor_id:
            return None
        with self._lock:
            return self._parked.get(actor_id)

    def replace_session(
        self,
        project_id: str,
        old_session_id: str,
        new_session_id: str,
    ) -> Optional[EditLease]:
        """Atomically swap a live lease's sessionId.

        Used by /session/ensure on resume: the requester (e.g. a
        freshly-restarted Agent) has no knowledge of the prior sessionId
        but presents the same actor_id. The server rotates the sessionId
        so the old one is dead and the new one is the bearer token.
        Returns the updated lease, or None if no matching live lease.
        """
        if not new_session_id or old_session_id == new_session_id:
            return self.get(project_id) if old_session_id == new_session_id else None
        with self._lock:
            lease = self._by_project.get(project_id)
            if lease is None or lease.session_id != old_session_id:
                return None
            if not lease.is_alive(self.HEARTBEAT_TTL):
                self._by_project.pop(project_id, None)
                return None
            new_lease = EditLease(
                session_id=new_session_id,
                project_id=lease.project_id,
                actor=lease.actor, mode=lease.mode,
                base_revision=lease.base_revision,
                acquired_at=lease.acquired_at,
                human_label=lease.human_label,
                actor_id=lease.actor_id,
            )
            self._by_project[project_id] = new_lease
            return new_lease


_g_stores: dict[int, LeaseStore] = {}


def get_lease_store(core: ProjectCore) -> LeaseStore:
    sid = id(core)
    if sid not in _g_stores:
        _g_stores[sid] = LeaseStore()
    return _g_stores[sid]


def require_edit_right(core: ProjectCore, session_id: str) -> EditLease:
    lease = get_lease_store(core).get(core.project.project_id)
    if lease is None or lease.session_id != session_id:
        raise LeaseError(f"no active lease for session {session_id[:8]}")
    if lease.mode != LeaseMode.EDIT:
        raise LeaseError(
            f"session {session_id[:8]} has {lease.mode.value} mode, EDIT required"
        )
    if not lease.is_alive(LeaseStore.HEARTBEAT_TTL):
        raise LeaseExpiredError("lease expired; renew heartbeat")
    return lease


def require_capable(core: ProjectCore, session_id: str) -> EditLease:
    """Return the live lease for `session_id` regardless of its mode.

    Unlike `require_edit_right`, this does NOT require EDIT — it just
    confirms the session exists and is alive. Handlers use the returned
    lease's `mode` to decide between "commit the mutation" (EDIT),
    "return a preview" (PROPOSE), or "403 with a clear reason" (OBSERVE).
    """
    store = get_lease_store(core)
    lease = store.get(core.project.project_id)
    if lease is None or lease.session_id != session_id:
        raise LeaseError(f"no active lease for session {session_id[:8]}")
    if not lease.is_alive(LeaseStore.HEARTBEAT_TTL):
        raise LeaseExpiredError("lease expired; renew heartbeat")
    return lease


def get_current_revision(core: ProjectCore) -> int:
    return len(core.operations())


def check_revision_match(core: ProjectCore, base_revision: int) -> None:
    current = get_current_revision(core)
    if current != base_revision:
        raise LeaseConflictError(
            f"revision mismatch: client has r{base_revision}, server is r{current}; "
            f"refuse silent overwrite"
        )
