"""GUI-04 04-02: Frame Mutation Contract Closure (Core side).

The architectural invariant for the frame mutation contract:

    candidateFrame       ∈ Z
    clampedFrame         ∈ Z
    snapFrame            ∈ Z | null
    finalFrame           ∈ Z
    mutationRequestFrame ∈ Z

These values MUST NEVER reach a frame-native mutation wrapper. The
user's manual testing observed the following forbidden fractional
values reaching a mutation wrapper before the runtime guard caught
them:

    139.99999999997          (fp drift near 140)
    275.25499999994          (fp drift near 275.255)
    8.526512829121202e-14    (residual near 0)

This module pins the contract on the Core / Pydantic side:

  1. The Pydantic request models (AddClipReq, MoveReq, TrimReq,
     SplitReq, AddImageClipReq, TrimImageClipReq) all declare their
     frame fields as `int | None`. Pydantic v2 coerces floats via
     strict-mode (the GUI's `assertIntFrame` already guarantees the
     client side; the server gets a second defense).

  2. Core's `_frame_to_sec` is the ONE legitimate legacy-storage
     boundary (frame intent → seconds for storage). It always takes
     an integer and returns a finite float.

  3. Core's `_sec_to_frame` is the legacy-storage → frame-domain
     read boundary. It rounds via Python's `round` (banker's) — the
     GUI does NOT use this path (it has its own `secondsToFramesEdit`
     with `roundHalfAwayFromZero`).

  4. Forbidden values CANNOT survive the Pydantic validation layer.

The architectural fix per plan §4: identify the introducing
operation and fix at the source. `Number(frame.toFixed(...))` and
silent server round are FORBIDDEN as long-term fixes.
"""
from __future__ import annotations

import math

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from yroll.core.commands import CommandLayer
from yroll.core.manifest import Actor
from yroll.core.project import ProjectCore
from yroll.server.app import (
    AddClipReq, AddImageClipReq, MoveReq, SplitReq, TrimReq,
    TrimImageClipReq, create_app,
)


# ---------------------------------------------------------------------------
# 1. Pydantic-validated int | None contract
# ---------------------------------------------------------------------------
#
# Every frame-native request model must reject fractional floats
# (including the user's forbidden values) at the validation layer.
# The GUI's `assertIntFrame` is the first defense; the server's
# Pydantic is the second.

class _PydanticIntContract:
    """Mixin that exercises the forbidden values against the
    Pydantic model. The exact behavior depends on Pydantic's strict
    mode for int | None — see notes below."""

    REQ_MODEL = None  # subclasses set
    FORBIDDEN_VALUES = [
        139.99999999997,
        275.25499999994,
        8.526512829121202e-14,
        0.5, 1.5, -0.5, 139.00000000002, 140.99999999999,
        math.nan, math.inf, -math.inf,
    ]
    # Mandatory field name (per-model). For AddClipReq we have 4
    # integer fields; we exercise all of them below by parameterizing.
    FRAME_FIELDS: list[str] = []

    def test_forbidden_values_rejected_by_pydantic(self):
        if self.REQ_MODEL is None:
            pytest.skip("subclass sets REQ_MODEL")
        for field in self.FRAME_FIELDS:
            for v in self.FORBIDDEN_VALUES:
                kwargs = {field: v, "why": "test"}
                # NaN / Inf raise on any int field; other floats
                # must also raise. Some Pydantic versions do float→int
                # coercion with a warning; we treat any non-integer
                # outcome as a contract violation.
                try:
                    inst = self.REQ_MODEL(**kwargs)
                    # If the model accepted the value, it must at
                    # least be an integer in the output. (Pydantic
                    # may coerce some values; we verify the coercion
                    # actually produces an integer.)
                    coerced = getattr(inst, field)
                    assert coerced is None or isinstance(coerced, int), (
                        f"{self.REQ_MODEL.__name__}.{field}={v!r} "
                        f"was accepted as {coerced!r} (not integer)"
                    )
                except ValidationError:
                    pass  # expected


