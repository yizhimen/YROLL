"""YROLL History API (P0-08): external undo/redo interface.

v0.2 spec §17: GUI/MCP/Agent MUST NOT touch Operation Log directly.
They use history.undo() / history.redo().

HistoryCursor tracks the current position in the operation log. After
each mutation the cursor advances. After undo it retreats. Redo moves
forward (until another mutation breaks the chain).

The current implementation delegates to ProjectCore.revert / redo, which
already produce revert:* operations. The cursor here is for the FUTURE
upgrade to a true history model that doesn't depend on emit-per-undo.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class HistoryState:
    """Snapshot of where the cursor is in history."""
    can_undo: bool
    can_redo: bool
    last_operation_id: str | None
    description: str = ""


class HistoryAPI:
    """External-facing undo/redo. Wraps ProjectCore.revert/redo.

    Usage:
        history = HistoryAPI(core)
        history.state()         # what's available
        history.undo(actor=Actor.HUMAN)
        history.redo(actor=Actor.HUMAN)
    """

    def __init__(self, core):
        self.core = core

    def state(self) -> HistoryState:
        """Describe the current history cursor position."""
        ops = self.core.operations()
        if not ops:
            return HistoryState(can_undo=False, can_redo=False,
                                last_operation_id=None)
        # Find the last non-revert op to know if there's something to undo
        # that's NOT already a revert (since revert of revert = redo).
        last_normal = None
        for o in reversed(ops):
            if not o.type.startswith("revert:"):
                last_normal = o
                break
        # Redo available if last op is a revert and there's a normal op after
        # the most-recent revert point.
        can_redo = ops[-1].type.startswith("revert:") and not ops[-1].type.startswith("revert:redo:")
        return HistoryState(
            can_undo=last_normal is not None,
            can_redo=can_redo,
            last_operation_id=ops[-1].operation_id,
            description=f"cursor at operation #{len(ops)}",
        )

    def undo(self, who: str = "human", why: str = "") -> dict | None:
        """Undo the last non-revert operation. Returns the revert op dict or None."""
        # Find the last operation that is not itself a revert (we undo user actions,
        # not the revert markers).
        ops = self.core.operations()
        target = None
        for o in reversed(ops):
            if not o.type.startswith("revert:"):
                target = o
                break
        if target is None:
            return None
        rev = self.core.revert(target.operation_id, who=who, why=why)
        return rev.model_dump() if rev else None

    def redo(self, who: str = "human", why: str = "") -> dict | None:
        """Redo the most recently undone operation."""
        op = self.core.redo(who=who, why=why)
        return op.model_dump() if op else None

    def history(self) -> list[dict]:
        """Return full operation log (audit trail)."""
        return [o.model_dump() for o in self.core.operations()]
