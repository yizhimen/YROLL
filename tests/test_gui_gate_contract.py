"""GUI-01: GUI → Core Mutation Gate contract.

Two halves:

1. A *static* guard over gui/src/api.ts. The point of the mutate()
   envelope (YROLL-Editor-Foundation-v0.2.md §二.2) is that adding a new
   mutation cannot silently skip the Gate. Without this test that promise
   is unenforced — commit 5ca70aa claimed "all 30+ mutations now route
   through mutate()" while mutate() in fact had zero call sites.

2. The *server* endpoints session.ts depends on. If /ui/status or
   /lease/heartbeat change shape, the GUI top bar goes blind and writes
   start failing with no explanation.
"""
import re
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pytest
from fastapi.testclient import TestClient

from yroll.core.project import ProjectCore
from yroll.server.app import create_app

API_TS = ROOT / "gui" / "src" / "api.ts"
SESSION_TS = ROOT / "gui" / "src" / "session.ts"
GUI_SRC = ROOT / "gui" / "src"

# Endpoints _MutationGateMiddleware lets through unauthenticated, so the
# client is allowed to call them with plain req(). Keep in sync with
# yroll/server/app.py.
GATE_EXEMPT = {
    "openProject",    # /project/open — can't hold a lease on an unopened project
    "newProject",     # /project/new
    "getLease",
    "acquireLease",
    "releaseLease",
    "heartbeatLease",
    "handoffLease",
    "mutationCheck",  # /mutation/check
}


@pytest.fixture
def client():
    td = Path(tempfile.mkdtemp())
    ProjectCore.create(str(td), "gui-gate-test")
    app = create_app(str(td / "gui-gate-test"))
    yield TestClient(app)
    shutil.rmtree(td, ignore_errors=True)


def _api_entries() -> dict[str, str]:
    """Split `export const api = {...}` into {name: source} chunks."""
    src = API_TS.read_text(encoding="utf-8")
    start = src.index("export const api = {")
    body = src[start:]
    # Entry names are `  name: (` at two-space indent inside the object.
    hits = list(re.finditer(r"^  (\w+):", body, re.MULTILINE))
    assert hits, "could not parse api.ts entries"
    out: dict[str, str] = {}
    for i, m in enumerate(hits):
        end = hits[i + 1].start() if i + 1 < len(hits) else len(body)
        out[m.group(1)] = body[m.start():end]
    return out


# --------------------------------------------------------------------------
# 1. Static guard: no mutation may bypass the envelope
# --------------------------------------------------------------------------

def test_no_mutation_bypasses_the_gate_envelope():
    """A write must go through mutate() or gated(), never bare req()."""
    offenders = []
    for name, chunk in _api_entries().items():
        if name in GATE_EXEMPT:
            continue
        writes = re.search(r"""method:\s*['"](POST|DELETE|PATCH|PUT)['"]""", chunk)
        gated = "mutate(" in chunk or "mutate<" in chunk \
            or "gated(" in chunk or "gated<" in chunk
        if writes and not gated:
            offenders.append(name)
    assert not offenders, (
        "these api.ts functions issue writes without the Mutation Gate; "
        f"route them through mutate(): {sorted(offenders)}"
    )


def test_gate_exempt_functions_are_actually_exempt_server_side(client):
    """The allowlist above must match the middleware, not just our belief."""
    # /project/open and /project/new are POSTs that must work with no lease.
    r = client.post("/project/new?root=%s&name=probe" % tempfile.mkdtemp())
    assert r.status_code != 403, f"/project/new should be gate-exempt: {r.text}"
    # /lease/* likewise, or you could never acquire a lease in the first place.
    assert client.post("/lease/acquire?actor=human&mode=edit").status_code != 403


def test_every_write_helper_lives_in_api_ts():
    """Components must not hand-roll fetch() writes around the envelope."""
    offenders = []
    for path in GUI_SRC.rglob("*.ts*"):
        if path.name in ("api.ts", "session.ts") or path.name.endswith(".test.ts"):
            continue
        text = path.read_text(encoding="utf-8")
        for m in re.finditer(r"""fetch\([^)]*method:\s*['"](POST|DELETE|PATCH|PUT)""",
                             text, re.DOTALL):
            offenders.append(f"{path.relative_to(ROOT)}: {m.group(0)[:60]}")
    assert not offenders, (
        "raw fetch() writes bypass the Mutation Gate: " + "; ".join(offenders))


