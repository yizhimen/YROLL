"""YROLL Snap Engine (P0-06): unified frame snap points.

v0.2 §15: "Snap 必须只有一个。禁止 ClipBlock Snap / App Snap / Core Snap
各自计算。统一 SnapEngine。"

GUI/CLI 调用：`engine.snap(frame, targets)` → 返回最近的 snap 点（如果
在 threshold 内），否则返回 None。

支持的候选 snap 类型：
- CLIP_START  — 视频/音频 clip 在 timeline 上的起始帧
- CLIP_END    — clip 在 timeline 上的结束帧
- PLAYHEAD    — 当前播放头位置
- SELECTION_EDGE — Selection 选区边界
- MARKER      — 用户/系统标记
- SUBTITLE_BOUNDARY — 字幕片段的起始/结束帧（来自 ASR）
- WORD_BOUNDARY — ASR 词级时间戳
- BEAT        — 音频节拍（v0.2 占位，未接外部 BPM 检测）

用法：
    engine = SnapEngine(threshold_frames=5)
    targets = engine.collect_targets(project, fps, playhead_frame=1832)
    snap = engine.snap(target_frame=1834, targets=targets)
    if snap:
        frame = snap.frame    # 实际吸附到的帧
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable

from yroll.core.manifest import Project, TrackKind
from yroll.core.timebase import FrameTime, Rational


class SnapKind(str, Enum):
    CLIP_START = "clip_start"
    CLIP_END = "clip_end"
    PLAYHEAD = "playhead"
    SELECTION_EDGE = "selection_edge"
    MARKER = "marker"
    SUBTITLE_BOUNDARY = "subtitle_boundary"
    WORD_BOUNDARY = "word_boundary"
    BEAT = "beat"


@dataclass(frozen=True)
class SnapTarget:
    """A single candidate point the snap engine may snap to."""
    frame: int
    kind: SnapKind
    label: str = ""        # human-readable context (e.g. "subtitle 'hello world'")
    clip_id: str = ""      # optional: which clip this target belongs to


@dataclass(frozen=True)
class SnapResult:
    """Result of a successful snap."""
    frame: int            # the frame we actually snapped to
    target: SnapTarget    # which target we snapped to
    delta_frames: int     # how far the input was from the snap point
    # (negative = target was to the left, positive = target was to the right)


class SnapEngine:
    """Frame-domain snap engine.

    Pure function of (target frame, list of candidates, threshold).
    No mutation, no project state. Multi-callable on the same engine.
    """

    def __init__(self, threshold_frames: int = 5):
        self.threshold = threshold_frames

    def snap(self, frame: int, targets: Iterable[SnapTarget]) -> SnapResult | None:
        """Snap `frame` to the nearest candidate within threshold.

        Returns None if no candidate is within threshold. If multiple
        candidates are equidistant, prefers the one with the lowest
        kind priority (CLIP_START < CLIP_END < PLAYHEAD < ... — i.e.
        structural anchors win over transient ones).
        """
        best: SnapResult | None = None
        best_kind_rank = 999
        for t in targets:
            d = t.frame - frame
            if abs(d) > self.threshold:
                continue
            kind_rank = list(SnapKind).index(t.kind)
            if (best is None
                    or abs(d) < abs(best.delta_frames)
                    or (abs(d) == abs(best.delta_frames)
                        and kind_rank < best_kind_rank)):
                best = SnapResult(frame=t.frame, target=t,
                                  delta_frames=d)
                best_kind_rank = kind_rank
        return best

    # ---------- Target collection helpers ----------

    @staticmethod
    def collect_clip_targets(project: Project, fps: Rational) -> list[SnapTarget]:
        """All clip start/end frames on the timeline (in frames)."""
        out: list[SnapTarget] = []
        for t in project.timeline.tracks:
            if t.kind in (TrackKind.TEXT,):
                continue  # subtitles handled separately if needed
            for cid in t.clip_ids:
                c = project.clips.get(cid)
                if c is None:
                    continue
                s = FrameTime.from_seconds(c.timeline_range.start, fps).frame
                e = FrameTime.from_seconds(c.timeline_range.end, fps).frame
                out.append(SnapTarget(s, SnapKind.CLIP_START,
                                       label=f"{t.kind.value}:{cid}", clip_id=cid))
                out.append(SnapTarget(e, SnapKind.CLIP_END,
                                       label=f"{t.kind.value}:{cid}", clip_id=cid))
        return out

    @staticmethod
    def collect_subtitle_targets(project: Project, fps: Rational) -> list[SnapTarget]:
        """Subtitle clip start/end on text tracks."""
        out: list[SnapTarget] = []
        for t in project.timeline.tracks:
            if t.kind != TrackKind.TEXT:
                continue
            for cid in t.clip_ids:
                c = project.clips.get(cid)
                if c is None:
                    continue
                text = (c.context.get("text") or "")[:30]
                s = FrameTime.from_seconds(c.timeline_range.start, fps).frame
                e = FrameTime.from_seconds(c.timeline_range.end, fps).frame
                out.append(SnapTarget(s, SnapKind.SUBTITLE_BOUNDARY,
                                       label=f"subtitle:{text}", clip_id=cid))
                out.append(SnapTarget(e, SnapKind.SUBTITLE_BOUNDARY,
                                       label=f"subtitle:{text}", clip_id=cid))
        return out

    @staticmethod
    def collect_word_targets(project: Project, fps: Rational,
                              transcripts: dict[str, list]) -> list[SnapTarget]:
        """ASR word boundaries (timeline frames via TimeMap per clip)."""
        from yroll.core.timemap import TimeMap
        out: list[SnapTarget] = []
        for t in project.timeline.tracks:
            if t.kind != TrackKind.VIDEO:
                continue
            for cid in t.clip_ids:
                c = project.clips.get(cid)
                if c is None:
                    continue
                words = transcripts.get(c.asset_id, [])
                if not words:
                    continue
                # Transcripts may be a flat list of segments with words inside
                # OR a flat list of words. Handle both shapes.
                # GUI-02.3: explicit source_fps; word boundaries are
                # source-frame-aligned so we need the asset's source fps.
                asset = next((a for a in project.assets
                              if a.asset_id == c.asset_id), None)
                src_fps = (asset.source_fps if asset and asset.source_fps is not None
                           else fps)
                tm = TimeMap.for_clip(c, fps, src_fps)
                for seg in words:
                    if "words" in seg:  # segment-level with embedded words
                        for w in seg["words"]:
                            ws_src = FrameTime.from_seconds(w["start"], fps).frame
                            we_src = FrameTime.from_seconds(w["end"], fps).frame
                            out.append(SnapTarget(
                                tm.timeline_from_source(ws_src),
                                SnapKind.WORD_BOUNDARY,
                                label=f"word:{w.get('word','')[:20]}",
                                clip_id=cid))
                            out.append(SnapTarget(
                                tm.timeline_from_source(we_src),
                                SnapKind.WORD_BOUNDARY,
                                label=f"word:{w.get('word','')[:20]}",
                                clip_id=cid))
                    elif "start" in seg and "end" in seg:
                        ws_src = FrameTime.from_seconds(seg["start"], fps).frame
                        we_src = FrameTime.from_seconds(seg["end"], fps).frame
                        out.append(SnapTarget(
                            tm.timeline_from_source(ws_src),
                            SnapKind.WORD_BOUNDARY,
                            label=f"word:{seg.get('text','')[:20]}",
                            clip_id=cid))
                        out.append(SnapTarget(
                            tm.timeline_from_source(we_src),
                            SnapKind.WORD_BOUNDARY,
                            label=f"word:{seg.get('text','')[:20]}",
                            clip_id=cid))
        return out

    @staticmethod
    def collect_playhead(playhead_seconds: float, fps: Rational) -> list[SnapTarget]:
        f = FrameTime.from_seconds(playhead_seconds, fps).frame
        return [SnapTarget(f, SnapKind.PLAYHEAD, label="playhead")]
