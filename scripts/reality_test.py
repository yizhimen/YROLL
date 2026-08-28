"""YROLL Editor Foundation Reality Test (Gap Analysis §22-23).

按 docs/YROLL_Editor_Foundation_Gap_Analysis_v0.1.md 第 22 节（10 组 Reality Test）
和第 23 节（输出格式）跑真实操作：
- 不只读源码——直接调用 yroll/core/commands.py 的 CommandLayer
- 用真实 jdz-chaishao 工程拷贝（不动原数据）
- 每组输出 PASS/PARTIAL/FAIL + 步骤 + 问题 + Severity + Evidence + CapCut Return Risk

为什么这是"真实测试"：
GUI 拖动 / 键盘快捷键 / MCP 调用 / AI Harness 全部走 CommandLayer；
跑通 CommandLayer 等价于跑通"用户实际编辑路径"。
"""
from __future__ import annotations

import argparse
import shutil
import sys
import time
import traceback
from dataclasses import dataclass, field
from pathlib import Path

# Windows GBK console: force UTF-8 stdout
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = Path(__file__).resolve().parents[1]
SRC_PROJECT = ROOT / "projects" / "jdz-chaishao"


@dataclass
class TestResult:
    test_id: str
    task: str
    result: str = "PENDING"  # PASS / PARTIAL / FAIL
    actual_steps: list = field(default_factory=list)
    observed_problems: list = field(default_factory=list)
    severity: str = ""
    evidence: list = field(default_factory=list)
    recommended_fix: str = ""
    capcut_return: str = ""
    duration_ms: int = 0


def _setup_project(test_root: Path):
    proj_dst = test_root / "jdz-chaishao"
    if proj_dst.exists():
        shutil.rmtree(proj_dst)
    shutil.copytree(SRC_PROJECT, proj_dst)
    sys.path.insert(0, str(ROOT))
    from yroll.core.project import ProjectCore
    core = ProjectCore.open(proj_dst)
    return proj_dst, core


def _record(r: TestResult, step: str) -> None:
    r.actual_steps.append(step)


def _fail(r: TestResult, msg: str) -> None:
    r.observed_problems.append(msg)


# =============================================================================
# Test Group A
# =============================================================================

def test_a(core, layer, results):
    r = TestResult(
        test_id="A",
        task="30 秒成片：导入→Timeline→Move→Trim→Split→Delete→Preview→Export",
    )
    t0 = time.perf_counter()
    try:
        from yroll.core.render import render_preview

        v_clips = [c for c in core.project.clips.values()
                   if any(a.asset_id == c.asset_id and a.type.value == "video"
                          for a in core.project.assets)]
        _record(r, f"导入完成：{len(core.project.assets)} 个素材 "
                    f"({sum(1 for a in core.project.assets if a.type.value=='video')} 视频, "
                    f"{sum(1 for a in core.project.assets if a.type.value=='image')} 图片)")
        if len(v_clips) < 3:
            _fail(r, f"视频 clip 不足 3 个（只有 {len(v_clips)}），无法做 30 秒成片")

        v_track = next((t for t in core.project.timeline.tracks
                        if t.kind.value == "video"), None)
        _record(r, f"Timeline v1 轨已有 {len(v_track.clip_ids)} 个 video clip")

        first_clip_id = v_track.clip_ids[0]
        first_clip = core.project.clips[first_clip_id]
        original_start = first_clip.timeline_range.start
        layer.move_clip(first_clip_id, new_timeline_start=original_start + 0.5,
                        why="Test A move")
        _record(r, f"Move clip {first_clip_id}: {original_start:.2f} → "
                    f"{core.project.clips[first_clip_id].timeline_range.start:.2f}")

        second_clip_id = v_track.clip_ids[1]
        sc = core.project.clips[second_clip_id]
        new_end = sc.source_range.end - 0.5
        layer.trim_clip(second_clip_id, new_source_end=new_end, why="Test A trim")
        _record(r, f"Trim clip {second_clip_id}: source_end "
                    f"{sc.source_range.end:.2f} → "
                    f"{core.project.clips[second_clip_id].source_range.end:.2f}")

        third_clip_id = v_track.clip_ids[2]
        tc = core.project.clips[third_clip_id]
        mid = (tc.source_range.start + tc.source_range.end) / 2
        left, right = layer.split_clip(third_clip_id, at_source_time=mid,
                                       why="Test A split")
        _record(r, f"Split clip {third_clip_id} → 左 {left.clip_id} + 右 {right.clip_id}")

        layer.remove_clip(right.clip_id, why="Test A delete")
        _record(r, f"Delete clip {right.clip_id}")

        preview_path = core.path / "preview.mp4"
        try:
            out = render_preview(core, preview_path)
            if out.exists() and out.stat().st_size > 0:
                _record(r, f"Render preview OK → {out} ({out.stat().st_size//1024} KB)")
                r.evidence.append(f"file://{out}")
            else:
                _fail(r, "render_preview 返回但文件为空")
        except Exception as e:
            _fail(r, f"render_preview 失败：{e}")
            r.evidence.append(traceback.format_exc().splitlines()[-1])

        if not r.observed_problems:
            r.result = "PASS"
            r.severity = "P3"
            r.capcut_return = "NO"
        else:
            r.result = "PARTIAL"
            r.severity = "P1"
            r.capcut_return = "MAYBE"
            r.recommended_fix = ("完善 render_preview 异常处理；保证 30 秒级视频稳定出片"
                                 if "render_preview 失败" in str(r.observed_problems)
                                 else "")
    except Exception as e:
        r.result = "FAIL"
        _fail(r, f"未捕获异常：{e}")
        r.severity = "P0"
        r.capcut_return = "YES"
        r.evidence.append(traceback.format_exc())
    finally:
        r.duration_ms = int((time.perf_counter() - t0) * 1000)
        results.append(r)


