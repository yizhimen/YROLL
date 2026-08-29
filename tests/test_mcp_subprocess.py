"""GUI-01.5 Scenario E: two real mcp_server.py subprocesses vs one
yroll serve. Exactly one Agent may hold EDIT at a time.

This is the only GUI-01.5 test that requires real OS subprocesses. It
is marked @pytest.mark.slow and skipped by default — opt in with
`pytest -m slow` or `pytest --runslow`. Run it when changing the
subprocess or server lifecycle; rely on the in-process TestClient
tests in test_mcp_cross_process.py for fast feedback.
"""
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest

from yroll.core.project import ProjectCore

pytestmark = pytest.mark.slow


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _wait_for_port(port: int, timeout: float = 10.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return True
        except OSError:
            time.sleep(0.1)
    return False


def _http_post(url: str, body: dict = None, params: dict = None) -> tuple:
    import urllib.request as r, urllib.parse as p, urllib.error as e
    full = url
    if params:
        full += "?" + p.urlencode(params)
    data = json.dumps(body).encode() if body is not None else None
    req = r.Request(full, data=data, method="POST",
                     headers={"Content-Type": "application/json"} if data else {})
    try:
        with r.urlopen(req, timeout=5) as resp:
            return resp.status, json.loads(resp.read() or "null")
    except e.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", errors="replace")


def _http_get(url: str, params: dict = None) -> tuple:
    import urllib.request as r, urllib.parse as p
    full = url
    if params:
        full += "?" + p.urlencode(params)
    with r.urlopen(full, timeout=5) as resp:
        return resp.status, json.loads(resp.read())


def test_two_mcp_subprocesses_cannot_both_hold_edit():
    """Two real `python -m yroll.server.mcp_server` processes racing
    for EDIT against one yroll serve: exactly one wins, the other
    falls back to observe.

    The "real subprocesses" part is what makes this different from
    the in-process TestClient tests: the GIL cannot hide cross-process
    lease races, and the in-memory LeaseStore is provably shared only
    because both clients hit the same server.
    """
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        # Set up a project
        ProjectCore.create(str(td), "subproc")
        proj = td / "subproc"

        # Start yroll serve in a real subprocess
        port = _free_port()
        url = f"http://127.0.0.1:{port}"
        env = {**os.environ,
                "PYTHONPATH": str(ROOT := Path(__file__).resolve().parents[1])}
        serve = subprocess.Popen(
            [sys.executable, "-c",
             "from yroll.cli.main import main; main()",
             "serve", str(proj), "--port", str(port)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
        try:
            assert _wait_for_port(port, timeout=15.0), \
                "yroll serve did not bind"
            # First MCP — should win EDIT
            mcp1 = subprocess.Popen(
                [sys.executable, "-c",
                 "from yroll.cli.main import main; main()",
                 "mcp", "--server", url, "--actor-id", "mcp-A"],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, env=env)
            try:
                time.sleep(2.0)  # let mcp1 do /session/ensure
                # Verify via the server: lease held by mcp-A
                st, lease = _http_get(url + "/lease")
                assert lease["heldBy"] == "agent", lease
                assert lease["actorId"] == "mcp-A", lease

                # Second MCP — should NOT steal; must land in observe
                mcp2 = subprocess.Popen(
                    [sys.executable, "-c",
                     "from yroll.cli.main import main; main()",
                     "mcp", "--server", url, "--actor-id", "mcp-B"],
                    stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE, env=env)
                try:
                    time.sleep(2.0)
                    # Server view: still held by mcp-A
                    st, lease2 = _http_get(url + "/lease")
                    assert lease2["heldBy"] == "agent", lease2
                    assert lease2["actorId"] == "mcp-A", lease2

                    # And mcp-B is parked (would be in the event log)
                    st, events = _http_get(
                        url + "/lease/events", params={"since": 0})
                    kinds = [e["kind"] for e in events["events"]]
                    assert "ensure_edit" in kinds, kinds
                    assert "ensure_parked" in kinds, kinds
                finally:
                    mcp2.terminate()
                    try:
                        mcp2.wait(timeout=3.0)
                    except subprocess.TimeoutExpired:
                        mcp2.kill()
            finally:
                mcp1.terminate()
                try:
                    mcp1.wait(timeout=3.0)
                except subprocess.TimeoutExpired:
                    mcp1.kill()
        finally:
            serve.terminate()
            try:
                serve.wait(timeout=3.0)
            except subprocess.TimeoutExpired:
                serve.kill()
