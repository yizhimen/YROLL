"""YROLL Story / Beat Model (v0.2 §13, §39 P2):

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

Kinds (extensible, default 3-act structure):
  setup / inciting_incident / rising_action / midpoint /
  climax / falling_action / resolution / denouement / custom
"""
from __future__ import annotations

import uuid
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
            start_frame=int(d.get("start_frame", 0)),
            end_frame=int(d.get("end_frame", 0)),
            intent=d.get("intent", ""),
            color=d.get("color", "#a78bfa"),
            note=d.get("note", ""),
            created_at=datetime.fromisoformat(d["created_at"])
                if d.get("created_at") else datetime.now(),
        )


_BEATS_KEY = "story_beats"


def list_beats(project) -> list[StoryBeat]:
    raw = (project.extensions or {}).get(_BEATS_KEY, [])
    return sorted((StoryBeat.from_dict(b) for b in raw),
                  key=lambda b: b.start_frame)


def add_beat(project, label: str, kind: str,
             start_frame: int, end_frame: int,
             intent: str = "", color: str = "#a78bfa",
             note: str = "") -> StoryBeat:
    if end_frame < start_frame:
        raise ValueError(f"end_frame ({end_frame}) < start_frame ({start_frame})")
    if kind not in STANDARD_BEAT_KINDS and kind != "custom":
        # Allow any kind string; warn but don't reject (extensibility).
        pass
    b = StoryBeat(
        beat_id=f"b{uuid.uuid4().hex[:6]}",
        label=label, kind=kind,
        start_frame=int(start_frame), end_frame=int(end_frame),
        intent=intent, color=color, note=note,
    )
    store = project.extensions.setdefault(_BEATS_KEY, [])
    store.append(b.to_dict())
    return b


def remove_beat(project, beat_id: str) -> bool:
    store = project.extensions.get(_BEATS_KEY, [])
    for i, b in enumerate(store):
        if b.get("beat_id") == beat_id:
            store.pop(i)
            return True
    return False


def beat_at_frame(project, frame: int) -> Optional[StoryBeat]:
    """Return the beat that contains this frame, if any."""
    for b in list_beats(project):
        if b.start_frame <= frame < b.end_frame:
            return b
    return None


def beats_overlapping(project, start_frame: int, end_frame: int
                       ) -> list[StoryBeat]:
    """Beats that overlap with [start, end)."""
    out: list[StoryBeat] = []
    for b in list_beats(project):
        if b.end_frame <= start_frame or b.start_frame >= end_frame:
            continue
        out.append(b)
    return out


def suggest_beat_boundaries(project, fps) -> list[StoryBeat]:
    """Heuristic: a project's beats can be inferred from clip density
    changes (e.g. silence gaps, long cuts). Returns suggested beats
    without committing them. Caller decides whether to add.

    Current heuristic: find gaps > 2 seconds between consecutive clips
    on the main video track and propose beats around them.
    """
    from yroll.core.timebase import FrameTime
    from yroll.core.manifest import TrackKind

    tracks = [t for t in project.timeline.tracks if t.kind == TrackKind.VIDEO]
    if not tracks or not tracks[0].clip_ids:
        return []

    clip_starts_ends: list[tuple[int, int]] = []
    for cid in tracks[0].clip_ids:
        c = project.clips.get(cid)
        if c is None:
            continue
        s = FrameTime.from_seconds(c.timeline_range.start, fps).frame
        e = FrameTime.from_seconds(c.timeline_range.end, fps).frame
        clip_starts_ends.append((s, e))
    clip_starts_ends.sort()

    suggestions: list[StoryBeat] = []
    gap_threshold_frames = int(fps.as_float() * 2)  # 2 seconds
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
