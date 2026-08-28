"""YROLL Lease Status / Conflict UI API (v0.2 §24-27):

Spec §24-27: GUI 顶部状态条显示"现在编辑权在谁手里" + "AI affected 范围"。
The Core computes this; the GUI consumes it as a single GET.

Status values:
- "human" — Human holds EDIT
- "agent" — Agent holds EDIT
- "observe" — only OBSERVE / READ_ONLY held
- "free"   — no lease, anyone can acquire (initial state)
- "conflict" — base revision has shifted since last known; user must refresh

Returns:
  {
    "actor": "human" | "agent" | "observe" | "free" | "conflict",
    "human_label": "User",
    "agent_label": "Claude",
    "session_id": "...",
    "alive": true/false,
    "base_revision": int,
    "client_last_known_revision": int (caller's view),
    "conflict": true/false,
    "ai_affected": [{"start_frame": int, "end_frame": int,
                     "reason": "last 3 mutations"}],
    "visual_cue": {
      "color": "green|yellow|gray|red",
      "text": "🟢 编辑权：我" | "🟡 编辑权：Claude" | ...
    }
  }
"""
from __future__ import annotations

from typing import Optional

from yroll.core.lease import (
    Actor as LeaseActor, LeaseMode, LeaseStore, get_lease_store,
    get_current_revision,
)
from yroll.core.project import ProjectCore


_VISUAL: dict[str, dict[str, str]] = {
    "human":   {"color": "green",  "text": "🟢 编辑权：我"},
    "agent":   {"color": "yellow", "text": "🟡 编辑权：Claude"},
    "observe": {"color": "gray",   "text": "⚪ 只读观察"},
    "free":    {"color": "white",  "text": "⭕ 编辑权：空闲"},
    "conflict":{"color": "red",    "text": "🔴 工程已变化，请刷新"},
}


def lease_status(core: ProjectCore,
                 client_known_revision: Optional[int] = None) -> dict:
    """Single-call status snapshot for the GUI top bar."""
    store = get_lease_store(core)
    ls = store.get(core.project.project_id)
    current_rev = get_current_revision(core)

    if ls is None or not ls.is_alive():
        actor = "free"
        human_label = ""
        agent_label = ""
        session_id = None
        alive = False
    else:
        alive = True
        session_id = ls.session_id
        human_label = ls.human_label or ""
        agent_label = ""
        if ls.mode == LeaseMode.OBSERVE:
            actor = "observe"
        elif ls.actor == LeaseActor.HUMAN:
            actor = "human"
        elif ls.actor == LeaseActor.AGENT:
            actor = "agent"
            agent_label = ls.human_label or "Agent"
        else:
            actor = "free"

    # Conflict: client says "I had r5" but server is now r7
    conflict = (client_known_revision is not None
                and client_known_revision != current_rev)

    if conflict:
        actor = "conflict"

    return {
        "actor": actor,
        "human_label": human_label,
        "agent_label": agent_label,
        "session_id": session_id,
        "alive": alive,
        "base_revision": current_rev,
        "client_last_known_revision": client_known_revision,
        "conflict": conflict,
        "ai_affected": [],  # TODO: derive from last N ops (placeholder)
        "visual_cue": _VISUAL.get(actor, _VISUAL["free"]),
    }