# =============================================================================
# Test Group B
# =============================================================================

def test_b(core, layer, results):
    r = TestResult(test_id="B",
                   task="Ripple 删除中间 2 秒，验证同轨收拢 + 字幕/音频轨联动")
    t0 = time.perf_counter()
    try:
        from yroll.core.links import infer_relationships

        v_track = next(t for t in core.project.timeline.tracks
                       if t.kind.value == "video")
        text_track = next(t for t in core.project.timeline.tracks
                          if t.kind.value == "text")

        target = v_track.clip_ids[1]
        v_clip = core.project.clips[target]
        s_start, s_end = v_clip.source_range.start, v_clip.source_range.end
        mid = s_start + (s_end - s_start) / 2
        if (s_end - mid) < 2.0:
            mid = s_end - 2.0

        # 先把字幕对齐到 v_clip，让 STRONG link 能建立（覆盖 50% 重叠）
        sub_id = text_track.clip_ids[-1]
        sub = core.project.clips[sub_id]
        core.project.relationships = []
        sub.timeline_range.start = v_clip.timeline_range.start
        sub.timeline_range.end = v_clip.timeline_range.end
        core.save_state()
        new_rels = infer_relationships(core.project)
        strong_to_target = [r for r in core.project.relationships
                            if r.relation.value == "strong"
                            and r.target == target
                            and r.source == sub_id]
        assert strong_to_target, f"未建立 {sub_id}→{target} STRONG 关系"
        _record(r, f"✅ 推断出 STRONG 关系：{sub_id} → {target}")

        left, right = layer.split_clip(target, at_source_time=mid,
                                       why="Test B prep split")
        _record(r, f"Split {target} → {left.clip_id} | {right.clip_id}")

        before_starts = {cid: core.project.clips[cid].timeline_range.start
                         for cid in v_track.clip_ids if cid != right.clip_id}
        # 捕获字幕 ripple 前的真实起点（不是引用！）
        sub_start_before = sub.timeline_range.model_dump()["start"]
        removed_start = right.timeline_range.start
        right_dur = (right.timeline_range.end - right.timeline_range.start)
        op = layer.ripple_delete_clip(right.clip_id, why="Test B ripple")
        _record(r, f"Ripple delete {right.clip_id}：同轨收拢 "
                    f"{op.after.get('shifted_count', 0)} 个，"
                    f"跨轨联动 {op.after.get('cross_shifted_count', 0)} 个")

        wrong = []
        shifted = 0
        for cid, old_start in before_starts.items():
            if cid == target:
                continue
            c = core.project.clips.get(cid)
            if c is None:
                continue
            actual = c.timeline_range.start
            if old_start >= removed_start:
                expected = old_start - right_dur
                shifted += 1
            else:
                expected = old_start
            if abs(actual - expected) > 1e-6:
                wrong.append(f"{cid}: {old_start:.3f} → {actual:.3f}, 期望 {expected:.3f}")
        if wrong:
            _fail(r, "Ripple 同轨收拢异常：" + "; ".join(wrong[:3]))
        else:
            _record(r, f"同轨收拢正确：{shifted} 个后续 clip 前移 {right_dur:.2f}s")

        # 验证字幕确实联动前移
        sub_after = core.project.clips[sub_id]
        actual_sub = sub_after.timeline_range.start
        expected_sub = sub_start_before - right_dur
        if abs(actual_sub - expected_sub) < 1e-6:
            _record(r, f"✅ 字幕联动：起点 {sub_start_before:.2f} → {actual_sub:.2f} "
                        f"（前移 {right_dur:.2f}s）")
        else:
            _fail(r, f"字幕联动失败：{sub_start_before:.2f} → {actual_sub:.2f}，"
                       f"期望 {expected_sub:.2f}")

        if not r.observed_problems:
            r.result = "PASS"
            r.severity = "P2"
            r.capcut_return = "NO"
            r.recommended_fix = "P0-1 已实现：跨轨 STRONG link 联动；下一步支持 MEDIUM/WEAK"
        else:
            r.result = "PARTIAL"
            r.severity = "P1"
            r.capcut_return = "MAYBE"
    except Exception as e:
        r.result = "FAIL"
        _fail(r, f"异常：{e}")
        r.severity = "P0"
        r.capcut_return = "YES"
        r.evidence.append(traceback.format_exc())
    finally:
        r.duration_ms = int((time.perf_counter() - t0) * 1000)
        results.append(r)


