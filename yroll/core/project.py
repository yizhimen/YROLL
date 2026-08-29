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

from yroll.core.manifest import Operation, Project, Version

LAYOUT = ("operations", "versions", "media", "cache", "generated")


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
        project = Project(
            project_id=uuid.uuid4().hex[:12], name=name, intent=intent or {}
        )
        # 默认轨道结构（对齐剪映/CapCut：V1 主轨 + V2/V3 PiP + A1/A2/A3 + T1/T2）
        from yroll.core.manifest import Track, TrackKind
        project.timeline.tracks = [
            Track(track_id="v1", kind=TrackKind.VIDEO),
            Track(track_id="v2", kind=TrackKind.VIDEO),  # PiP 画中画
            Track(track_id="v3", kind=TrackKind.VIDEO),  # 叠加/特效
            Track(track_id="a1", kind=TrackKind.AUDIO),  # 主音（视频自带）
            Track(track_id="a2", kind=TrackKind.AUDIO),  # 旁白/人声
            Track(track_id="a3", kind=TrackKind.AUDIO),  # BGM/音效
            Track(track_id="t1", kind=TrackKind.TEXT),   # 主字幕
            Track(track_id="t2", kind=TrackKind.TEXT),   # 标题/特效字幕
        ]
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
        project = Project.model_validate(raw)
        # Ensure the flat fields match Sequence (denormalized sync).
        project.sequence.sync_to_project(project)
        return cls(path, project)

    def save_state(self) -> None:
        # GUI-02: sync canonical Sequence → flat fields on save so
        # legacy v0.1 readers still see fps_num/fps_den correctly.
        self.project.sequence.sync_to_project(self.project)
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
            for cid, pre in before.items():
                c = p.clips.get(cid)
                if c is None:
                    # Was deleted by delete_selection; restore from dump
                    if "timeline_range" in pre and "source_range" in pre:
                        from yroll.core.manifest import Clip
                        p.clips[cid] = Clip.model_validate(pre)
                        # Re-attach to original track
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
