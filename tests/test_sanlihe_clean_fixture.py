# GUI-03R4.1 P0-2: Sanlihe clean-fixture invariants.
#
# Pins the shape of projects/sanlihe-slice-30s-clean/ so that
# future edits can't silently reintroduce the stale/test debris
# this fixture was built to remove. The checks are deliberately
# behavior-only — they don't care about clip IDs (which are
# random) but DO care about:
#
#   1. No clip lives at the [600, 608.5s] debris range on any
#      VISIBLE track. (The hidden v10 still has clips past 600s
#      — that's the original long-tail fixture content and it's
#      R4-1-correct that the hidden track is excluded from the
#      plan. v10 stays untouched.)
#   2. The t1/c61ee32 anomaly (50s subtitle past editorial end)
#      is gone.
#   3. The zero-duration v2/c3e7628 ([600, 600]) is gone.
#   4. The V1 editorial extent is preserved at exactly 49.51s.
#   5. The visible extent equals the V1 editorial extent (no
#      stale test clip pulls Fit Content out to 600+ px/sec).
#   6. The fixture has a `fixture_cleanup` op recording what was
#      removed and why.
#
# These checks run as a static test — they don't need yroll serve
# running and don't mutate the fixture. Browser smoke that wants
# to mutate MUST copy the fixture first.

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "projects" / "sanlihe-slice-30s-clean"

pytestmark = pytest.mark.skipif(
    not (FIXTURE / "current.json").exists(),
    reason="sanlihe-slice-30s-clean fixture not built",
)


@pytest.fixture(scope="module")
def project():
    with (FIXTURE / "current.json").open(encoding="utf-8") as f:
        return json.load(f)


def _main_timeline_tracks(project):
    """Return tracks from the `main` timeline only."""
    for tl in project["timelines"]:
        if tl["timeline_id"] == "main":
            return tl["tracks"]
    raise AssertionError("no main timeline")


def _clip_track_ranges(project, visible_only=True):
    """Return list of (clip_id, track_id, start, end, hidden) tuples."""
    out = []
    for t in _main_timeline_tracks(project):
        if visible_only and t.get("hidden"):
            continue
        for cid in t.get("clip_ids", []):
            c = project["clips"].get(cid)
            if not c:
                continue
            tr = c["timeline_range"]
            out.append((cid, t["track_id"], tr["start"], tr["end"],
                        t.get("hidden", False)))
    return out


def test_no_visible_clip_at_debris_range_600_608_5(project):
    """All 4 stale auto-test clips lived at [600, 608.5s]. They
    MUST be gone from every visible track."""
    bad = [
        (cid, tid, s, e) for (cid, tid, s, e, hidden)
        in _clip_track_ranges(project, visible_only=True)
        if s >= 595 and s <= 605 and e - s < 15
    ]
    assert bad == [], (
        f"stale 600s debris clips remain on visible tracks: {bad}"
    )


def test_no_visible_clip_with_debris_position(project):
    """The auto-test clips all started at EXACTLY 600s on a
    visible track. No VISIBLE track should have a clip
    starting in [595, 605] (a 10s tolerance around the debris
    anchor). Position is the strong signal — editorial clips
    may use the same source asset (ae45f65, 8.5s) but never
    at 600s."""
    bad = [
        (cid, tid, s, e) for (cid, tid, s, e, hidden)
        in _clip_track_ranges(project, visible_only=True)
        if s >= 595 and s <= 605
    ]
    assert bad == [], (
        f"clip(s) starting in the [595, 605]s debris anchor: {bad}"
    )


def test_t1_subtitle_durations_are_editorial(project):
    """Sanlihe editorial T1 subtitles are 2.5-5.0s (5 of them).
    c61ee32's 50s duration was the anomaly. Any T1 clip > 10s is
    almost certainly stale/test."""
    t1 = next(t for t in _main_timeline_tracks(project)
              if t["track_id"] == "t1")
    bad = []
    for cid in t1.get("clip_ids", []):
        c = project["clips"][cid]
        dur = c["timeline_range"]["end"] - c["timeline_range"]["start"]
        if dur > 10:
            bad.append((cid, dur, c["timeline_range"]))
    assert bad == [], (
        f"T1 subtitle(s) with non-editorial duration > 10s: {bad}"
    )