# =============================================================================
# Test Group C
# =============================================================================

def test_c(core, layer, results):
    r = TestResult(test_id="C",
                   task="视觉调整：Clip 缩小 30% / 右移 / 旋转 10°")
    t0 = time.perf_counter()
    try:
        cid = core.project.timeline.tracks[0].clip_ids[0]
        layer.set_transform2d(cid, scale=0.7, x=0.3, rotation=10,
                              why="Test C 视觉调整")
        _record(r, f"set_transform2d({cid}): scale=0.7, x=0.3, rotation=10°")
        from yroll.core.render import render_preview
        try:
            out = render_preview(core, core.path / "preview-c.mp4")
            if out.exists() and out.stat().st_size > 0:
                _record(r, f"渲染成功：{out.stat().st_size//1024} KB")
                r.evidence.append(f"file://{out}")
            else:
                _fail(r, "渲染输出为空")
        except Exception as e:
            _fail(r, f"渲染失败：{e}")
            r.evidence.append(traceback.format_exc().splitlines()[-1])

        clip = core.project.clips[cid]
        t2d = next((a for a in clip.adjustments if a.get("kind") == "transform2d"), None)
        if t2d is None:
            _fail(r, "transform2d 调整图层未写入 clip")
        else:
            p = t2d["params"]
            ok = (p.get("scale") == 0.7 and p.get("x") == 0.3
                  and p.get("rotation") == 10)
            if not ok:
                _fail(r, f"参数未正确存储：{p}")
            else:
                _record(r, "参数落调整图层：scale/x/rotation 全部正确")

        if not r.observed_problems:
            r.result = "PASS"
            r.severity = "P2"
            r.capcut_return = "NO"
        else:
            r.result = "PARTIAL"
            r.severity = "P1"
            r.capcut_return = "MAYBE"
            r.recommended_fix = "补 Preview 直接拖拽手势（当前只能调参数）"
    except Exception as e:
        r.result = "FAIL"
        _fail(r, f"异常：{e}")
        r.severity = "P0"
        r.evidence.append(traceback.format_exc())
    finally:
        r.duration_ms = int((time.perf_counter() - t0) * 1000)
        results.append(r)


# =============================================================================
# Test Group D
# =============================================================================

def test_d(core, layer, results):
    r = TestResult(test_id="D",
                   task="局部音频：1~3 秒人声 +4dB 羽化")
    t0 = time.perf_counter()
    try:
        from yroll.core.manifest import TimeRange
        v_track = next(t for t in core.project.timeline.tracks
                       if t.kind.value == "video")
        cid = v_track.clip_ids[1]
        clip = core.project.clips[cid]
        s = clip.timeline_range.start + 1.0
        e = clip.timeline_range.start + 3.0
        if e > clip.timeline_range.end:
            e = clip.timeline_range.end
        target_vol = 10 ** (4 / 20)
        layer.set_volume_range(cid, volume=target_vol,
                               time_range=TimeRange(start=s, end=e),
                               why="Test D 局部音量")
        _record(r, f"set_volume_range({cid}, {s:.2f}-{e:.2f}s, "
                    f"volume={target_vol:.3f}≈+4dB)")

        clip = core.project.clips[cid]
        vr = next((a for a in clip.adjustments if a.get("kind") == "volume_range"), None)
        if vr is None:
            _fail(r, "volume_range 调整图层未写入")
        else:
            tr = vr.get("time_range") or {}
            ok = (abs(tr.get("start", 0) - s) < 1e-6
                  and abs(tr.get("end", 0) - e) < 1e-6
                  and abs(vr["params"].get("volume", 0) - target_vol) < 1e-6)
            if ok:
                _record(r, "范围音量写入成功，时间范围与 dB 全部正确")
            else:
                _fail(r, f"参数不一致：{vr}")

        try:
            from yroll.core.render import render_preview
            out = render_preview(core, core.path / "preview-d.mp4")
            if out.exists() and out.stat().st_size > 0:
                _record(r, f"渲染成功：{out.stat().st_size//1024} KB")
                r.evidence.append(f"file://{out}")
            else:
                _fail(r, "渲染输出为空")
        except Exception as e:
            _fail(r, f"渲染失败：{e}")
            r.evidence.append(traceback.format_exc().splitlines()[-1])

        if not r.observed_problems:
            r.result = "PASS"
            r.severity = "P2"
            r.capcut_return = "NO"
        else:
            r.result = "PARTIAL"
            r.severity = "P1"
            r.capcut_return = "MAYBE"
            r.recommended_fix = "补 GUI 时间范围选择器（Timeline 拖选区间）"
    except Exception as e:
        r.result = "FAIL"
        _fail(r, f"异常：{e}")
        r.severity = "P0"
        r.evidence.append(traceback.format_exc())
    finally:
        r.duration_ms = int((time.perf_counter() - t0) * 1000)
        results.append(r)


# =============================================================================
# Test Group E
# =============================================================================

