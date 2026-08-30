"""YROLL Markers (P1 §38): named time-point markers on the timeline.

GUI-03E-2A: markers are Timeline-local. Each Timeline owns its own
list of markers on `timeline.markers` (list of dicts). Every marker
dict carries `timeline_id` so ownership is explicit.

`list_markers` / `add_marker` / `remove_marker` / `update_marker`
take a Timeline (not a Project). For legacy/internal callers that
still pass a Project, the module exposes `legacy_project_markers_*`
helpers that route through `project.active_timeline` and emit a
telemetry warning. New code MUST pass a Timeline.
"""
from __future__ import annotations

import uuid
import warnings
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
        # timeline_id is stamped by `_to_dict_with_timeline` so the
        # dataclass doesn't have to know its owner.
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


def _to_dict_with_timeline(m: "Marker", timeline_id: str) -> dict:
    d = m.to_dict()
    d["timeline_id"] = timeline_id
    return d


# ---------- canonical Timeline-local API ----------

def list_markers(timeline) -> list[Marker]:
    """Return all markers on a Timeline, sorted by frame."""
    raw = getattr(timeline, "markers", None) or []
    return sorted((Marker.from_dict(m) for m in raw),
                  key=lambda m: m.timeline_frame)


def add_marker(timeline, timeline_frame: int, label: str,
               color: str = "#ffd400", note: str = "") -> Marker:
    """Add a marker to a Timeline. Returns the new Marker."""
    m = Marker(marker_id=f"mk{uuid.uuid4().hex[:6]}",
               timeline_frame=int(timeline_frame),
               label=label, color=color, note=note)
    if not hasattr(timeline, "markers") or timeline.markers is None:
        timeline.markers = []
    timeline.markers.append(_to_dict_with_timeline(m, timeline.timeline_id))
    return m


def remove_marker(timeline, marker_id: str) -> bool:
    """Remove a marker by id. Returns True if found and removed."""
    store = getattr(timeline, "markers", None) or []
    for i, m in enumerate(store):
        if m.get("marker_id") == marker_id:
            store.pop(i)
            return True
    return False


def update_marker(timeline, marker_id: str,
                  label: Optional[str] = None,
                  color: Optional[str] = None,
                  note: Optional[str] = None) -> Optional[Marker]:
    """Patch a marker; None if not found."""
    store = getattr(timeline, "markers", None) or []
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


def frames_near_markers(timeline, fps, radius_frames: int = 5) -> list[int]:
    """Return marker timeline_frames — convenient for SnapEngine."""
    return [m.timeline_frame for m in list_markers(timeline)]


# ---------- legacy Project-extensions shim ----------
# Pre-03E-2A callers passed a Project; we route through the active
# Timeline and emit a telemetry warning. New code MUST pass a Timeline.

def legacy_list_markers(project) -> list[Marker]:
    warnings.warn(
        "markers.legacy_list_markers is deprecated; "
        "pass project.active_timeline (or a specific Timeline) "
        "to list_markers instead.",
        DeprecationWarning, stacklevel=2,
    )
    return list_markers(project.active_timeline)


def legacy_add_marker(project, timeline_frame, label, color="#ffd400", note=""):
    warnings.warn(
        "markers.legacy_add_marker is deprecated; "
        "pass a Timeline to add_marker instead.",
        DeprecationWarning, stacklevel=2,
    )
    return add_marker(project.active_timeline, timeline_frame, label,
                       color=color, note=note)


def legacy_remove_marker(project, marker_id: str) -> bool:
    warnings.warn(
        "markers.legacy_remove_marker is deprecated; "
        "pass a Timeline to remove_marker instead.",
        DeprecationWarning, stacklevel=2,
    )
    return remove_marker(project.active_timeline, marker_id)


def legacy_update_marker(project, marker_id: str,
                          label=None, color=None, note=None):
    warnings.warn(
        "markers.legacy_update_marker is deprecated; "
        "pass a Timeline to update_marker instead.",
        DeprecationWarning, stacklevel=2,
    )
    return update_marker(project.active_timeline, marker_id,
                          label=label, color=color, note=note)


def legacy_frames_near_markers(project, fps, radius_frames: int = 5):
    warnings.warn(
        "markers.legacy_frames_near_markers is deprecated; "
        "pass a Timeline to frames_near_markers instead.",
        DeprecationWarning, stacklevel=2,
    )
    return frames_near_markers(project.active_timeline, fps,
                                radius_frames=radius_frames)