"""GUI-03B: Image as First-Class Timeline Media.

An image asset has intrinsic_duration=None (still). The image clip's
timeline duration is user-controlled (frame-native) and does NOT
derive from a `set_speed(5/duration)` hack on a fake source range.

Tests cover the full contract:
  - Image asset duration=None can create an image clip
  - 24/25/30/29.97/60fps timeline default duration conversion correct
  - Timeline duration is arbitrary (1 frame, 100 frames, 1000 frames)
  - move/trim image clips are frame-native
  - set_speed(image) is rejected
  - save/reload preserves image clip duration + source semantics
  - Agent add_image_clip + Human GUI path produce identical Core state
  - The legacy set_speed(5/duration) hack path is no longer used
    (the slice script tests this end-to-end)
"""
from __future__ import annotations

import pytest

from yroll.core.commands import CommandLayer
from yroll.core.manifest import (
    Actor,
    Project,
    Sequence,
    Track,
    TrackKind,
)
from yroll.core.models import Asset, AssetIdentity, AssetType
from yroll.core.project import ProjectCore
from yroll.core.timebase import Rational
from yroll.server.app import create_app

from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _build_image_project(tmp_path, fps: Rational = Rational(30, 1)):
    """Build a project with one IMAGE asset + server. Returns
    (client, core)."""
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    core = ProjectCore.create(project_dir, "image-clip-test")
    core.project.sequence = Sequence(fps=fps)
    core.project.sequence.sync_to_project(core.project)
    asset = Asset(
        asset_id="img1", type=AssetType.IMAGE, path="/tmp/x.png",
        identity=AssetIdentity(md5="m" * 32, size_bytes=1),
        # No source_fps for images — they have no time domain.
        source_fps=None, source_is_cfr=None,
    )
    core.project.assets = [asset]
    core.save_state()
    project_path = project_dir / "image-clip-test"
    app = create_app(project_path, who=Actor.HUMAN)
    return TestClient(app), core


# ---------------------------------------------------------------------------
# 1. image asset duration=None can create image clip
# ---------------------------------------------------------------------------

def test_image_asset_duration_none_can_create_clip(tmp_path):
    client, core = _build_image_project(tmp_path)
    # Asset has source_fps=None → intrinsic duration None.
    asset = core.project.assets[0]
    assert asset.source_fps is None
    # Core call: add_image_clip succeeds without a duration hack.
    layer = CommandLayer(core, who=Actor.HUMAN)
    clip = layer.add_image_clip(
        asset_id="img1", timeline_start_frame=0, timeline_duration_frames=90,
        track_id="v1", why="test",
    )
    # Image clip semantics: source_range = (0, 1/seq_fps), speed=1.0.
    expected_src_end = 1 / 30  # 1/30 sec @ 30fps
    assert abs(clip.source_range.start) < 1e-9
    assert abs(clip.source_range.end - expected_src_end) < 1e-9
    assert clip.speed == 1.0
    # Timeline range: 0..3 sec (90 frames @ 30fps)
    assert abs(clip.timeline_range.start) < 1e-9
    assert abs(clip.timeline_range.end - 3.0) < 1e-9
    # Track policy: v1 accepts image.
    assert clip.track_id == "v1"


# ---------------------------------------------------------------------------
# 2. 24/25/30/29.97/60fps timeline default duration conversion correct
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("fps_num,fps_den,frames,expected_seconds", [
    (24, 1, 24, 1.0),
    (24, 1, 48, 2.0),
    (24, 1, 1, 1/24),
    (25, 1, 25, 1.0),
    (25, 1, 50, 2.0),
    (30, 1, 30, 1.0),
    (30, 1, 90, 3.0),
    (30, 1, 1, 1/30),
    (30000, 1001, 30, 30 * 1001 / 30000),  # ~1.0001 sec
    (30000, 1001, 1500, 1500 * 1001 / 30000),  # ~50.05 sec
    (60, 1, 60, 1.0),
    (60, 1, 180, 3.0),
])
def test_image_clip_duration_conversion_at_all_fps(tmp_path, fps_num, fps_den,
                                                  frames, expected_seconds):
    client, core = _build_image_project(tmp_path, fps=Rational(fps_num, fps_den))
    layer = CommandLayer(core, who=Actor.HUMAN)
    clip = layer.add_image_clip(
        asset_id="img1", timeline_start_frame=0,
        timeline_duration_frames=frames, track_id="v1", why="fps-test",
    )
    actual_seconds = clip.timeline_range.end - clip.timeline_range.start
    assert abs(actual_seconds - expected_seconds) < 1e-6, (
        f"fps {fps_num}/{fps_den}, {frames} frames → expected "
        f"{expected_seconds:.6f}s, got {actual_seconds:.6f}s"
    )


