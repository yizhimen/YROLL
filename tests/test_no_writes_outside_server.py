"""GUI-01.5 architecture guard: the MCP server must not own a ProjectCore.

Per the user review:
> No code path outside ProjectServer may call ProjectCore.save_state()
> for a served project.

This is the single most load-bearing architectural property of GUI-01.5:
the MCP server is a thin HTTP client of the running YROLL Project
Server, NOT a ProjectCore owner. If anyone adds `ProjectCore(...)` or
`.save_state(...)` back into yroll/server/mcp_server.py, this test
fails and the regression is caught before it ships.

Note: the yroll/core/* internal modules (problems, publish, harness
runtime, jianying) DO call .save_state() — they are called by the
server itself, not by external writers. They are out of scope for this
guard. The guard's job is narrow: pin the mcp_server.py invariant.
"""
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MCP_SERVER = ROOT / "yroll" / "server" / "mcp_server.py"


def test_mcp_server_does_not_instantiate_projectcore():
    """mcp_server.py must not call ProjectCore(...). All project-state
    access goes through the HTTP client (yroll/mcp_http.py)."""
    src = MCP_SERVER.read_text(encoding="utf-8")
    offenders = []
    for i, line in enumerate(src.splitlines(), 1):
        if re.search(r"ProjectCore\s*\(", line):
            offenders.append((i, line.strip()[:80]))
    assert not offenders, (
        "GUI-01.5 invariant violated: mcp_server.py must not call "
        f"ProjectCore(...). Offenders: {offenders[:5]}"
    )


def test_mcp_server_does_not_call_save_state():
    """Same invariant for save_state()."""
    src = MCP_SERVER.read_text(encoding="utf-8")
    offenders = []
    for i, line in enumerate(src.splitlines(), 1):
        if re.search(r"\.save_state\s*\(", line):
            offenders.append((i, line.strip()[:80]))
    assert not offenders, (
        "GUI-01.5 invariant violated: mcp_server.py must not call "
        f"save_state(). Offenders: {offenders[:5]}"
    )


def test_mcp_server_does_not_import_commandlayer():
    """CommandLayer wraps a ProjectCore; importing it is the same
    violation as constructing ProjectCore directly. The MCP server
    routes all writes through YrollHttpClient.mutate() instead."""
    src = MCP_SERVER.read_text(encoding="utf-8")
    for bad in ("CommandLayer", "from yroll.core.commands",
                 "from yroll.core.project import ProjectCore"):
        assert bad not in src, (
            f"GUI-01.5 invariant violated: mcp_server.py imports "
            f"'{bad}'. MCP must use the HTTP client only."
        )


def test_mcp_http_is_the_only_network_entrypoint_in_mcp_server():
    """MCP server may talk to the network only via YrollHttpClient.
    No raw urllib / requests / httpx / socket calls."""
    src = MCP_SERVER.read_text(encoding="utf-8")
    for bad in ("urllib.request", "import requests", "import httpx",
                 "import socket", "urlopen(", "urlretrieve("):
        assert bad not in src, (
            f"mcp_server.py uses raw network library '{bad}'; "
            f"route all calls through yroll.mcp_http.YrollHttpClient "
            f"so the gate envelope is enforced uniformly."
        )
