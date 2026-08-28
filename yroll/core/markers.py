"""YROLL Markers (P1 §38): named time-point markers on the timeline.

A marker is a user-placed annotation at a specific timeline frame.
Used for: scene beats, review notes, sync points, Snap targets.

Markers are project-scoped (not clip-scoped): they live at the timeline
level so they survive clip deletions/moves. Persisted as
project.extensions.markers (list of dicts).
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class Marker:
    marker_id: str
    timeline_frame: int
    label: str
    color: str = "#ffd400"  # default yellow (CapCut-style)
    note: str = ""
    created_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict:
        return {
            "marker_id": self.marker_id,
            "timeline_frame": self.timeline_frame,
            "label": self.label,
            "color": self.color,
            "note": self.note,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Marker":
        return cls(
            marker_id=d["marker_id"],
            timeline_frame=int(d["timeline_frame"]),
            label=d.get("label", ""),
            color=d.get("color", "#ffd400"),
            note=d.get("note", ""),
            created_at=datetime.fromisoformat(d["created_at"])
                if d.get("created_at") else datetime.now(),
        )


_MARKERS_KEY = "markers"


def list_markers(project) -> list[Marker]:
    """Return all markers for a project, sorted by frame."""
    raw = (project.extensions or {}).get(_MARKERS_KEY, [])
    return sorted((Marker.from_dict(m) for m in raw),
                  key=lambda m: m.timeline_frame)


def add_marker(project, timeline_frame: int, label: str,
               color: str = "#ffd400", note: str = "") -> Marker:
    """Add a marker. Returns the new Marker."""
    m = Marker(marker_id=f"mk{uuid.uuid4().hex[:6]}",
               timeline_frame=int(timeline_frame),
               label=label, color=color, note=note)
    store = project.extensions.setdefault(_MARKERS_KEY, [])
    store.append(m.to_dict())
    return m


def remove_marker(project, marker_id: str) -> bool:
    """Remove a marker by id. Returns True if found and removed."""
    store = project.extensions.get(_MARKERS_KEY, [])
    for i, m in enumerate(store):
        if m.get("marker_id") == marker_id:
            store.pop(i)
            return True
    return False


def update_marker(project, marker_id: str,
                  label: Optional[str] = None,
                  color: Optional[str] = None,
                  note: Optional[str] = None) -> Optional[Marker]:
    """Patch a marker; None if not found."""
    store = project.extensions.get(_MARKERS_KEY, [])
    for m in store:
        if m.get("marker_id") == marker_id:
            if label is not None:
                m["label"] = label
            if color is not None:
                m["color"] = color
            if note is not None:
                m["note"] = note
            return Marker.from_dict(m)
    return None


def frames_near_markers(project, fps, radius_frames: int = 5) -> list[int]:
    """Return marker timeline_frames — convenient for SnapEngine."""
    return [m.timeline_frame for m in list_markers(project)]
