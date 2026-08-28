"""Semantic Link：视频不是轨道集合，而是语义关系网络（蓝图 §2.8）。

两级能力：
1. infer_relationships：按时间重叠自动推断 clip 间关系（确定性代码，离线可用；
   "AI 负责建立理解，普通系统负责执行已确定的关系"——V0 先做规则版，
   后续由 AI Understanding 写入更精确的关系，都落在同一个 Relationship Graph）
2. impact_preview：修改前告诉用户"这个操作会影响谁"——
   强关联自动同步 / 中关联提示 / 弱关联不动 / 独立绝不动
"""

from __future__ import annotations

import uuid

from yroll.core.manifest import (
    Project,
    Relationship,
    RelationStrength,
    TimeRange,
    TrackKind,
)


def _overlap(a: TimeRange, b: TimeRange) -> float:
    """时间重叠长度（秒）。"""
    return max(0.0, min(a.end, b.end) - max(a.start, b.start))


def _overlap_ratio(inner: TimeRange, outer: TimeRange) -> float:
    """inner 被 outer 覆盖的比例。"""
    length = inner.end - inner.start
    return _overlap(inner, outer) / length if length > 0 else 0.0


def infer_relationships(project: Project) -> list[Relationship]:
    """按时间重叠推断关系（幂等：先清掉自动推断的旧关系，保留人工/AI 标记的）。

    规则（V0 启发式，够用即可）：
    - text clip 与 video clip 重叠 >50% → caption_of，强关联（字幕随视频走）
    - audio clip 只覆盖一个 video clip → voice_of，强关联（人声随视频走）
    - audio clip 横跨多个 video clip → bgm_of，独立（BGM 不随单 clip 裁剪移动）
    """
    video_clips = [
        project.clips[cid]
        for t in project.timeline.tracks if t.kind == TrackKind.VIDEO
        for cid in t.clip_ids if cid in project.clips
    ]
    relations: list[Relationship] = []

    for t in project.timeline.tracks:
        if t.kind == TrackKind.VIDEO:
            continue
        for cid in t.clip_ids:
            clip = project.clips.get(cid)
            if clip is None:
                continue
            covering = [v for v in video_clips
                        if _overlap_ratio(v.timeline_range, clip.timeline_range) > 0.5
                        or _overlap_ratio(clip.timeline_range, v.timeline_range) > 0.5]
            if not covering:
                continue

            if t.kind == TrackKind.TEXT:
                for v in covering:
                    conf = round(_overlap_ratio(clip.timeline_range, v.timeline_range), 2)
                    relations.append(Relationship(
                        relation_id=f"r{uuid.uuid4().hex[:6]}",
                        source=clip.clip_id, target=v.clip_id,
                        relation=RelationStrength.STRONG,
                        kind="caption_of", confidence=conf,
                        reason="字幕与该视频时间段重叠（自动推断）",
                    ))
            elif t.kind == TrackKind.AUDIO:
                if len(covering) == 1:
                    relations.append(Relationship(
                        relation_id=f"r{uuid.uuid4().hex[:6]}",
                        source=clip.clip_id, target=covering[0].clip_id,
                        relation=RelationStrength.STRONG,
                        kind="voice_of",
                        confidence=0.8,
                        reason="音频只覆盖该视频片段，视为人声/同期声（自动推断）",
                    ))
                else:
                    for v in covering:
                        relations.append(Relationship(
                            relation_id=f"r{uuid.uuid4().hex[:6]}",
                            source=clip.clip_id, target=v.clip_id,
                            relation=RelationStrength.INDEPENDENT,
                            kind="bgm_of", confidence=0.7,
                            reason="音频横跨多个片段，视为 BGM（不随单片段变动）",
                        ))

    # 幂等：移除旧的自动推断关系，保留人工/AI 显式建立的
    project.relationships = [r for r in project.relationships
                             if "自动推断" not in r.reason]
    project.relationships.extend(relations)
    return relations


