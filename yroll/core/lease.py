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

    def touch(self) -> None:
        self.last_heartbeat = time.time()

    def is_alive(self, ttl_sec: float = 300.0) -> bool:
        return (time.time() - self.last_heartbeat) < ttl_sec


class LeaseStore:
    HEARTBEAT_TTL = 300.0

    def __init__(self):
        self._lock = threading.Lock()
        self._by_project: dict[str, EditLease] = {}

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
            )
            self._by_project[project_id] = lease
            return lease

    def release(self, project_id: str, session_id: str) -> bool:
        with self._lock:
            lease = self._by_project.get(project_id)
            if lease and lease.session_id == session_id:
                self._by_project.pop(project_id, None)
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
    ) -> EditLease:
        with self._lock:
            current = self._by_project.get(project_id)
            if not current or current.session_id != from_session_id:
                raise LeaseError(f"session {from_session_id[:8]} does not hold {project_id}")
            if not current.is_alive(self.HEARTBEAT_TTL):
                self._by_project.pop(project_id, None)
                raise LeaseExpiredError("current lease expired; cannot handoff")
            new_lease = EditLease(
                session_id=uuid.uuid4().hex,
                project_id=project_id,
                actor=to_actor,
                mode=to_mode,
                base_revision=current.base_revision,
                human_label=to_label,
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


def get_current_revision(core: ProjectCore) -> int:
    return len(core.operations())


def check_revision_match(core: ProjectCore, base_revision: int) -> None:
    current = get_current_revision(core)
    if current != base_revision:
        raise LeaseConflictError(
            f"revision mismatch: client has r{base_revision}, server is r{current}; "
            f"refuse silent overwrite"
        )
