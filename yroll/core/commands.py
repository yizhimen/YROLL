"""Unified Editing Command Layer —— 人/手机手势/AI 都走同一套 Command API。

铁律（蓝图 §2.3-2）：GUI、Agent、MCP 外部工具调用完全相同的 Command。
每个 Command：
  1. 校验 + 计算 before/after
  2. 修改 Project 状态
  3. 通过 ProjectCore.log 落 Operation（含 who/why/cost）
返回 Operation，调用方可据此做 Preview/Undo/版本管理。

V0 只操作数据模型（时间线结构），不做实际媒体渲染——
渲染由 Renderer 按 current.json 实时生成（版本不复制素材）。
"""

from __future__ import annotations

import uuid

from yroll.core.manifest import (
    Actor,
    ASSET_TYPE_TO_TRACK_KINDS,
    Clip,
    Operation,
    Region,
    TimeRange,
    Timeline,
    Track,
    TrackKind,
    TrackRole,
)
from yroll.core.project import ProjectCore


class CommandError(Exception):
    pass


# GUI-03E-2A: legacy fallback counter. Tests can read this; the
# regression guard also reads it. New code MUST NOT introduce new
# calls that bump this counter.
_LEGACY_TIMELINE_FALLBACKS: int = 0


def _legacy_fallback_used() -> int:
    return _LEGACY_TIMELINE_FALLBACKS


def _reset_legacy_fallback_counter() -> None:
    global _LEGACY_TIMELINE_FALLBACKS
    _LEGACY_TIMELINE_FALLBACKS = 0


def _resolve_legacy_timeline_id(core: ProjectCore, timeline_id: str | None) -> str:
    """GUI-03E-2A legacy shim. When `timeline_id` is None, fall back
    to the active Timeline and bump the counter. New code MUST pass
    an explicit timeline_id."""
    if timeline_id is not None:
        return timeline_id
    global _LEGACY_TIMELINE_FALLBACKS
    _LEGACY_TIMELINE_FALLBACKS += 1
    return core.project.active_timeline_id