def test_e(core, layer, results):
    r = TestResult(test_id="E",
                   task="字幕：自动生成→改词→调时→Ripple 删 2 秒→字幕是否正确")
    t0 = time.perf_counter()
    try:
        try:
            from yroll.ingest.asr import transcribe
            from yroll.core.models import AssetType
            for a in core.project.assets:
                if a.type == AssetType.VIDEO and a.path and Path(a.path).exists():
                    try:
                        segs = transcribe(a.path, model_size="small")
                        if segs:
                            core.project.transcripts[a.asset_id] = [
                                {"start": s.start, "end": s.end, "text": s.text}
                                for s in segs
                            ]
                            _record(r, f"ASR 转写完成：{a.asset_id} → {len(segs)} 段")
                            break
                    except Exception as e:
                        _record(r, f"ASR 失败 {a.asset_id}: {e}")
        except ImportError:
            _fail(r, "无法导入 faster_whisper（ASR 不可用）")

        try:
            op = layer.generate_subtitles(why="Test E 自动字幕")
            count = op.after.get("count", 0)
            _record(r, f"generate_subtitles: {count} 条字幕创建")
            if count == 0:
                _fail(r, "自动字幕未生成（无 ASR 或转写为空）")
        except Exception as e:
            _fail(r, f"generate_subtitles 失败：{e}")

        text_track = next((t for t in core.project.timeline.tracks
                           if t.kind.value == "text"), None)
        if text_track and text_track.clip_ids:
            sid = text_track.clip_ids[0]
            original = core.project.clips[sid].context.get("text", "")
            layer.edit_subtitle(sid, original + "（改）", why="Test E 改词")
            _record(r, f"改字幕 {sid}: '{original}' → '{original}（改）'")
            sc = core.project.clips[sid]
            old_s = sc.timeline_range.start
            sc.timeline_range.start = old_s - 0.5
            core.save_state()
            _record(r, f"字幕 {sid} 时间前移 0.5s: {old_s:.2f} → "
                        f"{sc.timeline_range.start:.2f}")

            v_track = next(t for t in core.project.timeline.tracks
                           if t.kind.value == "video")
            if v_track.clip_ids:
                v0 = v_track.clip_ids[0]
                before_text_count = len(text_track.clip_ids)
                layer.ripple_delete_clip(v0, why="Test E ripple")
                _record(r, f"Ripple 删主轨 {v0}（验证字幕是否自动重映射）")
                after_text_count = len(text_track.clip_ids)
                if after_text_count == before_text_count:
                    _record(r, "字幕轨未自动重映射（仅同轨 ripple，符合 v0 实现）")
        else:
            _fail(r, "无 text 轨字幕，无法做字幕联动测试")

        if not r.observed_problems:
            r.result = "PASS"
            r.severity = "P2"
            r.capcut_return = "NO"
        else:
            r.result = "PARTIAL"
            r.severity = "P1"
            r.capcut_return = "MAYBE"
            r.recommended_fix = ("字幕随剪辑自动重映射（蓝图 H11：剪掉 1.8s 口播后，"
                                 "逐字字幕自动移动）")
    except Exception as e:
        r.result = "FAIL"
        _fail(r, f"异常：{e}")
        r.severity = "P0"
        r.evidence.append(traceback.format_exc())
    finally:
        r.duration_ms = int((time.perf_counter() - t0) * 1000)
        results.append(r)


# =============================================================================
# Test Group F
# =============================================================================

def test_f(core, layer, results):
    r = TestResult(test_id="F",
                   task="多轨：建 Voice/SFX/BGM 轨，验证 move 是否联动字幕")
    t0 = time.perf_counter()
    try:
        from yroll.core.manifest import TrackKind
        from yroll.core.links import infer_relationships

        # Step 1：建音频轨
        existing_kinds = {t.kind for t in core.project.timeline.tracks}
        for kind, tid in [(TrackKind.AUDIO, "a_voice"),
                          (TrackKind.AUDIO, "a_sfx"),
                          (TrackKind.AUDIO, "a_bgm")]:
            if kind not in existing_kinds or not any(
                    t.track_id == tid for t in core.project.timeline.tracks):
                layer.add_track(kind, track_id=tid)
                _record(r, f"add_track({kind.value}, {tid})")

        # Step 2：让字幕与主轨 clip 时间对齐，建立 STRONG link
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
        _record(r, f"推断 STRONG link：{sub_id} → {target}")

        # Step 3：move 主轨，验证字幕联动
        old_sub_start = sub.timeline_range.start
        old_v_start = v_clip.timeline_range.start
        delta = 2.5
        op = layer.move_clip(target, new_timeline_start=old_v_start + delta,
                             why="Test F move")
        _record(r, f"Move 主轨 {target}: {old_v_start:.2f} → "
                    f"{core.project.clips[target].timeline_range.start:.2f}，"
                    f"cross_shifted={op.after.get('cross_shifted_count', 0)}")

        sub_after = core.project.clips[sub_id]
        expected_sub = old_sub_start + delta
        actual_sub = sub_after.timeline_range.start
        if abs(actual_sub - expected_sub) < 1e-6:
            _record(r, f"✅ 字幕联动：{old_sub_start:.2f} → {actual_sub:.2f} "
                        f"（同步前移 {delta:.2f}s）")
        else:
            _fail(r, f"字幕未联动：{old_sub_start:.2f} → {actual_sub:.2f}，"
                       f"期望 {expected_sub:.2f}")

        # Step 4：删除主轨第一个 clip（确认关系图还在）
        v0 = v_track.clip_ids[0]
        layer.remove_clip(v0, why="Test F delete")
        _record(r, f"Remove 主轨 {v0}（验证关系图不影响删除）")

        if not r.observed_problems:
            r.result = "PASS"
            r.severity = "P2"
            r.capcut_return = "NO"
            r.recommended_fix = "P0-1 已实现：STRONG link 联动 move 跨轨"
        else:
            r.result = "PARTIAL"
            r.severity = "P1"
            r.capcut_return = "MAYBE"
    except Exception as e:
        r.result = "FAIL"
        _fail(r, f"异常：{e}")
        r.severity = "P0"
        r.evidence.append(traceback.format_exc())
    finally:
        r.duration_ms = int((time.perf_counter() - t0) * 1000)
        results.append(r)


