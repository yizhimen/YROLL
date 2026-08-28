"""YROLL Mutation Proposal (v0.2 §3 P3 + §29 Agent Plan):

Agent proposes a mutation → Core evaluates impact (using existing
preview_mutation) → proposal gets a unique id → user/system approves
or rejects → only on approval is the mutation actually committed.

This is the core of "Preview Before Commit" (P3) and the agent
contract's "preview_mutation / commit_mutation" pair (already
exposed via YrollAgent). This module adds the proposal_id bookkeeping
so multi-step plans can be reviewed as a batch.

ProposalStore: in-memory, per-project. Mutations referenced by
proposal_id; expiry via TTL (default 5 minutes).
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Optional

from yroll.core.links import preview_mutation
from yroll.core.project import ProjectCore
from yroll.core.selection import Selection


@dataclass
class Proposal:
    proposal_id: str
    selection: Selection
    op: str
    params: dict
    preview: dict          # output of preview_mutation
    created_at: float
    expires_at: float
    approved_by: Optional[str] = None
    rejected_by: Optional[str] = None
    reason: str = ""


class ProposalStore:
    """Holds pending proposals for one project."""

    DEFAULT_TTL_SEC = 300

    def __init__(self, ttl_seconds: int = DEFAULT_TTL_SEC):
        self.ttl = ttl_seconds
        self._by_id: dict[str, Proposal] = {}

    def propose(self, project: ProjectCore, selection, op: str,
                params: Optional[dict] = None,
                reason: str = "") -> Proposal:
        sel = (selection if isinstance(selection, Selection)
               else Selection.from_clip_or_id(selection))
        now = time.time()
        preview = preview_mutation(project, sel, op, params or {})
        p = Proposal(
            proposal_id=f"pp{uuid.uuid4().hex[:8]}",
            selection=sel,
            op=op,
            params=params or {},
            preview=preview,
            created_at=now,
            expires_at=now + self.ttl,
            reason=reason,
        )
        self._by_id[p.proposal_id] = p
        self._evict_expired(now)
        return p

    def get(self, proposal_id: str) -> Optional[Proposal]:
        p = self._by_id.get(proposal_id)
        if p is None:
            return None
        if time.time() > p.expires_at:
            self._by_id.pop(proposal_id, None)
            return None
        return p

    def approve(self, proposal_id: str, approved_by: str = "human") -> bool:
        p = self.get(proposal_id)
        if p is None or p.rejected_by is not None:
            return False
        p.approved_by = approved_by
        return True

    def reject(self, proposal_id: str, rejected_by: str = "human") -> bool:
        p = self.get(proposal_id)
        if p is None or p.approved_by is not None:
            return False
        p.rejected_by = rejected_by
        return True

    def consume(self, proposal_id: str) -> Optional[Proposal]:
        """Remove and return a proposal (call after commit succeeds)."""
        return self._by_id.pop(proposal_id, None)

    def list_pending(self) -> list[Proposal]:
        now = time.time()
        return [p for p in self._by_id.values()
                if p.expires_at > now
                and p.approved_by is None and p.rejected_by is None]

    def _evict_expired(self, now: float) -> None:
        expired = [pid for pid, p in self._by_id.items()
                   if p.expires_at <= now]
        for pid in expired:
            self._by_id.pop(pid, None)


# Process-wide singleton (per-project; YrollAgent manages per-instance).
# The HTTP layer creates one per app startup.
_GLOBAL: dict[int, ProposalStore] = {}


def get_proposal_store(core: ProjectCore) -> ProposalStore:
    """Get-or-create the proposal store for a given core."""
    key = id(core)
    if key not in _GLOBAL:
        _GLOBAL[key] = ProposalStore()
    return _GLOBAL[key]