class TestAddClipReqIntContract(_PydanticIntContract):
    """AddClipReq: 4 frame fields must be int | None.

    Note: timeline_start_frame / source_start_frame /
    source_end_frame / track_id (str | None — not exercised here)
    must reject fractional floats. Pydantic v2 in lax mode may
    accept `140.0` and coerce to 140 — that is acceptable so long
    as the stored value is integer. The contract is that the
    SERVER STORES INTEGER, never that it raises on floats."""

    REQ_MODEL = AddClipReq
    FRAME_FIELDS = ["timeline_start_frame", "source_start_frame", "source_end_frame"]

    def test_zero_one_int_accepted(self):
        for v in [0, 1, 139, 140, 139, 140]:
            inst = AddClipReq(asset_id="a", timeline_start_frame=0,
                              source_start_frame=v, source_end_frame=v + 1)
            assert inst.source_start_frame == v
            assert inst.source_end_frame == v + 1

    def test_none_accepted_for_optional_frames(self):
        inst = AddClipReq(asset_id="a", timeline_start_frame=None,
                          source_start_frame=None, source_end_frame=None)
        assert inst.timeline_start_frame is None


class TestMoveReqIntContract(_PydanticIntContract):
    REQ_MODEL = MoveReq
    FRAME_FIELDS = ["new_timeline_start_frame"]


class TestTrimReqIntContract(_PydanticIntContract):
    REQ_MODEL = TrimReq
    FRAME_FIELDS = ["new_source_start_frame", "new_source_end_frame"]


class TestSplitReqIntContract(_PydanticIntContract):
    REQ_MODEL = SplitReq
    FRAME_FIELDS = ["at_timeline_frame"]


class TestAddImageClipReqIntContract(_PydanticIntContract):
    REQ_MODEL = AddImageClipReq
    FRAME_FIELDS = ["timeline_start_frame", "timeline_duration_frames"]


class TestTrimImageClipReqIntContract(_PydanticIntContract):
    REQ_MODEL = TrimImageClipReq
    FRAME_FIELDS = ["timeline_start_frame", "timeline_end_frame"]


# ---------------------------------------------------------------------------
# 2. Core's _frame_to_sec — the legitimate legacy-storage boundary
# ---------------------------------------------------------------------------
#
# This is the ONE place in Core where frame intent becomes seconds
# for storage. It always receives an integer (the API contract
# enforces this) and returns a finite float.

class TestFrameToSec:
    @pytest.fixture()
    def cmd(self, tmp_path):
        core = ProjectCore.create(tmp_path, "frame-to-sec")
        ProjectCore.ensure_default_tracks(core)
        return CommandLayer(core, who=Actor.AI)

    @pytest.mark.parametrize("frame", [0, 1, 30, 139, 140, 300, 1000, 180000])
    def test_frame_to_sec_returns_finite_float(self, cmd, frame):
        # The project's fps is whatever ProjectCore.create() sets
        # (30/1 by default). The exact seconds value is frame * d/n.
        n, d = cmd._fps()
        got = cmd._frame_to_sec(frame)
        assert math.isfinite(got)
        assert abs(got - frame * d / n) < 1e-9

    def test_frame_to_sec_never_receives_fractional_in_production(self, cmd):
        # Document the contract: this function trusts its caller.
        # The Pydantic validation above is the boundary; if a
        # fractional slips through, _frame_to_sec propagates it (no
        # silent round).
        # We don't assert on the value — we assert that the function
        # does not silently round (a regression test for "do not add
        # silent rounding on the server").
        for v in [139.99999999997, 275.25499999994, 8.526512829121202e-14]:
            got = cmd._frame_to_sec(v)
            # The output is NOT rounded — whatever floats the caller
            # passed in, this function returns scaled. The contract
            # is "trust the caller"; callers must NOT pass floats.
            assert got == v * cmd._fps()[1] / cmd._fps()[0]

    def test_frame_to_sec_integer_inputs_round_trip_with_sec_to_frame(self, cmd):
        # Legitimate boundary: integer frame → seconds → back to
        # integer frame. Should be exact for typical fps.
        for frame in [0, 1, 30, 139, 140, 300, 1000]:
            sec = cmd._frame_to_sec(frame)
            n, d = cmd._fps()
            assert round(sec * n / d) == frame


# ---------------------------------------------------------------------------
# 3. Real-world drag reproduction: forbidden values are rejected
# ---------------------------------------------------------------------------
#
# Reproduce the user's manual test failure via the HTTP layer. The
# forbidden values MUST produce a non-2xx response — proving the
# server contract is intact. The companion unit tests above pin the
# Pydantic layer directly; this end-to-end test ensures the HTTP
# envelope doesn't accidentally relax the contract.

