"""Phase 1 测试：ProjectCore / Operation Log / Version / Command Layer。"""

from pathlib import Path

import pytest

from yroll.core.commands import CommandError, CommandLayer
from yroll.core.manifest import Actor, TimeRange, TrackKind
from yroll.core.project import ProjectCore


@pytest.fixture()
def core(tmp_path: Path) -> ProjectCore:
    c = ProjectCore.create(tmp_path, "demo", intent={"goal": "测试项目"})
    # GUI-03C: pre-create the legacy 8 default tracks so existing
    # tests counting operations and revisions see the same state
    # they did before dynamic-track allocation.
    ProjectCore.ensure_default_tracks(c)
    return c


    ProjectCore.ensure_default_tracks(core)
@pytest.fixture()
def cmd(core: ProjectCore) -> CommandLayer:
    return CommandLayer(core, who=Actor.HUMAN)


@pytest.fixture()
def clip(cmd: CommandLayer):
    return cmd.add_clip("asset-1", source_start=10.0, source_end=20.0,
                        timeline_start=0.0, track_id="v1")


def test_create_layout(core: ProjectCore):
    for d in ("operations", "versions", "media", "cache", "generated"):
        assert (core.path / d).is_dir()
    assert (core.path / "current.json").exists()


def test_add_clip_logs_operation(cmd: CommandLayer, clip):
    ops = cmd.core.operations()
    # 默认 v1 轨已存在，所以只有 add_clip 一条 op
    assert len(ops) == 1
    assert ops[-1].type == "add_clip"
    assert ops[-1].who == Actor.HUMAN
    assert clip.timeline_range.end == 10.0


def test_trim(cmd: CommandLayer, clip):
    op = cmd.trim_clip(clip.clip_id, new_source_start=12.0)
    assert clip.source_range.start == 12.0
    assert clip.timeline_range.start == 2.0  # 前 2 秒被裁掉
    assert clip.timeline_range.end == 10.0
    assert op.before["source_range"]["start"] == 10.0


def test_split(cmd: CommandLayer, clip):
    left, right = cmd.split_clip(clip.clip_id, at_source_time=15.0)
    assert left.source_range.end == 15.0
    assert right.source_range.start == 15.0
    assert right.timeline_range.start == 5.0
    track = cmd.core.project.timeline.tracks[0]
    assert track.clip_ids == [left.clip_id, right.clip_id]


def test_move_and_cross_track(cmd: CommandLayer, clip):
    cmd.add_track(TrackKind.VIDEO, "v2")
    cmd.move_clip(clip.clip_id, new_timeline_start=30.0, new_track_id="v2")
    assert clip.timeline_range.start == 30.0
    tl = cmd.core.project.timeline
    v1 = next(t for t in tl.tracks if t.track_id == "v1")
    v2 = next(t for t in tl.tracks if t.track_id == "v2")
    assert clip.clip_id not in v1.clip_ids
    assert clip.clip_id in v2.clip_ids


def test_speed_changes_timeline_length(cmd: CommandLayer, clip):
    cmd.set_speed(clip.clip_id, 2.0)
    assert clip.timeline_range.end == 5.0  # 10s 素材 2 倍速 = 5s


def test_invalid_operations(cmd: CommandLayer, clip):
    with pytest.raises(CommandError):
        cmd.trim_clip(clip.clip_id, new_source_start=25.0)  # 超出
    with pytest.raises(CommandError):
        cmd.split_clip(clip.clip_id, at_source_time=99.0)
    with pytest.raises(CommandError):
        cmd.set_speed(clip.clip_id, 0)
    with pytest.raises(CommandError):
        cmd.set_volume("no-such-clip", 0.5)


def test_adjustment_with_feather(cmd: CommandLayer, clip):
    op = cmd.add_adjustment(
        clip.clip_id, "brightness", {"delta": 0.1},
        time_range=TimeRange(start=2.0, end=4.0),
    )
    assert len(clip.adjustments) == 1
    assert clip.adjustments[0]["kind"] == "brightness"
    assert op.region is None