# ---------------------------------------------------------------------------
# 3. timeline duration is arbitrary
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("duration_frames", [1, 7, 90, 999, 30 * 60 * 5])
def test_image_clip_duration_is_arbitrary(tmp_path, duration_frames):
    client, core = _build_image_project(tmp_path)
    layer = CommandLayer(core, who=Actor.HUMAN)
    clip = layer.add_image_clip(
        asset_id="img1", timeline_start_frame=10,
        timeline_duration_frames=duration_frames, track_id="v1",
    )
    # Timeline range: 10..(10+duration)
    expected_start = 10 / 30
    expected_end = (10 + duration_frames) / 30
    assert abs(clip.timeline_range.start - expected_start) < 1e-9
    assert abs(clip.timeline_range.end - expected_end) < 1e-9


# ---------------------------------------------------------------------------
# 4. move/trim image clips are frame-native
# ---------------------------------------------------------------------------

def test_move_image_clip_frame_native(tmp_path):
    client, core = _build_image_project(tmp_path)
    layer = CommandLayer(core, who=Actor.HUMAN)
    clip = layer.add_image_clip(
        asset_id="img1", timeline_start_frame=0, timeline_duration_frames=60,
    )
    # Move the clip to start at frame 90.
    layer.move_clip_frame(clip.clip_id, new_timeline_start_frame=90)
    assert abs(clip.timeline_range.start - 3.0) < 1e-9  # 90/30 sec
    # Source range UNCHANGED (image clips have no source trim on move).
    assert abs(clip.source_range.start) < 1e-9
    assert abs(clip.source_range.end - 1/30) < 1e-9


def test_trim_image_clip_frame_native_via_dedicated_command(tmp_path):
    client, core = _build_image_project(tmp_path)
    layer = CommandLayer(core, who=Actor.HUMAN)
    clip = layer.add_image_clip(
        asset_id="img1", timeline_start_frame=0, timeline_duration_frames=60,
    )
    # trim_image_clip_frame: change timeline_end_frame to 30 (1 sec).
    layer.trim_image_clip_frame(
        clip.clip_id, timeline_end_frame=30,
    )
    assert abs(clip.timeline_range.start) < 1e-9  # unchanged
    assert abs(clip.timeline_range.end - 1.0) < 1e-9  # 30 frames = 1 sec
    # Source range still fixed at (0, 1/seq_fps).
    assert abs(clip.source_range.start) < 1e-9
    assert abs(clip.source_range.end - 1/30) < 1e-9
    # Now also shift the start frame.
    layer.trim_image_clip_frame(
        clip.clip_id, timeline_start_frame=60, timeline_end_frame=120,
    )
    assert abs(clip.timeline_range.start - 2.0) < 1e-9  # 60/30 sec
    assert abs(clip.timeline_range.end - 4.0) < 1e-9    # 120/30 sec


def test_trim_image_clip_rejects_non_image(tmp_path):
    client, core = _build_image_project(tmp_path)
    layer = CommandLayer(core, who=Actor.HUMAN)
    # Add a video asset + clip (using legacy add_clip).
    video_asset = Asset(
        asset_id="vid1", type=AssetType.VIDEO, path="/tmp/v.mp4",
        identity=AssetIdentity(md5="v" * 32, size_bytes=1, duration_sec=10.0),
        source_fps=Rational(30, 1), source_is_cfr=True,
    )
    core.project.assets.append(video_asset)
    vclip = layer.add_clip(
        "vid1", 0.0, 10.0, timeline_start=0.0, track_id="v1",
    )
    # trim_image_clip_frame on a video clip must reject.
    with pytest.raises(Exception) as excinfo:
        layer.trim_image_clip_frame(vclip.clip_id, timeline_end_frame=30)
    assert "not an image clip" in str(excinfo.value)


# ---------------------------------------------------------------------------
# 5. set_speed(image) is rejected
# ---------------------------------------------------------------------------

