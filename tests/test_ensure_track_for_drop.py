"""GUI-03R3-W-B.6: ensure_track_for_drop semantics.

Pins the contract for the new track-resolution API:

  - no insert_after_track_id + tl_start/tl_end given: allocator finds
    or creates a compatible track of the right kind.
  - insert_after_track_id given: create a NEW track of the right
    kind; existing tracks keep their ids (lowest unused wins).
  - prefer_kind: optional kind hint (must be in the asset type's
    allowed kinds, else asset type drives).
  - Distinguishes explicit target vs automatic allocation:
    explicit target + overlap → reject (Core's add_clip path);
    no explicit target → allocator picks/creates.
  - Unknown asset type → raises CommandError.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from yroll.core.commands import CommandError, CommandLayer
from yroll.core.manifest import Actor, TrackKind
from yroll.core.models import Asset, AssetIdentity, AssetType
from yroll.core.project import ProjectCore
from yroll.core.timebase import Rational


def _fresh_core(tmp_path: Path, with_assets: bool = True) -> ProjectCore:
    core = ProjectCore.create(tmp_path, "ensure-track-test")
    if with_assets:
        for atype, aid in [
            (AssetType.VIDEO, "a_vid"),
            (AssetType.IMAGE, "a_img"),
            (AssetType.AUDIO, "a_aud"),
            (AssetType.SUBTITLE, "a_sub"),
        ]:
            a = Asset(
                asset_id=aid, type=atype, path=f"{aid}.bin",
                identity=AssetIdentity(
                    md5=aid.encode().hex().ljust(32, "0")[:32],
                    size_bytes=1,
                    duration_sec=10.0 if atype != AssetType.IMAGE else None,
                ),
            )
            if atype != AssetType.IMAGE:
                a.source_fps = Rational(30, 1)
                a.source_is_cfr = True
            core.project.assets.append(a)
    core.save_state()
    return core


# ---------- 1. drop image on empty Timeline → creates v1 ----------

def test_drop_image_on_empty_creates_v1(tmp_path):
    core = _fresh_core(tmp_path)
    layer = CommandLayer(core, who=Actor.HUMAN)
    t = layer.ensure_track_for_drop("image")
    assert t.track_id == "v1"
    assert t.kind == TrackKind.VIDEO
    # VIDEO tracks can host images (asset-type → allowed kinds).


# ---------- 2. drop audio on empty Timeline → creates a1 ----------

def test_drop_audio_on_empty_creates_a1(tmp_path):
    core = _fresh_core(tmp_path)
    layer = CommandLayer(core, who=Actor.HUMAN)
    t = layer.ensure_track_for_drop("audio")
    assert t.track_id == "a1"
    assert t.kind == TrackKind.AUDIO


# ---------- 3. drop subtitle on empty Timeline → creates t1 ----------

def test_drop_subtitle_on_empty_creates_t1(tmp_path):
    core = _fresh_core(tmp_path)
    layer = CommandLayer(core, who=Actor.HUMAN)
    t = layer.ensure_track_for_drop("subtitle")
    assert t.track_id == "t1"
    # subtitle → allowed kinds = {subtitle, text}; the allocator
    # picks one (set ordering may vary). Both are valid — semantic
    # equivalence is documented in ASSET_TYPE_TO_TRACK_KINDS.
    assert t.kind in (TrackKind.SUBTITLE, TrackKind.TEXT)


# ---------- 4. explicit insert_after creates a new track of the right kind ----------

def test_insert_after_creates_new_track(tmp_path):
    core = _fresh_core(tmp_path)
    layer = CommandLayer(core, who=Actor.HUMAN)
    layer.add_track(TrackKind.VIDEO, "v1")
    # Anchor exists; create a new video track.
    t = layer.ensure_track_for_drop("image", insert_after_track_id="v1")
    assert t.track_id == "v2"
    assert t.kind == TrackKind.VIDEO
    # v1 keeps its id (no renumber).
    assert any(x.track_id == "v1" for x in core.project.timeline.tracks)


# ---------- 5. prefer_kind honored if in allowed kinds ----------

def test_prefer_kind_honored(tmp_path):
    core = _fresh_core(tmp_path)
    layer = CommandLayer(core, who=Actor.HUMAN)
    # text asset type's allowed kinds include both subtitle and text.
    # prefer_kind=text → creates a text track, not subtitle.
    t = layer.ensure_track_for_drop("text", prefer_kind=TrackKind.TEXT)
    assert t.kind == TrackKind.TEXT


# ---------- 6. prefer_kind ignored if NOT in allowed kinds ----------

def test_prefer_kind_ignored_when_disallowed(tmp_path):
    core = _fresh_core(tmp_path)
    layer = CommandLayer(core, who=Actor.HUMAN)
    # audio asset type's allowed kinds = {audio}. prefer_kind=video
    # is NOT in that set; asset type drives (still audio).
    t = layer.ensure_track_for_drop(
        "audio", prefer_kind=TrackKind.VIDEO,
    )
    assert t.kind == TrackKind.AUDIO


# ---------- 7. unknown asset type raises ----------

def test_unknown_asset_type_raises(tmp_path):
    core = _fresh_core(tmp_path, with_assets=False)
    layer = CommandLayer(core, who=Actor.HUMAN)
    with pytest.raises(CommandError, match=r"not a Timeline media"):
        layer.ensure_track_for_drop("document")


# ---------- 8. unknown anchor in insert_after raises ----------

def test_unknown_anchor_raises(tmp_path):
    core = _fresh_core(tmp_path)
    layer = CommandLayer(core, who=Actor.HUMAN)
    with pytest.raises(CommandError, match=r"anchor track .* not found"):
        layer.ensure_track_for_drop("image", insert_after_track_id="phantom")


# ---------- 9. ensure is idempotent for the same intent ----------

def test_insert_after_is_idempotent_within_session(tmp_path):
    """The allocator's `add_track` is already idempotent (same id +
    same kind → return existing). Insert-after-tracks are NEW track
    creations, so calling twice with the same anchor creates two new
    tracks (the anchor itself is unchanged, but each call appends a
    new one)."""
    core = _fresh_core(tmp_path)
    layer = CommandLayer(core, who=Actor.HUMAN)
    layer.add_track(TrackKind.VIDEO, "v1")
    t1 = layer.ensure_track_for_drop("image", insert_after_track_id="v1")
    # Anchor exists (v1); ensure_track_for_drop with the same anchor
    # creates yet another track — v2 was already created above, so
    # the lowest unused id is now v3.
    t2 = layer.ensure_track_for_drop("image", insert_after_track_id="v1")
    assert t1.track_id == "v2"
    assert t2.track_id == "v3"


# ---------- 10. tl_start/tl_end are used for overlap checking ----------

def test_tl_start_end_used_for_overlap_check(tmp_path):
    """When tl_start/tl_end are provided, the allocator uses them for
    overlap. Inserting a second clip at the SAME range on the same
    kind returns a DIFFERENT track (or creates a new one)."""
    core = _fresh_core(tmp_path)
    layer = CommandLayer(core, who=Actor.HUMAN)
    # Add a clip at [0, 10] on v1.
    layer.add_clip("a_vid", 0.0, 10.0, timeline_start=0.0, track_id="v1")
    # Now drop another video at the SAME range. Allocator should NOT
    # return v1 (which has the [0,10] clip) — it creates v2.
    t = layer.ensure_track_for_drop(
        "video", tl_start_frame=0, tl_end_frame=600,  # 10 sec @ 60fps, [0,600]
    )
    assert t.track_id == "v2", (
        f"expected new v2 because v1 has [0,600] clip, got {t.track_id}"
    )