def impact_preview(project: Project, clip_id: str, op: str) -> dict:
    """Impact Preview：如果对这个 clip 做 op，会发生什么（蓝图 §43.2）。

    返回分级影响清单，供 GUI/AI 在执行前展示：
        {"will_sync": [...], "will_prompt": [...], "untouched": [...]}
    """
    related = [r for r in project.relationships
               if r.source == clip_id or r.target == clip_id]
    will_sync, will_prompt, untouched = [], [], []
    for r in related:
        other_id = r.target if r.source == clip_id else r.source
        other = project.clips.get(other_id)
        desc = {
            "clip_id": other_id,
            "kind": r.kind,
            "reason": r.reason,
            "text": (other.context.get("text") if other else None) or other_id,
        }
        if r.relation == RelationStrength.STRONG:
            will_sync.append(desc)
        elif r.relation == RelationStrength.MEDIUM:
            will_prompt.append(desc)
        else:  # WEAK / INDEPENDENT
            untouched.append(desc)

    return {
        "op": op,
        "target": clip_id,
        "will_sync": will_sync,
        "will_prompt": will_prompt,
        "untouched": untouched,
    }


def preview_mutation(project: Project, selection: 'Selection',
                     op: str, params: dict | None = None) -> dict:
    """v0.2 §14: Mutation Preview — describe what an operation WOULD do,
    without committing it. Selection-aware, Frame-aware.

    Returns:
        {
          "op": ..., "params": {...},
          "primary": [{clip_id, from, to}],
          "secondary": [{clip_id, effect, reason}],
          "untouched": [{clip_id, relation}],
          "summary": {n_primary, n_secondary, n_untouched},
        }
    """
    from yroll.core.selection import Selection as _Sel
    if not isinstance(selection, _Sel):
        selection = _Sel.from_clip_or_id(selection)

    target_ids: list[str] = list(selection.clip_ids)
    if not target_ids and selection.track_ids:
        for t in project.timeline.tracks:
            if t.track_id in selection.track_ids:
                target_ids.extend([c for c in t.clip_ids if c in project.clips])

    primary: list[dict] = []
    for cid in target_ids:
        c = project.clips.get(cid)
        if c is None:
            continue
        to_state: dict = {"timeline_range": c.timeline_range.model_dump()}
        if op == "move" and params:
            delta = float(params.get("delta_seconds", 0.0))
            to_state["timeline_range"] = {
                "start": c.timeline_range.start + delta,
                "end": c.timeline_range.end + delta,
            }
        elif op == "delete" and params:
            to_state = {"removed": True}
        primary.append({
            "clip_id": cid,
            "track_id": c.track_id,
            "from": {"timeline_range": c.timeline_range.model_dump()},
            "to": to_state,
        })

    secondary: list[dict] = []
    untouched: list[dict] = []
    if op in ("delete", "ripple_delete"):
        related_ids: set[str] = set()
        for cid in target_ids:
            for r in project.relationships:
                if r.relation != RelationStrength.STRONG:
                    continue
                if r.source == cid:
                    related_ids.add(r.target)
                elif r.target == cid:
                    related_ids.add(r.source)
        for rid in related_ids:
            rc = project.clips.get(rid)
            if rc is None:
                continue
            secondary.append({
                "clip_id": rid, "track_id": rc.track_id,
                "effect": "strong_link_propagate",
                "reason": "ripple from primary delete",
            })
        for cid in target_ids:
            for r in project.relationships:
                if r.relation in (RelationStrength.STRONG, RelationStrength.MEDIUM):
                    continue
                other_id = r.target if r.source == cid else r.source
                if other_id and other_id in project.clips:
                    untouched.append({"clip_id": other_id,
                                     "relation": r.relation.value})

    return {
        "op": op,
        "params": params or {},
        "primary": primary,
        "secondary": secondary,
        "untouched": untouched,
        "summary": {
            "n_primary": len(primary),
            "n_secondary": len(secondary),
            "n_untouched": len(untouched),
        },
    }
