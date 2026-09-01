"""R6.2-B1: every mutation path that produces a clip on a track must
reject any mutation that would create a same-track overlap.

The audit found V1/c4b3597 [953,1073] and V1/cb82e96 [960,1080]
overlapping on the same track. Provenance was a `move_clip` call
that produced the overlap. The Core-level `_check_no_overlap` already
guards add/move/trim; the R6.2 fix adds it to split (which had no
check) and pins every path with a regression test.
"""
import pytest

from yroll.core.project import ProjectCore
from yroll.core.commands import CommandError, CommandLayer
from yroll.core.manifest import Actor


def _setup_core(tmp_path) -> tuple:
    """Return (core_facade, cmd) where cmd is a fresh CommandLayer
    with 3 non-overlapping clips at frames [0,100], [200,300],
    [400,500] on track v1."""
    pc = ProjectCore.create(str(tmp_path), "r6-2-b1-overlap-test")
    ProjectCore.ensure_default_tracks(pc)
    from yroll.core.models import Asset, AssetIdentity, AssetType
    pc.project.assets.append(Asset(
        asset_id="a1", type=AssetType.VIDEO, path="/test/a1.mp4",
        identity=AssetIdentity(md5="x" * 32, size_bytes=1, duration_sec=30.0),
    ))
    cmd = CommandLayer(pc, who=Actor.HUMAN)
    cmd.add_clip_frame(
        asset_id="a1",
        src_start_frame=0, src_end_frame=100,
        timeline_start_frame=0, track_id="v1",
        timeline_id="main", why="setup-a",
    )
    cmd.add_clip_frame(
        asset_id="a1",
        src_start_frame=0, src_end_frame=100,
        timeline_start_frame=200, track_id="v1",
        timeline_id="main", why="setup-b",
    )
    cmd.add_clip_frame(
        asset_id="a1",
        src_start_frame=0, src_end_frame=100,
        timeline_start_frame=400, track_id="v1",
        timeline_id="main", why="setup-c",
    )
    return pc, cmd


def test_add_clip_rejects_overlap(tmp_path):
    """add_clip_frame must reject a clip that overlaps an existing one."""
    pc, cmd = _setup_core(tmp_path)
    with pytest.raises(CommandError, match=r"重叠|overlap"):
        cmd.add_clip_frame(
            asset_id="a1",
            src_start_frame=0, src_end_frame=100,
            timeline_start_frame=50, track_id="v1",
            timeline_id="main", why="should-fail",
        )


def test_move_clip_rejects_overlap_into_non_adjacent_sibling(tmp_path):
    """move_clip_frame: moving clip [200,300] into [50,150] overlaps
    clip [0,100] — must raise."""
    pc, cmd = _setup_core(tmp_path)
    # Find the clip at frames [200,300] — second on the track
    track = next(t for t in pc.project.timelines[0].tracks if t.track_id == "v1")
    clip_id = track.clip_ids[1]
    with pytest.raises(CommandError, match=r"重叠|overlap"):
        cmd.move_clip_frame(
            clip_id=clip_id, new_timeline_start_frame=50,
            timeline_id="main", why="should-fail",
        )


def test_trim_clip_rejects_overlap(tmp_path):
    """trim_clip_frame extending clip [0,100] past frame 200 would
    overlap clip [200,300] — must raise."""
    pc, cmd = _setup_core(tmp_path)
    track = next(t for t in pc.project.timelines[0].tracks if t.track_id == "v1")
    with pytest.raises(CommandError, match=r"重叠|overlap"):
        cmd.trim_clip_frame(
            clip_id=track.clip_ids[0],
            src_end_frame=250,  # extend past 200 = overlap with [200,300]
            timeline_id="main", why="should-fail",
        )


def test_split_clip_calls_overlap_check(tmp_path):
    """split_clip must call _check_no_overlap (R6.2-B1 source invariant).
    Source inspection is the cheapest robust guard for a defensive
    check that fires only when an upstream mutation has already
    broken the no-overlap invariant."""
    import inspect
    pc, cmd = _setup_core(tmp_path)
    src = inspect.getsource(cmd.split_clip)
    assert "_check_no_overlap" in src, (
        "split_clip must call _check_no_overlap (R6.2-B1)"
    )


def test_ripple_delete_does_not_create_overlap(tmp_path):
    """ripple_delete_clip shifts remaining clips left; no new overlaps."""
    pc, cmd = _setup_core(tmp_path)
    track = next(t for t in pc.project.timelines[0].tracks if t.track_id == "v1")
    cmd.ripple_delete_clip(
        clip_id=track.clip_ids[1], timeline_id="main", why="test-ripple",
    )
    # Verify no overlap: dump project and check pairs
    state = pc.project.model_dump()
    track = next(t for t in state["timelines"][0]["tracks"] if t["kind"] == "video")
    fps = state.get("fps_num", 30)
    clips = []
    for cid in track["clip_ids"]:
        c = state["clips"][cid]
        s = round(c["timeline_range"]["start"] * fps)
        e = round(c["timeline_range"]["end"] * fps)
        clips.append((cid, s, e))
    clips.sort(key=lambda x: x[1])
    for i in range(len(clips)):
        for j in range(i + 1, len(clips)):
            ci, cs, ce = clips[i]
            cj, js, je = clips[j]
            assert not (ce > js and js >= cs), f"overlap detected: {ci} <-> {cj}"


def test_split_clip_actually_overlap_rejected(tmp_path):
    """Manually break the invariant (bypass add_clip check), then verify
    split_clip fires _check_no_overlap and refuses the split."""
    from yroll.core.manifest import Clip, TimeRange
    pc, cmd = _setup_core(tmp_path)
    track = next(t for t in pc.project.timelines[0].tracks if t.track_id == "v1")
    # Inject a bad clip directly to bypass the add_clip overlap guard
    bad_clip_id = "bad_overlap"
    bad = Clip(
        clip_id=bad_clip_id, asset_id="a1",
        source_range=TimeRange(start=0.0, end=0.0),
        timeline_range=TimeRange(start=50/30, end=80/30),
        track_id=track.track_id,
        speed=1.0, volume=1.0, transform={},
    )
    pc.project.clips[bad_clip_id] = bad
    track.clip_ids.insert(1, bad_clip_id)
    # Now split the first clip [0,100] at frame 60. The right half
    # [60,100] overlaps bad_overlap [50,80] — must raise.
    first_clip_id = track.clip_ids[0]
    with pytest.raises(CommandError, match=r"重叠|overlap"):
        cmd.split_clip_frame(
            clip_id=first_clip_id, at_timeline_frame=60,
            timeline_id="main", why="should-fail",
        )