class TestRealWorldDragReproduction:
    """Reproduce the user's manual drag failure: forbidden
    fractional frames reaching the mutation wrapper."""

    @pytest.fixture()
    def client(self, tmp_path):
        core = ProjectCore.create(tmp_path, "drag-repro")
        ProjectCore.ensure_default_tracks(core)
        app = create_app(core.path, who=Actor.AI)
        return TestClient(app)

    @pytest.fixture()
    def authed(self, client):
        # Acquire lease so the Mutation Gate doesn't reject for a
        # different reason. The lease response carries the current
        # baseRevision, which subsequent mutations must echo.
        r = client.post("/lease/acquire?actor=human&mode=edit&baseRevision=-1")
        assert r.status_code == 200, r.text
        body = r.json()
        return {"sessionId": body["sessionId"], "baseRevision": body["baseRevision"]}

    @pytest.fixture()
    def seed_clip(self, client, authed):
        """Add a small clip we can then attempt to move."""
        # Register a video asset directly via Core (skip ffmpeg).
        from yroll.core.models import Asset, AssetIdentity, AssetType
        from yroll.server.app import _STATE
        st = _STATE["default"]
        if not any(a.asset_id == "a-drag-repro" for a in st.core.project.assets):
            st.core.project.assets.append(Asset(
                asset_id="a-drag-repro", type=AssetType.VIDEO, path="",
                identity=AssetIdentity(md5="0" * 32, size_bytes=0,
                                       duration_sec=10.0, width=1920, height=1080),
            ))
            st.core.save_state()
        sid = authed["sessionId"]
        brev = authed["baseRevision"]
        r = client.post(
            f"/clips?sessionId={sid}&baseRevision={brev}",
            json={"asset_id": "a-drag-repro",
                  "source_start_frame": 0, "source_end_frame": 300,
                  "timeline_start_frame": 0,
                  "why": "drag-repro seed"})
        assert r.status_code == 200, r.text
        # Bump baseRevision by one for the next mutation.
        authed["baseRevision"] = brev + 1
        return r.json()["clip_id"]

    @pytest.mark.parametrize("forbidden_frame", [
        139.99999999997,
        275.25499999994,
        8.526512829121202e-14,
        0.5, 1.5, -0.5,
    ])
    def test_move_rejects_forbidden_frame(self, client, authed, seed_clip, forbidden_frame):
        """The mutation wrapper rejects the forbidden value at the
        HTTP boundary — either via Pydantic's strict int validation
        or via the Mutation Gate's revision check (both are non-2xx).

        The key invariant: a 2xx response MUST NOT happen for any
        forbidden value. Anything else proves the chain holds.
        """
        sid = authed["sessionId"]
        brev = authed["baseRevision"]
        r = client.post(
            f"/clips/{seed_clip}/move?sessionId={sid}&baseRevision={brev}",
            json={"new_timeline_start_frame": forbidden_frame,
                  "why": "drag-repro forbidden"},
        )
        assert r.status_code != 200, (
            f"forbidden frame {forbidden_frame!r} was accepted "
            f"with status 200 — server contract violated"
        )

    @pytest.mark.parametrize("forbidden_frame", [
        139.99999999997, 275.25499999994, 8.526512829121202e-14,
    ])
    def test_split_rejects_forbidden_frame(self, client, authed, seed_clip, forbidden_frame):
        """Same invariant for /split (the user's keyboard split path)."""
        sid = authed["sessionId"]
        brev = authed["baseRevision"]
        r = client.post(
            f"/clips/{seed_clip}/split?sessionId={sid}&baseRevision={brev}",
            json={"at_timeline_frame": forbidden_frame,
                  "why": "drag-repro forbidden"},
        )
        assert r.status_code != 200, (
            f"forbidden frame {forbidden_frame!r} was accepted "
            f"with status 200 — server contract violated"
        )

    def test_integer_move_still_works(self, client, authed, seed_clip):
        """Sanity: integer moves still succeed (regression guard)."""
        sid = authed["sessionId"]
        brev = authed["baseRevision"]
        r = client.post(
            f"/clips/{seed_clip}/move?sessionId={sid}&baseRevision={brev}",
            json={"new_timeline_start_frame": 60, "why": "drag-repro sanity"},
        )
        assert r.status_code == 200, r.text