def test_session_state_is_owned_by_session_ts_only():
    """§二.1: EditLease.tsx must not keep its own session/localStorage."""
    offenders = []
    for path in GUI_SRC.rglob("*.ts*"):
        if path.name in ("session.ts",) or path.name.endswith(".test.ts"):
            continue
        text = path.read_text(encoding="utf-8")
        if "localStorage" in text and "yroll.session" in text:
            offenders.append(str(path.relative_to(ROOT)))
        # The old EditLease kept a release-then-acquire poll loop.
        if "setInterval" in text and "acquireLease" in text:
            offenders.append(f"{path.relative_to(ROOT)} (lease poll loop)")
    assert not offenders, (
        "session state must live in session.ts only: " + ", ".join(offenders))


def test_chat_carries_the_gate_in_the_body_too():
    """The middleware reads query params; Task re-checks the body (audit §6.5)."""
    chunk = _api_entries()["chat"]
    assert "sessionId: currentGate().sessionId" in chunk
    assert "baseRevision: currentGate().baseRevision" in chunk


# --------------------------------------------------------------------------
# 2. Server contract session.ts depends on
# --------------------------------------------------------------------------

def test_ui_status_shape_matches_session_store(client):
    """session.ts reads exactly these fields off /ui/status."""
    st = client.get("/ui/status").json()
    for field in ("actor", "human_label", "agent_label", "session_id",
                  "alive", "base_revision", "conflict"):
        assert field in st, f"/ui/status lost `{field}`; session.ts reads it"
    assert st["actor"] == "free", "fresh project should have no lease"
    assert st["base_revision"] == 0


def test_ui_status_reports_conflict_against_client_revision(client):
    sid = client.post("/lease/acquire?actor=human&mode=edit").json()["sessionId"]
    client.post(f"/clips?sessionId={sid}&baseRevision=0", json={
        "asset_id": "nope", "source_start": 0, "source_end": 1,
        "timeline_start": 0, "track_id": "V1", "why": "probe",
    })
    current = client.get("/ui/status").json()["base_revision"]
    stale = client.get(f"/ui/status?client_known_revision={current + 5}").json()
    assert stale["conflict"] is True
    assert stale["actor"] == "conflict"
    fresh = client.get(f"/ui/status?client_known_revision={current}").json()
    assert fresh["conflict"] is False


def test_heartbeat_keeps_a_lease_without_releasing_it(client):
    """session.ts heartbeats instead of the old release-then-acquire race."""
    sid = client.post("/lease/acquire?actor=human&mode=edit").json()["sessionId"]
    assert client.post(f"/lease/heartbeat?sessionId={sid}").json()["ok"] is True
    # Same session still holds it — a release/re-acquire would mint a new id.
    assert client.get("/lease").json()["sessionId"] == sid


def test_multipart_asset_import_is_gated(client):
    """importAsset() previously used a bare fetch() and always 403'd."""
    r = client.post("/assets/import", files={"file": ("a.txt", b"x", "text/plain")})
    assert r.status_code == 403
    assert "sessionId required" in r.text


def test_chat_is_gated(client):
    r = client.post("/chat", json={"message": "hi"})
    assert r.status_code == 403
    assert "sessionId required" in r.text


def test_gate_rejection_details_match_what_the_gui_parses(client):
    """api.ts classifyGate() keys off these strings; don't drift them."""
    sid = client.post("/lease/acquire?actor=human&mode=edit").json()["sessionId"]

    no_session = client.post("/clips/x/speed", json={"speed": 2, "why": ""})
    assert no_session.status_code == 403
    assert "sessionId required" in no_session.text

    no_rev = client.post(f"/clips/x/speed?sessionId={sid}", json={"speed": 2, "why": ""})
    assert no_rev.status_code == 400
    assert "baseRevision" in no_rev.text

    bad_lease = client.post(
        "/clips/x/speed?sessionId=bogus&baseRevision=0", json={"speed": 2, "why": ""})
    assert bad_lease.status_code == 403
    assert "lease rejected" in bad_lease.text

    stale = client.post(
        f"/clips/x/speed?sessionId={sid}&baseRevision=99", json={"speed": 2, "why": ""})
    assert stale.status_code == 409
    assert "revision mismatch" in stale.text