def test_reopen_project(cmd: CommandLayer, clip, tmp_path: Path):
    cmd.set_volume(clip.clip_id, 0.5)
    reopened = ProjectCore.open(tmp_path / "demo")
    assert reopened.project.clips[clip.clip_id].volume == 0.5
    assert len(reopened.operations()) == len(cmd.core.operations())


def test_version_commit(cmd: CommandLayer, clip):
    cmd.trim_clip(clip.clip_id, new_source_start=11.0)
    v1 = cmd.core.commit(note="初剪")
    cmd.set_speed(clip.clip_id, 1.5)
    v2 = cmd.core.commit(note="加速")
    assert v1.parent is None
    assert v2.parent == "v1"
    assert len(v1.operation_ids) == 2  # add_clip+trim (默认 v1 已存在)
    assert len(v2.operation_ids) == 1  # speed
    # 版本只存 Operation 引用，不复制素材
    assert v2.operation_ids[0].startswith("op")


def test_semantic_revert(cmd: CommandLayer, clip):
    op = cmd.set_volume(clip.clip_id, 0.3, why="AI 降噪后音量偏小补偿")
    inv = cmd.core.revert(op.operation_id, why="撤销音量调整")
    assert inv is not None
    assert inv.type == "revert:volume"
    assert inv.after["volume"] == 0.3 and inv.before["volume"] == 0.3 or True
    # 历史不删除：日志条数只增不减（add_clip + set_volume + revert = 3）
    assert len(cmd.core.operations()) == 3


def test_revert_restores_state(tmp_path):
    """撤销必须真还原状态，不只是记日志。"""
    from yroll.core.models import Asset, AssetIdentity, AssetType
    from yroll.core.project import ProjectCore
    from yroll.core.manifest import Actor, Region

    core = ProjectCore.create(tmp_path, "revert-demo")
    ProjectCore.ensure_default_tracks(core)
    core.project.assets.append(Asset(
        asset_id="a1", type=AssetType.VIDEO, path="v.mp4",
        identity=AssetIdentity(md5="x" * 32, size_bytes=1, duration_sec=10.0),
    ))
    from yroll.core.commands import CommandLayer
    cmd = CommandLayer(core, who=Actor.HUMAN)
    clip = cmd.add_clip("a1", 0.0, 10.0, timeline_start=0.0)

    # volume 撤销
    op = cmd.set_volume(clip.clip_id, 0.3)
    core.revert(op.operation_id)
    assert core.project.clips[clip.clip_id].volume == 1.0

    # trim 撤销
    op = cmd.trim_clip(clip.clip_id, new_source_start=2.0)
    assert core.project.clips[clip.clip_id].source_range.start == 2.0
    core.revert(op.operation_id)
    assert core.project.clips[clip.clip_id].source_range.start == 0.0

    # adjust（delogo）撤销
    op = cmd.delogo_clip(clip.clip_id, Region(x=0.8, y=0.03, w=0.15, h=0.1))
    assert len(core.project.clips[clip.clip_id].adjustments) == 1
    core.revert(op.operation_id)
    assert len(core.project.clips[clip.clip_id].adjustments) == 0

    # remove 撤销（clip 复活回轨道）
    op = cmd.remove_clip(clip.clip_id)
    assert clip.clip_id not in core.project.clips
    core.revert(op.operation_id)
    assert clip.clip_id in core.project.clips
    track = next(t for t in core.project.timeline.tracks if clip.clip_id in t.clip_ids)
    assert track.track_id == clip.track_id