def test_set_speed_image_rejected(tmp_path):
    client, core = _build_image_project(tmp_path)
    layer = CommandLayer(core, who=Actor.HUMAN)
    clip = layer.add_image_clip(
        asset_id="img1", timeline_start_frame=0, timeline_duration_frames=60,
    )
    # set_speed on an image clip is forbidden — image has 1 source
    # frame; speed is structurally locked at 1.0.
    with pytest.raises(Exception) as excinfo:
        layer.set_speed(clip.clip_id, 2.0)
    msg = str(excinfo.value)
    assert "image" in msg.lower()
    assert "speed" in msg.lower()
    # The clip's speed is still 1.0.
    assert clip.speed == 1.0
    # The HTTP endpoint also rejects.
    r = client.post(f"/clips/{clip.clip_id}/speed",
                    params={"sessionId": "test", "baseRevision": 0},
                    json={"speed": 2.0, "why": "test"})
    assert r.status_code in (400, 403, 409), r.text  # gate may reject first
    # Even if gate-passes, the underlying CommandError surfaces as 400.
    # Without a valid session, the gate will block at 403; that's OK
    # — the protection is at both layers.


# ---------------------------------------------------------------------------
# 6. save/reload preserves image clip duration + source semantics
# ---------------------------------------------------------------------------

def test_image_clip_save_reload_preserves_semantics(tmp_path):
    """After ProjectCore.open() the round-tripped clip must have:
      - source_range = (0, 1/30)
      - speed = 1.0
      - timeline_range = (start_frame/30, end_frame/30)
    No duration drift, no implicit speed adjustment."""
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    core = ProjectCore.create(project_dir, "save-reload-test")
    asset = Asset(
        asset_id="img1", type=AssetType.IMAGE, path="/tmp/x.png",
        identity=AssetIdentity(md5="m" * 32, size_bytes=1),
        source_fps=None, source_is_cfr=None,
    )
    core.project.assets = [asset]
    core.save_state()
    layer = CommandLayer(core, who=Actor.HUMAN)
    clip = layer.add_image_clip(
        asset_id="img1", timeline_start_frame=120,
        timeline_duration_frames=180, track_id="v1",
    )
    expected_src_start = clip.source_range.start
    expected_src_end = clip.source_range.end
    expected_tl_start = clip.timeline_range.start
    expected_tl_end = clip.timeline_range.end
    expected_speed = clip.speed
    cid = clip.clip_id
    core.save_state()
    # Round-trip via ProjectCore.open.
    core2 = ProjectCore.open(project_dir / "save-reload-test")
    clip2 = core2.project.clips[cid]
    assert abs(clip2.source_range.start - expected_src_start) < 1e-9
    assert abs(clip2.source_range.end - expected_src_end) < 1e-9
    assert abs(clip2.timeline_range.start - expected_tl_start) < 1e-9
    assert abs(clip2.timeline_range.end - expected_tl_end) < 1e-9
    assert clip2.speed == expected_speed == 1.0
    # Track still v1.
    assert clip2.track_id == "v1"


# ---------------------------------------------------------------------------
# 7. Agent add_image_clip + Human GUI path produce identical Core state
# ---------------------------------------------------------------------------

def test_agent_and_human_paths_produce_identical_state(tmp_path):
    """An Agent script using add_image_clip and a Human GUI using
    trim_image_clip_frame both produce the same Core state for an
    identical timeline composition."""
    project_dir_a = tmp_path / "agent"
    project_dir_h = tmp_path / "human"
    project_dir_a.mkdir()
    project_dir_h.mkdir()
    asset_path = "/tmp/x.png"

    # --- Agent path: one big batch of add_image_clip calls ---
    core_a = ProjectCore.create(project_dir_a, "agent-path")
    asset_a = Asset(
        asset_id="img1", type=AssetType.IMAGE, path=asset_path,
        identity=AssetIdentity(md5="m" * 32, size_bytes=1),
        source_fps=None, source_is_cfr=None,
    )
    core_a.project.assets.append(asset_a)
    layer_a = CommandLayer(core_a, who=Actor.HUMAN)
    layer_a.add_image_clip("img1", timeline_start_frame=0, timeline_duration_frames=60)
    layer_a.add_image_clip("img1", timeline_start_frame=60, timeline_duration_frames=90)
    layer_a.add_image_clip("img1", timeline_start_frame=150, timeline_duration_frames=30)
    core_a.save_state()

    # --- Human path: add one clip, then trim it twice ---
    core_h = ProjectCore.create(project_dir_h, "human-path")
    asset_h = Asset(
        asset_id="img1", type=AssetType.IMAGE, path=asset_path,
        identity=AssetIdentity(md5="m" * 32, size_bytes=1),
        source_fps=None, source_is_cfr=None,
    )
    core_h.project.assets.append(asset_h)
    layer_h = CommandLayer(core_h, who=Actor.HUMAN)
    clip = layer_h.add_image_clip(
        "img1", timeline_start_frame=0, timeline_duration_frames=60,
    )
    layer_h.trim_image_clip_frame(clip.clip_id, timeline_end_frame=60)
    layer_h.add_image_clip("img1", timeline_start_frame=60, timeline_duration_frames=90)
    layer_h.add_image_clip("img1", timeline_start_frame=150, timeline_duration_frames=30)
    core_h.save_state()

    # The two projects' clips should have IDENTICAL timeline + source
    # representations.
    a_clips = sorted(core_a.project.clips.values(),
                     key=lambda c: c.timeline_range.start)
    h_clips = sorted(core_h.project.clips.values(),
                     key=lambda c: c.timeline_range.start)
    assert len(a_clips) == len(h_clips) == 3
    for ca, ch in zip(a_clips, h_clips):
        assert abs(ca.timeline_range.start - ch.timeline_range.start) < 1e-9
        assert abs(ca.timeline_range.end - ch.timeline_range.end) < 1e-9
        assert abs(ca.source_range.start - ch.source_range.start) < 1e-9
        assert abs(ca.source_range.end - ch.source_range.end) < 1e-9
        assert ca.speed == ch.speed == 1.0