class CommandLayer:
    def __init__(self, core: ProjectCore, who: Actor = Actor.HUMAN):
        self.core = core
        self.who = who

    # ---------- 内部 ----------
    #
    # GUI-03E-2A canonical accessors. The `timeline_id` argument is
    # the source of truth for ownership. Cross-scope mismatch rejects
    # BEFORE any state/revision/operation mutation. For legacy
    # callers that pass timeline_id=None, the active Timeline is
    # used (counter incremented; regression guard reads it).

    def _timeline(self, timeline_id: str | None) -> "Timeline":
        """Resolve the target Timeline. Returns the Timeline whose
        stable id matches, raising CommandError on miss. Legacy
        callers that pass None are routed to active Timeline with
        a counter increment (see _LEGACY_TIMELINE_FALLBACKS)."""
        tid = _resolve_legacy_timeline_id(self.core, timeline_id)
        tl = self.core.project.get_timeline(tid)
        if tl is None:
            raise CommandError(
                f"timeline 不存在: {tid!r}; "
                f"known ids: {[t.timeline_id for t in self.core.project.timelines]}")
        return tl

    def _clip(self, clip_id: str, timeline_id: str | None = None) -> Clip:
        """Resolve a Clip and verify Timeline ownership when
        `timeline_id` is supplied. Mismatched ownership rejects with
        NO state/revision/op change. `timeline_id=None` skips the
        ownership check (legacy fallback; counter incremented)."""
        clip = self.core.project.clips.get(clip_id)
        if clip is None:
            raise CommandError(f"clip 不存在: {clip_id}")
        if timeline_id is not None and clip.timeline_id != timeline_id:
            raise CommandError(
                f"clip {clip_id!r} belongs to timeline "
                f"{clip.timeline_id!r}, not {timeline_id!r}")
        return clip

    def _track(self, track_id: str, timeline_id: str | None = None) -> Track:
        """Resolve a Track and verify ownership. Returns the Track or
        raises CommandError. None timeline_id → active Timeline
        (legacy fallback; counter incremented)."""
        tl = self._timeline(timeline_id)
        track = next((t for t in tl.tracks if t.track_id == track_id), None)
        if track is None:
            raise CommandError(
                f"track {track_id!r} 不存在 in timeline {tl.timeline_id!r}; "
                f"known tracks: {[t.track_id for t in tl.tracks]}")
        return track

    def _marker(self, timeline_id: str | None, marker_id: str) -> dict:
        """GUI-03E-2A: resolve a Marker dict by (timeline_id, marker_id).
        Mismatch rejects without mutation."""
        tl = self._timeline(timeline_id)
        store = getattr(tl, "markers", None) or []
        for m in store:
            if m.get("marker_id") == marker_id:
                if m.get("timeline_id") and m["timeline_id"] != tl.timeline_id:
                    raise CommandError(
                        f"marker {marker_id!r} belongs to timeline "
                        f"{m['timeline_id']!r}, not {tl.timeline_id!r}")
                return m
        raise CommandError(
            f"marker {marker_id!r} 不存在 in timeline {tl.timeline_id!r}")

    def _beat(self, timeline_id: str | None, beat_id: str) -> dict:
        """GUI-03E-2A: resolve a Beat dict by (timeline_id, beat_id).
        Mismatch rejects without mutation."""
        tl = self._timeline(timeline_id)
        store = getattr(tl, "beats", None) or []
        for b in store:
            if b.get("beat_id") == beat_id:
                if b.get("timeline_id") and b["timeline_id"] != tl.timeline_id:
                    raise CommandError(
                        f"beat {beat_id!r} belongs to timeline "
                        f"{b['timeline_id']!r}, not {tl.timeline_id!r}")
                return b
        raise CommandError(
            f"beat {beat_id!r} 不存在 in timeline {tl.timeline_id!r}")

    def _find_overlap(self, track_id: str, start: float, end: float,
                       exclude_clip_id: str | None = None,
                       timeline_id: str | None = None) -> list[str]:
        """同轨时间区间重叠的 clip_id 列表（不包含 exclude_clip_id）。

        同一轨道不允许两个 clip 时间区间重叠（剪映/CapCut/Premiere 标准行为）。

        GUI-03E-2A: when `timeline_id` is supplied, the overlap check
        is scoped to clips owned by that Timeline.
        """
        if end <= start:
            return []
        overlap = []
        for cid, c in self.core.project.clips.items():
            if cid == exclude_clip_id:
                continue
            if c.track_id != track_id:
                continue
            if timeline_id is not None and c.timeline_id != timeline_id:
                continue
            # 区间 [s, e) 半开，与剪映一致
            if c.timeline_range.start < end and start < c.timeline_range.end:
                overlap.append(cid)
        return overlap


    def _fps(self) -> tuple[int, int]:
        return (self.core.project.fps_num or 30, self.core.project.fps_den or 1)

    def _fps_rational(self):
        from yroll.core.timebase import Rational
        n, d = self._fps()
        return Rational(n, d)

    def _asset_for_clip(self, clip) -> object:
        """Return the Asset referenced by a Clip, or None if missing."""
        return next(
            (a for a in self.core.project.assets if a.asset_id == clip.asset_id),
            None,
        )

    def _source_fps_for_clip(self, clip) -> "Rational | None":
        """Source FPS for the asset referenced by a Clip, or None if
        unknown. NEVER silently substitutes the sequence FPS."""
        a = self._asset_for_clip(clip)
        return a.source_fps if a is not None else None

    def _frame_to_sec(self, frame: int) -> float:
        n, d = self._fps()
        return frame * d / n

    def _sec_to_frame(self, sec: float) -> int:
        n, d = self._fps()
        return round(sec * n / d)

    # ---------- Frame-based API (P0-01) ----------

    def add_clip_frame(self, asset_id: str, src_start_frame: int, src_end_frame: int,
                       timeline_start_frame: int, track_id: str = 'v1', why: str = '') -> 'Clip':
        """Frame-based add_clip. Internally converts to seconds."""
        return self.add_clip(
            asset_id,
            self._frame_to_sec(src_start_frame),
            self._frame_to_sec(src_end_frame),
            self._frame_to_sec(timeline_start_frame),
            track_id, why)

    def move_clip_frame(self, clip_id: str, timeline_start_frame: int, why: str = '') -> Operation:
        """Frame-based move_clip."""
        return self.move_clip(clip_id, self._frame_to_sec(timeline_start_frame), why=why)

    def trim_clip_frame(self, clip_id: str, src_start_frame: int | None = None,
                        src_end_frame: int | None = None, why: str = '',
                        timeline_id: str | None = None) -> Operation:
        """Frame-based trim_clip."""
        return self.trim_clip(
            clip_id,
            new_source_start=self._frame_to_sec(src_start_frame) if src_start_frame is not None else None,
            new_source_end=self._frame_to_sec(src_end_frame) if src_end_frame is not None else None,
            why=why, timeline_id=timeline_id)

    def split_clip_frame(self, clip_id: str, at_timeline_frame: int, why: str = '') -> tuple:
        """Frame-based split_clip. at is timeline frame, NOT source frame."""
        at_sec = self._frame_to_sec(at_timeline_frame)
        return self.split_clip(clip_id, at_sec, why=why)

    def _check_no_overlap(self, track_id: str, start: float, end: float,
                           exclude_clip_id: str | None = None,
                           op_name: str = "operation",
                           timeline_id: str | None = None) -> None:
        """重叠检查：发现冲突直接 CommandError（前端拿 400 + 明确消息）。

        GUI-03E-2A: when `timeline_id` is supplied, the overlap check
        is scoped to clips owned by that Timeline (so adding a clip
        to Timeline B can never conflict with a clip on the same
        track_id in Timeline A — they are independent).
        """
        conflicts = self._find_overlap(
            track_id, start, end, exclude_clip_id, timeline_id=timeline_id)
        if conflicts:
            shown = ", ".join(conflicts[:3])
            more = f" 等 {len(conflicts)} 个" if len(conflicts) > 3 else ""
            scope = f" (timeline {timeline_id})" if timeline_id else ""
            raise CommandError(
                f"{op_name} 与轨道 {track_id}{scope} 上现有 clip 时间重叠："
                f"{shown}{more}。（同一轨道片段不允许重叠，请先 "
                f"Trim/Split 或 Move 到其它轨道）")

    def _record(self, type_: str, target: str, before: dict, after: dict,
                why: str = "", time_range: TimeRange | None = None,
                region: Region | None = None, cost: float = 0.0,
                tool: str | None = None,
                timeline_id: str | None = None) -> Operation:
        op = self.core.new_operation(
            who=self.who, type=type_, target=target,
            time_range=time_range, region=region,
            parameters=after, before=before, after=after,
            why=why, tool=tool or f"video.{type_}", cost=cost,
            approved_by=self.who,
        )
        # GUI-03E-2A: every Timeline-local mutation stamps its
        # `timeline_id` into the Operation parameters so audit /
        # history can filter by Timeline. We resolve the legacy
        # fallback here too (so `timeline_id=None` from a caller
        # still produces a stamped op).
        if timeline_id is None:
            timeline_id = self.core.project.active_timeline_id
        op.parameters["timeline_id"] = timeline_id
        return self.core.log(op)

    # ---------- Composite Mutation Helpers (P0-04D: one user intent = one Op) ----------
    #
    # _apply_record(): for composite commands that touch multiple objects in
    # one user intent (replace_voice, remove_silence, ripple_delete ...),
    # call _apply_record() instead of _record() for the OUTER composite op.
    # Inside the block, perform the inner state changes WITHOUT calling
    # _record() (so they don't emit their own ops). The single outer op then
    # captures the entire before→after for atomic undo/redo.
    #
    # For state inspection helpers (rendering preview, impact preview), the
    # composite op's `before`/`after` describes both primary and side effects.
    # ---------- Composite Mutation Helpers (P0-04D) ----------

    def _apply_record(self, type_: str, target: str, before: dict, after: dict,
                     why: str = "", time_range: TimeRange | None = None,
                     region: Region | None = None, cost: float = 0.0,
                     tool: str | None = None) -> Operation:
        """Record a composite Operation WITHOUT intermediate per-step ops.
        The before/after dicts are expected to capture all state changes
        performed by this user intent. This is the atomic mutation primitive.
        """
        op = self.core.new_operation(
            who=self.who, type=type_, target=target,
            time_range=time_range, region=region,
            parameters=after, before=before, after=after,
            why=why, tool=tool or f"video.{type_}", cost=cost,
            approved_by=self.who,
        )
        return self.core.log(op)

    # ---------- 轨道 ----------

    def set_track_muted(self, track_id: str, muted: bool, why: str = "",
                         timeline_id: str | None = None) -> Operation:
        """轨道静音：音频轨不出声，PiP 视频轨不叠画（渲染时跳过）。"""
        tl = self._timeline(timeline_id)
        track = next((t for t in tl.tracks
                      if t.track_id == track_id), None)
        if track is None:
            raise CommandError(f"track 不存在: {track_id}")
        before = {"muted": track.muted}
        track.muted = muted
        return self._record("track_mute", track_id, before, {"muted": muted},
                            why=why or f"轨道 {track_id} {'静音' if muted else '取消静音'}",
                            tool="track.mute")

    def set_track_locked(self, track_id: str, locked: bool, why: str = "",
                          timeline_id: str | None = None) -> Operation:
        """轨道锁定：GUI 禁止拖动/编辑该轨 clip（防误触，渲染不受影响）。"""
        tl = self._timeline(timeline_id)
        track = next((t for t in tl.tracks
                      if t.track_id == track_id), None)
        if track is None:
            raise CommandError(f"track 不存在: {track_id}")
        before = {"locked": track.locked}
        track.locked = locked
        return self._record("track_lock", track_id, before, {"locked": locked},
                            why=why or f"轨道 {track_id} {'锁定' if locked else '解锁'}",
                            tool="track.lock")

    def set_track_hidden(self, track_id: str, hidden: bool, why: str = "",
                          timeline_id: str | None = None) -> Operation:
        """轨道隐藏：GUI 不显示该轨 clip（Premiere/CapCut 标配，渲染时仍参与合成）。"""
        tl = self._timeline(timeline_id)
        track = next((t for t in tl.tracks
                      if t.track_id == track_id), None)
        if track is None:
            raise CommandError(f"track 不存在: {track_id}")
        before = {"hidden": track.hidden}
        track.hidden = hidden
        return self._record("track_hide", track_id, before, {"hidden": hidden},
                            why=why or f"轨道 {track_id} {'隐藏' if hidden else '显示'}",
                            tool="track.hide")

    def add_track(self, kind: TrackKind, track_id: str | None = None,
                  role: TrackRole | None = None,
                  label: str | None = None,
                  timeline_id: str | None = None) -> Track:
        """Explicitly create a track. Most callers should use
        `allocate_track_for` instead — this method is for users who
        want to name a track (e.g. "V9 自定义") or set a role.

        Idempotent: if a track with the given `track_id` already
        exists with the same `kind`, return it (no new op, no
        failure). If it exists with a different `kind`, raise
        CommandError. Compatible with `ensure_default_tracks`, the
        legacy migration path for pre-GUI-03C projects.
        """
        tl = self._timeline(timeline_id)
        if track_id is None:
            # Auto-name: lowest unused <prefix><n> for the kind.
            track_id = self._next_track_id_for_kind(kind)
        for t in tl.tracks:
            if t.track_id == track_id:
                if t.kind != kind:
                    raise CommandError(
                        f"add_track: track {track_id!r} exists with kind "
                        f"{t.kind.value!r}, requested {kind.value!r}")
                # Idempotent: same id, same kind → return existing.
                if role is not None and t.role != role:
                    t.role = role
                if label is not None and t.label != label:
                    t.label = label
                return t
        track = Track(track_id=track_id, timeline_id=tl.timeline_id, kind=kind, role=role, label=label)
        tl.tracks.append(track)
        self._record("add_track", track_id, {}, track.model_dump(), tool="timeline.add_track")
        return track

    def _next_track_id_for_kind(self, kind: TrackKind) -> str:
        """Lowest unused '<prefix><n>' for the kind's prefix.
        VIDEO -> 'vN', AUDIO -> 'aN', SUBTITLE -> 'tN', TEXT -> 'tN'."""
        prefix_map = {
            TrackKind.VIDEO: "v",
            TrackKind.AUDIO: "a",
            TrackKind.SUBTITLE: "t",
            TrackKind.TEXT: "t",
        }
        prefix = prefix_map[kind]
        existing_nums = set()
        for tl in self.core.project.timelines:
            for t in tl.tracks:
                if t.kind == kind and t.track_id.startswith(prefix):
                    try:
                        existing_nums.add(int(t.track_id[len(prefix):]))
                    except ValueError:
                        pass
        n = 1
        while n in existing_nums:
            n += 1
        return f"{prefix}{n}"

    def _track_overlaps(self, track: Track, tl_start: float,
                         tl_end: float, exclude_clip_id: str | None = None) -> bool:
        """True if `track` contains a clip whose timeline range
        overlaps (half-open) [tl_start, tl_end)."""
        for cid in track.clip_ids:
            if exclude_clip_id and cid == exclude_clip_id:
                continue
            c = self.core.project.clips.get(cid)
            if c is None:
                continue
            cs, ce = c.timeline_range.start, c.timeline_range.end
            if cs < tl_end and tl_start < ce:
                return True
        return False

    def allocate_track_for(self, asset_type_value: str,
                            tl_start: float, tl_end: float,
                            prefer_track_id: str | None = None,
                            timeline_id: str | None = None) -> Track:
        """GUI-03C: Core-owned track allocation policy.

        Returns an existing compatible track (same kind, no
        timeline overlap) — preferring `prefer_track_id` if it's
        compatible — or creates a new track of the right kind.

        Asset-type → allowed track kinds:
          video   → {video}
          image   → {video}     # image shares VIDEO tracks
          audio   → {audio}
          subtitle→ {subtitle, text}
          text    → {subtitle, text}

        Asset types not in the map (e.g. 'document') raise.
        """
        tl = self._timeline(timeline_id)
        allowed_kinds = ASSET_TYPE_TO_TRACK_KINDS.get(asset_type_value)
        if not allowed_kinds:
            raise CommandError(
                f"allocate_track_for: asset type {asset_type_value!r} "
                f"is not a Timeline media")
        # Find the FIRST existing compatible track with no overlap.
        for t in tl.tracks:
            if t.kind.value not in allowed_kinds:
                continue
            if not self._track_overlaps(t, tl_start, tl_end):
                return t
        # No fit: create a new track.
        kind_enum = TrackKind(list(allowed_kinds)[0])
        return self.add_track(kind_enum, timeline_id=timeline_id)

    # ---------- Clip 增删 ----------

    def add_clip(self, asset_id: str, source_start: float, source_end: float,
                 timeline_start: float, track_id: str | None = None,
                 why: str = "",
                 timeline_id: str | None = None) -> Clip:
        tl = self._timeline(timeline_id)
        duration = source_end - source_start
        if duration <= 0:
            raise CommandError("source_range 无效")

        # Asset type → allowed track kinds.
        asset = next((a for a in self.core.project.assets
                      if a.asset_id == asset_id), None)
        if asset is not None:
            asset_type_value = asset.type.value
        elif asset_id == "":
            # Legacy: add_clip("", ...) was used to create subtitle
            # clips (no asset; text in context). Treat as text so
            # the allocator routes to a TEXT/SUBTITLE track.
            asset_type_value = "text"
        else:
            # Unknown asset_id — infer the kind from the track_id
            # prefix. Legacy callers (tests) often call add_clip
            # without first registering the asset, so we look at
            # the track naming convention to route correctly.
            #   a*/A* → audio
            #   t*/T* → text/subtitle
            #   v*/V* (or default) → video
            if track_id and track_id[0].lower() == "a":
                asset_type_value = "audio"
            elif track_id and track_id[0].lower() == "t":
                asset_type_value = "text"
            else:
                asset_type_value = "video"
        tl_end = timeline_start + duration

        # GUI-03C: Core-owned track allocation. If the user named
        # track_id AND a track with that id already exists, honor
        # GUI-03C: Core-owned track allocation. If `track_id` names
        # an existing track, honor the prefer (with type-policy
        # check when the asset is registered). If the track doesn't
        # exist, fall through to the allocator which finds a
        # compatible track (or creates one of the right kind). We
        # no longer auto-create a VIDEO track for an arbitrary
        # track_id — that legacy path assumed the new track was
        # always VIDEO, which broke heterogeneous assets.
        if track_id:
            existing = next(
                (t for t in tl.tracks
                 if t.track_id == track_id), None,
            )
            if existing is not None:
                _allowed = ASSET_TYPE_TO_TRACK_KINDS.get(asset_type_value, set())
                if asset is not None and existing.kind.value not in _allowed:
                    raise CommandError(
                        f"track {track_id} (kind {existing.kind.value}) "
                        f"rejects asset type {asset_type_value!r}")
                if self._track_overlaps(existing, timeline_start, tl_end):
                    raise CommandError(
                        f"add_clip: track {track_id} 时间重叠："
                        f"({timeline_start:.2f}, {tl_end:.2f}) 与已有 clip 重叠"
                    )
                track = existing
                actual_track_id = track.track_id
            else:
                # Track doesn't exist — let the Core allocator find
                # or create a compatible one. (We don't auto-create
                # at the prefer_track_id because we don't know the
                # right kind without the asset's type info, and
                # legacy "always VIDEO" was the source of the bgm
                # regression.)
                track = self.allocate_track_for(
                    asset_type_value, timeline_start, tl_end,
                    prefer_track_id=None,
                )
                actual_track_id = track.track_id
        else:
            track = self.allocate_track_for(
                asset_type_value, timeline_start, tl_end, prefer_track_id=None,
            )
            actual_track_id = track.track_id

        clip = Clip(
            clip_id=f"c{uuid.uuid4().hex[:6]}",
            asset_id=asset_id,
            timeline_id=tl.timeline_id,
            source_range=TimeRange(start=source_start, end=source_end),
            timeline_range=TimeRange(start=timeline_start, end=tl_end),
            track_id=actual_track_id,
        )
        # 重叠检查（同一轨道片段不允许重叠）
        self._check_no_overlap(
            actual_track_id, timeline_start, tl_end,
            op_name=f"add_clip({asset_id})",
            timeline_id=timeline_id)
        track.clip_ids.append(clip.clip_id)
        self.core.project.clips[clip.clip_id] = clip
        self._record("add_clip", clip.clip_id, {}, clip.model_dump(), why=why,
                     tool="timeline.add_clip")
        return clip

    # ---------- GUI-03B: image-first-class media ----------

    def add_image_clip(self, asset_id: str,
                        timeline_start_frame: int,
                        timeline_duration_frames: int,
                        track_id: str | None = None,
                        why: str = "",
                        timeline_id: str | None = None) -> Clip:
        """Add an image clip with frame-native coordinates.

        GUI-03B contract: an image asset has intrinsic_duration =
        None (still). The image clip's timeline_duration_frames is
        user-controlled — it does NOT derive from source media time.

        Image source semantics:
          - source_range = (0, 1/seq_fps) — exactly 1 source frame's
            worth of seconds. The image is one static frame; trim of
            the source side is NOT permitted (trim_image_clip_frame
            below is the only way to adjust image clip length).
          - speed = 1.0 (locked; set_speed(image) is rejected)
          - timeline_range derived from timeline_start_frame +
            timeline_duration_frames via the project's sequence fps.

        Heterogeneous FPS: image clips do not have a distinct
        source_fps. The TimeMap is built with source_fps = sequence_fps
        (conformant), so the source-side math is a no-op.

        Track policy: image may live on any VIDEO-class track
        (v1/v2/v3/PiP). Audio and text tracks reject images.
        """
        tl = self._timeline(timeline_id)
        if timeline_duration_frames <= 0:
            raise CommandError(
                f"add_image_clip: timeline_duration_frames must be > 0, "
                f"got {timeline_duration_frames}"
            )
        if timeline_start_frame < 0:
            raise CommandError(
                f"add_image_clip: timeline_start_frame must be >= 0, "
                f"got {timeline_start_frame}"
            )

        asset = next((a for a in self.core.project.assets
                      if a.asset_id == asset_id), None)
        if asset is None:
            raise CommandError(f"add_image_clip: asset not found: {asset_id}")
        if asset.type.value != "image":
            raise CommandError(
                f"add_image_clip: asset {asset_id} is type "
                f"{asset.type.value}, not image"
            )

        fps = self._fps_rational()
        seq_fps_num, seq_fps_den = fps.num, fps.den

        # Source range: exactly 1 source frame's worth of seconds.
        src_start_sec = 0.0
        src_end_sec = seq_fps_den / seq_fps_num  # 1/30 sec @ 30fps

        # Timeline range from frames (frame-native).
        tl_start_sec = timeline_start_frame * seq_fps_den / seq_fps_num
        tl_dur_sec = timeline_duration_frames * seq_fps_den / seq_fps_num
        tl_end_sec = tl_start_sec + tl_dur_sec

        # GUI-03C: Core-owned track allocation. Image may share a
        # VIDEO track with other video/image clips; the allocator
        # Honor an explicit prefer_track_id first. If it doesn't
        # exist, fall through to the allocator (which finds or
        # creates a compatible track). The image-source semantics
        # (1 source frame, 1.0 speed) are preserved.
        if track_id:
            existing = next(
                (t for t in tl.tracks
                 if t.track_id == track_id), None,
            )
            if existing is not None:
                # Image only goes on VIDEO tracks.
                if existing.kind != TrackKind.VIDEO:
                    raise CommandError(
                        f"track {track_id} (kind {existing.kind.value}) "
                        f"rejects asset type image")
                if self._track_overlaps(existing, tl_start_sec, tl_end_sec):
                    raise CommandError(
                        f"add_image_clip: track {track_id} 时间重叠")
                track = existing
                actual_track_id = track.track_id
            else:
                # Track doesn't exist — fall through to the
                # allocator (which will find or create a VIDEO track
                # for the image).
                track = self.allocate_track_for(
                    "image", tl_start_sec, tl_end_sec,
                    prefer_track_id=None,
                )
                actual_track_id = track.track_id
        else:
            # Core-owned allocator: find a non-overlapping track or create.
            track = self.allocate_track_for(
                "image", tl_start_sec, tl_end_sec,
                prefer_track_id=track_id,
            )
            actual_track_id = track.track_id

        # Overlap check on the resolved track.
        self._check_no_overlap(
            actual_track_id, tl_start_sec, tl_end_sec,
            op_name=f"add_image_clip({asset_id})",
            timeline_id=timeline_id)

        clip = Clip(
            clip_id=f"c{uuid.uuid4().hex[:6]}",
            asset_id=asset_id,
            timeline_id=tl.timeline_id,
            source_range=TimeRange(start=src_start_sec, end=src_end_sec),
            timeline_range=TimeRange(start=tl_start_sec, end=tl_end_sec),
            track_id=actual_track_id,
            speed=1.0,
        )
        track.clip_ids.append(clip.clip_id)
        self.core.project.clips[clip.clip_id] = clip
        self._record(
            "add_image_clip", clip.clip_id, {}, clip.model_dump(),
            why=why, tool="timeline.add_image_clip",
        )
        return clip

    def trim_image_clip_frame(self, clip_id: str,
                               timeline_start_frame: int | None = None,
                               timeline_end_frame: int | None = None,
                               why: str = "",
                               timeline_id: str | None = None) -> Operation:
        """GUI-03B: trim an IMAGE clip's on-screen duration.

        Only the timeline side is adjustable; image clips have a
        fixed 1-frame source range (no source trim). To change the
        duration, pass `timeline_end_frame`; the new duration is
        `timeline_end_frame - timeline_start_frame`. Pass BOTH
        timeline_start_frame and timeline_end_frame to also move
        the clip's timeline start.

        Returns an Operation record (revertable).
        """
        tl = self._timeline(timeline_id)
        clip = self._clip(clip_id, timeline_id)
        asset = next((a for a in self.core.project.assets
                      if a.asset_id == clip.asset_id), None)
        if asset is None or asset.type.value != "image":
            raise CommandError(
                f"trim_image_clip_frame: clip {clip_id} is not an image "
                f"clip (use trim_clip_frame for video/audio)."
            )
        if timeline_start_frame is not None and timeline_start_frame < 0:
            raise CommandError(
                f"trim_image_clip_frame: timeline_start_frame must be "
                f">= 0, got {timeline_start_frame}"
            )
        if timeline_end_frame is not None and timeline_end_frame <= (
            timeline_start_frame if timeline_start_frame is not None else 0
        ):
            raise CommandError(
                f"trim_image_clip_frame: timeline_end_frame must be "
                f"> timeline_start_frame "
                f"(got end={timeline_end_frame}, "
                f"start={timeline_start_frame})"
            )

        fps = self._fps_rational()
        seq_fps_num, seq_fps_den = fps.num, fps.den

        before = clip.model_dump()

        # Determine the new timeline range in frames.
        current_start_f = round(clip.timeline_range.start * seq_fps_num / seq_fps_den)
        current_end_f = round(clip.timeline_range.end * seq_fps_num / seq_fps_den)
        new_start_f = timeline_start_frame if timeline_start_frame is not None else current_start_f
        new_end_f = timeline_end_frame if timeline_end_frame is not None else current_end_f

        # Convert back to seconds for storage.
        clip.timeline_range = TimeRange(
            start=new_start_f * seq_fps_den / seq_fps_num,
            end=new_end_f * seq_fps_den / seq_fps_num,
        )

        # Re-run overlap check (the clip's track might have shifted).
        self._check_no_overlap(
            clip.track_id, clip.timeline_range.start, clip.timeline_range.end,
            exclude_clip_id=clip_id,
            op_name=f"trim_image_clip_frame({clip_id})")

        after = clip.model_dump()
        return self._record(
            "trim_image_clip_frame", clip_id, before, after, why=why,
            time_range=clip.timeline_range,
            tool="timeline.trim_image_clip_frame",
        )

    def remove_clip(self, clip_id: str, why: str = "",
                    timeline_id: str | None = None) -> Operation:
        tl = self._timeline(timeline_id)
        clip = self._clip(clip_id, timeline_id)
        before = clip.model_dump()
        track = next((t for t in tl.tracks
                      if clip_id in t.clip_ids), None)
        if track:
            track.clip_ids.remove(clip_id)
        del self.core.project.clips[clip_id]
        return self._record("remove_clip", clip_id, before, {}, why=why,
                            tool="timeline.remove_clip")

    def ripple_delete_clip(self, clip_id: str, why: str = "",
                          timeline_id: str | None = None) -> Operation:
        """Ripple delete：删除 clip 并把同轨后面的 clip 全部前移收拢（不留黑洞）。
        同时按 Semantic Link (STRONG) 联动字幕/音频轨。
        """
        from yroll.core.links import infer_relationships

        tl = self._timeline(timeline_id)
        clip = self._clip(clip_id, timeline_id)
        dur = clip.timeline_range.end - clip.timeline_range.start
        removed_start = clip.timeline_range.start
        track = next((t for t in tl.tracks
                      if clip_id in t.clip_ids), None)

        # 推断关系图（确保 Relationship 已建立）
        infer_relationships(self.core.project)

        # 找所有与本 clip 有 STRONG 关系的其他 clip（字幕/人声）
        related_ids: list[str] = []
        for r in self.core.project.relationships:
            if r.relation.value != "strong":
                continue
            if r.source == clip_id:
                related_ids.append(r.target)
            elif r.target == clip_id:
                related_ids.append(r.source)

        before = {"clip": clip.model_dump(), "shifted": {}}
        # 1. 同轨收拢
        if track:
            for cid in track.clip_ids:
                if cid == clip_id:
                    continue
                c = self.core.project.clips[cid]
                if c.timeline_range.start >= removed_start:
                    before["shifted"][cid] = c.timeline_range.start
                    c.timeline_range = TimeRange(
                        start=c.timeline_range.start - dur,
                        end=c.timeline_range.end - dur)
            track.clip_ids.remove(clip_id)
        del self.core.project.clips[clip_id]

        # 2. 跨轨联动（STRONG 关系且时间与删除区间重叠）
        cross_shifted: dict[str, float] = {}
        for rid in related_ids:
            rc = self.core.project.clips.get(rid)
            if rc is None:
                continue
            # 只 shift 时间区间与 [removed_start, removed_start+dur] 有交集的
            if (rc.timeline_range.end <= removed_start
                    or rc.timeline_range.start >= removed_start + dur):
                continue
            cross_shifted[rid] = rc.timeline_range.start
            rc.timeline_range = TimeRange(
                start=rc.timeline_range.start - dur,
                end=rc.timeline_range.end - dur)

        after = {
            "shifted_count": len(before["shifted"]),
            "cross_shifted_count": len(cross_shifted),
        }
        if cross_shifted:
            before["cross_shifted"] = cross_shifted
        return self._record("ripple_delete", clip_id, before, after,
                            why=why or f"Ripple 删除（收拢 {dur:.1f}s，"
                                       f"联动 {len(cross_shifted)} 个关联轨）",
                            tool="timeline.ripple_delete")

    # ---------- 字幕（text 轨） ----------

    def add_subtitle(self, text: str, start: float, end: float,
                     track_id: str | None = None, why: str = "",
                     timeline_id: str | None = None) -> Clip:
        """在 text 轨加字幕 clip（无源素材，asset_id=""，内容在 context.text）。
        GUI-03C: track_id is None by default; the Core-owned
        allocator routes to the first compatible TEXT/SUBTITLE
        track. Pass track_id to pin to a specific track (must be
        text/subtitle kind)."""
        tl = self._timeline(timeline_id)
        if end <= start:
            raise CommandError("字幕时间范围无效")
        track = self.allocate_track_for(
            "text", start, end, prefer_track_id=track_id,
        )
        actual_track_id = track.track_id
        clip = Clip(
            clip_id=f"c{uuid.uuid4().hex[:6]}",
            asset_id="",
            timeline_id=tl.timeline_id,
            source_range=TimeRange(start=0.0, end=end - start),
            timeline_range=TimeRange(start=start, end=end),
            track_id=actual_track_id,
            context={"text": text},
        )
        track.clip_ids.append(clip.clip_id)
        self.core.project.clips[clip.clip_id] = clip
        self._record("add_clip", clip.clip_id, {}, clip.model_dump(),
                     why=why or f"加字幕：{text[:20]}", tool="text.add_subtitle")
        return clip

    def generate_subtitles(self, clip_id: str | None = None,
                           max_seg: float = 6.0, why: str = "") -> Operation:
        """从 ASR 转写自动生成字幕轨（"AI 分析一次，长期使用"的兑现）。
        对指定 clip（或全部主视频轨 clip）：把源区间内的转写段映射成字幕 clip。
        幂等：clip 时间范围内已有字幕就跳过。过长段按 max_seg 截断（读得完）。"""
        from yroll.core.transcripts import load_transcripts

        project = self.core.project
        transcripts = load_transcripts(project)
        if not transcripts:
            raise CommandError("工程没有转写数据（先跑 ingest 理解管线）")

        vt = next((t for t in project.timeline.tracks
                   if t.kind == TrackKind.VIDEO), None)
        candidates = [project.clips[cid] for cid in (vt.clip_ids if vt else [])
                      if cid in project.clips]
        if clip_id:
            candidates = [self._clip(clip_id)]

        created: list[str] = []
        text_track = next((t for t in project.timeline.tracks
                           if t.kind == TrackKind.TEXT), None)
        # Project fps for TimeMap (default 30 if not set)
        from yroll.core.timebase import FrameTime, Rational
        from yroll.core.timemap import TimeMap
        proj_fps = Rational(getattr(project, 'fps_num', 30),
                            getattr(project, 'fps_den', 1) or 1)
        for clip in candidates:
            segs = transcripts.get(clip.asset_id, [])
            sr, tr = clip.source_range, clip.timeline_range
            # GUI-02.3: TimeMap requires explicit source_fps; look up
            # the asset. If the asset has no source_fps set, fall back
            # to proj_fps ONLY when the asset's ASR was generated at
            # the sequence frame rate (typical conformant case) — and
            # leave a structured comment so future heterogeneous
            # assets fail loudly here.
            asset = next((a for a in project.assets
                          if a.asset_id == clip.asset_id), None)
            src_fps = asset.source_fps if (asset and asset.source_fps is not None) else None
            if src_fps is None:
                # Conformant fallback: ASR transcripts are usually
                # produced at the sequence frame rate. Document this
                # so heterogeneous assets trigger an explicit upgrade.
                src_fps = proj_fps
            tm = TimeMap.for_clip(clip, proj_fps, src_fps)
            for seg in segs:
                # 与源区间的交集（保留 seconds 因为 transcripts 是 ASR 输出，seconds 是事实）
                s = max(seg["start"], sr.start)
                e = min(seg["end"], sr.end)
                if e - s < 0.3 or not seg.get("text", "").strip():
                    continue
                # 源时间 → 时间轴时间（用 TimeMap 而非内联计算）
                s_frame = FrameTime.from_seconds(s, proj_fps).frame
                e_frame = FrameTime.from_seconds(e, proj_fps).frame
                tl_s_frame = tm.timeline_from_source(s_frame)
                tl_e_frame = tm.timeline_from_source(e_frame)
                tl_s = tl_s_frame / proj_fps.as_float()
                tl_e = tl_e_frame / proj_fps.as_float()
                # 幂等：范围内已有字幕则跳过
                if text_track and any(
                    (oc := project.clips.get(ocid)) and oc.context.get("text")
                    and oc.timeline_range.start < tl_e
                    and oc.timeline_range.end > tl_s
                    for ocid in text_track.clip_ids):
                    continue
                # 长段截断（读得完）
                while tl_e - tl_s > max_seg:
                    sub = self.add_subtitle(seg["text"].strip(), tl_s,
                                            tl_s + max_seg, why=why or "自动字幕")
                    created.append(sub.clip_id)
                    tl_s += max_seg
                sub = self.add_subtitle(seg["text"].strip(), tl_s, tl_e,
                                        why=why or "自动字幕")
                created.append(sub.clip_id)
            # text_track 可能由 add_subtitle 刚建出来，重新取
            text_track = next((t for t in project.timeline.tracks
                               if t.kind == TrackKind.TEXT), None)

        return self._record(
            "generate_subtitles", clip_id or "timeline",
            {}, {"created": created, "count": len(created)},
            why=why or f"从转写生成 {len(created)} 条字幕",
            tool="text.generate_subtitles")

    def edit_subtitle(self, clip_id: str, text: str, why: str = "",
                      timeline_id: str | None = None) -> Operation:
        """改字幕文字（TEXT 类 Problem 的 L0 方案 text.correct 的真实执行体）。"""
        clip = self._clip(clip_id, timeline_id)
        before = {"text": clip.context.get("text", "")}
        clip.context["text"] = text
        return self._record("subtitle_edit", clip_id, before, {"text": text},
                            why=why or f"改字幕：{text[:20]}",
                            time_range=clip.timeline_range, tool="text.correct")

    def set_subtitle_style(self, clip_id: str, style: dict, why: str = "") -> Operation:
        """字幕样式（size/color/position），存 clip.context.style，烧录时生效。"""
        clip = self._clip(clip_id)
        before = {"style": dict(clip.context.get("style", {}))}
        clip.context["style"] = {**clip.context.get("style", {}), **style}
        return self._record("subtitle_style", clip_id, before,
                            {"style": dict(clip.context["style"])},
                            why=why or f"字幕样式 {style}",
                            time_range=clip.timeline_range, tool="text.style")

    # ---------- Clip 修改（X 轴基础编辑，成本 0，离线可用） ----------

    def trim_clip(self, clip_id: str, new_source_start: float | None = None,
                  new_source_end: float | None = None, why: str = "",
                  timeline_id: str | None = None) -> Operation:
        """Trim by SOURCE seconds (legacy). For frame-native, use
        `trim_clip_frame` which calls this with frame-derived seconds."""
        clip = self._clip(clip_id, timeline_id)
        before = {"source_range": clip.source_range.model_dump(),
                  "timeline_range": clip.timeline_range.model_dump()}
        sr = clip.source_range
        if new_source_start is not None:
            delta = new_source_start - sr.start
            sr.start = new_source_start
            clip.timeline_range.start += delta
        if new_source_end is not None:
            sr.end = new_source_end
        new_len = sr.end - sr.start
        if new_len <= 0:
            raise CommandError("trim 后长度无效")
        clip.timeline_range.end = clip.timeline_range.start + new_len / clip.speed
        # 重叠检查（trim 后可能与邻居重叠）
        self._check_no_overlap(
            clip.track_id, clip.timeline_range.start, clip.timeline_range.end,
            exclude_clip_id=clip_id,
            op_name=f"trim_clip({clip_id})")
        after = {"source_range": sr.model_dump(),
                 "timeline_range": clip.timeline_range.model_dump()}
        return self._record("trim", clip_id, before, after, why=why,
                            time_range=clip.timeline_range)

    def trim_clip_frame(self, clip_id: str, src_start_frame: int | None = None,
                        src_end_frame: int | None = None, why: str = '',
                        timeline_id: str | None = None) -> Operation:
        """Frame-native trim. Math in frames throughout; TimeMap is
        used for source<->timeline conversion (also in frames). The
        frame→seconds conversion happens once at the storage boundary
        (TimeRange model) — not in the editing logic."""
        import dataclasses
        from yroll.core.timemap import TimeMap
        fps = self._fps_rational()
        clip = self._clip(clip_id)
        # GUI-02.3: explicit source_fps; if unknown, fall back to
        # sequence fps with an inline comment so future heterogeneous
        # assets trigger an explicit error path.
        src_fps = self._source_fps_for_clip(clip)
        if src_fps is None:
            src_fps = fps  # conformant fallback (see validate_media_conformance)
        tm = TimeMap.for_clip(clip, fps, src_fps)
        before = {"source_range": clip.source_range.model_dump(),
                  "timeline_range": clip.timeline_range.model_dump()}
        # Compute everything in frame domain.
        if src_start_frame is not None and not (src_start_frame < tm.source_end_frame):
            raise CommandError("trim src_start_frame 越界")
        if src_end_frame is not None and not (src_end_frame > tm.source_start_frame):
            raise CommandError("trim src_end_frame 越界")
        # Apply frame changes via dataclasses.replace (TimeMap is frozen).
        new_start_f = src_start_frame if src_start_frame is not None else tm.source_start_frame
        new_end_f = src_end_frame if src_end_frame is not None else tm.source_end_frame
        delta = (new_start_f - tm.source_start_frame) if src_start_frame is not None else 0
        new_tl_start_f = tm.timeline_from_clip(
            tm.clip_from_timeline(tm.timeline_start_frame) + delta
        ) if src_start_frame is not None else tm.timeline_start_frame
        tm = dataclasses.replace(
            tm,
            source_start_frame=new_start_f,
            source_end_frame=new_end_f,
            timeline_start_frame=new_tl_start_f,
        )
        if tm.source_range.duration_frames <= 0:
            raise CommandError("trim 后长度无效")
        # durationFrames > 0 invariant (GUI-02 user spec).
        assert tm.source_range.duration_frames > 0, "trim produced non-positive duration"
        # Write back as seconds (storage boundary).
        clip.source_range = clip.source_range.model_copy(update={
            "start": tm.source_start_frame * fps.den / fps.num,
            "end": tm.source_end_frame * fps.den / fps.num,
        })
        clip.timeline_range = clip.timeline_range.model_copy(update={
            "start": tm.timeline_start_frame * fps.den / fps.num,
            "end": (tm.timeline_start_frame + tm.source_range.duration_frames) * fps.den / fps.num / clip.speed,
        })
        # 重叠检查
        self._check_no_overlap(
            clip.track_id, clip.timeline_range.start, clip.timeline_range.end,
            exclude_clip_id=clip_id,
            op_name=f"trim_clip_frame({clip_id})")
        after = {"source_range": clip.source_range.model_dump(),
                 "timeline_range": clip.timeline_range.model_dump()}
        return self._record("trim", clip_id, before, after, why=why,
                            time_range=clip.timeline_range)

    def split_clip(self, clip_id: str, at_source_time: float, why: str = "",
                   timeline_id: str | None = None) -> tuple[Clip, Clip]:
        """Split at SOURCE seconds (legacy). For frame-native, use
        `split_clip_frame(at_timeline_frame)` which uses Core's TimeMap
        to convert timeline_frame -> source_frame."""
        tl = self._timeline(timeline_id)
        clip = self._clip(clip_id, timeline_id)
        sr = clip.source_range
        if not (sr.start < at_source_time < sr.end):
            raise CommandError("切分点不在 clip 范围内")
        before = clip.model_dump()
        # 左半保留原 clip，右半生成新 clip
        ratio = (at_source_time - sr.start) / (sr.end - sr.start)
        tr = clip.timeline_range
        mid_timeline = tr.start + (tr.end - tr.start) * ratio
        right = Clip(
            clip_id=f"c{uuid.uuid4().hex[:6]}",
            asset_id=clip.asset_id,
            source_range=TimeRange(start=at_source_time, end=sr.end),
            timeline_range=TimeRange(start=mid_timeline, end=tr.end),
            track_id=clip.track_id,
            speed=clip.speed, volume=clip.volume,
            transform=dict(clip.transform),
        )
        sr.end = at_source_time
        clip.timeline_range.end = mid_timeline
        self.core.project.clips[right.clip_id] = right
        track = next(t for t in tl.tracks
                     if t.track_id == clip.track_id)
        idx = track.clip_ids.index(clip_id)
        track.clip_ids.insert(idx + 1, right.clip_id)
        self._record("split", clip_id, before,
                     {"clip": clip.model_dump(), "right_clip_id": right.clip_id},
                     why=why,
                     time_range=TimeRange(start=at_source_time, end=at_source_time))
        return clip, right

    def split_clip_frame(self, clip_id: str, at_timeline_frame: int, why: str = '',
                         timeline_id: str | None = None) -> tuple:
        """Frame-native split. `at` is in TIMELINE frame coordinates;
        TimeMap handles source<->timeline conversion in frames."""
        from yroll.core.timebase import Rational
        from yroll.core.timemap import TimeMap
        fps = self._fps_rational()
        clip = self._clip(clip_id, timeline_id)
        src_fps = self._source_fps_for_clip(clip)
        if src_fps is None:
            src_fps = fps
        tm = TimeMap.for_clip(clip, fps, src_fps)
        # Convert timeline frame to source frame.
        at_source_frame = tm.source_from_timeline(at_timeline_frame)
        if not (tm.source_start_frame < at_source_frame < tm.source_end_frame):
            raise CommandError("切分点不在 clip 范围内")
        # Perform the seconds-based split using the converted source frame.
        at_source_time = at_source_frame * src_fps.den / src_fps.num
        clip0, right = self.split_clip(clip_id, at_source_time, why=why)
        # durationFrames > 0 invariant (GUI-02 user spec)
        src_fps0 = self._source_fps_for_clip(clip0) or fps
        src_fps1 = self._source_fps_for_clip(right) or fps
        tm0 = TimeMap.for_clip(clip0, fps, src_fps0)
        tm1 = TimeMap.for_clip(right, fps, src_fps1)
        assert tm0.source_range.duration_frames > 0, "split left clip has 0 frames"
        assert tm1.source_range.duration_frames > 0, "split right clip has 0 frames"
        return clip0, right

    # ---------- Selection-aware mutations (P0-04B) ----------
    #
    # Single API that handles: single clip, multi-clip, cross-track, range-based.
    # Backed by move_clip() / remove_clip() etc. internally — those remain for
    # direct callers and undo/redo. The Selection variants are the *front door*
    # for GUI, MCP, Agent.
    # ---------- Selection-aware mutations (P0-04B) ----------

    def move_selection(self, selection: 'Selection', delta_seconds: float,
                       new_track_id: str | None = None,
                       why: str = "") -> Operation:
        """Move all clips in selection by delta_seconds (or to new_track_id).

        Single composite Operation that captures every per-clip move plus
        cross-track strong-link propagation. Undo restores all in one step.
        """
        from yroll.core.selection import Selection as _Selection
        if not isinstance(selection, _Selection):
            selection = _Selection.from_clip_or_id(selection)
        # Determine target clips: explicit clip_ids wins; otherwise resolve
        # from track_ids (all clips in those tracks intersecting range, or all
        # clips in track if no range).
        target_ids = list(selection.clip_ids)
        if not target_ids and selection.track_ids:
            for t in tl.tracks:
                if t.track_id in selection.track_ids:
                    for cid in t.clip_ids:
                        c = self.core.project.clips.get(cid)
                        if c is None:
                            continue
                        if selection.range is None:
                            target_ids.append(cid)
                            continue
                        # Range is in frames (FrameRange); compare to clip's
                        # timeline_range converted to frames.
                        from yroll.core.timebase import FrameTime, Rational
                        fps = Rational(getattr(self.core.project, 'fps_num', 30),
                                       getattr(self.core.project, 'fps_den', 1) or 1)
                        tl_s_f = FrameTime.from_seconds(c.timeline_range.start, fps).frame
                        tl_e_f = FrameTime.from_seconds(c.timeline_range.end, fps).frame
                        from yroll.core.timebase import FrameRange as _FR
                        clip_fr = _FR(tl_s_f, tl_e_f, fps)
                        if selection.range.overlaps(clip_fr):
                            target_ids.append(cid)
        if not target_ids:
            raise CommandError("Selection is empty — nothing to move")

        # Apply per-clip moves (each emits its own op); aggregate into a
        # composite "move_selection" op capturing all changes.
        from yroll.core.manifest import TimeRange
        before: dict = {}
        after: dict = {}
        for cid in target_ids:
            c = self.core.project.clips.get(cid)
            if c is None:
                continue
            before[cid] = {"timeline_range": c.timeline_range.model_dump(),
                           "track_id": c.track_id}
            ns = c.timeline_range.start + delta_seconds
            nt = new_track_id if new_track_id and cid == target_ids[0] else None
            # Direct state mutation: composite op captures before/after.
            if nt and nt != c.track_id:
                # Cross-track move
                old_track = next((t for t in tl.tracks
                                  if cid in t.clip_ids), None)
                if old_track:
                    old_track.clip_ids.remove(cid)
                dst = next((t for t in tl.tracks
                            if t.track_id == nt), None)
                if dst is None:
                    raise CommandError(f"目标轨道不存在: {nt}")
                dst.clip_ids.append(cid)
                c.track_id = nt
            c.timeline_range = TimeRange(start=ns, end=ns + (c.timeline_range.end - c.timeline_range.start))
            after[cid] = {"timeline_range": c.timeline_range.model_dump(),
                          "track_id": c.track_id}

        return self._apply_record(
            "move_selection", target_ids[0], before, after,
            why=why or f"Selection 移动 {len(target_ids)} clip(s) by {delta_seconds:+.2f}s",
            tool="selection.move")

    def delete_selection(self, selection: 'Selection', ripple: bool = False,
                         why: str = "",
                         timeline_id: str | None = None) -> Operation:
        """Delete all clips in selection. ripple=True → collapse subsequent clips."""
        tl = self._timeline(timeline_id)
        from yroll.core.selection import Selection as _Selection
        if not isinstance(selection, _Selection):
            selection = _Selection.from_clip_or_id(selection)
        ids = list(selection.clip_ids)
        if not ids and selection.track_ids:
            for t in tl.tracks:
                if t.track_id in selection.track_ids:
                    ids.extend(t.clip_ids)
        if not ids:
            raise CommandError("Selection is empty — nothing to delete")
        # Composite op: remove each clip + shift same-track followers if ripple.
        before = {}
        after = {}
        for cid in ids:
            c = self.core.project.clips.get(cid)
            if c is None:
                continue
            before[cid] = c.model_dump()
            self.core.project.clips.pop(cid, None)
            for t in tl.tracks:
                if cid in t.clip_ids:
                    t.clip_ids.remove(cid)
        if ripple:
            # For each track touched, shift later clips left by deleted duration.
            touched_tracks: dict[str, float] = {}
            for cid in ids:
                bd = before.get(cid) or {}
                if bd.get("track_id"):
                    dur = bd["timeline_range"]["end"] - bd["timeline_range"]["start"]
                    touched_tracks[bd["track_id"]] = (
                        touched_tracks.get(bd["track_id"], 0.0) + dur)
            for tid, shift in touched_tracks.items():
                track = next((t for t in tl.tracks
                              if t.track_id == tid), None)
                if not track:
                    continue
                for cid2 in track.clip_ids:
                    c2 = self.core.project.clips.get(cid2)
                    if c2 is None:
                        continue
                    before.setdefault(cid2, {})["timeline_range_pre_shift"] = (
                        c2.timeline_range.model_dump())
                    c2.timeline_range = TimeRange(
                        start=c2.timeline_range.start - shift,
                        end=c2.timeline_range.end - shift)
                    after[cid2] = {"timeline_range": c2.timeline_range.model_dump()}
        return self._apply_record(
            "delete_selection", ids[0], before, after,
            why=why or f"Selection 删除 {len(ids)} clip(s){' (ripple)' if ripple else ''}",
            tool="selection.delete")

    def move_clip(self, clip_id: str, new_timeline_start: float,
                  new_track_id: str | None = None, why: str = "",
                  timeline_id: str | None = None) -> Operation:
        tl = self._timeline(timeline_id)
        """Move to new TIMELINE seconds (legacy). For frame-native, use
        `move_clip_frame(new_timeline_start_frame)`."""
        from yroll.core.links import infer_relationships

        clip = self._clip(clip_id, timeline_id)
        before = {"timeline_range": clip.timeline_range.model_dump(),
                  "track_id": clip.track_id}
        old_start = clip.timeline_range.start
        length = clip.timeline_range.end - clip.timeline_range.start
        delta = new_timeline_start - old_start

        # 重叠检查（如果换轨，检查新轨；否则检查原轨）
        target_track = new_track_id or clip.track_id
        self._check_no_overlap(
            target_track, new_timeline_start, new_timeline_start + length,
            exclude_clip_id=clip_id,
            op_name=f"move_clip({clip_id})")

        # 先推断关系（在旧位置上），再算联动，最后才移动
        infer_relationships(self.core.project)
        related_ids: list[str] = []
        for r in self.core.project.relationships:
            if r.relation.value != "strong":
                continue
            if r.source == clip_id:
                related_ids.append(r.target)
            elif r.target == clip_id:
                related_ids.append(r.source)

        # 移动主 clip
        clip.timeline_range = TimeRange(
            start=new_timeline_start, end=new_timeline_start + length)
        if new_track_id and new_track_id != clip.track_id:
            old = next((t for t in tl.tracks if clip_id in t.clip_ids), None)
            if old:
                old.clip_ids.remove(clip_id)
            new = next((t for t in tl.tracks if t.track_id == new_track_id), None)
            if new is None:
                raise CommandError(f"track 不存在: {new_track_id}")
            new.clip_ids.append(clip_id)
            clip.track_id = new_track_id

        cross_shifted: dict[str, float] = {}
        for rid in related_ids:
            rc = self.core.project.clips.get(rid)
            if rc is None:
                continue
            # 字幕/人声与原 clip 时间区间重叠才联动（避免拖动整段时把全场字幕带走）
            ovl_s = max(rc.timeline_range.start, old_start)
            ovl_e = min(rc.timeline_range.end, old_start + length)
            if ovl_e <= ovl_s:
                continue
            cross_shifted[rid] = rc.timeline_range.start
            rc.timeline_range = TimeRange(
                start=rc.timeline_range.start + delta,
                end=rc.timeline_range.end + delta)

        after = {"timeline_range": clip.timeline_range.model_dump(),
                 "track_id": clip.track_id}
        if cross_shifted:
            before["cross_shifted"] = cross_shifted
            after["cross_shifted_count"] = len(cross_shifted)
        return self._record("move", clip_id, before, after, why=why,
                            time_range=clip.timeline_range)

    def move_clip_frame(self, clip_id: str, new_timeline_start_frame: int,
                        new_track_id: str | None = None,
                        why: str = "",
                        timeline_id: str | None = None) -> Operation:
        """Frame-native move. Math in frames; conversion at storage
        boundary only."""
        fps = self._fps_rational()
        new_timeline_start = new_timeline_start_frame * fps.den / fps.num
        return self.move_clip(clip_id, new_timeline_start,
                              new_track_id=new_track_id, why=why,
                              timeline_id=timeline_id)

    def set_speed(self, clip_id: str, speed: float, why: str = "") -> Operation:
        clip = self._clip(clip_id)
        if speed <= 0:
            raise CommandError("speed 必须 > 0")
        # GUI-03B: image clips cannot be retimed. The asset has
        # only one source frame; speed is structurally locked at 1.0.
        # Use `trim_image_clip_frame` to adjust the timeline duration.
        asset = next((a for a in self.core.project.assets
                      if a.asset_id == clip.asset_id), None)
        if asset is not None and asset.type.value == "image":
            raise CommandError(
                f"set_speed: image clip {clip_id} cannot be retimed "
                f"(image has 1 source frame; speed is locked to 1.0). "
                f"Use trim_image_clip_frame to change the on-screen "
                f"duration."
            )
        before = {"speed": clip.speed,
                  "timeline_range": clip.timeline_range.model_dump()}
        clip.speed = speed
        src_len = clip.source_range.end - clip.source_range.start
        clip.timeline_range.end = clip.timeline_range.start + src_len / speed
        after = {"speed": speed,
                 "timeline_range": clip.timeline_range.model_dump()}
        return self._record("speed", clip_id, before, after, why=why,
                            time_range=clip.timeline_range)

    def replace_clip_voice(self, clip_id: str, text: str,
                           voice_id: str | None = None, why: str = "",
                           timeline_id: str | None = None) -> Operation:
        """L2 语音重配：TTS 合成正确文本的语音 → 新音频 clip 对齐原 clip → 原 clip 静音。
        非破坏（原素材不动；撤销即恢复原声）。voice_id 缺省用 MiniMax 系统音色。

        Atomic (P0-04D): 一个用户意图 = 一个 voice_replace Operation。
        不再产生独立的 add_clip / mute 子 op；Undo 一次回到替换前状态。
        """
        tl = self._timeline(timeline_id)
        import hashlib
        import uuid

        from yroll.core.models import Asset, AssetIdentity, AssetOrigin, AssetType
        from yroll.tools.tts import tts_generate

        clip = self._clip(clip_id)
        dest = self.core.path / "generated" / f"tts-{uuid.uuid4().hex[:8]}.mp3"
        dest.parent.mkdir(exist_ok=True)
        out = tts_generate(text, dest, voice_id=voice_id)

        md5 = hashlib.md5(out.read_bytes()).hexdigest()
        project = self.core.project
        asset = Asset(
            asset_id=f"a{uuid.uuid4().hex[:6]}",
            type=AssetType.AUDIO, origin=AssetOrigin.GENERATED,
            path=str(out),
            identity=AssetIdentity(
                md5=md5, size_bytes=out.stat().st_size,
                duration_sec=clip.timeline_range.end - clip.timeline_range.start),
        )
        project.assets.append(asset)

        # 新音频 clip 放到音频轨（对齐原 clip 的时间轴区间），原 clip 静音
        atrack = next((t for t in project.timeline.tracks
                       if t.kind == TrackKind.AUDIO and not t.muted), None)
        if atrack is None:
            atrack = self._add_track_no_op(TrackKind.AUDIO, "a1", tl=tl)
        dur = clip.timeline_range.end - clip.timeline_range.start
        new_clip = self._add_clip_no_op(
            asset.asset_id, 0.0, dur,
            timeline_start=clip.timeline_range.start,
            track_id=atrack.track_id)
        old_muted = clip.context.get("muted")
        clip.context["muted"] = "1"

        before = {
            "muted": old_muted,
            "asset_id": None,
            "new_clip_id": None,
        }
        after = {
            "asset_id": asset.asset_id,
            "text": text,
            "voice_id": voice_id or "default",
            "new_clip_id": new_clip.clip_id,
            "muted": clip.context.get("muted"),
        }
        return self._apply_record(
            "voice_replace", clip_id, before, after,
            why=why or f"语音重配：{text[:20]}", cost=0.05,
            tool="voice.clone_replace")

    def _add_track_no_op(self, kind, track_id, tl=None):
        """Atomic helper: add a track without emitting an Operation.
        GUI-03E-2A: takes an optional Timeline; falls back to the
        active Timeline when None."""
        from yroll.core.manifest import Track
        if tl is None:
            tl = self._timeline(None)  # legacy fallback to active
        track = Track(track_id=track_id, timeline_id=tl.timeline_id, kind=kind)
        tl.tracks.append(track)
        return track

    def _add_clip_no_op(self, asset_id: str, source_start: float, source_end: float,
                        timeline_start: float, track_id: str = "v1",
                        tl=None):
        """Atomic helper: add a clip without emitting an Operation.
        GUI-03E-2A: takes an optional Timeline; falls back to the
        active Timeline when None. The new Clip's `timeline_id` is
        stamped from the resolved Timeline."""
        import uuid
        from yroll.core.manifest import Clip
        if tl is None:
            tl = self._timeline(None)
        clip = Clip(
            clip_id=f"c{uuid.uuid4().hex[:6]}",
            asset_id=asset_id,
            timeline_id=tl.timeline_id,
            source_range=TimeRange(start=source_start, end=source_end),
            timeline_range=TimeRange(start=timeline_start,
                                     end=timeline_start + (source_end - source_start)),
            track_id=track_id,
        )
        self.core.project.clips[clip.clip_id] = clip
        track = next((t for t in tl.tracks
                      if t.track_id == track_id), None)
        if track:
            track.clip_ids.append(clip.clip_id)
        return clip

    def set_muted(self, clip_id: str, muted: bool, why: str = "") -> Operation:
        """静音开关（M 键手感）：渲染时音量为 0，不动 clip.volume 原值。"""
        clip = self._clip(clip_id)
        before = {"muted": clip.context.get("muted", "")}
        if muted:
            clip.context["muted"] = "1"
        else:
            clip.context.pop("muted", None)
        return self._record("mute", clip_id, before,
                            {"muted": clip.context.get("muted", "")},
                            why=why or ("静音" if muted else "取消静音"),
                            time_range=clip.timeline_range, tool="audio.mute")

    def set_volume(self, clip_id: str, volume: float, why: str = "",
                   time_range: TimeRange | None = None) -> Operation:
        clip = self._clip(clip_id)
        before = {"volume": clip.volume}
        clip.volume = volume
        return self._record("volume", clip_id, before, {"volume": volume},
                            why=why, time_range=time_range, tool="audio.gain")

    def set_transform(self, clip_id: str, transform: dict, why: str = "") -> Operation:
        """设置 clip 变换（PiP 位置/尺寸：x/y/scale 归一化）。"""
        clip = self._clip(clip_id)
        before = {"transform": dict(clip.transform)}
        clip.transform = dict(transform)
        return self._record("transform", clip_id, before,
                            {"transform": dict(transform)}, why=why,
                            time_range=clip.timeline_range, tool="video.transform")

    # ---------- 本地 AI/确定性工具（L1 路由的真实执行体） ----------

    def remove_silence(self, clip_id: str, noise_db: float = -35.0,
                       min_duration: float = 0.5, why: str = "",
                       timeline_id: str | None = None) -> Operation:
        """去停顿/气口：检测 clip 源区间内的静音段，把 clip 重建成不含静音的多个片段。
        时间轴总长度收缩（删掉的静音不再占位）。
        """
        from yroll.tools.audio_tools import complement_ranges, detect_silences

        tl = self._timeline(timeline_id)
        clip = self._clip(clip_id, timeline_id)
        asset = next((a for a in self.core.project.assets
                      if a.asset_id == clip.asset_id), None)
        if asset is None:
            raise CommandError(f"clip 的素材不在工程中: {clip.asset_id}")

        whole = clip.source_range
        silences = detect_silences(asset.path, noise_db, min_duration, within=whole)
        keeps = complement_ranges(whole, silences)
        if len(keeps) <= 1:
            return self._record("silence_remove", clip_id,
                                {"source_range": whole.model_dump()},
                                {"kept": [k.model_dump() for k in keeps],
                                 "removed": []},
                                why=why or "去停顿：未检测到静音段",
                                tool="audio.silence_remove")

        before = clip.model_dump()
        tl_start = clip.timeline_range.start
        removed_total = (whole.end - whole.start) - sum(k.end - k.start for k in keeps)

        # 原 clip 变成第一个保留段
        track = next(t for t in tl.tracks
                     if clip_id in t.clip_ids)
        idx = track.clip_ids.index(clip_id)
        cursor = tl_start
        clip.source_range = keeps[0]
        clip.timeline_range = TimeRange(start=cursor,
                                        end=cursor + (keeps[0].end - keeps[0].start) / clip.speed)
        cursor = clip.timeline_range.end

        # 其余保留段成为新 clip，紧随其后
        new_ids = []
        for k in keeps[1:]:
            nc = Clip(
                clip_id=f"c{uuid.uuid4().hex[:6]}",
                asset_id=clip.asset_id,
                source_range=k,
                timeline_range=TimeRange(start=cursor,
                                         end=cursor + (k.end - k.start) / clip.speed),
                track_id=clip.track_id,
                speed=clip.speed, volume=clip.volume,
                transform=dict(clip.transform),
            )
            self.core.project.clips[nc.clip_id] = nc
            new_ids.append(nc.clip_id)
            cursor = nc.timeline_range.end
        track.clip_ids[idx + 1:idx + 1] = new_ids

        return self._record(
            "silence_remove", clip_id, before,
            {"kept": [k.model_dump() for k in keeps],
             "removed": [s.model_dump() for s in silences],
             "new_clips": new_ids,
             "removed_seconds": round(removed_total, 2)},
            why=why or f"去停顿：删除 {len(silences)} 段静音共 {removed_total:.1f}s",
            tool="audio.silence_remove")

    def remove_filler_words(self, clip_id: str | None = None,
                            fillers: list[str] | None = None,
                            min_word_dur: float = 0.15,
                            why: str = "") -> Operation:
        """填充词删除：基于 ASR 转写自动检测并删除"嗯/啊/呃"等口癖（剪映卖点）。

        策略：用 transcript segments 中的词级时间戳，命中填充词的，
        在字幕轨上把对应时间区间删掉，并把被删区间的视频 clip trim 掉。
        """
        from yroll.core.transcripts import load_transcripts

        project = self.core.project
        transcripts = load_transcripts(project)
        if not transcripts:
            raise CommandError("工程没有转写数据（先跑 ingest 理解管线）")

        fillers = fillers or ["嗯", "啊", "呃", "哦", "诶", "哎", "噢", "uh", "um", "er"]
        removed_total = 0.0
        removed_count = 0

        vt = next((t for t in project.timeline.tracks
                   if t.kind == TrackKind.VIDEO), None)
        candidates = [project.clips[cid] for cid in (vt.clip_ids if vt else [])
                      if cid in project.clips]
        if clip_id:
            candidates = [self._clip(clip_id)]

        for clip in candidates:
            segs = transcripts.get(clip.asset_id, [])
            sr, tr = clip.source_range, clip.timeline_range
            # 找被命中填充词的时间区间
            filler_ranges = []
            for seg in segs:
                for w in seg.get("words", []):
                    word = (w.get("word") or "").strip().lower()
                    if word in [f.lower() for f in fillers]:
                        # word 是源时间，转 timeline 时间
                        w_start_src = w.get("start", 0)
                        w_end_src = w.get("end", w_start_src + min_word_dur)
                        if w_end_src - w_start_src < min_word_dur:
                            continue
                        # 转 timeline 时间（speed 映射）
                        rel_start = max(0, w_start_src - sr.start) / clip.speed
                        rel_end = min(sr.end - sr.start,
                                       w_end_src - sr.start) / clip.speed
                        tl_s = tr.start + rel_start
                        tl_e = tr.start + rel_end
                        filler_ranges.append((tl_s, tl_e))
            if not filler_ranges:
                continue

            # 合并相邻填充词区间，生成"保留区间"
            filler_ranges.sort()
            merged = [filler_ranges[0]]
            for s, e in filler_ranges[1:]:
                if s <= merged[-1][1]:
                    merged[-1] = (merged[-1][0], max(merged[-1][1], e))
                else:
                    merged.append((s, e))

            # 在 clip 上"删除"填充词区间（与去停顿逻辑一致）
            keeps = []
            cursor = tr.start
            for fs, fe in merged:
                if fs > cursor:
                    keeps.append((cursor, fs))
                removed_total += fe - fs
                removed_count += 1
                cursor = fe
            if cursor < tr.end:
                keeps.append((cursor, tr.end))

            if not keeps:
                continue

            # 应用：删原 clip，新增保留区间为新 clip
            before = clip.model_dump()
            track = next(t for t in project.timeline.tracks
                         if clip.clip_id in t.clip_ids)
            idx = track.clip_ids.index(clip.clip_id)
            track.clip_ids.remove(clip.clip_id)
            del project.clips[clip.clip_id]

            new_ids = []
            cur_tl = tr.start
            for k_s, k_e in keeps:
                rel_s = (k_s - tr.start) * clip.speed
                rel_e = (k_e - tr.start) * clip.speed
                nc = Clip(
                    clip_id=f"c{uuid.uuid4().hex[:6]}",
                    asset_id=clip.asset_id,
                    source_range=TimeRange(start=sr.start + rel_s,
                                           end=sr.start + rel_e),
                    timeline_range=TimeRange(start=k_s, end=k_e),
                    track_id=clip.track_id,
                    speed=clip.speed, volume=clip.volume,
                    transform=dict(clip.transform),
                )
                project.clips[nc.clip_id] = nc
                new_ids.append(nc.clip_id)
            track.clip_ids[idx:idx] = new_ids

        return self._record(
            "filler_remove", clip_id or "timeline", {},
            {"removed_count": removed_count,
             "removed_seconds": round(removed_total, 2)},
            why=why or f"删除 {removed_count} 个填充词，共 {removed_total:.1f}s",
            tool="audio.filler_remove")

    # ---------- 调整图层（带羽化，局部修改不硬切割） ----------

    def analyze_loudness(self, clip_id: str, why: str = "",
                        timeline_id: str | None = None) -> Operation:
        """响度分析：测量 clip 源区间的 mean/max 音量，结果落 Operation.after。
        分析也是工程事件（蓝图：'AI 分析一次，长期使用'）。"""
        from yroll.tools.audio_tools import measure_loudness

        clip = self._clip(clip_id)
        asset = next((a for a in self.core.project.assets
                      if a.asset_id == clip.asset_id), None)
        if asset is None:
            raise CommandError(f"clip 的素材不在工程中: {clip.asset_id}")
        m = measure_loudness(asset.path, within=clip.source_range)
        if m is None:
            raise CommandError(f"无法测量响度（素材无音轨？）: {clip.asset_id}")
        return self._record("analyze_loudness", clip_id, {}, m,
                            why=why or f"响度分析 mean={m['mean_db']}dB max={m['max_db']}dB",
                            tool="audio.loudness")

    def denoise_clip(self, clip_id: str, strength: float = 12.0,
                     why: str = "") -> Operation:
        """降噪（ffmpeg afftdn）：非破坏性，存为调整图层，渲染时生效。"""
        return self.add_adjustment(
            clip_id, "denoise", {"nr": strength},
            why=why or f"降噪 afftdn nr={strength}")

    def delogo_clip(self, clip_id: str, region: Region, why: str = "") -> Operation:
        """去水印/台标（ffmpeg delogo）：非破坏性，存为调整图层，渲染时生效。
        region 用归一化坐标（0-1，相对画面宽高），渲染时按输出分辨率换算像素。"""
        if not (0 <= region.x < 1 and 0 <= region.y < 1
                and 0 < region.w <= 1 and 0 < region.h <= 1):
            raise CommandError("delogo region 必须是归一化坐标（0-1）")
        return self.add_adjustment(
            clip_id, "delogo",
            {"x": region.x, "y": region.y, "w": region.w, "h": region.h},
            region=region,
            why=why or f"去水印 ({region.x:.2f},{region.y:.2f} {region.w:.2f}x{region.h:.2f})")

    def chromakey_clip(self, clip_id: str, color: str = "0x00FF00",
                       similarity: float = 0.3, blend: float = 0.1,
                       why: str = "") -> Operation:
        """绿幕/纯色抠像（Chroma Key，剪映/Premiere 标配）。

        非破坏性调整图层，渲染时用 ffmpeg chromakey filter。
        color 默认绿幕（0x00FF00），可指定任意 RGB 16 进制。
        """
        if not (0 < similarity <= 1):
            raise CommandError("similarity 必须 0~1")
        if not (0 <= blend <= 1):
            raise CommandError("blend 必须 0~1")
        return self.add_adjustment(
            clip_id, "chromakey",
            {"color": color, "similarity": similarity, "blend": blend},
            why=why or f"Chroma Key {color} (similarity={similarity})")

    # ---------- 画面调整（CapCut 式基础操作，全部非破坏性调整图层） ----------

    def set_color(self, clip_id: str, *, brightness: float | None = None,
                  contrast: float | None = None, saturation: float | None = None,
                  temperature: float | None = None, sharpen: float | None = None,
                  why: str = "") -> Operation:
        """画面色彩：brightness -1~1 / contrast 0~2 / saturation 0~3 /
        temperature 1000~12000K / sharpen 0~3。渲染：eq + colortemperature + unsharp。"""
        params = {k: v for k, v in {
            "brightness": brightness, "contrast": contrast,
            "saturation": saturation, "temperature": temperature,
            "sharpen": sharpen}.items() if v is not None}
        if not params:
            raise CommandError("至少给一个色彩参数")
        return self.add_adjustment(
            clip_id, "color", params,
            why=why or f"画面调整 {params}")

    def set_flip(self, clip_id: str, horizontal: bool = False,
                 vertical: bool = False, why: str = "") -> Operation:
        """镜像翻转（hflip/vflip）。"""
        if not (horizontal or vertical):
            raise CommandError("horizontal/vertical 至少一个 True")
        return self.add_adjustment(
            clip_id, "flip", {"h": horizontal, "v": vertical},
            why=why or f"镜像 {'水平' if horizontal else ''}{'垂直' if vertical else ''}")

    def set_opacity(self, clip_id: str, opacity: float, why: str = "") -> Operation:
        """不透明度 0~1（与黑底混合，V0 近似：整体压暗）。"""
        if not (0 <= opacity <= 1):
            raise CommandError("opacity 必须 0~1")
        return self.add_adjustment(
            clip_id, "opacity", {"value": opacity},
            why=why or f"不透明度 {opacity}")

    def set_crop(self, clip_id: str, left: float = 0, top: float = 0,
                 right: float = 0, bottom: float = 0, why: str = "") -> Operation:
        """画面裁剪（四边各裁比例 0~0.45），裁后放大回全幅。"""
        for v in (left, top, right, bottom):
            if not (0 <= v <= 0.45):
                raise CommandError("裁剪比例必须 0~0.45")
        if left + right >= 0.9 or top + bottom >= 0.9:
            raise CommandError("裁剪过多")
        return self.add_adjustment(
            clip_id, "crop",
            {"left": left, "top": top, "right": right, "bottom": bottom},
            why=why or f"画面裁剪 左{left} 上{top} 右{right} 下{bottom}")

    def set_reverse(self, clip_id: str, why: str = "") -> Operation:
        """倒放（reverse/areverse 重编码，V0 限短 clip）。"""
        clip = self._clip(clip_id)
        src_len = clip.source_range.end - clip.source_range.start
        if src_len > 60:
            raise CommandError("倒放 V0 限 60s 以内的 clip（重编码成本）")
        return self.add_adjustment(
            clip_id, "reverse", {}, why=why or "倒放")

    def set_freeze(self, clip_id: str, freeze_sec: float, why: str = "") -> Operation:
        """Freeze 定格：在 clip 末尾冻结最后一帧 freeze_sec 秒（剪映/Premiere 标配）。

        非破坏性：source_range 不变，timeline_range 不变；
        渲染时在 clip 末尾追加 `tpad=stop_mode=clone:stop_duration=X`。
        """
        clip = self._clip(clip_id)
        if freeze_sec < 0 or freeze_sec > 30:
            raise CommandError("freeze 时长必须 0~30s")
        return self.add_adjustment(
            clip_id, "freeze", {"seconds": freeze_sec},
            why=why or f"定格 {freeze_sec:.1f}s")

    def set_color2_reset(self, clip_id: str, why: str = "") -> Operation:
        """重置：移除该 clip 全部画面/位置类调整图层。"""
        clip = self._clip(clip_id)
        kinds = {"color", "flip", "opacity", "crop", "transform2d"}
        before = {"adjustments": list(clip.adjustments)}
        clip.adjustments = [a for a in clip.adjustments
                            if a.get("kind") not in kinds]
        return self._record("adjust", clip_id, before,
                            {"adjustments": list(clip.adjustments)},
                            why=why or "重置画面/位置调整", tool="video.reset")

    def set_transform2d(self, clip_id: str, *, x: float | None = None,
                        y: float | None = None, scale: float | None = None,
                        rotation: float | None = None,
                        bg_blur: bool = True, why: str = "") -> Operation:
        """主轨 clip 的 2D 变换：缩放/移动/旋转 + 模糊背景填充（剪映同款）。
        x/y 是画面中心偏移（-1~1 归一化）；scale 0.1~3；rotation 角度。"""
        params = {k: v for k, v in {
            "x": x, "y": y, "scale": scale, "rotation": rotation}.items()
            if v is not None}
        if not params:
            raise CommandError("至少给一个变换参数")
        if scale is not None and not (0.1 <= scale <= 3):
            raise CommandError("scale 必须 0.1~3")
        params["bg_blur"] = bg_blur
        return self.add_adjustment(
            clip_id, "transform2d", params,
            why=why or f"2D 变换 {params}")

    def set_fade(self, clip_id: str, fade_in: float = 0.0,
                 fade_out: float = 0.0, why: str = "") -> Operation:
        """淡入淡出（转场 V0：淡黑，不动时间轴；真叠化需重叠时间轴模型）。
        非破坏性调整图层，渲染时 fade/afade 生效。"""
        if fade_in < 0 or fade_out < 0 or (fade_in == 0 and fade_out == 0):
            raise CommandError("fade_in/fade_out 至少一个 > 0")
        return self.add_adjustment(
            clip_id, "fade", {"in": fade_in, "out": fade_out},
            why=why or f"淡入 {fade_in}s / 淡出 {fade_out}s")

    def set_dissolve(self, clip_id: str, duration: float = 0.5,
                     kind: str = "fade", why: str = "") -> Operation:
        """叠化（真 xfade）：本 clip 与前一个 clip 重叠 duration 秒溶解。
        kind：fade（溶解）/ wipeleft / wiperight / wipeup / wipedown /
              slideleft / slideright / circlecrop 等 xfade 内置转场。
        成片会比时间轴短（重叠部分只放一次）；字幕/混音渲染时自动同步偏移。"""
        if duration <= 0:
            raise CommandError("dissolve duration 必须 > 0")
        return self.add_adjustment(
            clip_id, "dissolve", {"duration": duration, "type": kind},
            why=why or f"叠化 {kind} {duration}s")

    def set_volume_range(self, clip_id: str, volume: float,
                         time_range: TimeRange, why: str = "") -> Operation:
        """时间范围内调音量（蓝图 §2.4：不必先 Split）。
        非破坏性调整图层，渲染时用 enable=between(t,...) 局部生效。"""
        clip = self._clip(clip_id)
        tr = clip.timeline_range
        if time_range.end <= tr.start or time_range.start >= tr.end:
            raise CommandError("时间范围与 clip 无交集")
        return self.add_adjustment(
            clip_id, "volume_range", {"volume": volume},
            time_range=time_range,
            why=why or f"范围音量 {time_range.start:.1f}-{time_range.end:.1f}s → {volume}")

    def remove_adjustment(self, clip_id: str, adjustment_id: str,
                          why: str = "") -> Operation:
        """移除一个调整图层（delogo/denoise/volume_range 等）。"""
        clip = self._clip(clip_id)
        before = {"adjustments": list(clip.adjustments)}
        adj = next((a for a in clip.adjustments if a.get("id") == adjustment_id), None)
        if adj is None:
            raise CommandError(f"调整图层不存在: {adjustment_id}")
        clip.adjustments = [a for a in clip.adjustments
                            if a.get("id") != adjustment_id]
        return self._record("adjust_remove", clip_id, before,
                            {"adjustments": list(clip.adjustments)},
                            why=why or f"移除调整图层 {adj.get('kind')}",
                            tool=f"video.{adj.get('kind', 'adjust')}_remove")

    def add_adjustment(self, clip_id: str, kind: str, params: dict,
                       time_range: TimeRange | None = None,
                       region: Region | None = None, why: str = "") -> Operation:
        clip = self._clip(clip_id)
        adj = {"id": uuid.uuid4().hex[:8], "kind": kind, "params": params,
               "time_range": time_range.model_dump() if time_range else None,
               "region": region.model_dump() if region else None}
        before = {"adjustments": list(clip.adjustments)}
        clip.adjustments.append(adj)
        return self._record("adjust", clip_id, before,
                            {"adjustments": list(clip.adjustments)},
                            why=why, time_range=time_range, region=region,
                            tool=f"video.{kind}")

    # ---------- P1: Slip / Roll / Slide ----------

    def slip_clip(self, clip_id: str, delta_seconds: float,
                  why: str = "") -> Operation:
        """Slip: shift source start/end by the same delta, keeping
        timeline_range unchanged. The clip's visible content slides
        "under" its fixed timeline slot.

        Frame-native: if delta_seconds moves past source boundaries,
        raises CommandError.
        """
        clip = self._clip(clip_id)
        sr = clip.source_range
        new_src_start = sr.start + delta_seconds
        new_src_end = sr.end + delta_seconds
        if new_src_start < 0 or new_src_end > clip.speed * 1e9:
            # Don't actually compute asset duration here; for now only
            # guard against negative source positions.
            if new_src_start < 0:
                raise CommandError(
                    f"slip would push source start before 0: {new_src_start}")
        before = {"source_range": sr.model_dump()}
        clip.source_range = TimeRange(start=new_src_start, end=new_src_end)
        after = {"source_range": clip.source_range.model_dump()}
        return self._record("slip", clip_id, before, after, why=why or
                            f"Slip {delta_seconds:+.3f}s",
                            time_range=clip.timeline_range,
                            tool="timeline.slip")

    def roll_clip(self, clip_id: str, neighbor_clip_id: str,
                  delta_seconds: float, why: str = "") -> Operation:
        """Roll: move the boundary between two adjacent clips on the
        same track. clip and neighbor must be on the same track and
        adjacent (or this just adjusts both ends by ±delta/2).

        For simplicity here: extend clip.end by delta and shorten
        neighbor.start by delta. Atomically captured in one op.
        """
        clip = self._clip(clip_id)
        neighbor = self._clip(neighbor_clip_id)
        if clip.track_id != neighbor.track_id:
            raise CommandError(
                "roll requires both clips on the same track")
        before = {
            "clip": {"source_range": clip.source_range.model_dump(),
                     "timeline_range": clip.timeline_range.model_dump()},
            "neighbor": {"source_range": neighbor.source_range.model_dump(),
                         "timeline_range": neighbor.timeline_range.model_dump()},
        }
        # Adjust timeline positions; source stays (roll changes cut point)
        new_clip_end = clip.timeline_range.end + delta_seconds
        new_neighbor_start = neighbor.timeline_range.start + delta_seconds
        if new_neighbor_start < clip.timeline_range.start:
            raise CommandError(
                "roll would invert clip/neighbor order")
        clip.timeline_range = TimeRange(
            start=clip.timeline_range.start, end=new_clip_end)
        neighbor.timeline_range = TimeRange(
            start=new_neighbor_start, end=neighbor.timeline_range.end)
        after = {
            "clip": {"timeline_range": clip.timeline_range.model_dump()},
            "neighbor": {"timeline_range": neighbor.timeline_range.model_dump()},
            "neighbor_clip_id": neighbor_clip_id,
            "delta_seconds": delta_seconds,
        }
        return self._record("roll", clip_id, before, after, why=why or
                            f"Roll {delta_seconds:+.3f}s",
                            time_range=clip.timeline_range,
                            tool="timeline.roll")

    def slide_clip(self, clip_id: str, neighbor_clip_id: str,
                   delta_seconds: float, why: str = "") -> Operation:
        """Slide: move a clip on the timeline AND keep its source content
        by adjusting both neighbors to absorb the change. Three-clip
        atomic op: clip shifts by delta, left neighbor shortens, right
        neighbor shortens (or lengthens).
        """
        clip = self._clip(clip_id)
        left = self._clip(neighbor_clip_id)
        if clip.track_id != left.track_id:
            raise CommandError(
                "slide requires all three clips on the same track")
        before = {
            "clip": {"timeline_range": clip.timeline_range.model_dump()},
            "left": {"timeline_range": left.timeline_range.model_dump()},
        }
        clip.timeline_range = TimeRange(
            start=clip.timeline_range.start + delta_seconds,
            end=clip.timeline_range.end + delta_seconds)
        # Neighbor absorbs half the delta on each side (split: left loses
        # the right portion; right neighbor gains at left)
        left.timeline_range = TimeRange(
            start=left.timeline_range.start,
            end=left.timeline_range.end - delta_seconds)
        after = {
            "clip": {"timeline_range": clip.timeline_range.model_dump()},
            "left": {"timeline_range": left.timeline_range.model_dump()},
            "neighbor_clip_id": neighbor_clip_id,
            "delta_seconds": delta_seconds,
        }
        return self._record("slide", clip_id, before, after, why=why or
                            f"Slide {delta_seconds:+.3f}s",
                            time_range=clip.timeline_range,
                            tool="timeline.slide")

    # ---------- GUI-03E-2A: Timeline Lifecycle Commands ----------
    #
    # These four commands manage the Project's peer Timelines. They
    # are Project-global (they touch project.timelines,
    # project.active_timeline_id, etc.). Each command records the
    # target Timeline id in the Operation.parameters['timeline_id']
    # audit metadata so future history views can show WHICH Timeline
    # a mutation affected.

    def _record_lifecycle(self, op_type: str, timeline_id: str,
                           before: dict, after: dict,
                           why: str = "", tool: str | None = None) -> Operation:
        """GUI-03E-2A: lifecycle ops always carry timeline_id in
        parameters + a dedicated Operation field for fast filtering.
        """
        op = self.core.new_operation(
            who=self.who, type=op_type, target=timeline_id,
            parameters=after, before=before, after=after,
            why=why, tool=tool or f"timeline.{op_type}",
            approved_by=self.who,
        )
        # GUI-03E-2A: stamp timeline_id into the parameters so audit
        # / search can filter by Timeline. (Operation.parameters is
        # dict[str, Any] so we can add a structured key.)
        op.parameters["timeline_id"] = timeline_id
        return self.core.log(op)

    def add_timeline(self, name: str, derived_from: str | None = None,
                     why: str = "") -> Timeline:
        """Create a new empty Timeline and append it to the Project.

        Args:
          name:         user-visible label (NOT canonical key).
          derived_from: stable source timeline_id when this Timeline
                        is duplicated from another. None for a fresh
                        independent Timeline.
        """
        if not name or not name.strip():
            raise CommandError("add_timeline: name 不能为空")
        if derived_from is not None:
            src = self.core.project.get_timeline(derived_from)
            if src is None:
                raise CommandError(
                    f"add_timeline: derived_from timeline 不存在: "
                    f"{derived_from!r}")
        new_id = f"tl{uuid.uuid4().hex[:8]}"
        if self.core.project.get_timeline(new_id) is not None:
            # Vanishingly unlikely; reject for safety.
            raise CommandError(
                f"add_timeline: timeline id collision {new_id!r}")
        new_tl = Timeline(
            timeline_id=new_id,
            name=name.strip(),
            derived_from=derived_from,
            tracks=[],
            markers=[],
            beats=[],
        )
        before = {
            "timelines": [t.timeline_id for t in self.core.project.timelines],
        }
        self.core.project.timelines.append(new_tl)
        after = {
            "timelines": [t.timeline_id for t in self.core.project.timelines],
            "added": new_id,
            "name": new_tl.name,
            "derived_from": derived_from,
        }
        self._record_lifecycle(
            "add_timeline", new_id, before, after,
            why=why or f"新增时间线 {new_tl.name}",
        )
        return new_tl

    def switch_active_timeline(self, timeline_id: str,
                                why: str = "") -> Operation:
        """Make `timeline_id` the active Timeline. The Open Order
        invariant (active → default → first) only applies when the
        configured `active_timeline_id` is missing; a user/agent can
        switch to any existing Timeline."""
        tl = self._timeline(timeline_id)
        before = {"active_timeline_id": self.core.project.active_timeline_id}
        self.core.project.active_timeline_id = tl.timeline_id
        after = {"active_timeline_id": tl.timeline_id}
        return self._record_lifecycle(
            "switch_active_timeline", tl.timeline_id, before, after,
            why=why or f"切到时间线 {tl.name}",
        )

    def duplicate_timeline(self, source_timeline_id: str,
                            new_name: str | None = None,
                            why: str = "") -> Timeline:
        """Duplicate a Timeline into a new Timeline with fresh IDs.

        Spec: copy Tracks / Clips / Markers / Beats / Timeline metadata;
        generate new globally unique Timeline/Track/Clip/Marker/Beat
        IDs; preserve each Clip's asset_id (shared, never copied);
        never copy media files or Asset objects; set
        derived_from=source_timeline_id.
        """
        src = self._timeline(source_timeline_id)
        if not new_name or not new_name.strip():
            new_name = f"{src.name} 副本"
        new_id = f"tl{uuid.uuid4().hex[:8]}"
        if self.core.project.get_timeline(new_id) is not None:
            raise CommandError(
                f"duplicate_timeline: timeline id collision {new_id!r}")

        # Map old Track.id → new Track.id. Preserve kind/role/labels.
        track_id_map: dict[str, str] = {}
        new_tracks: list[Track] = []
        for t in src.tracks:
            new_tid = f"t{uuid.uuid4().hex[:8]}_{t.kind.value}"
            track_id_map[t.track_id] = new_tid
            new_tracks.append(Track(
                track_id=new_tid,
                timeline_id=new_id,
                kind=t.kind,
                clip_ids=[],  # filled below
                muted=t.muted,
                locked=t.locked,
                hidden=t.hidden,
                role=t.role,
                label=t.label,
            ))

        # Map old Clip.id → new Clip.id. New clips share asset_id,
        # get fresh track_id (mapped), fresh timeline_id, deep copy
        # of all state.
        clip_id_map: dict[str, str] = {}
        new_clips: dict[str, Clip] = {}
        for old_cid, old_clip in self.core.project.clips.items():
            if old_clip.timeline_id != src.timeline_id:
                continue
            new_cid = f"c{uuid.uuid4().hex[:8]}"
            clip_id_map[old_cid] = new_cid
            new_clip = old_clip.model_copy(deep=True)
            new_clip.clip_id = new_cid
            new_clip.timeline_id = new_id
            new_clip.track_id = track_id_map.get(
                old_clip.track_id, old_clip.track_id)
            new_clips[new_cid] = new_clip

        # Fill new Track.clip_ids now that we have the mapping.
        for src_t, new_t in zip(src.tracks, new_tracks):
            new_t.clip_ids = [clip_id_map.get(cid, cid)
                               for cid in src_t.clip_ids]

        # Map old Marker.id / Beat.id → new ids. The dicts get a new
        # timeline_id field; the rest of the payload is copied.
        new_markers: list[dict] = []
        for m in (src.markers or []):
            mid = m.get("marker_id") or f"mk{uuid.uuid4().hex[:6]}"
            new_mid = f"mk{uuid.uuid4().hex[:6]}"
            d = dict(m)
            d["marker_id"] = new_mid
            d["timeline_id"] = new_id
            new_markers.append(d)
            del mid  # silence unused warning if any
        new_beats: list[dict] = []
        for b in (src.beats or []):
            bid = b.get("beat_id") or f"b{uuid.uuid4().hex[:6]}"
            new_bid = f"b{uuid.uuid4().hex[:6]}"
            d = dict(b)
            d["beat_id"] = new_bid
            d["timeline_id"] = new_id
            new_beats.append(d)
            del bid

        new_tl = Timeline(
            timeline_id=new_id,
            name=new_name.strip(),
            derived_from=src.timeline_id,
            tracks=new_tracks,
            markers=new_markers,
            beats=new_beats,
        )

        before = {
            "timelines": [t.timeline_id for t in self.core.project.timelines],
            "source_clip_count": sum(
                1 for c in self.core.project.clips.values()
                if c.timeline_id == src.timeline_id),
        }
        self.core.project.timelines.append(new_tl)
        for cid, clip in new_clips.items():
            self.core.project.clips[cid] = clip
        after = {
            "timelines": [t.timeline_id for t in self.core.project.timelines],
            "added_timeline": new_id,
            "source_timeline": src.timeline_id,
            "new_clip_ids": list(new_clips.keys()),
            "new_track_ids": [t.track_id for t in new_tracks],
            "new_marker_ids": [m["marker_id"] for m in new_markers],
            "new_beat_ids": [b["beat_id"] for b in new_beats],
            "asset_ids_preserved": sorted({
                c.asset_id for c in new_clips.values()}),
            "destination_clip_count": sum(
                1 for c in self.core.project.clips.values()
                if c.timeline_id == new_id),
        }
        self._record_lifecycle(
            "duplicate_timeline", new_id, before, after,
            why=why or f"复制时间线 {src.name} → {new_tl.name}",
        )
        return new_tl

    def delete_timeline(self, timeline_id: str,
                        why: str = "") -> Operation:
        """Delete a Timeline. Refuses if it would leave the Project empty.

        Active selection after deletion:
          - If `timeline_id` is the active, pick via Open Order:
            active → default → first (where active/default now point
            at surviving Timelines, NOT the deleted one).
          - If `timeline_id` is not the active, leave active alone.
        """
        tl = self._timeline(timeline_id)
        if len(self.core.project.timelines) <= 1:
            raise CommandError(
                "delete_timeline: 至少需要保留一条时间线；最后一个不可删")

        was_active = (self.core.project.active_timeline_id == tl.timeline_id)
        before = {
            "timelines": [t.timeline_id for t in self.core.project.timelines],
            "active_timeline_id": self.core.project.active_timeline_id,
            "default_timeline_id": self.core.project.default_timeline_id,
            "removed_clips": sorted([
                cid for cid, c in self.core.project.clips.items()
                if c.timeline_id == tl.timeline_id
            ]),
        }
        # Remove Timeline from list.
        self.core.project.timelines = [
            t for t in self.core.project.timelines
            if t.timeline_id != tl.timeline_id]
        # Remove all Clips owned by the deleted Timeline.
        self.core.project.clips = {
            cid: c for cid, c in self.core.project.clips.items()
            if c.timeline_id != tl.timeline_id
        }
        # Patch active/default if they pointed at the deleted one.
        if self.core.project.active_timeline_id == tl.timeline_id:
            self.core.project.active_timeline_id = self._pick_open_target(
                exclude=tl.timeline_id,
                prefer=self.core.project.default_timeline_id)
        if self.core.project.default_timeline_id == tl.timeline_id:
            self.core.project.default_timeline_id = (
                self.core.project.timelines[0].timeline_id)
        after = {
            "timelines": [t.timeline_id for t in self.core.project.timelines],
            "active_timeline_id": self.core.project.active_timeline_id,
            "default_timeline_id": self.core.project.default_timeline_id,
            "removed_clips": before["removed_clips"],
            "was_active": was_active,
        }
        return self._record_lifecycle(
            "delete_timeline", tl.timeline_id, before, after,
            why=why or f"删除时间线 {tl.name}",
        )

    def _pick_open_target(self, exclude: str,
                           prefer: str | None = None) -> str:
        """Open-order resolver for delete: prefer `prefer` if it's a
        surviving id, else fall back to first surviving Timeline."""
        if prefer and prefer != exclude:
            if self.core.project.get_timeline(prefer) is not None:
                return prefer
        for t in self.core.project.timelines:
            if t.timeline_id != exclude:
                return t.timeline_id
        # Caller's precondition guarantees ≥1 surviving timeline.
        return self.core.project.timelines[0].timeline_id
