"""Shared test fixtures.

Provides `client` (TestClient) and `authed_client` (auto-acquires lease + baseRevision).
Mutation endpoints now require sessionId + baseRevision; authed_client wraps the
TestClient to auto-attach them. Tests using bare `client` and expecting 200 on mutations
should switch to `authed_client`.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from yroll.core.manifest import Actor
from yroll.core.project import ProjectCore
from yroll.server.app import create_app


class _AuthedClient:
    """TestClient wrapper: each mutation call auto-acquires lease (if needed) and
    attaches sessionId + current baseRevision as query params.

    GET requests pass through untouched.
    """

    def __init__(self, raw: TestClient):
        self._raw = raw
        self._sid: str | None = None
        self._proj: str | None = None

    def _ensure_lease(self) -> tuple[str, int]:
        """Acquire (or re-acquire after project switch) lease; read live revision every call."""
        # Detect project switch: if current /project path differs from cached, re-acquire.
        try:
            proj = self._raw.get("/project").json()
            cur_proj = proj.get("path") or proj.get("name") or ""
        except Exception:
            cur_proj = ""
        if self._sid is None or cur_proj != self._proj:
            r = self._raw.post("/lease/acquire?actor=human&mode=edit&humanLabel=Test")
            if r.status_code == 200:
                self._sid = r.json()["sessionId"]
                self._proj = cur_proj
        ops = self._raw.get("/operations").json()
        rev = len(ops) if isinstance(ops, list) else 0
        return self._sid or "", int(rev)

    def _attach(self, url: str) -> str:
        from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
        sp = urlsplit(url)
        qs = dict(parse_qsl(sp.query, keep_blank_values=True))
        if "sessionId" not in qs or "baseRevision" not in qs:
            sid, rev = self._ensure_lease()
            qs.setdefault("sessionId", sid)
            qs.setdefault("baseRevision", str(rev))
        return urlunsplit(sp._replace(query=urlencode(qs)))

    def _attach_params(self, kw: dict, url: str) -> dict:
        """Merge sessionId + baseRevision into params. TestClient merges URL query
        and `params` kw with params taking precedence, so if user already provided
        baseRevision in URL we skip the auto-inject."""
        from urllib.parse import urlsplit, parse_qsl
        sid, rev = self._ensure_lease()
        existing = dict(parse_qsl(urlsplit(url).query, keep_blank_values=True))
        params = dict(kw.pop("params", None) or {})
        if "sessionId" not in existing and "sessionId" not in params:
            params["sessionId"] = sid
        # Always inject live baseRevision from server state.
        # (TestClient params will override URL query — desired for mutations.)
        # But preserve URL-provided baseRevision if user wants stale:
        if "baseRevision" not in existing and "baseRevision" not in params:
            params["baseRevision"] = str(rev)
        return {**kw, "params": params}

    def _wrap(self, method: str, url: str, **kw):
        if method.upper() in ("GET", "HEAD", "OPTIONS"):
            return getattr(self._raw, method.lower())(url, **kw)
        return getattr(self._raw, method.lower())(url, **self._attach_params(kw, url))

    # Generic pass-throughs
    def get(self, url, **kw):
        return self._raw.get(url, **kw)
    def post(self, url, **kw):
        return self._wrap("post", url, **kw)
    def delete(self, url, **kw):
        return self._wrap("delete", url, **kw)
    def put(self, url, **kw):
        return self._wrap("put", url, **kw)
    def patch(self, url, **kw):
        return self._wrap("patch", url, **kw)

    @property
    def raw(self) -> TestClient:
        return self._raw


@pytest.fixture()
def client(tmp_path: Path) -> TestClient:
    """Raw TestClient (no auto-lease). Use for tests that explicitly verify gate rejection."""
    core = ProjectCore.create(tmp_path, "api-demo")
    app = create_app(core.path, who=Actor.AI)
    return TestClient(app)


@pytest.fixture()
def authed_client(tmp_path: Path) -> _AuthedClient:
    """TestClient wrapper that auto-attaches sessionId + baseRevision to mutations."""
    core = ProjectCore.create(tmp_path, "api-demo")
    app = create_app(core.path, who=Actor.AI)
    return _AuthedClient(TestClient(app))
