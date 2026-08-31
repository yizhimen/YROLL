"""ProjectCore：目录式工程 + Operation Log + Git 式 Version。

工程目录布局（不是单个巨大文件）：
    MyProject/
    ├── current.json      # 当前 Project 状态
    ├── operations/       # op0001.json ... 不可变操作日志（工程黑匣子）
    ├── versions/         # v1.json ... 版本树（只存 Operation 引用）
    ├── media/            # 素材（或外链 + Asset Identity）
    ├── cache/            # 可清理
    └── generated/        # 确认使用的生成结果

铁律：GUI 和 AI 都只能通过 Operation 修改工程；
Operation 落盘先于状态落盘（崩溃后可从日志重建）。
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path

from yroll.core.manifest import Actor, Operation, Project, Version

LAYOUT = ("operations", "versions", "media", "cache", "generated")


# ----------------------------------------------------------------------
# GUI-03E-1: multi-Timeline migration (raw JSON in → raw JSON out).
#
# Pre-03E project files use:
#   project.timeline: Timeline     # single, "main"
#
# Post-03E storage is:
#   project.timelines: list[Timeline]
#   project.active_timeline_id: str
#   project.default_timeline_id: str
#   project.schema_version: "0.2"
#
# Migration policy (lossless + idempotent):
#   1. If raw["timeline"] is a dict AND raw["timelines"] is absent
#      or empty → lift it into timelines[0], copy its timeline_id to
#      both active/default, and bump schema_version to "0.2". The
#      `timeline` field is left untouched on disk (the loader strips
#      it via the model migration step); the next save_state() will
#      rewrite the file without it.
#   2. If raw["timelines"] is present (post-03E save), do nothing.
#      This makes the migration idempotent across repeated opens.
#   3. If raw lacks BOTH legacy `timeline` AND `timelines`, create
#      a default `main` Timeline so a brand-new project still works.
#      (Defense in depth — ProjectCore.create() already sets these.)
# ----------------------------------------------------------------------

_DEFAULT_TIMELINE_ID = "main"


def _migrate_raw_to_multi_timeline(raw: dict) -> dict:
    """Return a new dict with multi-Timeline fields populated. The
    input is not mutated.

    GUI-03E-2A ownership invariants applied here:
      - Every Clip gets `clip.timeline_id` stamped (legacy projects
        own all clips by the active Timeline).
      - Every Track gets `track.timeline_id` stamped.
      - Every Marker / Beat dict gets `timeline_id` stamped (these
        are Timeline-local dicts after 03E-1; the lift from `extensions`
        carries the owner Timeline).
    """
    has_legacy = isinstance(raw.get("timeline"), dict)
    has_new = isinstance(raw.get("timelines"), list) and len(raw["timelines"]) > 0

    if has_new and not has_legacy:
        # Already post-03E. Repair missing ids defensively and ensure
        # every Clip/Track/Marker/Beat has a timeline_id.
        timelines = raw["timelines"]
        ids = {t["timeline_id"] for t in timelines if isinstance(t, dict)
               and "timeline_id" in t}
        active_id = raw.get("active_timeline_id")
        if not active_id or active_id not in ids:
            active_id = (raw.get("default_timeline_id")
                          if raw.get("default_timeline_id") in ids
                          else (next(iter(ids)) if ids else _DEFAULT_TIMELINE_ID))
        default_id = raw.get("default_timeline_id")
        if not default_id or default_id not in ids:
            default_id = active_id

        raw = dict(raw)
        raw["active_timeline_id"] = active_id
        raw["default_timeline_id"] = default_id
        raw["schema_version"] = "0.2"

        # Lift legacy extensions.markers/beats once (idempotent).
        ext = raw.get("extensions") or {}
        lift_markers = ext.get("markers")
        lift_beats = ext.get("story_beats")
        if lift_markers or lift_beats:
            for t in raw["timelines"]:
                if not isinstance(t, dict):
                    continue
                if t["timeline_id"] == active_id:
                    if lift_markers and "markers" not in t:
                        t["markers"] = list(lift_markers)
                    if lift_beats and "beats" not in t:
                        t["beats"] = list(lift_beats)
            new_ext = {k: v for k, v in ext.items()
                       if k not in ("markers", "story_beats")}
            raw["extensions"] = new_ext

        _stamp_ownership(raw, active_id)
        return raw

    if has_legacy:
        legacy = raw["timeline"]
        legacy_id = legacy.get("timeline_id", _DEFAULT_TIMELINE_ID)
        ext = raw.get("extensions") or {}
        lift_markers = ext.get("markers") or []
        lift_beats = ext.get("story_beats") or []
        lifted = {
            "timeline_id": legacy_id,
            "name": legacy.get("name", legacy_id),
            "derived_from": legacy.get("derived_from"),
            "tracks": legacy.get("tracks", []),
            "markers": list(lift_markers),
            "beats": list(lift_beats),
        }
        raw = dict(raw)
        raw["timelines"] = [lifted]
        active = raw.get("active_timeline_id") or legacy_id
        default = raw.get("default_timeline_id") or legacy_id
        raw["active_timeline_id"] = active
        raw["default_timeline_id"] = default
        if lift_markers or lift_beats:
            new_ext = {k: v for k, v in ext.items()
                       if k not in ("markers", "story_beats")}
            raw["extensions"] = new_ext
        raw["schema_version"] = "0.2"
        _stamp_ownership(raw, active)
        return raw

    # Neither present: create default `main` so empty/hand-written
    # projects still validate.
    raw = dict(raw)
    raw["timelines"] = [{
        "timeline_id": _DEFAULT_TIMELINE_ID,
        "name": _DEFAULT_TIMELINE_ID,
        "tracks": [],
        "markers": [],
        "beats": [],
    }]
    raw["active_timeline_id"] = raw.get("active_timeline_id", _DEFAULT_TIMELINE_ID)
    raw["default_timeline_id"] = raw.get("default_timeline_id", _DEFAULT_TIMELINE_ID)
    raw["schema_version"] = "0.2"
    _stamp_ownership(raw, _DEFAULT_TIMELINE_ID)
    return raw


def _stamp_ownership(raw: dict, active_id: str) -> None:
    """Mutate raw in place: stamp timeline_id on every Clip, every
    Track on every Timeline, every Marker dict, and every Beat dict.
    The owner Timeline is determined by the Timeline the Track /
    Marker / Beat lives under, falling back to active_id for legacy
    singletons."""
    for tl in raw.get("timelines") or []:
        if not isinstance(tl, dict):
            continue
        tid = tl.get("timeline_id") or active_id
        for t in tl.get("tracks") or []:
            if isinstance(t, dict) and "timeline_id" not in t:
                t["timeline_id"] = tid
        for m in tl.get("markers") or []:
            if isinstance(m, dict) and "timeline_id" not in m:
                m["timeline_id"] = tid
        for b in tl.get("beats") or []:
            if isinstance(b, dict) and "timeline_id" not in b:
                b["timeline_id"] = tid
    for cid, c in (raw.get("clips") or {}).items():
        if isinstance(c, dict) and "timeline_id" not in c:
            c["timeline_id"] = active_id


class ProjectCore:
    def __init__(self, path: str | Path, project: Project):
        self.path = Path(path)
        self.project = project
        self._op_seq = self._count_operations()

    # ---------- 生命周期 ----------

    @classmethod
    def create(cls, root: str | Path, name: str, intent: dict | None = None) -> "ProjectCore":
        path = Path(root) / name
        for d in LAYOUT:
            (path / d).mkdir(parents=True, exist_ok=True)
        import uuid as _uuid
        from yroll.core.manifest import Timeline
        project_id = _uuid.uuid4().hex[:12]
        project = Project(
            project_id=project_id, name=name, intent=intent or {},
            timelines=[Timeline(timeline_id="main", name="main")],
            active_timeline_id="main",
            default_timeline_id="main",
            schema_version="0.2",
        )
        # GUI-03C: no pre-created default tracks. Tracks are allocated
        # on demand by `cmd.allocate_track_for` (and `cmd.add_track` for
        # explicit creation). Old projects that had v1/v2/v3/a1/a2/a3/
        # t1/t2 pre-created still work — those tracks are present
        # in `project.timeline.tracks` after ProjectCore.open() and
        # the allocator reuses them when compatible.
        core = cls(path, project)
        core.save_state()
        return core

    @classmethod
    def ensure_default_tracks(cls, core: "ProjectCore") -> None:
        """给已有工程补齐缺失的默认轨道（不删已有轨道/clip，幂等）。"""
        from yroll.core.manifest import Track, TrackKind
        default = [
            ("v1", TrackKind.VIDEO), ("v2", TrackKind.VIDEO), ("v3", TrackKind.VIDEO),
            ("a1", TrackKind.AUDIO), ("a2", TrackKind.AUDIO), ("a3", TrackKind.AUDIO),
            ("t1", TrackKind.TEXT), ("t2", TrackKind.TEXT),
        ]
        existing = {(t.track_id, t.kind) for t in core.project.timeline.tracks}
        added = False
        for tid, kind in default:
            if (tid, kind) not in existing:
                core.project.timeline.tracks.append(Track(track_id=tid, kind=kind))
                added = True
        if added:
            core.save_state()

    @classmethod
    def open(cls, path: str | Path) -> "ProjectCore":
        path = Path(path)
        raw = json.loads((path / "current.json").read_text(encoding="utf-8"))
        # GUI-02: backwards compat — v0.1 project files lack `sequence`.
        # Build it from the flat fields on the fly.
        if "sequence" not in raw and "fps_num" in raw:
            raw["sequence"] = {
                "fps": {"num": raw.get("fps_num", 30),
                         "den": raw.get("fps_den", 1) or 1},
                "width": raw.get("width", 1920),
                "height": raw.get("height", 1080),
            }
        # GUI-03E-1: migrate pre-03E single-timeline projects to the
        # multi-Timeline container. Lossless and idempotent.
        raw = _migrate_raw_to_multi_timeline(raw)
        project = Project.model_validate(raw)
        # Ensure the flat fields match Sequence (denormalized sync).
        project.sequence.sync_to_project(project)
        core = cls(path, project)
        # GUI-03R3-W-B: load-time migration — remove empty tracks
        # from legacy projects. Pre-W-B projects may have empty
        # tracks on disk (from the old `ensure_default_tracks` which
        # pre-created v1..v3, a1..a3, t1, t2 with no clips). The
        # invariant is "every track has >= 1 clip"; enforce it on
        # load. Idempotent: running twice is a no-op.
        from yroll.core.commands import CommandLayer
        cl = CommandLayer(core, who=Actor.HUMAN)
        any_removed = False
        for tl in core.project.timelines:
            removed = cl._cleanup_empty_tracks(tl)
            if removed:
                any_removed = True
        # GUI-03R4-R2: load-time repair of historical negative-start
        # clips. Some legacy projects on disk have clips whose
        # timeline_range.start < 0 (e.g. sanlihe v1/cff462a starts at
        # -0.33s; v6/c2325dd starts at -4.33s). The R4-R2 invariant
        # is: persisted clip timeline frames cannot have start < 0.
        # The repair clamps start to 0, shrinks the duration by the
        # same amount so .end stays at the original end-frame, and
        # records ONE `repair_negative_start` Operation per clamped
        # clip in the operations log so the change is auditable.
        # Idempotent: a project with no negative-start clips exits
        # early without producing any Operation.
        repair_recorded = core._apply_negative_start_repair()
        if any_removed or repair_recorded:
            core.save_state()
        return core

    # ---------- GUI-03R4-R2: load-time repair ----------

    def _apply_negative_start_repair(self) -> bool:
        """Detect clips whose timeline_range.start < 0 and clamp each
        to start = 0 (preserving the original end-frame; duration
        shrinks accordingly). Records ONE `repair_negative_start`
        Operation per affected clip so the change is auditable.

        Returns True iff any clip was clamped (caller should
        save_state to persist the repair).

        Idempotency: a project whose has no negative-start clips
        returns False without producing any Operation. Re-opening a
        project after the first repair is a no-op.
        """
        from yroll.core.commands import CommandLayer
        from yroll.core.manifest import Actor, TimeRange
        cl = CommandLayer(self, who=Actor.HUMAN)
        any_repaired = False
        # Iterate a stable snapshot (clip_ids ordering).
        for cid in list(self.project.clips.keys()):
            c = self.project.clips.get(cid)
            if c is None:
                continue
            if c.timeline_range.start >= 0:
                continue
            before = c.model_dump()
            original_end = c.timeline_range.end
            # Preserve the original end-frame; duration shrinks.
            new_start = 0.0
            new_end = original_end
            c.timeline_range = TimeRange(start=new_start, end=new_end)
            after = c.model_dump()
            cl._record(
                "repair_negative_start", cid, before, after,
                why=(f"GUI-03R4-R2: 历史负向 start={before['timeline_range']['start']:.4f}s "
                     f"自动 clamp 到 0（保留 end={original_end:.4f}s）"),
                time_range=c.timeline_range,
                tool="repair.negative_start",
            )
            any_repaired = True
        return any_repaired

    def save_state(self) -> None:
        # GUI-02: sync canonical Sequence → flat fields on save so
        # legacy v0.1 readers still see fps_num/fps_den correctly.
        self.project.sequence.sync_to_project(self.project)
        # GUI-03E-1 invariant: a Project must always contain at
        # least one Timeline. Refuse to persist a zero-timeline
        # state — the caller must explicitly add one first.
        if not self.project.timelines:
            raise ValueError(
                "save_state: project must contain at least one Timeline; "
                "cannot persist zero-timeline project")
        (self.path / "current.json").write_text(
            self.project.model_dump_json(indent=2), encoding="utf-8"
        )

    # ---------- Operation Log ----------

    def _count_operations(self) -> int:
        d = self.path / "operations"
        return len(list(d.glob("op*.json"))) if d.exists() else 0

    def log(self, op: Operation) -> Operation:
        """不可变追加。先落日志，再落状态。"""
        self._op_seq += 1
        op_file = self.path / "operations" / f"op{self._op_seq:05d}.json"
        op_file.write_text(op.model_dump_json(indent=2), encoding="utf-8")
        self.save_state()
        return op

    def operations(self) -> list[Operation]:
        d = self.path / "operations"
        if not d.exists():
            return []
        return [
            Operation.model_validate(json.loads(p.read_text(encoding="utf-8")))
            for p in sorted(d.glob("op*.json"))
        ]

    def new_operation(self, **kwargs) -> Operation:
        return Operation(operation_id=f"op{self._op_seq + 1:05d}", **kwargs)

    # ---------- Version（Git 式，只存 diff） ----------

    def commit(self, note: str = "", since_version: str | None = None) -> Version:
        """把上一个版本之后的所有 Operation 打成一个版本节点。"""
        existing = self.versions()
        if since_version is None and existing:
            since_version = existing[-1].version_id
        ops = self.operations()
        if since_version:
            parent = self.get_version(since_version)
            done = set(parent.operation_ids)
            op_ids = [o.operation_id for o in ops if o.operation_id not in done]
        else:
            op_ids = [o.operation_id for o in ops]
        parent_id = existing[-1].version_id if existing else None
        v = Version(
            version_id=f"v{len(self.versions()) + 1}",
            parent=parent_id,
            operation_ids=op_ids,
            note=note,
        )
        (self.path / "versions" / f"{v.version_id}.json").write_text(
            v.model_dump_json(indent=2), encoding="utf-8"
        )
        return v

    def versions(self) -> list[Version]:
        d = self.path / "versions"
        if not d.exists():
            return []
        return [
            Version.model_validate(json.loads(p.read_text(encoding="utf-8")))
            for p in sorted(d.glob("v*.json"))
        ]

    def get_version(self, version_id: str) -> Version:
        return Version.model_validate(
            json.loads((self.path / "versions" / f"{version_id}.json").read_text(encoding="utf-8"))
        )

    # ---------- Semantic Undo ----------

    def revert(self, operation_id: str, who: str = "human", why: str = "") -> Operation | None:
        """语义化撤销：不是 Ctrl+Z，而是对指定 Operation 记录一条反向 Operation。
        before/after 互换，状态回到该操作前，历史不删除。
        """
        target = next((o for o in self.operations() if o.operation_id == operation_id), None)
        if target is None:
            return None
        from yroll.core.manifest import Actor

        self._apply_inverse(target)  # 状态真正回到 before（只记日志不还原 = 假撤销）

        inverse = self.new_operation(
            who=Actor(who),
            type=f"revert:{target.type}",
            target=target.target,
            time_range=target.time_range,
            region=target.region,
            parameters={**target.before, "revert_of": target.operation_id},
            before=target.after,
            after=target.before,
            why=why or f"撤销 {operation_id}",
        )
        return self.log(inverse)

    def redo(self, who: str = "human", why: str = "") -> Operation | None:
        """Redo：重做最近一次尚未被 redo 的撤销。
        状态真正回到 after（不是只记日志），并落一条 revert:redo:X 的 Operation。"""
        # 收集所有已被 redo 的原始 op_id
        redone_ids: set[str] = set()
        for o in self.operations():
            if o.type.startswith("revert:redo:"):
                rid = (o.parameters or {}).get("redo_of")
                if rid:
                    redone_ids.add(rid)

        # 找最近的 revert op（未被 redo 过）
        revert_op = None
        original = None
        for o in reversed(self.operations()):
            if not o.type.startswith("revert:"):
                continue
            if o.type.startswith("revert:redo:"):
                continue  # 跳过 redo 标记本身
            original_id = (o.parameters or {}).get("revert_of")
            if not original_id or original_id in redone_ids:
                continue
            original = next((x for x in self.operations()
                             if x.operation_id == original_id), None)
            if original is None:
                continue
            revert_op = o
            break
        if revert_op is None or original is None:
            return None

        self._apply_forward(original)  # 重新应用 X

        from yroll.core.manifest import Actor
        redo_op = self.new_operation(
            who=Actor(who),
            type=f"revert:redo:{original.type}",
            target=original.target,
            time_range=original.time_range,
            region=original.region,
            parameters={**original.after, "redo_of": original.operation_id},
            before=original.before,
            after=original.after,
            why=why or f"重做 {original.operation_id}",
        )
        return self.log(redo_op)

    def _apply_forward(self, op: Operation) -> None:
        """把 op.after 应用回工程状态（Redo 用）。"""
        from yroll.core.manifest import Clip, TimeRange

        p = self.project
        clip = p.clips.get(op.target)
        after = op.after or {}
        op_type = op.type

        if op_type == "volume" and clip:
            clip.volume = after.get("volume", clip.volume)
        elif op_type == "speed" and clip:
            clip.speed = after.get("speed", clip.speed)
            if "timeline_range" in after:
                clip.timeline_range = TimeRange(**after["timeline_range"])
        elif op_type == "trim" and clip:
            if "source_range" in after:
                clip.source_range = TimeRange(**after["source_range"])
            if "timeline_range" in after:
                clip.timeline_range = TimeRange(**after["timeline_range"])
        elif op_type == "move" and clip:
            if "timeline_range" in after:
                clip.timeline_range = TimeRange(**after["timeline_range"])
            # 跨轨联动 shift
            cross = (op.before or {}).get("cross_shifted", {})
            delta = (after["timeline_range"]["start"]
                     - op.before["timeline_range"]["start"])
            for rid, old_start in cross.items():
                rc = p.clips.get(rid)
                if rc:
                    rc.timeline_range = TimeRange(
                        start=old_start + delta,
                        end=rc.timeline_range.end - rc.timeline_range.start
                            + old_start + delta)
        elif op_type == "transform" and clip:
            clip.transform = dict(after.get("transform", clip.transform))
        elif op_type in ("adjust", "adjust_remove") and clip:
            clip.adjustments = list(after.get("adjustments", clip.adjustments))
        elif op_type == "remove_clip" and op.target not in p.clips:
            # Redo 删除：从工程和轨道移除
            p.clips.pop(op.target, None)
            for t in p.timeline.tracks:
                if op.target in t.clip_ids:
                    t.clip_ids.remove(op.target)
        elif op_type == "ripple_delete" and op.target not in p.clips:
            # Redo ripple：删除 + 后面的 shift + 跨轨 shift
            dur = (op.before["clip"]["timeline_range"]["end"]
                   - op.before["clip"]["timeline_range"]["start"])
            removed_start = op.before["clip"]["timeline_range"]["start"]
            shifted = op.before.get("shifted", {})
            cross = op.before.get("cross_shifted", {})
            for cid, old_start in shifted.items():
                c = p.clips.get(cid)
                if c:
                    c.timeline_range = TimeRange(
                        start=old_start - dur, end=c.timeline_range.end
                            - c.timeline_range.start + old_start - dur)
            for rid, old_start in cross.items():
                rc = p.clips.get(rid)
                if rc:
                    rc.timeline_range = TimeRange(
                        start=old_start - dur,
                        end=rc.timeline_range.end - rc.timeline_range.start
                            + old_start - dur)
            for t in p.timeline.tracks:
                if op.target in t.clip_ids:
                    t.clip_ids.remove(op.target)
        elif op_type == "add_clip" and op.target not in p.clips:
            restored = Clip.model_validate(op.after.get("clip", op.after))
            p.clips[restored.clip_id] = restored
            track = next((t for t in p.timeline.tracks
                          if t.track_id == restored.track_id), None)
            if track:
                track.clip_ids.append(restored.clip_id)
        elif op_type == "split" and op.target in p.clips:
            # Redo split：从单 clip 切成两半
            right_id = (op.after or {}).get("right_clip_id")
            if right_id:
                right = Clip.model_validate(op.after["clip"])
                # 左半保留（已经在 op.target），右半新建
                p.clips[right_id] = right
                track = next(t for t in p.timeline.tracks
                             if t.track_id == clip.track_id)
                if track and right_id not in track.clip_ids:
                    idx = track.clip_ids.index(op.target)
                    track.clip_ids.insert(idx + 1, right_id)
        elif op_type == "subtitle_edit" and clip:
            clip.context["text"] = after.get("text", clip.context.get("text"))
        elif op_type == "generate_subtitles":
            for cid in (op.after or {}).get("created", []):
                if cid in p.clips:
                    continue
                # 创建字幕 clip
                # 简化处理：实际数据由 generate_subtitles 完整记录
                pass
        self.save_state()

    def _apply_inverse(self, op: Operation) -> None:
        """把 op.before 应用回工程状态。支持主流程 op；不支持的类型只记日志。
        revert:X 的反操作 = 把 X 再改回去（即 Redo）。"""
        from yroll.core.manifest import Clip, TimeRange

        p = self.project
        clip = p.clips.get(op.target)
        before = op.before or {}
        # 支持双层 revert 嵌套：revert:redo:X 的 before 是 X.before
        op_type = op.type
        while op_type.startswith("revert:") and op_type[7:].startswith("redo:"):
            op_type = op_type[12:]  # 剥掉 "revert:redo:"
        if op_type.startswith("revert:"):
            op_type = op_type[7:]

        if op_type == "volume" and clip:
            clip.volume = before["volume"]
        elif op_type == "mute" and clip:
            if before.get("muted"):
                clip.context["muted"] = before["muted"]
            else:
                clip.context.pop("muted", None)
        elif op_type == "transform" and clip:
            clip.transform = dict(before.get("transform", {}))
        elif op_type == "speed" and clip:
            clip.speed = before["speed"]
            clip.timeline_range = TimeRange(**before["timeline_range"])
        elif op_type == "trim" and clip:
            clip.source_range = TimeRange(**before["source_range"])
            clip.timeline_range = TimeRange(**before["timeline_range"])
        elif op_type == "slip" and clip:
            # Slip only changes source_range; timeline unchanged.
            if "source_range" in before:
                clip.source_range = TimeRange(**before["source_range"])
        elif op_type == "roll" and clip:
            # roll records before.clip.timeline_range and before.neighbor.timeline_range.
            clip.timeline_range = TimeRange(**before["clip"]["timeline_range"])
            nb_id = (op.after or {}).get("neighbor_clip_id")
            if nb_id:
                nb = p.clips.get(nb_id)
                if nb and "neighbor" in before:
                    nb.timeline_range = TimeRange(
                        **before["neighbor"]["timeline_range"])
        elif op_type == "slide" and clip:
            clip.timeline_range = TimeRange(**before["clip"]["timeline_range"])
            nb_id = (op.after or {}).get("neighbor_clip_id")
            if nb_id and "left" in before:
                nb = p.clips.get(nb_id)
                if nb:
                    nb.timeline_range = TimeRange(
                        **before["left"]["timeline_range"])
        elif op_type == "move" and clip:
            clip.timeline_range = TimeRange(**before["timeline_range"])
            if before.get("track_id") and before["track_id"] != clip.track_id:
                tl = p.timeline
                cur = next((t for t in tl.tracks if op.target in t.clip_ids), None)
                dst = next((t for t in tl.tracks if t.track_id == before["track_id"]), None)
                if cur and dst:
                    cur.clip_ids.remove(op.target)
                    dst.clip_ids.append(op.target)
                    clip.track_id = before["track_id"]
            # 撤销跨轨联动 shift
            for rid, old_start in (before.get("cross_shifted") or {}).items():
                rc = p.clips.get(rid)
                if rc:
                    own_len = rc.timeline_range.end - rc.timeline_range.start
                    rc.timeline_range = TimeRange(
                        start=old_start, end=old_start + own_len)
        elif op_type in ("adjust", "adjust_remove") and clip:
            clip.adjustments = list(before.get("adjustments", []))
        elif op_type == "remove_clip" and op.target not in p.clips:
            # W-B: if the auto-cleanup removed the clip's original
            # track, recreate it before re-attaching the clip.
            if "removed_track" in before:
                from yroll.core.manifest import Track
                restored_track = Track.model_validate(before["removed_track"])
                if not any(t.track_id == restored_track.track_id
                           for t in p.timeline.tracks):
                    p.timeline.tracks.append(restored_track)
            # before 是完整 clip dump：恢复 clip 并挂回原轨道末尾
            restored = Clip.model_validate(before)
            p.clips[restored.clip_id] = restored
            track = next((t for t in p.timeline.tracks
                          if t.track_id == restored.track_id), None)
            if track and restored.clip_id not in track.clip_ids:
                track.clip_ids.append(restored.clip_id)
        elif op_type == "ripple_delete":
            # 撤销收拢删除：后面的 clip 移回原位，删除的 clip 恢复
            restored = Clip.model_validate(before["clip"])
            for cid, old_start in (before.get("shifted") or {}).items():
                c = p.clips.get(cid)
                if c:
                    own_len = c.timeline_range.end - c.timeline_range.start
                    c.timeline_range = TimeRange(
                        start=old_start, end=old_start + own_len)
            # 撤销跨轨联动 shift
            for rid, old_start in (before.get("cross_shifted") or {}).items():
                rc = p.clips.get(rid)
                if rc:
                    own_len = rc.timeline_range.end - rc.timeline_range.start
                    rc.timeline_range = TimeRange(
                        start=old_start, end=old_start + own_len)
            p.clips[restored.clip_id] = restored
            track = next((t for t in p.timeline.tracks
                          if t.track_id == restored.track_id), None)
            if track and restored.clip_id not in track.clip_ids:
                track.clip_ids.append(restored.clip_id)
        elif op_type == "silence_remove":
            # 撤销重建：删除新产生的 clip，原 clip 恢复完整 dump
            for nid in (op.after or {}).get("new_clips", []):
                p.clips.pop(nid, None)
                for t in p.timeline.tracks:
                    if nid in t.clip_ids:
                        t.clip_ids.remove(nid)
            restored = Clip.model_validate(before)
            p.clips[restored.clip_id] = restored
        elif op_type == "split":
            # 撤销切分：删除右半 clip，左半恢复原 dump
            right_id = (op.after or {}).get("right_clip_id")
            if right_id:
                p.clips.pop(right_id, None)
                for t in p.timeline.tracks:
                    if right_id in t.clip_ids:
                        t.clip_ids.remove(right_id)
            restored = Clip.model_validate(before)
            p.clips[restored.clip_id] = restored
        elif op_type == "report_problem":
            # 撤销问题登记：连问题带方案一起移除
            p.problems = [x for x in p.problems if x.problem_id != op.target]
            p.solutions = [x for x in p.solutions if x.problem_id != op.target]
        elif op_type == "add_clip":
            # 撤销新增：clip 从工程和轨道移除
            p.clips.pop(op.target, None)
            for t in p.timeline.tracks:
                if op.target in t.clip_ids:
                    t.clip_ids.remove(op.target)
        elif op_type == "generate_subtitles":
            # 撤销自动生成：删掉本次创建的全部字幕 clip
            for cid in (op.after or {}).get("created", []):
                p.clips.pop(cid, None)
                for t in p.timeline.tracks:
                    if cid in t.clip_ids:
                        t.clip_ids.remove(cid)
        elif op_type == "subtitle_edit" and clip:
            clip.context["text"] = before.get("text", "")
        elif op_type == "subtitle_style" and clip:
            clip.context["style"] = dict(before.get("style", {}))
        elif op_type == "voice_replace" and clip:
            # Atomic undo (P0-04D): 还原 muted 状态 + 移除 TTS clip/asset
            old_muted = before.get("muted")
            if old_muted:
                clip.context["muted"] = old_muted
            else:
                clip.context.pop("muted", None)
            aid = (op.after or {}).get("asset_id")
            new_cid = (op.after or {}).get("new_clip_id")
            # 优先用 new_clip_id 精确删除（避免误删其他同 asset 引用）
            if new_cid:
                p.clips.pop(new_cid, None)
                for t in p.timeline.tracks:
                    if new_cid in t.clip_ids:
                        t.clip_ids.remove(new_cid)
            elif aid:
                for cid in [c.clip_id for c in p.clips.values()
                            if c.asset_id == aid]:
                    p.clips.pop(cid, None)
                    for t in p.timeline.tracks:
                        if cid in t.clip_ids:
                            t.clip_ids.remove(cid)
            if aid:
                p.assets = [a for a in p.assets if a.asset_id != aid]
        elif op_type in ("move_selection", "delete_selection") and before:
            # P0-04B: atomic composite Selection op. Restore every touched clip.
            from yroll.core.manifest import TimeRange
            # GUI-03R4.1 P0-4: when a Selection-delete folds an
            # auto-track-cleanup into itself, the removed track ids
            # land in after.removed_tracks. The undo MUST recreate
            # those tracks before re-attaching their clips, else the
            # restored clip lands in p.clips but no track contains
            # it (a "ghost clip" — visible in /project but invisible
            # to the timeline renderer).
            from yroll.core.manifest import Track
            after = op.after or {}
            removed_tracks_data = after.get("removed_tracks_data") or {}
            for tid, tdump in removed_tracks_data.items():
                if not any(t.track_id == tid for t in p.timeline.tracks):
                    p.timeline.tracks.append(Track.model_validate(tdump))
            for cid, pre in before.items():
                c = p.clips.get(cid)
                if c is None:
                    # Was deleted by delete_selection; restore from dump
                    if "timeline_range" in pre and "source_range" in pre:
                        from yroll.core.manifest import Clip
                        p.clips[cid] = Clip.model_validate(pre)
                        # Re-attach to original track (now restored above)
                        orig_tid = pre.get("track_id", "v1")
                        track = next((t for t in p.timeline.tracks
                                      if t.track_id == orig_tid), None)
                        if track and cid not in track.clip_ids:
                            track.clip_ids.append(cid)
                    continue
                if "timeline_range" in pre:
                    c.timeline_range = TimeRange(**pre["timeline_range"])
                if "track_id" in pre and pre["track_id"] != c.track_id:
                    cur = next((t for t in p.timeline.tracks
                                if cid in t.clip_ids), None)
                    dst = next((t for t in p.timeline.tracks
                                if t.track_id == pre["track_id"]), None)
                    if cur and dst:
                        cur.clip_ids.remove(cid)
                        dst.clip_ids.append(cid)
                        c.track_id = pre["track_id"]
        elif op_type in ("track_mute", "track_lock"):
            track = next((t for t in p.timeline.tracks
                          if t.track_id == op.target), None)
            if track:
                if "muted" in before:
                    track.muted = bool(before.get("muted"))
                if "locked" in before:
                    track.locked = bool(before.get("locked"))
        self.save_state()
