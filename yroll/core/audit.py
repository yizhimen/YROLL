"""YROLL Agent Action Audit (v0.2 §28, §39 P2 Agent Evaluation):

After every Agent commit, produce a human-readable summary of what
the agent did in that batch. Used by the GUI's conflict/review dialog
("看看 Claude 刚才改了什么") and the Agent Evaluation system.

Typical output:
  {
    "actor": "agent",
    "from_revision": 105,
    "to_revision": 108,
    "operations": 3,
    "summary": "2 moved, 1 trimmed",
    "details": [
      {"op": "move_selection", "clip_count": 2, "delta_seconds": 0.4,
       "clips": ["c1", "c2"]},
      {"op": "trim_clip", "clip_id": "c3", "new_source_start": 2.0}
    ],
    "affected_frame_range": [1800, 2400],
    "previewed": True   # whether preview_mutation was shown first
  }
"""
from __future__ import annotations

from typing import Iterable

from yroll.core.manifest import Operation
from yroll.core.project import ProjectCore


def audit_batch(project: ProjectCore, ops: Iterable[Operation],
                previewed: bool = False,
                from_revision: int | None = None,
                to_revision: int | None = None) -> dict:
    """Summarize a batch of operations into an Agent action audit record."""
    ops = list(ops)
    if not ops:
        return {"actor": "agent", "operations": 0, "summary": "no-op",
                "details": [], "previewed": previewed}

    cur = from_revision if from_revision is not None else ops[0].operation_id
    nxt = to_revision if to_revision is not None else ops[-1].operation_id

    by_kind: dict[str, int] = {}
    details: list[dict] = []
    affected_min: int | None = None
    affected_max: int | None = None

    for op in ops:
        kind = op.type
        by_kind[kind] = by_kind.get(kind, 0) + 1
        # Track frame range from time_range if present
        if op.time_range is not None:
            s = op.time_range.start
            e = op.time_range.end
            if affected_min is None or s < affected_min:
                affected_min = s
            if affected_max is None or e > affected_max:
                affected_max = e
        # Per-op detail
        d = {"op": kind, "target": op.target}
        if op.before:
            d["before"] = op.before
        if op.after:
            d["after"] = op.after
        if op.why:
            d["why"] = op.why
        details.append(d)

    summary_parts = []
    for k in ("move_selection", "move", "trim", "trim_clip", "split",
              "delete_selection", "remove_clip", "ripple_delete",
              "slip", "roll", "slide", "add_clip", "add_subtitle",
              "generate_subtitles"):
        if k in by_kind:
            summary_parts.append(f"{by_kind[k]} {k}")

    return {
        "actor": "agent",
        "from_revision": cur,
        "to_revision": nxt,
        "operations": len(ops),
        "summary": ", ".join(summary_parts) if summary_parts
                    else f"{len(ops)} operations",
        "by_kind": by_kind,
        "details": details,
        "affected_frame_range": [affected_min, affected_max]
            if affected_min is not None and affected_max is not None
            else None,
        "previewed": previewed,
    }


def audit_since(project: ProjectCore, since_operation_id: str,
                previewed: bool = False) -> dict:
    """Audit all operations after `since_operation_id` up to the current end."""
    ops = project.operations()
    idx = next((i for i, o in enumerate(ops)
                if o.operation_id == since_operation_id), -1)
    batch = ops[idx + 1:]
    return audit_batch(project, batch, previewed=previewed,
                       from_revision=since_operation_id,
                       to_revision=ops[-1].operation_id if ops else since_operation_id)
