"""P0-1 跨轨 Ripple/Move + P0-6 Redo 验证测试。

P0-1：subtitle/voice 跟 video clip 一起 ripple_delete / move
P0-6：undo 之后能 redo 回到原状态

不依赖 GUI，直接走 Command Layer（Layer 1 Reality Test）。
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _fresh_project(test_root: Path):
    src = ROOT / "projects" / "jdz-chaishao"
    dst = test_root / "jdz-chaishao"
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)
    from yroll.core.project import ProjectCore
    return ProjectCore.open(dst)


def test_p01_cross_track_ripple():
    """P0-1a：ripple 一个主轨 clip，与之有 STRONG link 的字幕应自动前移。"""
    test_root = ROOT / "tests" / "_p01_tmp"
    test_root.mkdir(exist_ok=True)
    try:
        core = _fresh_project(test_root)
        from yroll.core.commands import CommandLayer
        from yroll.core.manifest import Actor
        from yroll.core.links import infer_relationships

        layer = CommandLayer(core, who=Actor.HUMAN)

        v_track = next(t for t in core.project.timeline.tracks
                       if t.kind.value == "video")
        text_track = next(t for t in core.project.timeline.tracks
                          if t.kind.value == "text")
        target = v_track.clip_ids[1]
        v_clip = core.project.clips[target]

        sub_id = text_track.clip_ids[-1]
        sub = core.project.clips[sub_id]

        core.project.relationships = []
        sub.timeline_range.start = v_clip.timeline_range.start
        sub.timeline_range.end = v_clip.timeline_range.end
        core.save_state()
        infer_relationships(core.project)

        strong_links = [r for r in core.project.relationships
                        if r.relation.value == "strong"
                        and r.source == sub_id]
        assert strong_links, "应该推断出字幕→视频 STRONG 关系"
        print(f"  ✓ STRONG 关系建立：{sub_id} → {strong_links[0].target}")

        sub_start_before = sub.timeline_range.start

        mid = (v_clip.source_range.start + v_clip.source_range.end) / 2
        left, right = layer.split_clip(target, at_source_time=mid, why="test")
        right_dur = right.timeline_range.end - right.timeline_range.start
        op = layer.ripple_delete_clip(right.clip_id, why="test ripple")
        print(f"  ✓ ripple_delete 完成：shifted={op.after.get('shifted_count', 0)}, "
              f"cross_shifted={op.after.get('cross_shifted_count', 0)}, "
              f"右半时长={right_dur:.2f}s")

        sub_after = core.project.clips[sub_id]
        expected = sub_start_before - right_dur
        actual = sub_after.timeline_range.start
        assert abs(actual - expected) < 1e-6, \
            f"字幕起点偏移不符（期望 {expected:.2f}, 实际 {actual:.2f}）"
        print(f"  ✅ PASS: 字幕起点前移 {right_dur:.2f}s "
              f"({sub_start_before:.2f} → {actual:.2f})")
    finally:
        shutil.rmtree(test_root, ignore_errors=True)


def test_p01_cross_track_move():
    """P0-1b：move 一个主轨 clip，与之有 STRONG link 的字幕应自动同步前移。"""
    test_root = ROOT / "tests" / "_p01_move_tmp"
    test_root.mkdir(exist_ok=True)
    try:
        core = _fresh_project(test_root)
        from yroll.core.commands import CommandLayer
        from yroll.core.manifest import Actor
        from yroll.core.links import infer_relationships

        layer = CommandLayer(core, who=Actor.HUMAN)

        # 清掉 jdz-chaishao 默认的 8 个视频 clip 和 2 个字幕 clip（避免重叠）
        # 只留第一个视频 clip 作为测试目标
        v_track = next(t for t in core.project.timeline.tracks
                       if t.kind.value == "video")
        text_track = next(t for t in core.project.timeline.tracks
                          if t.kind.value == "text")
        # 删掉除第一个外的所有 video clip
        keep_first = v_track.clip_ids[0]
        for cid in v_track.clip_ids[1:]:
            layer.remove_clip(cid, why="test setup cleanup")
        # 删掉所有 text clip
        for cid in list(text_track.clip_ids):
            layer.remove_clip(cid, why="test setup cleanup")

        target = keep_first
        v_clip = core.project.clips[target]
        # 加一个干净字幕对齐到 v_clip 时间
        layer.add_subtitle("test sub", v_clip.timeline_range.start,
                           v_clip.timeline_range.end, why="test setup")
        # W-B: removing all text clips auto-removed the (empty) text
        # track. add_subtitle auto-created a new track of kind
        # 'subtitle' (the asset type's primary kind per ASSET_TYPE_TO_
        # TRACK_KINDS). Find whatever text-or-subtitle track now exists.
        text_track = next(t for t in core.project.timeline.tracks
                          if t.kind.value in ("text", "subtitle"))
        sub_id = text_track.clip_ids[-1]
        sub = core.project.clips[sub_id]

        core.project.relationships = []
        sub.timeline_range.start = v_clip.timeline_range.start
        sub.timeline_range.end = v_clip.timeline_range.end
        core.save_state()
        infer_relationships(core.project)

        sub_start_before = sub.timeline_range.start
        v_start_before = v_clip.timeline_range.start
        delta = 0.5  # 用小位移，避免移到下一个 clip

        op = layer.move_clip(target, new_timeline_start=v_start_before + delta,
                             why="test move")
        print(f"  ✓ move_clip 完成：cross_shifted={op.after.get('cross_shifted_count', 0)}")

        sub_after = core.project.clips[sub_id]
        expected = sub_start_before + delta
        actual = sub_after.timeline_range.start
        assert abs(actual - expected) < 1e-6, \
            f"字幕起点未前移（期望 {expected:.2f}, 实际 {actual:.2f}）"
        print(f"  ✅ PASS: 字幕起点前移 {delta:.2f}s "
              f"({sub_start_before:.2f} → {actual:.2f})")
    finally:
        shutil.rmtree(test_root, ignore_errors=True)


def test_p06_undo_redo():
    """P0-6：Undo → Redo 闭环。"""
    test_root = ROOT / "tests" / "_p06_tmp"
    test_root.mkdir(exist_ok=True)
    try:
        core = _fresh_project(test_root)
        from yroll.core.commands import CommandLayer
        from yroll.core.manifest import Actor

        layer = CommandLayer(core, who=Actor.HUMAN)
        v_track = next(t for t in core.project.timeline.tracks
                       if t.kind.value == "video")
        cid = v_track.clip_ids[0]
        original_vol = core.project.clips[cid].volume

        op = layer.set_volume(cid, 1.7, why="test vol")
        mid_vol = core.project.clips[cid].volume
        assert abs(mid_vol - 1.7) < 1e-6

        core.revert(op.operation_id, why="test undo")
        undo_vol = core.project.clips[cid].volume
        assert abs(undo_vol - original_vol) < 1e-6, \
            f"Undo 不精准：{undo_vol}, 期望 {original_vol}"
        print(f"  ✓ Undo: vol {mid_vol} → {undo_vol} (回原始)")

        redo_op = core.redo(why="test redo")
        assert redo_op is not None, "core.redo() 返回 None"
        redo_vol = core.project.clips[cid].volume
        assert abs(redo_vol - 1.7) < 1e-6, \
            f"Redo 不精准：{redo_vol}, 期望 1.7"
        print(f"  ✅ PASS Redo: vol {undo_vol} → {redo_vol} (回到 mid)")
    finally:
        shutil.rmtree(test_root, ignore_errors=True)


def test_p06_full_loop():
    """P0-6 完整版：人→AI→人→Undo×3→Redo×3，最终状态 = 第 3 次人改。"""
    test_root = ROOT / "tests" / "_p06_loop_tmp"
    test_root.mkdir(exist_ok=True)
    try:
        core = _fresh_project(test_root)
        from yroll.core.commands import CommandLayer
        from yroll.core.manifest import Actor

        layer = CommandLayer(core, who=Actor.HUMAN)
        v_track = next(t for t in core.project.timeline.tracks
                       if t.kind.value == "video")
        cid = v_track.clip_ids[0]
        original_vol = core.project.clips[cid].volume
        original_speed = core.project.clips[cid].speed

        op1 = layer.set_volume(cid, 1.5, why="人 1")
        ai = CommandLayer(core, who=Actor.AI)
        op2 = ai.set_speed(cid, 1.3, why="AI 2")
        op3 = layer.set_volume(cid, 0.5, why="人 3")

        core.revert(op3.operation_id)
        core.revert(op2.operation_id)
        core.revert(op1.operation_id)

        u_vol = core.project.clips[cid].volume
        u_speed = core.project.clips[cid].speed
        assert abs(u_vol - original_vol) < 1e-6, f"Undo×3 vol: {u_vol}"
        assert abs(u_speed - original_speed) < 1e-6, f"Undo×3 speed: {u_speed}"
        print(f"  ✓ Undo×3: 回到原始 vol={u_vol}, speed={u_speed}")

        core.redo()
        core.redo()
        core.redo()

        f_vol = core.project.clips[cid].volume
        f_speed = core.project.clips[cid].speed
        assert abs(f_vol - 0.5) < 1e-6, f"Redo×3 vol: {f_vol}, 期望 0.5"
        assert abs(f_speed - 1.3) < 1e-6, f"Redo×3 speed: {f_speed}, 期望 1.3"
        print(f"  ✅ PASS Redo×3: vol={f_vol}, speed={f_speed} "
              f"（回到第 3 次修改后的状态）")
    finally:
        shutil.rmtree(test_root, ignore_errors=True)


if __name__ == "__main__":
    print("=" * 60)
    print("P0-1a: 跨轨 Ripple Delete 联动")
    print("=" * 60)
    try:
        test_p01_cross_track_ripple()
        r1 = "PASS"
    except AssertionError as e:
        print(f"  ❌ FAIL: {e}")
        r1 = "FAIL"
    print()
    print("=" * 60)
    print("P0-1b: 跨轨 Move 联动")
    print("=" * 60)
    try:
        test_p01_cross_track_move()
        r2 = "PASS"
    except AssertionError as e:
        print(f"  ❌ FAIL: {e}")
        r2 = "FAIL"
    print()
    print("=" * 60)
    print("P0-6a: Undo → Redo 单操作闭环")
    print("=" * 60)
    try:
        test_p06_undo_redo()
        r3 = "PASS"
    except AssertionError as e:
        print(f"  ❌ FAIL: {e}")
        r3 = "FAIL"
    print()
    print("=" * 60)
    print("P0-6b: 人→AI→人→Undo×3→Redo×3 完整循环")
    print("=" * 60)
    try:
        test_p06_full_loop()
        r4 = "PASS"
    except AssertionError as e:
        print(f"  ❌ FAIL: {e}")
        r4 = "FAIL"
    print()
    print("=" * 60)
    print(f"总结：P0-1a={r1}  P0-1b={r2}  P0-6a={r3}  P0-6b={r4}")
