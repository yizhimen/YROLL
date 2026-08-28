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


def test_describe_keymap_includes_all_keys():
    km = describe_keymap()
    keys = {entry["key"] for entry in km}
    # Every key in §34 is present
    for k in ["J", "K", "L", "Shift+J", "Shift+L", "I", "O",
              "S", "Delete", "Shift+Delete", "ArrowLeft", "ArrowRight",
              "Shift+ArrowLeft", "Shift+ArrowRight", "Space"]:
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
