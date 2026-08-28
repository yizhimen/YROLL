"""P0-10 Edit Lease tests."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pytest
from fastapi.testclient import TestClient

from yroll.core.lease import (
    LeaseStore, LeaseMode, Actor as LeaseActor,
    LeaseError, LeaseConflictError, LeaseExpiredError,
    get_lease_store, get_current_revision,
)
from yroll.core.project import ProjectCore
from yroll.server.app import create_app


@pytest.fixture()
def app_client():
    import shutil, tempfile
    td = Path(tempfile.mkdtemp())
    proj = td / 'p'
    proj.mkdir()
    core = ProjectCore.create(str(td), 'p', intent={'goal': 'lease test'})
    app = create_app(str(proj))
    yield app, core
    shutil.rmtree(td, ignore_errors=True)


# Unit tests for LeaseStore
def test_lease_acquire_and_release():
    store = LeaseStore()
    assert store.get('p1') is None
    ls = store.acquire('p1', LeaseActor.HUMAN, LeaseMode.EDIT, 10, 'User')
    assert ls.session_id
    assert store.get('p1').actor == LeaseActor.HUMAN
    assert store.release('p1', ls.session_id) is True
    assert store.get('p1') is None


def test_lease_conflict_blocks_other_actor():
    store = LeaseStore()
    store.acquire('p1', LeaseActor.HUMAN, LeaseMode.EDIT, 10, 'User')
    with pytest.raises(LeaseConflictError):
        store.acquire('p1', LeaseActor.AGENT, LeaseMode.EDIT, 11, 'Claude')


def test_lease_handoff_atomic():
    store = LeaseStore()
    a = store.acquire('p1', LeaseActor.HUMAN, LeaseMode.EDIT, 10, 'User')
    b = store.handoff('p1', a.session_id, LeaseActor.AGENT, LeaseMode.EDIT, 'Claude')
    assert b.actor == LeaseActor.AGENT
    assert b.human_label == 'Claude'
    # Original session can no longer release (lease has moved on)
    assert store.release('p1', a.session_id) is False
    # But agent's session can
    assert store.release('p1', b.session_id) is True


def test_lease_handoff_rejects_wrong_session():
    store = LeaseStore()
    store.acquire('p1', LeaseActor.HUMAN, LeaseMode.EDIT, 10)
    with pytest.raises(LeaseError):
        store.handoff('p1', 'wrong-session', LeaseActor.AGENT, LeaseMode.EDIT)


def test_lease_expires():
    store = LeaseStore()
    lease = store.acquire('p1', LeaseActor.HUMAN, LeaseMode.EDIT, 0)
    lease.last_heartbeat -= 1000
    assert store.get('p1') is None


def test_lease_heartbeat_extends():
    store = LeaseStore()
    ls = store.acquire('p1', LeaseActor.HUMAN, LeaseMode.EDIT, 0)
    old = ls.last_heartbeat
    ls.last_heartbeat -= 100
    assert store.heartbeat('p1', ls.session_id) is True
    assert ls.last_heartbeat > old - 50


# HTTP API tests
def test_get_lease_initially_empty(app_client):
    app, _ = app_client
    client = TestClient(app)
    r = client.get('/lease')
    assert r.status_code == 200
    data = r.json()
    assert data['heldBy'] is None
    assert 'baseRevision' in data


def test_acquire_and_release_via_http(app_client):
    app, _ = app_client
    client = TestClient(app)
    r = client.post('/lease/acquire?actor=human&mode=edit&humanLabel=User')
    assert r.status_code == 200
    sid = r.json()['sessionId']
    r = client.get('/lease')
    assert r.json()['heldBy'] == 'human'
    r = client.post(f'/lease/release?sessionId={sid}')
    assert r.json()['ok'] is True


def test_http_acquire_conflict_returns_409(app_client):
    app, _ = app_client
    client = TestClient(app)
    client.post('/lease/acquire?actor=human&mode=edit')
    r = client.post('/lease/acquire?actor=agent&mode=edit')
    assert r.status_code == 409
    assert 'currently held' in r.json()['detail']


def test_http_handoff_releases_previous_session(app_client):
    app, _ = app_client
    client = TestClient(app)
    a = client.post('/lease/acquire?actor=human&mode=edit&humanLabel=User').json()
    b = client.post(f'/lease/handoff?fromSessionId={a["sessionId"]}&toActor=agent&toLabel=Claude').json()
    assert b['actor'] == 'agent'
    assert b['humanLabel'] == 'Claude'
    r = client.post('/lease/acquire?actor=human&mode=edit')
    assert r.status_code == 409


def test_mutation_check_returns_current_revision(app_client):
    app, core = app_client
    client = TestClient(app)
    initial_rev = get_current_revision(core)
    # mutation/check is exempt from gate
    r = client.post(f'/mutation/check?baseRevision={initial_rev}')
    assert r.json()['ok'] is True
    # Acquire lease then add a track to bump revision (gate needs sessionId)
    s = client.post('/lease/acquire?actor=human&mode=edit').json()
    sid = s['sessionId']
    # TestClient merges URL query + params, with params taking precedence.
    # To preserve sessionId+baseRevision in URL, put them in params too.
    r = client.post(
        f'/tracks',
        params={'sessionId': sid, 'baseRevision': initial_rev,
                'kind': 'video', 'track_id': 't_test'})
    assert r.status_code == 200
    # Now mutation/check with stale revision should report mismatch
    r = client.post(f'/mutation/check?baseRevision={initial_rev}')
    assert r.json()['ok'] is False
    assert r.json()['currentRevision'] == initial_rev + 1
