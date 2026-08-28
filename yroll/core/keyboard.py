"""YROLL Keyboard Editing (P1 §34): canonical key bindings for the editor.

The GUI binds these to physical keys; AI agents can also invoke them
programmatically. Every binding is frame-native (input/output in frames).

Bindings:
  J              step playhead backward N frames (default 1)
  K              pause / toggle play
  L              step playhead forward N frames (default 1)
  Shift+J        step backward M frames (default 10)
  Shift+L        step forward M frames (default 10)
  Space          toggle play/pause
  I              set In-point at playhead
  O              set Out-point at playhead
  S              split clip at playhead (or selection edge)
  Delete         remove selected clip
  Shift+Delete   ripple-remove selected clip
  ← / →          nudge playhead by 1 frame
  Shift+← / →    nudge playhead by 10 frames

Inputs are always (selection, project_state, playhead_frame) — a pure
function so the GUI can preview the action before commit.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


# Default frame steps for J/K/L and arrow nudges.
DEFAULT_STEP_SMALL = 1
DEFAULT_STEP_LARGE = 10


@dataclass
class KeyboardAction:
    """A single keypress resolved to a mutation intent (no commit)."""
    key: str                  # e.g. "J", "Shift+L", "Delete"
    description: str
    mutation_op: str          # name of a CommandLayer / Selection method
    params: dict


# Table of key → KeyboardAction. Params reference playhead_frame /
# selection — the caller substitutes at invocation time.
KEY_TABLE: dict[str, KeyboardAction] = {
    "J": KeyboardAction(
        "J", "step playhead backward 1 frame",
        "_nudge_playhead", {"delta_frames": -DEFAULT_STEP_SMALL}),
    "Shift+J": KeyboardAction(
        "Shift+J", "step playhead backward 10 frames",
        "_nudge_playhead", {"delta_frames": -DEFAULT_STEP_LARGE}),
    "K": KeyboardAction(
        "K", "toggle play/pause",
        "_toggle_play", {}),
    "L": KeyboardAction(
        "L", "step playhead forward 1 frame",
        "_nudge_playhead", {"delta_frames": DEFAULT_STEP_SMALL}),
    "Shift+L": KeyboardAction(
        "Shift+L", "step playhead forward 10 frames",
        "_nudge_playhead", {"delta_frames": DEFAULT_STEP_LARGE}),
    "Space": KeyboardAction(
        "Space", "toggle play/pause",
        "_toggle_play", {}),
    "I": KeyboardAction(
        "I", "set in-point at playhead (selection.start = playhead)",
        "_set_in_out", {"which": "in"}),
    "O": KeyboardAction(
        "O", "set out-point at playhead",
        "_set_in_out", {"which": "out"}),
    "S": KeyboardAction(
        "S", "split clip at playhead",
        "split_clip_at_frame", {"at_frame": "{playhead}"}),
    "Delete": KeyboardAction(
        "Delete", "remove selected clip",
        "delete_selection", {"ripple": False}),
    "Shift+Delete": KeyboardAction(
        "Shift+Delete", "ripple-remove selected clip",
        "delete_selection", {"ripple": True}),
    "ArrowLeft": KeyboardAction(
        "ArrowLeft", "nudge playhead -1 frame",
        "_nudge_playhead", {"delta_frames": -DEFAULT_STEP_SMALL}),
    "ArrowRight": KeyboardAction(
        "ArrowRight", "nudge playhead +1 frame",
        "_nudge_playhead", {"delta_frames": DEFAULT_STEP_SMALL}),
    "Shift+ArrowLeft": KeyboardAction(
        "Shift+ArrowLeft", "nudge playhead -10 frames",
        "_nudge_playhead", {"delta_frames": -DEFAULT_STEP_LARGE}),
    "Shift+ArrowRight": KeyboardAction(
        "Shift+ArrowRight", "nudge playhead +10 frames",
        "_nudge_playhead", {"delta_frames": DEFAULT_STEP_LARGE}),
}


def lookup_key(combo: str) -> Optional[KeyboardAction]:
    """Resolve a key combo string (e.g. 'Shift+L') to its action."""
    return KEY_TABLE.get(combo)


def describe_keymap() -> list[dict]:
    """Return full keymap as a list of {key, description, mutation_op} dicts."""
    return [
        {"key": a.key, "description": a.description,
         "mutation_op": a.mutation_op, "params": a.params}
        for a in KEY_TABLE.values()
    ]