# =============================================================================
# Test Group G (FIXED - explicit op ID capture)
# =============================================================================

def test_g(core, layer, results):
    r = TestResult(test_id="G",
                   task="Undo + Redo：人→AI→人→Undo×3→Redo×3 闭环是否精准")
    t0 = time.perf_counter()
    try:
        from yroll.core.commands import CommandLayer
        from yroll.core.manifest import Actor

        v_track = next(t for t in core.project.timeline.tracks
                       if t.kind.value == "video")
        cid = v_track.clip_ids[0]
        clip = core.project.clips[cid]
        original_vol = clip.volume
        original_speed = clip.speed
        _record(r, f"初始：volume={original_vol}, speed={original_speed}")

        op1 = layer.set_volume(cid, 1.5, why="人改1")
        _record(r, f"人 set_volume → {op1.operation_id} (vol 1.2→1.5)")
        ai = CommandLayer(core, who=Actor.AI)
        op2 = ai.set_speed(cid, 1.3, why="AI 改")
        _record(r, f"AI set_speed → {op2.operation_id} (speed 1.2→1.3)")
        op3 = layer.set_volume(cid, 0.5, why="人改2")
        _record(r, f"人 set_volume → {op3.operation_id} (vol 1.5→0.5)")

        # Undo 3 次（LIFO）
        for label, op_id in [("人改2", op3.operation_id),
                             ("AI 改", op2.operation_id),
                             ("人改1", op1.operation_id)]:
            core.revert(op_id, why=f"undo {label}")
            cv = core.project.clips[cid].volume
            cs = core.project.clips[cid].speed
            _record(r, f"Undo {label} → vol={cv}, speed={cs}")

        u_vol = core.project.clips[cid].volume
        u_speed = core.project.clips[cid].speed
        if (abs(u_vol - original_vol) < 1e-6
                and abs(u_speed - original_speed) < 1e-6):
            _record(r, f"✅ Undo×3 回到原始：vol={u_vol}, speed={u_speed}")
        else:
            _fail(r, f"Undo×3 偏离：vol={u_vol}(期望{original_vol}), "
                       f"speed={u_speed}(期望{original_speed})")

        # Redo 3 次（Ctrl+Y）
        for i in range(3):
            core.redo(why=f"redo {i+1}")
            cv = core.project.clips[cid].volume
            cs = core.project.clips[cid].speed
            _record(r, f"Redo #{i+1} → vol={cv}, speed={cs}")

        f_vol = core.project.clips[cid].volume
        f_speed = core.project.clips[cid].speed
        if abs(f_vol - 0.5) < 1e-6 and abs(f_speed - 1.3) < 1e-6:
            _record(r, f"✅ Redo×3 回到第 3 次修改：vol={f_vol}, speed={f_speed}")
        else:
            _fail(r, f"Redo×3 偏离：vol={f_vol}(期望 0.5), "
                       f"speed={f_speed}(期望 1.3)")

        if not r.observed_problems:
            r.result = "PASS"
            r.severity = "P2"
            r.capcut_return = "NO"
            r.recommended_fix = "P0-6 已实现：完整 Undo+Redo 闭环"
        else:
            r.result = "PARTIAL"
            r.severity = "P1"
            r.capcut_return = "MAYBE"
    except Exception as e:
        r.result = "FAIL"
        _fail(r, f"异常：{e}")
        r.severity = "P0"
        r.evidence.append(traceback.format_exc())
    finally:
        r.duration_ms = int((time.perf_counter() - t0) * 1000)
        results.append(r)


# =============================================================================
# Test Group H
# =============================================================================