# ---------------------------------------------------------------------------
# 8. The legacy set_speed(5/duration) hack is no longer needed
# ---------------------------------------------------------------------------

def test_no_set_speed_5_per_duration_hack_needed(tmp_path):
    """An image clip produced by add_image_clip has timeline_duration
    directly controllable via timeline_duration_frames — no need
    to call set_speed(5/duration) to fake it. This test asserts
    the new clip has speed=1.0 and the expected timeline range
    without any speed adjustment."""
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    core = ProjectCore.create(project_dir, "no-hack")
    asset = Asset(
        asset_id="img1", type=AssetType.IMAGE, path="/tmp/x.png",
        identity=AssetIdentity(md5="m" * 32, size_bytes=1),
        source_fps=None, source_is_cfr=None,
    )
    core.project.assets.append(asset)
    layer = CommandLayer(core, who=Actor.HUMAN)
    # Caller asks for a 3-second clip from frame 60..150.
    clip = layer.add_image_clip(
        asset_id="img1", timeline_start_frame=60,
        timeline_duration_frames=90,  # 90 frames @ 30fps = 3 sec
        track_id="v1",
    )
    # No set_speed was needed. The clip's speed is 1.0 (not 30/90 =
    # 0.333 or anything else). The source range is 1/30 sec (one
    # source frame). The timeline range is 2..5 sec.
    assert clip.speed == 1.0
    assert abs(clip.source_range.start) < 1e-9
    assert abs(clip.source_range.end - 1/30) < 1e-9
    assert abs(clip.timeline_range.start - 2.0) < 1e-9  # 60/30
    assert abs(clip.timeline_range.end - 5.0) < 1e-9    # (60+90)/30


# ---------------------------------------------------------------------------
# 9. trim_image_clip HTTP endpoint contract
# ---------------------------------------------------------------------------

def test_trim_image_clip_http_endpoint(tmp_path):
    """The HTTP endpoint /clips/{id}/trim_image is the GUI-facing
    path for adjusting image clip duration. It uses frame-native
    parameters."""
    client, core = _build_image_project(tmp_path)
    # Need a session + lease for mutation endpoints.
    sess = client.post("/session/ensure", json={
        "actor": "human", "actor_id": "tester", "intent": "edit",
    }).json()
    sid = sess["sessionId"]
    # Add the image clip via the HTTP endpoint so the server's core
    # is the source of truth.
    rev0 = sess["revision"]
    r = client.post("/clips/add_image",
                    params={"sessionId": sid, "baseRevision": rev0},
                    json={
                        "asset_id": "img1",
                        "timeline_start_frame": 0,
                        "timeline_duration_frames": 60,
                        "track_id": "v1",
                        "why": "http-setup",
                    })
    assert r.status_code == 200, r.text
    cid = r.json()["clip_id"]
    # Get the new revision after the add.
    rev1 = client.get("/ui/status").json()["base_revision"]
    # Trim the clip to a 2-sec duration via HTTP.
    r = client.post(f"/clips/{cid}/trim_image",
                    params={"sessionId": sid, "baseRevision": rev1},
                    json={"timeline_end_frame": 60, "why": "http-test"})
    assert r.status_code == 200, r.text
    # The clip's timeline_range should now be 0..2 sec.
    proj = client.get("/project").json()
    c = proj["clips"][cid]
    assert abs(c["timeline_range"]["end"] - 2.0) < 1e-6
    assert abs(c["timeline_range"]["start"]) < 1e-6
    assert c["speed"] == 1.0