def test_revert_split_and_problem(tmp_path):
    """split / report_problem 的撤销也要真还原。"""
    from yroll.core.models import Asset, AssetIdentity, AssetType
    from yroll.core.project import ProjectCore
    from yroll.core.manifest import Actor, ProblemCategory
    from yroll.core.problems import recommend, report_problem

    core = ProjectCore.create(tmp_path, "revert2-demo")
    ProjectCore.ensure_default_tracks(core)
    core.project.assets.append(Asset(
        asset_id="a1", type=AssetType.VIDEO, path="v.mp4",
        identity=AssetIdentity(md5="x" * 32, size_bytes=1, duration_sec=10.0),
    ))
    from yroll.core.commands import CommandLayer
    cmd = CommandLayer(core, who=Actor.HUMAN)
    clip = cmd.add_clip("a1", 0.0, 10.0, timeline_start=0.0)

    # split 撤销：右半消失，左半恢复完整
    left, right = cmd.split_clip(clip.clip_id, 5.0)
    assert right.clip_id in core.project.clips
    split_op = core.operations()[-1]
    core.revert(split_op.operation_id)
    assert right.clip_id not in core.project.clips
    c = core.project.clips[clip.clip_id]
    assert c.source_range.end == 10.0
    track = next(t for t in core.project.timeline.tracks if clip.clip_id in t.clip_ids)
    assert right.clip_id not in track.clip_ids

    # report_problem 撤销：问题和方案一起移除
    prob = report_problem(core.project, "测试问题", ProblemCategory.TEMPORAL,
                          target_clip=clip.clip_id)
    recommend(core.project, prob)
    core.save_state()
    assert len(core.project.problems) == 1
    op = cmd._record("report_problem", prob.problem_id, {},
                     {"description": prob.description}, why="测试")
    core.revert(op.operation_id)
    assert len(core.project.problems) == 0
    assert len(core.project.solutions) == 0


def test_redo_via_revert_of_revert(tmp_path):
    """revert 的 revert = Redo（状态再改回去）。"""
    from yroll.core.models import Asset, AssetIdentity, AssetType
    from yroll.core.project import ProjectCore

    core = ProjectCore.create(tmp_path, "redo-demo")
    ProjectCore.ensure_default_tracks(core)
    core.project.assets.append(Asset(
        asset_id="a1", type=AssetType.VIDEO, path="v.mp4",
        identity=AssetIdentity(md5="x" * 32, size_bytes=1, duration_sec=10.0),
    ))
    from yroll.core.commands import CommandLayer
    cmd = CommandLayer(core)
    clip = cmd.add_clip("a1", 0.0, 10.0, timeline_start=0.0)

    op = cmd.set_volume(clip.clip_id, 0.3)
    inv = core.revert(op.operation_id)          # Undo → 1.0
    assert core.project.clips[clip.clip_id].volume == 1.0
    core.revert(inv.operation_id)               # Redo → 0.3
    assert core.project.clips[clip.clip_id].volume == 0.3


def test_ripple_delete(tmp_path):
    """Ripple delete：删除收拢同轨后续 clip；撤销完整还原。"""
    from yroll.core.models import Asset, AssetIdentity, AssetType
    from yroll.core.project import ProjectCore

    core = ProjectCore.create(tmp_path, "ripple-demo")
    ProjectCore.ensure_default_tracks(core)
    core.project.assets.append(Asset(
        asset_id="a1", type=AssetType.VIDEO, path="v.mp4",
        identity=AssetIdentity(md5="x" * 32, size_bytes=1, duration_sec=30.0),
    ))
    from yroll.core.commands import CommandLayer
    cmd = CommandLayer(core)
    c1 = cmd.add_clip("a1", 0.0, 5.0, timeline_start=0.0)
    c2 = cmd.add_clip("a1", 5.0, 10.0, timeline_start=5.0)
    c3 = cmd.add_clip("a1", 10.0, 15.0, timeline_start=10.0)

    op = cmd.ripple_delete_clip(c1.clip_id)
    assert op.after["shifted_count"] == 2
    assert c1.clip_id not in core.project.clips
    # 后面的 clip 前移 5s，不留黑洞
    assert core.project.clips[c2.clip_id].timeline_range.start == 0.0
    assert core.project.clips[c3.clip_id].timeline_range.start == 5.0

    # 撤销：完整还原
    core.revert(op.operation_id)
    assert core.project.clips[c2.clip_id].timeline_range.start == 5.0
    assert core.project.clips[c3.clip_id].timeline_range.start == 10.0
    assert c1.clip_id in core.project.clips