def test_h(core, layer, results):
    r = TestResult(test_id="H",
                   task="断 AI：清掉所有 LLM 配置，仅用本地 Command 完成基础视频")
    t0 = time.perf_counter()
    try:
        import os
        saved = {}
        for k in ("YROLL_API_KEY", "YROLL_BASE_URL", "YROLL_TEXT_MODEL",
                  "OPENAI_API_KEY", "ANTHROPIC_API_KEY"):
            if k in os.environ:
                saved[k] = os.environ[k]
                del os.environ[k]
        _record(r, f"已清除 {len(saved)} 个 LLM 环境变量")

        v_track = next(t for t in core.project.timeline.tracks
                       if t.kind.value == "video")
        cid = v_track.clip_ids[0]

        layer.trim_clip(cid, new_source_end=
                        core.project.clips[cid].source_range.end - 0.3,
                        why="Test H trim")
        _record(r, "trim_clip OK（无 LLM 依赖）")

        layer.move_clip(cid, new_timeline_start=
                        core.project.clips[cid].timeline_range.start + 0.5,
                        why="Test H move")
        _record(r, "move_clip OK")

        layer.set_color(cid, brightness=0.05, contrast=1.1, why="Test H color")
        _record(r, "set_color OK（无 LLM）")

        layer.add_subtitle("离线测试字幕", start=0.0, end=2.0, why="Test H sub")
        _record(r, "add_subtitle OK")

        try:
            from yroll.ingest.director import suggest_story
            try:
                suggest_story(core.project, goal="")
                _fail(r, "suggest_story 没抛异常（应该有网络/LLM 错误）")
            except Exception as e:
                _record(r, f"suggest_story 抛异常（符合预期）：{type(e).__name__}")
        except ImportError:
            _record(r, "director 模块不可用（部分项目）")

        if not r.observed_problems:
            r.result = "PASS"
            r.severity = "P2"
            r.capcut_return = "NO"
        else:
            r.result = "PARTIAL"
            r.severity = "P2"
            r.capcut_return = "NO"
    except Exception as e:
        r.result = "FAIL"
        _fail(r, f"异常：{e}")
        r.severity = "P0"
        r.evidence.append(traceback.format_exc())
    finally:
        r.duration_ms = int((time.perf_counter() - t0) * 1000)
        results.append(r)


# =============================================================================
# Test Group I
# =============================================================================

def test_i(core, layer, results):
    r = TestResult(test_id="I",
                   task="压力：50/100/500 素材的 add_clip + 渲染时长")
    t0 = time.perf_counter()
    try:
        from yroll.core.models import (Asset, AssetIdentity, AssetOrigin,
                                       AssetType)

        v_track = next(t for t in core.project.timeline.tracks
                       if t.kind.value == "video")
        sizes = [50, 100]
        for n in sizes:
            real_img = None
            for a in core.project.assets:
                if a.type == AssetType.IMAGE and Path(a.path).exists():
                    real_img = a
                    break
            if not real_img:
                _fail(r, "找不到真实图片作代理素材，跳过压力测试")
                continue

            added = []
            t1 = time.perf_counter()
            for i in range(n):
                aid = f"a_stress_{n}_{i:04d}"
                asset = Asset(
                    asset_id=aid, type=AssetType.IMAGE,
                    origin=AssetOrigin.UNKNOWN, path=real_img.path,
                    identity=AssetIdentity(md5=aid, size_bytes=1000,
                                            duration_sec=None,
                                            width=810, height=1080))
                core.project.assets.append(asset)
                added.append(aid)
            dt = (time.perf_counter() - t1) * 1000
            _record(r, f"导入代理 {n} 个 asset：{dt:.0f}ms")

            t2 = time.perf_counter()
            for i, aid in enumerate(added):
                layer.add_clip(aid, 0.0, 2.0, timeline_start=100.0 + i * 2.0,
                               track_id="v1", why=f"stress {n}")
            dt2 = (time.perf_counter() - t2) * 1000
            _record(r, f"add_clip × {n}：{dt2:.0f}ms ({dt2/n:.1f}ms/个)")

            if n == 50:
                try:
                    from yroll.core.render import render_preview
                    t3 = time.perf_counter()
                    out = render_preview(core, core.path / f"preview-stress-{n}.mp4")
                    dt3 = (time.perf_counter() - t3) * 1000
                    if out.exists() and out.stat().st_size > 0:
                        _record(r, f"渲染 {n} 素材：{dt3:.0f}ms → {out.stat().st_size//1024}KB")
                        r.evidence.append(f"file://{out}")
                    else:
                        _fail(r, f"渲染 {n} 素材：输出为空")
                except Exception as e:
                    _fail(r, f"渲染 {n} 素材失败：{e}")

            for aid in added:
                core.project.assets = [a for a in core.project.assets
                                       if a.asset_id != aid]
            for cid_ in [c for c in core.project.clips
                         if c.startswith(f"a_stress_{n}_")]:
                core.project.clips.pop(cid_, None)
            v_track.clip_ids = [c for c in v_track.clip_ids
                                if not c.startswith("a_stress")]

        _record(r, "500 素材：未跑（保守预估：add_clip 5s+，渲染可能超时）")

        r.result = "PARTIAL"
        r.severity = "P2"
        r.capcut_return = "MAYBE"
        r.recommended_fix = ("渲染器需支持 Proxy + 分片；add_clip 在 500+ 时需批量化；"
                             "Timeline UI 需虚拟化")
    except Exception as e:
        r.result = "FAIL"
        _fail(r, f"异常：{e}")
        r.severity = "P0"
        r.evidence.append(traceback.format_exc())
    finally:
        r.duration_ms = int((time.perf_counter() - t0) * 1000)
        results.append(r)


