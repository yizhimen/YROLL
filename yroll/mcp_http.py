"""GUI-01.5: HTTP client for the MCP server.

Per the GUI-01.5 spec, the MCP server is a *thin* HTTP client of a
running YROLL Project Server. It does not own a ProjectCore, it does
not maintain its own lease store, and it does not compute revision
itself. Every project-state write goes through this client, which:

  - injects sessionId + baseRevision into mutation requests (the same
    envelope the GUI uses; see gui/src/api.ts `mutate()`);
  - classifies the four Gate rejections (no_session, no_revision,
    lease_rejected, revision_conflict) into structured exceptions that
    the MCP tool dispatcher can handle uniformly;
  - exposes a heartbeat-loop helper for the McpServer lifecycle (per
    user review: heartbeat is started by .start(), not __init__).

urllib-only so MCP remains stdlib-clean and runnable in any subprocess
that `claude mcp add` spawns.
"""
from __future__ import annotations

import json
import time
import uuid
from typing import Any, Optional
from urllib import error as urlerror
from urllib import parse as urlparse
from urllib import request as urlrequest


class GateRejection(Exception):
    """The Mutation Gate refused a write. Carries the same `kind` codes
    the GUI's GateRejection uses (yroll/server/app.py) so the two sides
    agree on error semantics."""

    def __init__(self, kind: str, status: int, detail: str):
        super().__init__(detail)
        self.kind = kind
        self.status = status
        self.detail = detail


def _classify(status: int, detail: str) -> Optional[str]:
    if status == 409 or "revision mismatch" in detail or "revision conflict" in detail:
        return "revision_conflict"
    if status == 403 and "sessionId required" in detail:
        return "no_session"
    if status == 403 and "lease rejected" in detail:
        return "lease_rejected"
    if status == 400 and "baseRevision" in detail:
        return "no_revision"
    return None


class YrollHttpClient:
    """Thin HTTP client for a YROLL Project Server.

    `base_url` is e.g. "http://127.0.0.1:8765". All paths passed to
    `read`/`mutate` are joined onto this.
    """

    def __init__(self, base_url: str, *, timeout: float = 30.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    # ---- low-level ----
    def _request(self, method: str, path: str, body: Any = None,
                  params: Optional[dict] = None) -> Any:
        if "://" in path:
            url = path
        else:
            url = self.base_url + (path if path.startswith("/") else "/" + path)
        if params:
            url = url + "?" + urlparse.urlencode(params)
        data = None
        headers = {"Accept": "application/json"}
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = urlrequest.Request(url, data=data, method=method, headers=headers)
        try:
            with urlrequest.urlopen(req, timeout=self.timeout) as r:
                text = r.read().decode("utf-8", errors="replace")
        except urlerror.HTTPError as e:
            text = e.read().decode("utf-8", errors="replace")
            kind = _classify(e.code, text)
            if kind:
                raise GateRejection(kind, e.code, text)
            raise
        if not text:
            return None
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return text

    # ---- reads (no Gate) ----
    def read(self, path: str) -> Any:
        return self._request("GET", path)

    def ui_status(self, client_known_revision: Optional[int] = None) -> dict:
        params = {}
        if client_known_revision is not None:
            params["client_known_revision"] = client_known_revision
        return self._request("GET", "/ui/status", params=params or None)

    def get_lease(self) -> dict:
        return self._request("GET", "/lease")

    def events(self, since: int) -> dict:
        return self._request("GET", "/lease/events",
                              params={"since": since})

    # ---- lease / session ----
    def ensure_session(self, *, actor: str, actor_id: str, intent: str,
                        base_revision: int = -1) -> dict:
        return self._request("POST", "/session/ensure", body={
            "actor": actor, "actor_id": actor_id,
            "intent": intent, "base_revision": base_revision,
        })

    def request_lease(self, *, actor: str, actor_id: str, intent: str) -> dict:
        return self._request("POST", "/lease/request", body={
            "actor": actor, "actor_id": actor_id, "intent": intent,
        })

    def acquire_lease(self, *, actor: str, mode: str, base_revision: Optional[int],
                       human_label: str, actor_id: str = "") -> dict:
        params = {"actor": actor, "mode": mode, "humanLabel": human_label}
        if base_revision is not None:
            params["baseRevision"] = base_revision
        if actor_id:
            params["actorId"] = actor_id
        return self._request("POST", "/lease/acquire", params=params)

    def release_lease(self, session_id: str) -> dict:
        return self._request("POST", "/lease/release",
                              params={"sessionId": session_id})

    def heartbeat_lease(self, session_id: str) -> dict:
        return self._request("POST", "/lease/heartbeat",
                              params={"sessionId": session_id})

    def handoff_lease(self, from_session_id: str, *, to_actor: str,
                       to_mode: str, to_label: str,
                       to_actor_id: str = "") -> dict:
        params = {"fromSessionId": from_session_id, "toActor": to_actor,
                  "toMode": to_mode, "toLabel": to_label}
        if to_actor_id:
            params["toActorId"] = to_actor_id
        return self._request("POST", "/lease/handoff", params=params)

    # ---- mutations ----
    def mutate(self, method: str, path: str, body: Any = None,
                *, session_id: Optional[str], base_revision: int) -> Any:
        """Send a mutation with the Gate envelope.

        The sessionId + baseRevision come from the McpServer's session
        state, NOT from the caller of the tool. They are the only
        parameters that distinguish "I want to commit" from "I want to
        preview".
        """
        params = {"baseRevision": base_revision}
        if session_id:
            params["sessionId"] = session_id
        return self._request(method, path, body=body, params=params)

    def preview(self, mutation_body: dict, *, session_id: Optional[str],
                 base_revision: int) -> Any:
        """/mutation/preview is also Gate-gated; same envelope."""
        return self.mutate("POST", "/mutation/preview", body=mutation_body,
                           session_id=session_id, base_revision=base_revision)


def heartbeat_loop(client: YrollHttpClient, session_id_provider,
                    interval_sec: float = 60.0,
                    stop=None) -> None:
    """Background heartbeat. Calls `session_id_provider()` to get the
    current sessionId (which may rotate on resume), POSTs
    /lease/heartbeat, sleeps, repeats until `stop()` is truthy.

    Returns nothing — heartbeat failures are silent (next tick will
    succeed or the lease will TTL out).
    """
    while not (stop and stop()):
        sid = session_id_provider()
        if sid:
            try:
                client.heartbeat_lease(sid)
            except Exception:
                # network blip, lease may expire, the next acquire
                # round will resolve it. Never crash the heartbeat.
                pass
        # Sleep in small slices so shutdown is responsive.
        for _ in range(int(interval_sec)):
            if stop and stop():
                return
            time.sleep(1)