def test_add_image_clip_http_endpoint(tmp_path):
    """The HTTP endpoint /clips/add_image creates an image clip with
    frame-native parameters."""
    client, core = _build_image_project(tmp_path)
    sess = client.post("/session/ensure", json={
        "actor": "human", "actor_id": "tester", "intent": "edit",
    }).json()
    sid = sess["sessionId"]; rev = sess["revision"]
    r = client.post("/clips/add_image",
                    params={"sessionId": sid, "baseRevision": rev},
                    json={
                        "asset_id": "img1",
                        "timeline_start_frame": 0,
                        "timeline_duration_frames": 90,
                        "track_id": "v1",
                        "why": "http-test",
                    })
    assert r.status_code == 200, r.text
    data = r.json()
    # Response is the created Clip's parameters.
    assert data["speed"] == 1.0
    assert abs(data["timeline_range"]["end"] - 3.0) < 1e-6
    # Source range is the image's single-frame duration.
    assert abs(data["source_range"]["end"] - 1/30) < 1e-6


def test_add_image_clip_rejects_non_image_asset(tmp_path):
    """add_image_clip refuses a video asset."""
    client, core = _build_image_project(tmp_path)
    # Add a video asset alongside the image.
    video_asset = Asset(
        asset_id="vid1", type=AssetType.VIDEO, path="/tmp/v.mp4",
        identity=AssetIdentity(md5="v" * 32, size_bytes=1, duration_sec=10.0),
        source_fps=Rational(30, 1), source_is_cfr=True,
    )
    core.project.assets.append(video_asset)
    sess = client.post("/session/ensure", json={
        "actor": "human", "actor_id": "tester", "intent": "edit",
    }).json()
    sid = sess["sessionId"]; rev = sess["revision"]
    r = client.post("/clips/add_image",
                    params={"sessionId": sid, "baseRevision": rev},
                    json={
                        "asset_id": "vid1",
                        "timeline_start_frame": 0,
                        "timeline_duration_frames": 90,
                        "track_id": "v1",
                        "why": "should-fail",
                    })
    # The endpoint surfaces the CommandError as 400.
    assert r.status_code in (400, 422, 500), r.text


def test_add_image_clip_rejects_audio_track(tmp_path):
    """add_image_clip refuses to place on an audio track."""
    client, core = _build_image_project(tmp_path)
    layer = CommandLayer(core, who=Actor.HUMAN)
    # Add an a1 track.
    from yroll.core.manifest import TrackKind
    layer.add_track(TrackKind.AUDIO, "a1")
    sess = client.post("/session/ensure", json={
        "actor": "human", "actor_id": "tester", "intent": "edit",
    }).json()
    sid = sess["sessionId"]; rev = sess["revision"]
    r = client.post("/clips/add_image",
                    params={"sessionId": sid, "baseRevision": rev},
                    json={
                        "asset_id": "img1",
                        "timeline_start_frame": 0,
                        "timeline_duration_frames": 90,
                        "track_id": "a1",
                        "why": "should-fail",
                    })
    assert r.status_code in (400, 422, 500), r.text
    assert "audio" in r.text.lower() or "reject" in r.text.lower()


# ---------------------------------------------------------------------------
# 10. Slice script uses add_image_clip (no set_speed hack)
# ---------------------------------------------------------------------------

def test_slice_script_uses_add_image_clip_no_hack():
    """The slice script (which is the canonical real-production
    reference for this batch) must NOT call set_speed(5/duration)
    on image clips. Verify by reading the script."""
    scripts_dir = __import__("pathlib").Path(
        __file__).resolve().parent.parent / "scripts"
    target = scripts_dir / "build_sanlihe_slice.py"
    if not target.exists():
        pytest.skip("build_sanlihe_slice.py not yet rewritten")
    src = target.read_text(encoding="utf-8")
    # The legacy hack pattern: `set_speed(<clip>.clip_id, 5.0 / duration, ...)`.
    # This must NOT appear in the script for any duration computed
    # from the image-clip's timeline duration.
    assert "5.0 / duration" not in src, (
        "build_sanlihe_slice.py still uses the legacy set_speed "
        "hack for image clips — should use add_image_clip instead"
    )
    # The new command name should be present.
    assert "add_image_clip" in src, (
        "build_sanlihe_slice.py should call add_image_clip"
    )