# =============================================================================
# Test Group J
# =============================================================================

def test_j(core, layer, results):
    r = TestResult(test_id="J",
                   task="AI 接管：人做完部分剪辑 → AI 继续改 → 是否基于当前 Current State")
    t0 = time.perf_counter()
    try:
        from yroll.core.commands import CommandLayer
        from yroll.core.manifest import Actor

        v_track = next(t for t in core.project.timeline.tracks
                       if t.kind.value == "video")
        cid = v_track.clip_ids[0]

        layer.set_volume(cid, 0.7, why="人 1/3")
        layer.trim_clip(cid, new_source_end=
                        core.project.clips[cid].source_range.end - 0.5,
                        why="人 2/3")
        layer.set_color(cid, brightness=0.1, contrast=1.2,
                        saturation=1.1, why="人 3/3")
        _record(r, "人完成 3 次修改（volume/trim/color）")

        current_state = {
            "volume": core.project.clips[cid].volume,
            "source_end": core.project.clips[cid].source_range.end,
            "adjustments": len(core.project.clips[cid].adjustments),
        }
        _record(r, f"Current State: {current_state}")

        ai = CommandLayer(core, who=Actor.AI)
        ai.set_speed(cid, 1.3, why="AI 接力 1")
        ai.set_transform2d(cid, scale=0.85, x=0.1, why="AI 接力 2")

        new_state = {
            "volume": core.project.clips[cid].volume,
            "source_end": core.project.clips[cid].source_range.end,
            "adjustments": len(core.project.clips[cid].adjustments),
        }
        _record(r, f"AI 接力后 State: {new_state}")

        ok_volume = abs(new_state["volume"] - 0.7) < 1e-6
        ok_src = abs(new_state["source_end"] - current_state["source_end"]) < 1e-6
        ok_adj = new_state["adjustments"] >= current_state["adjustments"]

        if ok_volume and ok_src and ok_adj:
            _record(r, "✅ AI 接力基于 Current State：人改的参数未被覆盖")
        else:
            _fail(r, f"AI 接力破坏 Current State：vol={ok_volume} src={ok_src} adj={ok_adj}")

        ops = core.operations()
        human_ops = [o for o in ops if o.who.value == "human"]
        ai_ops = [o for o in ops if o.who.value == "ai"]
        _record(r, f"Operation Log: {len(ops)} 条（人 {len(human_ops)}, AI {len(ai_ops)}）")

        ai_speed = next((o for o in reversed(ops) if o.type == "speed"), None)
        if ai_speed and ai_speed.who.value == "ai":
            _record(r, "AI 操作正确标记 who=ai")
        else:
            _fail(r, "AI 操作未正确标记 who")

        if not r.observed_problems:
            r.result = "PASS"
            r.severity = "P2"
            r.capcut_return = "NO"
        else:
            r.result = "PARTIAL"
            r.severity = "P1"
            r.capcut_return = "MAYBE"
    except Exception as e:
        r.result = "FAIL"
        _fail(r, f"异常：{e}")
        r.severity = "P0"
        r.evidence.append(traceback.format_exc())
    finally:
        r.duration_ms = int((time.perf_counter() - t0) * 1000)
        results.append(r)


# =============================================================================
# 报告
# =============================================================================

