"""YROLL Story / Beat Model (v0.2 §13, §39 P2):

GUI-03E-2A: beats are Timeline-local. Each Timeline owns its own
list of beats on `timeline.beats` (list of dicts). Every beat dict
carries `timeline_id` so ownership is explicit.

Project-level narrative structure annotations. Beats are higher-level
than markers: they describe story arc sections, not single frames.

Like markers, beats survive clip deletions. They're used for:
- High-level navigation (jump to "climax")
- AI storytelling (Claude proposes: "make this a 3-act structure")
- Auto-edit suggestions (split long flat sections into beats)
- Frame-level snap targets via StoryBeat → SnapKind

Schema:
  StoryBeat {
    beat_id, label, kind, start_frame, end_frame,
    intent, color, note
  }

Kinds (default 3-act structure):
  setup / inciting_incident / rising_action / midpoint /
  climax / falling_action / resolution / denouement / custom
"""
from __future__ import annotations

import uuid
import warnings
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


# Standard 3-act + midpoint beat kinds.
STANDARD_BEAT_KINDS = (
    "setup", "inciting_incident", "rising_action", "midpoint",
    "climax", "falling_action", "resolution", "denouement",
)


@dataclass
class StoryBeat:
    beat_id: str
    label: str
    kind: str
    start_frame: int
    end_frame: int                # half-open
    intent: str = ""              # what this beat is trying to do (story-wise)
    color: str = "#a78bfa"        # default purple (vs marker's yellow)
    note: str = ""
    created_at: datetime = field(default_factory=datetime.now)

    def duration_frames(self) -> int:
        return self.end_frame - self.start_frame

    def to_dict(self) -> dict:
        return {
            "beat_id": self.beat_id,
            "label": self.label,
            "kind": self.kind,
            "start_frame": self.start_frame,
            "end_frame": self.end_frame,
            "intent": self.intent,
            "color": self.color,
            "note": self.note,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "StoryBeat":
        return cls(
            beat_id=d["beat_id"],
            label=d.get("label", ""),
            kind=d.get("kind", "custom"),
            start_frame=int(d["start_frame"]),
            end_frame=int(d["end_frame"]),
            intent=d.get("intent", ""),
            color=d.get("color", "#a78bfa"),
            note=d.get("note", ""),
            created_at=datetime.fromisoformat(d["created_at"])
                if d.get("created_at") else datetime.now(),
        )


def _to_dict_with_timeline(b: "StoryBeat", timeline_id: str) -> dict:
    d = b.to_dict()
    d["timeline_id"] = timeline_id
    return d


# ---------- canonical Timeline-local API ----------

def list_beats(timeline) -> list[StoryBeat]:
    raw = getattr(timeline, "beats", None) or []
    return sorted((StoryBeat.from_dict(b) for b in raw),
                  key=lambda b: b.start_frame)


def add_beat(timeline, label: str, kind: str,
             start_frame: int, end_frame: int,
             intent: str = "", color: str = "#a78bfa",
             note: str = "") -> StoryBeat:
    if end_frame < start_frame:
        raise ValueError(f"end_frame ({end_frame}) < start_frame ({start_frame})")
    if kind not in STANDARD_BEAT_KINDS and kind != "custom":
        pass
    b = StoryBeat(
        beat_id=f"b{uuid.uuid4().hex[:6]}",
        label=label, kind=kind,
        start_frame=int(start_frame), end_frame=int(end_frame),
        intent=intent, color=color, note=note,
    )
    if not hasattr(timeline, "beats") or timeline.beats is None:
        timeline.beats = []
    timeline.beats.append(_to_dict_with_timeline(b, timeline.timeline_id))
    return b


def remove_beat(timeline, beat_id: str) -> bool:
    store = getattr(timeline, "beats", None) or []
    for i, b in enumerate(store):
        if b.get("beat_id") == beat_id:
            store.pop(i)
            return True
    return False


def beat_at_frame(timeline, frame: int) -> Optional[StoryBeat]:
    for b in list_beats(timeline):
        if b.start_frame <= frame < b.end_frame:
            return b
    return None


def beats_overlapping(timeline, start_frame: int, end_frame: int
                       ) -> list[StoryBeat]:
    out: list[StoryBeat] = []
    for b in list_beats(timeline):
        if b.end_frame <= start_frame or b.start_frame >= end_frame:
            continue
        out.append(b)
    return out


def suggest_beat_boundaries(timeline, fps, clips: dict | None = None) -> list[StoryBeat]:
    from yroll.core.timebase import FrameTime
    from yroll.core.manifest import TrackKind

    tracks = [t for t in timeline.tracks if t.kind == TrackKind.VIDEO]
    if not tracks or not tracks[0].clip_ids:
        return []
    if clips is None:
        return []

    clip_starts_ends: list[tuple[int, int]] = []
    for cid in tracks[0].clip_ids:
        c = clips.get(cid)
        if c is None:
            continue
        s = FrameTime.from_seconds(c.timeline_range.start, fps).frame
        e = FrameTime.from_seconds(c.timeline_range.end, fps).frame
        clip_starts_ends.append((s, e))
    clip_starts_ends.sort()

    suggestions: list[StoryBeat] = []
    gap_threshold_frames = int(fps.as_float() * 2)
    for i in range(1, len(clip_starts_ends)):
        prev_end = clip_starts_ends[i - 1][1]
        this_start = clip_starts_ends[i][0]
        if this_start - prev_end >= gap_threshold_frames:
            suggestions.append(StoryBeat(
                beat_id=f"suggest-{uuid.uuid4().hex[:6]}",
                label=f"gap at frame {prev_end}",
                kind="custom",
                start_frame=prev_end,
                end_frame=this_start,
                intent="detected gap; consider pacing or insert",
                color="#fbbf24",
            ))
    return suggestions


# ---------- legacy Project-extensions shim ----------
# Pre-03E-2A callers passed a Project; we route through the active
# Timeline and emit a telemetry warning. New code MUST pass a Timeline.

def legacy_list_beats(project) -> list[StoryBeat]:
    warnings.warn(
        "story.legacy_list_beats is deprecated; "
        "pass project.active_timeline to list_beats instead.",
        DeprecationWarning, stacklevel=2,
    )
    return list_beats(project.active_timeline)


def legacy_add_beat(project, label, kind, start_frame, end_frame,
                     intent="", color="#a78bfa", note=""):
    warnings.warn(
        "story.legacy_add_beat is deprecated; "
        "pass a Timeline to add_beat instead.",
        DeprecationWarning, stacklevel=2,
    )
    return add_beat(project.active_timeline, label, kind,
                     start_frame, end_frame, intent=intent,
                     color=color, note=note)


def legacy_remove_beat(project, beat_id: str) -> bool:
    warnings.warn(
        "story.legacy_remove_beat is deprecated; "
        "pass a Timeline to remove_beat instead.",
        DeprecationWarning, stacklevel=2,
    )
    return remove_beat(project.active_timeline, beat_id)


def legacy_beats_overlapping(project, start_frame: int, end_frame: int):
    warnings.warn(
        "story.legacy_beats_overlapping is deprecated; "
        "pass a Timeline to beats_overlapping instead.",
        DeprecationWarning, stacklevel=2,
    )
    return beats_overlapping(project.active_timeline, start_frame, end_frame)


def legacy_beat_at_frame(project, frame: int):
    warnings.warn(
        "story.legacy_beat_at_frame is deprecated; "
        "pass a Timeline to beat_at_frame instead.",
        DeprecationWarning, stacklevel=2,
    )
    return beat_at_frame(project.active_timeline, frame)


def legacy_suggest_beat_boundaries(project, fps):
    warnings.warn(
        "story.legacy_suggest_beat_boundaries is deprecated; "
        "pass a Timeline to suggest_beat_boundaries instead.",
        DeprecationWarning, stacklevel=2,
    )
    return suggest_beat_boundaries(project.active_timeline, fps,
                                      clips=project.clips)