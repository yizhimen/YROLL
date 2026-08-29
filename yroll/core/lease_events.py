"""GUI-01.5: In-memory ring of lease state transitions.

Why: GUI and MCP both poll the project server. When the human clicks
"交给 Claude" the MCP should learn about the handoff within one poll
interval, not after a 5s delay caused by stale state. /lease/events
exposes a small ring of {seq, kind, ...} records the clients can poll
on the same cadence as /ui/status.

This is process-local (the HTTP server is the sole owner; only one
process serves a project at a time). That's the same scope as
LeaseStore itself. Cross-process consistency comes from the same fact:
yroll serve <project> is the only writer.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class LeaseEvent:
    seq: int
    kind: str  # acquired | released | handed_off | expired |
               # ensure_observe | ensure_edit | ensure_resume |
               # ensure_parked | promote_parked
    at: float
    actor_id: str = ""
    session_id: str = ""
    from_actor: str = ""
    to_actor: str = ""
    from_mode: str = ""
    to_mode: str = ""
    project_id: str = ""
    detail: str = ""


class LeaseEventLog:
    """Ring buffer of lease state transitions.

    Bounded so a long-lived server doesn't grow without limit. 256 events
    covers many minutes of normal activity; older events are dropped
    silently (clients can always re-read /ui/status for current state).
    """

    CAPACITY = 256

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._events: list[LeaseEvent] = []
        self._next_seq = 0

    def record(
        self,
        kind: str,
        *,
        actor_id: str = "",
        session_id: str = "",
        from_actor: str = "",
        to_actor: str = "",
        from_mode: str = "",
        to_mode: str = "",
        project_id: str = "",
        detail: str = "",
    ) -> LeaseEvent:
        with self._lock:
            ev = LeaseEvent(
                seq=self._next_seq,
                kind=kind,
                at=time.time(),
                actor_id=actor_id,
                session_id=session_id,
                from_actor=from_actor,
                to_actor=to_actor,
                from_mode=from_mode,
                to_mode=to_mode,
                project_id=project_id,
                detail=detail,
            )
            self._next_seq += 1
            self._events.append(ev)
            if len(self._events) > self.CAPACITY:
                self._events = self._events[-self.CAPACITY:]
            return ev

    def since(self, seq: int) -> tuple[list[LeaseEvent], int]:
        """Return (events with seq >= given, current next_seq).

        Use `seq=-1` to get all events. Use `seq=last_next_seq` to poll
        for new ones (the contract documented for /lease/events).
        """
        with self._lock:
            tail = [e for e in self._events if e.seq >= seq]
            return tail, self._next_seq

    def reset(self) -> None:
        """Clear the ring (used when /project/open swaps ProjectCore)."""
        with self._lock:
            self._events.clear()
            self._next_seq = 0


# Module-level singleton, in the same style as _g_stores. One log per
# ProjectCore identity. Per the GUI-01.5 spec the only valid scope is
# "served by the running yroll serve", so a single log per process is
# correct: there is at most one serve per project per process.
_logs: dict[int, LeaseEventLog] = {}


def get_lease_event_log(core) -> LeaseEventLog:
    sid = id(core)
    if sid not in _logs:
        _logs[sid] = LeaseEventLog()
    return _logs[sid]