def test_no_zero_duration_visible_clip(project):
    """The v2/c3e7628 [600, 600] zero-duration clip was a test
    artifact. No VISIBLE track should contain a zero-length
    clip."""
    bad = [
        (cid, tid, s, e) for (cid, tid, s, e, hidden)
        in _clip_track_ranges(project, visible_only=True)
        if e - s < 0.01
    ]
    assert bad == [], (
        f"zero-duration clip(s) on visible tracks: {bad}"
    )


def test_v1_editorial_extent_is_49_51s(project):
    """V1 carries the main story. Its last clip's end is the
    'editorial content end'. This must equal 49.51s exactly."""
    v1 = next(t for t in _main_timeline_tracks(project)
              if t["track_id"] == "v1")
    assert v1["clip_ids"], "V1 has no clips"
    max_end = max(
        project["clips"][cid]["timeline_range"]["end"]
        for cid in v1["clip_ids"]
    )
    assert abs(max_end - 49.51) < 0.05, (
        f"V1 editorial extent drifted: expected ~49.51s, got {max_end:.2f}s"
    )


def test_visible_extent_matches_v1_editorial(project):
    """Visible extent (Fit Content zoom target) must equal V1's
    editorial extent. No stale test clip should pull the visible
    extent out to 600+s."""
    v1 = next(t for t in _main_timeline_tracks(project)
              if t["track_id"] == "v1")
    v1_end = max(project["clips"][cid]["timeline_range"]["end"]
                 for cid in v1["clip_ids"])
    visible_max = 0.0
    for t in _main_timeline_tracks(project):
        if t.get("hidden"):
            continue
        for cid in t.get("clip_ids", []):
            c = project["clips"].get(cid, {})
            if c.get("timeline_range", {}).get("end", 0) > visible_max:
                visible_max = c["timeline_range"]["end"]
    assert abs(visible_max - v1_end) < 0.5, (
        f"visible extent {visible_max:.2f}s ≠ V1 editorial end {v1_end:.2f}s"
    )


def test_fixture_has_cleanup_op(project):
    """The fixture must self-document its origin (derived from
    sanlihe-slice-30s) and what was removed."""
    intent = project.get("intent", {})
    assert intent.get("derived_from") == "sanlihe-slice-30s"
    removed = intent.get("removed_stale_clip_ids", [])
    assert "cc61634" in removed
    assert "c0f1e08" in removed
    assert "cf3267c" in removed
    assert "c884a18" in removed
    assert "c3e7628" in removed
    assert "c61ee32" in removed


def test_fixture_declares_editorial_track_ids(project):
    """GUI-03R4.1 P1-5: the fixture must declare which tracks count
    as editorial so Fit Content zooms to the right extent even if
    other visible tracks carry test debris."""
    intent = project.get("intent", {})
    editorial = intent.get("editorial_track_ids", [])
    assert "v1" in editorial, (
        f"v1 must be declared editorial (carries the main story); "
        f"got {editorial}"
    )


def test_cleanup_op_file_exists():
    """The cleanup op MUST be in the operations directory so
    the fixture is self-explaining to anyone reading its log."""
    ops = list((FIXTURE / "operations").glob("op*.json"))
    assert ops, "no operations files in clean fixture"
    with ops[0].open(encoding="utf-8") as f:
        op = json.load(f)
    assert op["type"] == "fixture_cleanup"
    assert op["target"] == "sanlihe-slice-30s-clean"
    classification = op["parameters"]["removed_classification"]
    assert "c61ee32" in classification
    assert "50s duration" in classification["c61ee32"]


def test_canonical_fixture_is_readonly_marker():
    """The canonical clean fixture must NOT be touched by browser
    smoke. We pin this with a sentinel file in the fixture root.
    Browser smoke that wants to mutate the fixture copies it to
    a working dir first."""
    sentinel = FIXTURE / "CANONICAL_READONLY_DO_NOT_MUTATE"
    assert sentinel.exists(), (
        f"{sentinel} missing — the clean fixture MUST carry a "
        f"readonly sentinel so browser smoke scripts know to "
        f"copy it rather than mutate it."
    )