"""GUI-02.5: PreviewPlayer + FrameClock invariants (static + dynamic).

Covers the closure spec for PreviewPlayer:

  - NO `setInterval(..., 33)` (or any setInterval) inside PreviewPlayer
  - NO TimelineFrame derivation from `video.currentTime` (HTML media
    time is external I/O, never the canonical timeline state source)
  - NO direct Timeline→media-seconds conversion using sequence FPS
    (the GUI must use the asset's source FPS via Core's TimeMap)
  - The new server endpoint `/clip/{id}/timemap/at_frame` resolves
    TimelineFrame → SourceFrame using Core's TimeMap (NOT a per-
    frame HTTP query — it's cached in the GUI)

Static guard walks `gui/src/components/PreviewPlayer.tsx` and flags
forbidden patterns; the server endpoint test exercises Core's
resolution to confirm the contract.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from fastapi.testclient import TestClient

from yroll.core.commands import CommandLayer
from yroll.core.manifest import (
    Actor,
    Clip,
    Project,
    Sequence,
    TimeRange,
    Track,
    TrackKind,
)
from yroll.core.models import Asset, AssetIdentity, AssetType
from yroll.core.project import ProjectCore
from yroll.core.timebase import Rational
from yroll.server import app as server_app


ROOT = Path(__file__).resolve().parent.parent
PREVIEWPLAYER = ROOT / "gui" / "src" / "components" / "PreviewPlayer.tsx"
FRAMECLOCK = ROOT / "gui" / "src" / "frame-clock.ts"


def _strip_comments_and_strings(src: str) -> str:
    """Remove TS comments and template-literal interpolations. Comments
    may legitimately mention forbidden patterns; the guard scans only
    active code."""
    def _block_repl(m: re.Match) -> str:
        return re.sub(r"[^\n]", " ", m.group(0))
    out = re.sub(r"/\*.*?\*/", _block_repl, src, flags=re.DOTALL)
    out = re.sub(r"//[^\n]*", "", out)
    out = re.sub(r"\$\{[^}]*\.speed[^}]*\}", "DISPLAY_SPEED", out)
    return out


# ---------------------------------------------------------------------------
# Static guard: PreviewPlayer must not contain forbidden patterns
# ---------------------------------------------------------------------------

def test_previewplayer_no_setinterval_for_playback_clock():
    """PreviewPlayer must NOT use setInterval as the playback clock.
    The closure spec: playback clock = performance.now() + start anchor;
    RAF is render cadence only. setInterval is forbidden."""
    src = _strip_comments_and_strings(PREVIEWPLAYER.read_text(encoding="utf-8"))
    m = re.search(r"\bsetInterval\s*\(", src)
    assert not m, (
        "PreviewPlayer must not use setInterval for playback clock; "
        "use RAF + performance.now() (see gui/src/frame-clock.ts)"
    )


def test_previewplayer_no_timeline_derivation_from_video_currenttime():
    """PreviewPlayer must NEVER read v.currentTime to derive the
    TimelineFrame. The only reads of v.currentTime are for end-of-file
    detection in rendered mode (orthogonal event), and they do NOT
    feed back into the playheadFrame state. Search for any line that
    writes to playheadFrame / onPlayhead / setPlayheadFrame from a
    computation involving v.currentTime."""
    src = _strip_comments_and_strings(PREVIEWPLAYER.read_text(encoding="utf-8"))
    # Forbidden: lines that combine v.currentTime with playhead update
    # (the feedback loop). The legitimate uses are:
    #   - v.currentTime = mediaSeconds  (write only)
    #   - v.duration > 0 && v.currentTime >= v.duration - 0.05  (end detection)
    # A bare `onPlayhead(v.currentTime)` or
    # `onPlayhead(Math.max(..., v.currentTime - ...))` is forbidden.
    for pattern in [
        # Most direct feedback: "onPlayhead(v.currentTime)"
        r"onPlayhead\s*\(\s*[a-zA-Z_]+\.currentTime\s*\)",
        # The legacy pattern we removed: deriving timeline via
        # source_range math + video.currentTime
        r"v\.currentTime\s*-\s*[a-zA-Z_.]+\.source_range\.start",
    ]:
        m = re.search(pattern, src)
        assert not m, (
            f"PreviewPlayer must not derive TimelineFrame from "
            f"v.currentTime. Found pattern {pattern!r} near: "
            f"'{src[max(0, m.start()-30):m.end()+30] if m else ''}'"
        )


def test_previewplayer_no_direct_timeline_to_seconds_via_seq_fps():
    """PreviewPlayer must NOT compute `v.currentTime = playheadFrame *
    sequenceFps.den / sequenceFps.num` (or equivalent) in INSTANT
    mode. The only allowed path: playheadFrame → Core TimeMap
    .source_from_timeline → SourceFrame × asset.sourceFps.den /
    asset.sourceFps.num.

    The rendered-mode path uses `v.currentTime = playheadFrame` and
    IS valid (the rendered output is at sequence FPS); it's
    permitted inside the `mode === "rendered"` branch."""
    src = _strip_comments_and_strings(PREVIEWPLAYER.read_text(encoding="utf-8"))
    # Find all `v.currentTime = ...` writes. Each must be either:
    #   - inside a `mode === "rendered"` block (legitimate; rendered
    #     file's frame rate matches the project), or
    #   - derived from mediaSeconds (= sourceFrame × source_fps.den /
    #     source_fps.num via Core's TimeMap response).
    writes = list(re.finditer(r"v\.currentTime\s*=\s*([^;]+);", src))
    assert writes, "PreviewPlayer should write v.currentTime at least once"
    for m in writes:
        rhs = m.group(1).strip()
        # Permitted: mediaSeconds (from Core TimeMap + asset source_fps)
        if rhs.startswith("mediaSeconds"):
            continue
        # Permitted in rendered mode only
        if rhs == "playheadFrame":
            # Walk backwards in the file to find the enclosing scope.
            # If the next enclosing `if (mode === "rendered")` is
            # within ~200 chars before this write, allow it.
            start = max(0, m.start() - 300)
            preceding = src[start:m.start()]
            if re.search(r"mode\s*===\s*[\"']rendered[\"']", preceding):
                continue
        assert False, (
            f"PreviewPlayer must write v.currentTime only from "
            f"mediaSeconds (Core TimeMap + asset source_fps), or "
            f"inside an explicit `mode === 'rendered'` branch. "
            f"Found RHS: {rhs!r}"
        )


# ---------------------------------------------------------------------------
# frame-clock.ts is the single playback clock abstraction
# ---------------------------------------------------------------------------

def test_frame_clock_module_exists():
    assert FRAMECLOCK.is_file(), (
        "gui/src/frame-clock.ts must exist as the single playback "
        "clock abstraction"
    )


def test_frame_clock_no_setinterval():
    src = _strip_comments_and_strings(FRAMECLOCK.read_text(encoding="utf-8"))
    assert not re.search(r"\bsetInterval\s*\(", src), (
        "frame-clock.ts must NOT use setInterval; it is the "
        "performance.now()-based clock abstraction"
    )


def test_frame_clock_no_videotime_or_dom_dependency():
    """frame-clock.ts is a pure timing module. It must not depend on
    DOM APIs (HTMLVideoElement, currentTime, etc.) — it's the
    authoritative TimelineFrame source, not a media wrapper."""
    src = _strip_comments_and_strings(FRAMECLOCK.read_text(encoding="utf-8"))
    forbidden = [
        "HTMLVideoElement", "HTMLAudioElement", ".currentTime",
        "document", "window",
    ]
    for f in forbidden:
        assert f not in src, (
            f"frame-clock.ts must not reference {f!r}; it's a pure "
            f"timing module, not a DOM wrapper"
        )


# ---------------------------------------------------------------------------
# Server endpoint: /clip/{id}/timemap/at_frame
# ---------------------------------------------------------------------------

@pytest.fixture
def client_and_core(tmp_path):
    """Build a project with one video clip and a uvicorn test client."""
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    # Build the project via ProjectCore.create so the standard
    # directory layout + default tracks exist.
    core = ProjectCore.create(project_dir, "frame-clock-test")
    # Add one video asset with explicit source_fps=60 (heterogeneous
    # against the default 30fps sequence). This is the 30seq+60src
    # closure test case.
    asset = Asset(
        asset_id="a1", type=AssetType.VIDEO, path="/tmp/v.mp4",
        identity=AssetIdentity(md5="m" * 32, size_bytes=1, duration_sec=10.0),
        source_fps=Rational(60, 1), source_is_cfr=True,
        source_frame_count=600,
    )
    core.project.assets = [asset]
    # Ensure sequence stays at 30fps (the default).
    core.project.sequence = Sequence(fps=Rational(30, 1))
    core.project.sequence.sync_to_project(core.project)
    # Add a clip: source 0..10s (= 600 source frames at 60fps), placed
    # at timeline 0..10s (= 300 timeline frames at 30fps). clip.speed=1.0.
    cmd = CommandLayer(core, who=Actor.HUMAN)
    cmd.add_clip("a1", 0.0, 10.0, timeline_start=0.0)
    core.save_state()

    # Use the server's create_app factory — it accepts a project
    # path, opens the project, registers all routes, and returns a
    # ready-to-test FastAPI app.
    # ProjectCore.create(root, name) writes to `<root>/<name>/`; pass
    # that nested path so ProjectCore.open() can find current.json.
    project_path = project_dir / "frame-clock-test"
    from yroll.server.app import create_app
    app = create_app(project_path, who=Actor.HUMAN)
    return TestClient(app), core


def _find_clip_id(core: ProjectCore) -> str:
    for cid, c in core.project.clips.items():
        if c.asset_id == "a1":
            return cid
    raise RuntimeError("clip a1 not found")


def test_timemap_at_frame_returns_source_frame(client_and_core):
    """Core's /clip/{id}/timemap/at_frame resolves TimelineFrame →
    SourceFrame via TimeMap. For seq=30, src=60, speed=1.0:
      timeline_frame=30 → source_frame=60  (1 sec at 60fps)
      timeline_frame=300 → source_frame=600  (10 sec at 60fps)
    """
    client, core = client_and_core
    cid = _find_clip_id(core)
    # timeline_frame=30 = 1 second at 30fps
    r = client.get(f"/clip/{cid}/timemap/at_frame", params={
        "timeline_frame": 30,
        "fps_num": 30, "fps_den": 1,
        "src_fps_num": 60, "src_fps_den": 1,
    })
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["source_frame"] == 60
    assert data["timeline_frame"] == 30
    assert data["source_fps"] == {"num": 60, "den": 1}
    assert data["sequence_fps"] == {"num": 30, "den": 1}


def test_timemap_at_frame_end_of_clip(client_and_core):
    """At timeline_end=300 (= 10s at 30fps), source_frame = 600
    (= 10s at 60fps). This pins that the conversion is correct at
    the boundary."""
    client, core = client_and_core
    cid = _find_clip_id(core)
    r = client.get(f"/clip/{cid}/timemap/at_frame", params={
        "timeline_frame": 300,
        "fps_num": 30, "fps_den": 1,
        "src_fps_num": 60, "src_fps_den": 1,
    })
    assert r.status_code == 200
    assert r.json()["source_frame"] == 600


def test_timemap_at_frame_speed_2x(client_and_core):
    """clip.speed=2.0 with seq=30, src=60:
      timeline_frame=100 → source_frame = 100 * 2 * 60 / 30 = 400.
    Mutate via the server's mutation endpoint so the server's
    in-memory core sees the new state."""
    client, core = client_and_core
    cid = _find_clip_id(core)
    # Acquire the lease (the Mutation Gate requires it for any
    # non-GET request).
    sess_resp = client.post("/session/ensure", json={
        "actor": "human", "actor_id": "tester", "intent": "edit",
    })
    assert sess_resp.status_code == 200, sess_resp.text
    sess_id = sess_resp.json()["sessionId"]
    base_rev = sess_resp.json()["revision"]
    # POST /clips/{id}/speed — frame-native, body {speed, why}
    r = client.post(f"/clips/{cid}/speed",
                    params={"baseRevision": base_rev, "sessionId": sess_id},
                    json={"speed": 2.0, "why": "test"})
    assert r.status_code == 200, r.text
    # Now hit the at_frame endpoint.
    r = client.get(f"/clip/{cid}/timemap/at_frame", params={
        "timeline_frame": 100,
        "fps_num": 30, "fps_den": 1,
        "src_fps_num": 60, "src_fps_den": 1,
    })
    assert r.status_code == 200, r.text
    assert r.json()["source_frame"] == 400


def test_timemap_at_frame_unknown_clip_404(client_and_core):
    client, _ = client_and_core
    r = client.get("/clip/nonexistent/timemap/at_frame", params={
        "timeline_frame": 0,
        "fps_num": 30, "fps_den": 1,
        "src_fps_num": 60, "src_fps_den": 1,
    })
    assert r.status_code == 404


def test_timemap_static_endpoint_includes_source_fps(client_and_core):
    """The existing /clip/{id}/timemap endpoint must include both
    sequence_fps and source_fps in its response — the GUI cache
    relies on this."""
    client, core = client_and_core
    cid = _find_clip_id(core)
    r = client.get(f"/clip/{cid}/timemap", params={
        "fps_num": 30, "fps_den": 1,
        "src_fps_num": 60, "src_fps_den": 1,
    })
    assert r.status_code == 200
    data = r.json()
    assert data["sequence_fps"] == {"num": 30, "den": 1}
    assert data["source_fps"] == {"num": 60, "den": 1}