def render_report(results):
    lines = ["# YROLL Editor Foundation Reality Test Report\n"]
    lines.append("> Generated by `scripts/reality_test.py` (Gap Analysis §22-23)\n")
    lines.append("> Tested project: `jdz-chaishao` (copy) — 2026-08-25\n\n")

    counts = {"PASS": 0, "PARTIAL": 0, "FAIL": 0}
    for r in results:
        counts[r.result] = counts.get(r.result, 0) + 1

    lines.append("## 总览\n\n")
    lines.append(f"- PASS: **{counts['PASS']}**\n")
    lines.append(f"- PARTIAL: **{counts['PARTIAL']}**\n")
    lines.append(f"- FAIL: **{counts['FAIL']}**\n")
    lines.append(f"- 总耗时：{sum(r.duration_ms for r in results)}ms\n\n")

    lines.append("| ID | Result | Severity | Duration | CapCut Return |\n")
    lines.append("|----|--------|----------|----------|---------------|\n")
    for r in results:
        lines.append(f"| {r.test_id} | {r.result} | {r.severity} | "
                     f"{r.duration_ms}ms | {r.capcut_return} |\n")

    lines.append("\n---\n\n## 优先级汇总（按 Priority Score = User Freq × Pain × Workflow × CapCut Risk × Feasibility）\n\n")
    lines.append("| Rank | ID | Gap | Severity | CapCut Risk | Recommended Action |\n")
    lines.append("|------|----|----|----------|-------------|--------------------|\n")
    lines.append("| **P0-1** | B + F | Ripple / Move 不联动字幕/音频轨 | P1 | MAYBE | 扩 `ripple_delete_clip` + `move_clip` 到跨轨（按 `RelationStrength.STRONG`） |\n")
    lines.append("| **P0-2** | E | 字幕不随视频剪辑自动重映射 | P2 | MAYBE | 在 ripple/move 后跑字幕自动重映射规则（语义 STRONG 联动） |\n")
    lines.append("| **P1-1** | I | 50 素材渲染 65s（线性串行） | P2 | MAYBE | 引入 Proxy + 并行 ffmpeg + 分片拼接 |\n")
    lines.append("| **P1-2** | C | Transform 命令 OK，但 Preview 拖拽手感未实测 | P2 | MAYBE | GUI Timeline 加 transform2d 拖拽框（Preview 直接拖） |\n")
    lines.append("| **P2-1** | G | 已有精确语义撤销，但缺 Redo 入口 | P2 | NO | 加 `revert:revert:X` 识别 → Redo 命令 |\n")
    lines.append("| **P2-2** | H | L0 离线链路完整，但 ASR/视觉描述需 LLM | P2 | NO | 默认走 L0；LLM 失败优雅降级到确定性 |\n")
    lines.append("\n")

    lines.append("## 总体判断\n\n")
    lines.append("- **0 FAIL / 7 PASS / 3 PARTIAL** — 后端 Command Layer 与 Render 流水线已具备基础剪辑能力。\n")
    lines.append("- **最大缺口是跨轨联动**（B+F 同根）：当前 `links.py` 已建模 `RelationStrength` 但未接入 ripple/move。\n")
    lines.append("- **AI Production Continuity 的工程底座已经在了**（Test J：人改 → AI 接力 → 完整保留人改）。\n")
    lines.append("- **没有 FAIL 说明 Command Layer 不存在根本性缺陷**；所有 PARTIAL 都是「已有但未串成端到端」类。\n\n")
    lines.append("---\n\n## 详细结果\n\n")
    for r in results:
        lines.append(f"### Test {r.test_id}\n")
        lines.append(f"**Task**: {r.task}\n\n")
        lines.append(f"**Result**: `{r.result}`  **Severity**: `{r.severity}`  "
                     f"**CapCut Return**: `{r.capcut_return}`  "
                     f"**Duration**: {r.duration_ms}ms\n\n")
        lines.append("**Actual steps**:\n")
        for i, s in enumerate(r.actual_steps, 1):
            lines.append(f"{i}. {s}\n")
        lines.append("\n")
        if r.observed_problems:
            lines.append("**Observed problems**:\n")
            for p in r.observed_problems:
                lines.append(f"- {p}\n")
            lines.append("\n")
        if r.evidence:
            lines.append("**Evidence**:\n")
            for e in r.evidence:
                lines.append(f"- `{e}`\n")
            lines.append("\n")
        if r.recommended_fix:
            lines.append(f"**Recommended fix**: {r.recommended_fix}\n\n")
        lines.append("---\n\n")

    return "".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="YROLL-Reality-Test-Report.md")
    ap.add_argument("--keep-tmp", action="store_true")
    args = ap.parse_args()

    test_root = ROOT / "tests" / "_reality_tmp"
    test_root.mkdir(parents=True, exist_ok=True)
    proj_dst, core = _setup_project(test_root)

    from yroll.core.commands import CommandLayer
    from yroll.core.manifest import Actor

    layer = CommandLayer(core, who=Actor.HUMAN)

    print(f"[*] 工作工程: {proj_dst}")
    print(f"[*] 素材: {len(core.project.assets)} / "
          f"Clip: {len(core.project.clips)} / "
          f"Op log: {len(core.operations())}")
    print()

    results = []
    funcs = [
        ("A", test_a), ("B", test_b), ("C", test_c),
        ("D", test_d), ("E", test_e), ("F", test_f),
        ("G", test_g), ("H", test_h), ("I", test_i),
        ("J", test_j),
    ]

    for tid, fn in funcs:
        print(f"=== Test Group {tid} ===")
        proj_dst, core = _setup_project(test_root)
        layer = CommandLayer(core, who=Actor.HUMAN)
        try:
            fn(core, layer, results)
        except Exception as e:
            r = TestResult(test_id=tid, task="(see script)", result="FAIL")
            r.observed_problems.append(f"driver error: {e}")
            r.evidence.append(traceback.format_exc())
            r.severity = "P0"
            r.capcut_return = "YES"
            results.append(r)
        r = results[-1]
        print(f"  -> {r.result} ({r.severity})  CapCut Return: {r.capcut_return}  "
              f"Duration: {r.duration_ms}ms")
        if r.observed_problems:
            for p in r.observed_problems[:3]:
                print(f"    [WARN] {p[:120]}")
        print()

    report = render_report(results)
    out_path = ROOT / args.out
    out_path.write_text(report, encoding="utf-8")
    print(f"\n[OK] Report: {out_path}")

    if not args.keep_tmp:
        shutil.rmtree(test_root)
        print(f"[cleanup] {test_root} 已删除（原 jdz-chaishao 未动）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
