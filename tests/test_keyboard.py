"""P1 Keyboard Editing tests — frame-native key bindings."""
from __future__ import annotations

import pytest

from yroll.core.keyboard import (
    DEFAULT_STEP_SMALL, DEFAULT_STEP_LARGE, KEY_TABLE,
    describe_keymap, lookup_key,
)


def test_J_steps_backward_one_frame():
    a = lookup_key("J")
    assert a is not None
    assert a.mutation_op == "_nudge_playhead"
    assert a.params["delta_frames"] == -DEFAULT_STEP_SMALL


def test_L_steps_forward_one_frame():
    a = lookup_key("L")
    assert a.mutation_op == "_nudge_playhead"
    assert a.params["delta_frames"] == DEFAULT_STEP_SMALL


def test_Shift_L_steps_forward_ten_frames():
    a = lookup_key("Shift+L")
    assert a.params["delta_frames"] == DEFAULT_STEP_LARGE


def test_K_toggles_play():
    assert lookup_key("K").mutation_op == "_toggle_play"
    assert lookup_key("Space").mutation_op == "_toggle_play"


def test_I_O_set_in_out():
    assert lookup_key("I").params["which"] == "in"
    assert lookup_key("O").params["which"] == "out"


def test_S_splits_at_playhead():
    a = lookup_key("S")
    assert a.mutation_op == "split_clip_at_frame"
    assert a.params["at_frame"] == "{playhead}"


def test_Delete_removes_selection():
    a = lookup_key("Delete")
    assert a.mutation_op == "delete_selection"
    assert a.params["ripple"] is False


def test_Shift_Delete_ripple_removes():
    a = lookup_key("Shift+Delete")
    assert a.params["ripple"] is True


def test_arrows_nudge_playhead():
    assert lookup_key("ArrowLeft").params["delta_frames"] == -1
    assert lookup_key("ArrowRight").params["delta_frames"] == 1
    assert lookup_key("Shift+ArrowLeft").params["delta_frames"] == -10
    assert lookup_key("Shift+ArrowRight").params["delta_frames"] == 10


# ---------------------------------------------------------------------------
# GUI-03R3-W-A.2: ArrowUp/ArrowDown jump to clip boundaries. The GUI
# keydown dispatch (App.tsx) reads `binding.params.direction` and calls
# jumpBoundary(dir). The binding used to be missing from the Core keymap
# (and was therefore a silent no-op on App's side); W-A.2 adds it so the
# keymap is the single source of truth for these keys.
# ---------------------------------------------------------------------------

def test_arrow_up_down_jump_to_boundary():
    up = lookup_key("ArrowUp")
    down = lookup_key("ArrowDown")
    assert up is not None, "ArrowUp binding missing from keymap"
    assert down is not None, "ArrowDown binding missing from keymap"
    assert up.mutation_op == "_nudge_playhead_boundary"
    assert down.mutation_op == "_nudge_playhead_boundary"
    assert up.params["direction"] == -1, "ArrowUp should mean 'previous boundary'"
    assert down.params["direction"] == 1, "ArrowDown should mean 'next boundary'"


# ---------------------------------------------------------------------------
# GUI-03R3-W-D: Home centers the playhead in the ContentViewport. The
# binding is GUI-local (no Core mutation, no /keyboard/execute endpoint);
# it lives in the keymap so the Help dialog can derive its labels from
# KEY_TABLE without inventing a second shortcut definition.
# ---------------------------------------------------------------------------

def test_home_centers_playhead():
    h = lookup_key("Home")
    assert h is not None, "Home binding missing from keymap"
    assert h.mutation_op == "_center_playhead"
    assert h.description == "center playhead in viewport"


def test_describe_keymap_includes_all_keys():
    km = describe_keymap()
    keys = {entry["key"] for entry in km}
    # Every key in §34 is present
    for k in ["J", "K", "L", "Shift+J", "Shift+L", "I", "O",
              "S", "Delete", "Shift+Delete", "ArrowLeft", "ArrowRight",
              "Shift+ArrowLeft", "Shift+ArrowRight", "Space",
              "ArrowUp", "ArrowDown",
              "Home"]:  # GUI-03R3-W-D: added (center playhead)
        assert k in keys, f"missing key in keymap: {k}"


def test_unknown_key_returns_none():
    assert lookup_key("Ctrl+Alt+F12") is None


def test_all_keys_are_frame_native():
    """All deltas must be integer frame counts, never floats."""
    for entry in describe_keymap():
        delta = entry["params"].get("delta_frames")
        if delta is not None:
            assert isinstance(delta, int), (
                f"{entry['key']} delta_frames must be int frames, got {delta!r}")
