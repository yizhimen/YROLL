"""P0-04D: 一个用户意图 = 一个 Operation（Atomic Mutation）。

Composite mutations (replace_clip_voice, ...) used to emit N sub-operations
internally. Atomic refactor collapses them into ONE outer op.
"""
from pathlib import Path

import pytest

from yroll.core.commands import CommandLayer
from yroll.core.manifest import Actor
from yroll.core.models import Asset, AssetIdentity, AssetType
from yroll.core.project import ProjectCore


@pytest.fixture()
def core(tmp_path: Path) -> ProjectCore:
    core = ProjectCore.create(tmp_path, "atomic-test")
    core.project.assets.append(Asset(
        asset_id="a1", type=AssetType.VIDEO, path="v.mp4",
        identity=AssetIdentity(md5="x" * 32, size_bytes=1, duration_sec=10.0),
    ))
    return core


def test_replace_voice_emits_one_operation(core):
    """replace_clip_voice: one intent should produce ONE Operation, not N."""
    from unittest.mock import patch
    cmd = CommandLayer(core, who=Actor.AI)
    clip = cmd.add_clip("a1", 0.0, 5.0, timeline_start=0.0)

    # Stub TTS so test doesn't need real network/audio.
    fake_mp3 = core.path / "generated" / "tts-fake.mp3"
    fake_mp3.parent.mkdir(exist_ok=True)
    fake_mp3.write_bytes(b"\x00" * 1024)  # 1KB of zeros; md5 doesn't matter for op count

    with patch("yroll.tools.tts.tts_generate", return_value=fake_mp3):
        op = cmd.replace_clip_voice(clip.clip_id, "你好世界")

    # Only ONE voice_replace op; no extra add_clip / mute ops from voice_replace itself.
    types = [o.type for o in core.operations()]
    # Setup produced 1 add_clip; voice_replace should add exactly 1 voice_replace.
    assert types.count("voice_replace") == 1
    # The number of add_clip / mute ops must equal pre-existing count (i.e. voice_replace
    # did not produce sub-add_clip / sub-mute).
    assert types.count("add_clip") == 1
    assert types.count("mute") == 0


def test_replace_voice_atomic_undo(core):
    """Undo a voice_replace must restore the original clip state in one step."""
    from unittest.mock import patch
    cmd = CommandLayer(core, who=Actor.AI)
    clip = cmd.add_clip("a1", 0.0, 5.0, timeline_start=0.0)
    pre_clip_dump = clip.model_dump()

    fake_mp3 = core.path / "generated" / "tts-fake.mp3"
    fake_mp3.parent.mkdir(exist_ok=True)
    fake_mp3.write_bytes(b"\x00" * 1024)

    with patch("yroll.tools.tts.tts_generate", return_value=fake_mp3):
        op = cmd.replace_clip_voice(clip.clip_id, "你好世界")

    # After: clip is muted, new asset + clip added
    assert clip.context.get("muted") == "1"
    assert len(core.project.assets) == 2  # a1 + tts asset
    pre_ops_count = len(core.operations())

    # Single undo: restore clip muted state AND remove tts clip/asset
    core.revert(op.operation_id)

    # After revert: clip not muted
    assert "muted" not in clip.context or clip.context.get("muted") != "1"
    # TTS asset removed
    assert len(core.project.assets) == 1
    # History grew by exactly 1 (the revert itself)
    assert len(core.operations()) == pre_ops_count + 1


def test_ripple_delete_still_one_op(core):
    """ripple_delete already produces ONE op (was correct from start). Verify still so."""
    cmd = CommandLayer(core)
    c1 = cmd.add_clip("a1", 0.0, 5.0, timeline_start=0.0)
    c2 = cmd.add_clip("a1", 5.0, 10.0, timeline_start=5.0)
    pre_ops = len(core.operations())

    op = cmd.ripple_delete_clip(c1.clip_id)
    assert op.type == "ripple_delete"
    # Should add exactly 1 op (the composite ripple_delete)
    assert len(core.operations()) == pre_ops + 1
    # And c2 is shifted
    assert core.project.clips[c2.clip_id].timeline_range.start == 0.0
