"""YROLL Project Revision (P0-09) - Git-like revision tracking.

Every project has a monotonic revision number (= operation count).
Mutations must declare base_revision; if server's current != client's,
the mutation is rejected with 409 (conflict). Client must refresh, re-evaluate,
and re-apply.
"""
from __future__ import annotations

import threading

from yroll.core.project import ProjectCore


class RevisionConflictError(Exception):
    """Raised when client's baseRevision is stale."""
    pass


def get_current_revision(core: ProjectCore) -> int:
    """Number of operations logged in the project = revision number."""
    return len(core.operations())


# Global lock per ProjectCore instance (matches LeaseStore pattern)
_lock_state: dict[int, threading.Lock] = {}


def _lock_for(core: ProjectCore) -> threading.Lock:
    sid = id(core)
    if sid not in _lock_state:
        _lock_state[sid] = threading.Lock()
    return _lock_state[sid]


def check_project_revision(core: ProjectCore, base_revision: int | None) -> int:
    """Verify base_revision matches current, else raise RevisionConflictError.

    If base_revision is None, skip the check (backward compat for v0.1 clients
    that don't track revisions). Returns the current revision.
    """
    if base_revision is None:
        return get_current_revision(core)
    with _lock_for(core):
        current = get_current_revision(core)
        if current != base_revision:
            raise RevisionConflictError(
                f"revision mismatch: client has r{base_revision}, server is r{current}; "
                f"refuse silent overwrite (P0-12)"
            )
        return current
