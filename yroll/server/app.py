"""YROLL Server：把 Command Layer 暴露为 HTTP API。

定位：GUI、手机端、外部 Agent（未来的 MCP）都调这层，
层下只有一个 CommandLayer —— 保证"人机共用同一套编辑指令"。

    yroll serve <工程目录> --port 8765
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, UploadFile, WebSocket, Body, Query
from pydantic import BaseModel
import uuid as _uuid

from yroll.core.commands import CommandError, CommandLayer
from yroll.core.manifest import Actor, Region, TimeRange
from yroll.core.lease import (
    LeaseStore, LeaseMode, Actor as LeaseActor,
    LeaseError, LeaseConflictError, LeaseExpiredError,
    get_lease_store, require_edit_right, require_capable,
    get_current_revision, check_revision_match,
)
from yroll.core.lease_events import get_lease_event_log, LeaseEvent
from yroll.core.revision import (
    RevisionConflictError as ProjectRevisionConflict,
    check_project_revision,
)
from yroll.core.project import ProjectCore


def _ranged_file_response(path: Path, request: Request):
    """支持 Range 的文件响应（HTML5 <video> seek 必需）。"""
    import mimetypes

    from fastapi.responses import FileResponse, StreamingResponse

    size = path.stat().st_size
    ctype = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
    range_header = request.headers.get("range")
    if not range_header:
        return FileResponse(path, media_type=ctype)
    try:
        _, rng = range_header.split("=")
        start_s, end_s = rng.split("-")
        start = int(start_s)
        end = int(end_s) if end_s else size - 1
    except ValueError:
        start, end = 0, size - 1
    end = min(end, size - 1)
    length = end - start + 1

    def stream():
        with path.open("rb") as f:
            f.seek(start)
            remaining = length
            while remaining > 0:
                chunk = f.read(min(1 << 20, remaining))
                if not chunk:
                    break
                remaining -= len(chunk)
                yield chunk

    return StreamingResponse(
        stream(), status_code=206, media_type=ctype,
        headers={
            "Content-Range": f"bytes {start}-{end}/{size}",
            "Accept-Ranges": "bytes",
            "Content-Length": str(length),
        })


class TrimReq(BaseModel):
    # GUI-02: frame-native. Seconds fields are removed; the server
    # rejects requests with the old field names.
    new_source_start_frame: int | None = None
    new_source_end_frame: int | None = None
    why: str = ""


class MoveReq(BaseModel):
    new_timeline_start_frame: int
    new_track_id: str | None = None
    why: str = ""


class SpeedReq(BaseModel):
    speed: float
    why: str = ""


class VolumeReq(BaseModel):
    volume: float
    why: str = ""
    time_range: TimeRange | None = None


class SplitReq(BaseModel):
    # GUI-02: at is in TIMELINE frame coordinates. The Core's TimeMap
    # converts to source frame internally.
    at_timeline_frame: int
    why: str = ""


class AddClipReq(BaseModel):
    asset_id: str
    source_start: float
    source_end: float
    timeline_start: float
    track_id: str = "v1"
    why: str = ""


class AddImageClipReq(BaseModel):
    """GUI-03B: add an image clip with frame-native coordinates."""
    asset_id: str
    timeline_start_frame: int
    timeline_duration_frames: int
    track_id: str = "v1"
    why: str = ""


class TrimImageClipReq(BaseModel):
    """GUI-03B: trim an image clip's on-screen duration in frames."""
    timeline_start_frame: int | None = None
    timeline_end_frame: int | None = None
    why: str = ""


class AdjustReq(BaseModel):
    kind: str
    params: dict = {}
    time_range: TimeRange | None = None
    region: Region | None = None
    why: str = ""


class RevertReq(BaseModel):
    operation_id: str
    why: str = ""


class ChatReq(BaseModel):
    message: str
    selected_clip: str | None = None
    playhead: float | None = None
    sessionId: str | None = None
    baseRevision: int | None = None


# GUI-01.5: request schemas for /session/ensure and /lease/request.
# Module-level so Pydantic can resolve the ForwardRef. create_app()
# uses these via Body(...) below.
class SessionEnsureReq(BaseModel):
    actor: str = "agent"
    actor_id: str = ""
    intent: str = "edit"   # edit | propose | observe
    base_revision: int = -1


class LeaseRequestReq(BaseModel):
    actor: str = "agent"
    actor_id: str = ""
    intent: str = "edit"


class ProblemReq(BaseModel):
    description: str
    category: str  # temporal/audio/text/visual/spatial_object/semantic/consistency
    target_clip: str | None = None
    time_range: TimeRange | None = None
    region: Region | None = None


class RecommendReq(BaseModel):
    problem_id: str


class ExecuteReq(BaseModel):
    solution_id: str


class _State:
    """可变工程状态：支持运行中打开/新建工程（多工程管理）。"""

    def __init__(self, core: ProjectCore, who: Actor):
        self.who = who
        self.set(core)

    def set(self, core: ProjectCore) -> None:
        self.core = core
        self.cmd = CommandLayer(core, who=self.who)

    def open(self, path: str | Path) -> None:
        core = ProjectCore.open(path)
        # 老工程自动补齐缺失的默认轨道（v2/v3/a2/a3/t2）
        ProjectCore.ensure_default_tracks(core)
        self.set(core)

    def new(self, root: str | Path, name: str, intent: dict | None = None) -> None:
        self.set(ProjectCore.create(root, name, intent=intent))


class _MutationGateMiddleware:
    """Unified gate: every non-GET mutation must pass Lease + Revision."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            await self.app(scope, receive, send)
            return
        method = scope['method'].upper()
        path = scope['path']
        if method in ('GET', 'HEAD', 'OPTIONS'):
            await self.app(scope, receive, send)
            return
        if path.startswith('/lease') or path == '/mutation/check':
            await self.app(scope, receive, send)
            return
        # GUI-01.5: /mutation/preview is a read despite being POST — it
        # never logs an operation, never advances revision, never writes
        # state. The Mutation Gate would refuse it for observe-mode
        # callers (who need it most), so it is exempt. The handler is
        # still responsible for not mutating.
        if path == '/mutation/preview':
            await self.app(scope, receive, send)
            return
        # GUI-02: /snap is a read despite being POST — it never writes
        # state. The handler runs Core's SnapEngine and returns the
        # result without logging an operation.
        if path == '/snap':
            await self.app(scope, receive, send)
            return
        if path == '/session/ensure':
            await self.app(scope, receive, send)
            return
        # 工程生命周期管理：初始化/切换无需 lease（创建新工程本身不可能持有该工程的 lease）
        if path in ('/project/new', '/project/open', '/project'):
            await self.app(scope, receive, send)
            return
        from starlette.responses import JSONResponse
        from urllib.parse import parse_qs
        qs = parse_qs((scope.get('query_string') or b'').decode('utf-8', errors='replace'))
        session_id = (qs.get('sessionId') or [''])[0]
        base_rev_raw = (qs.get('baseRevision') or [''])[0]
        try:
            base_rev = int(base_rev_raw) if base_rev_raw else None
        except (TypeError, ValueError):
            base_rev = None
        st = _STATE.get('default')
        if st is None:
            response = JSONResponse({'detail': 'server state unavailable'}, status_code=500)
            await response(scope, receive, send)
            return
        if not session_id:
            response = JSONResponse({'detail': 'sessionId required for mutations (call /lease/acquire first)'}, status_code=403)
            await response(scope, receive, send)
            return
        if base_rev is None:
            response = JSONResponse({'detail': 'baseRevision query param required for mutations'}, status_code=400)
            await response(scope, receive, send)
            return
        try:
            from yroll.core.lease import require_edit_right
            require_edit_right(st.core, session_id)
        except Exception as e:
            response = JSONResponse({'detail': f'lease rejected: {e}'}, status_code=403)
            await response(scope, receive, send)
            return
        try:
            from yroll.core.revision import check_project_revision as _cpr
            _cpr(st.core, base_rev)
        except Exception as e:
            response = JSONResponse({'detail': f'revision conflict: {e}'}, status_code=409)
            await response(scope, receive, send)
            return
        await self.app(scope, receive, send)


# Global state for middleware lookup
_STATE: dict = {}

def create_app(project_path: str | Path, who: Actor = Actor.HUMAN) -> FastAPI:
    core = ProjectCore.open(project_path)
    ProjectCore.ensure_default_tracks(core)  # 老工程补齐默认轨道
    st = _State(core, who)
    _STATE.clear()
    _STATE["default"] = st
    app = FastAPI(title="YROLL Server", version="0.1.0")
    app.add_middleware(_MutationGateMiddleware)
    # GUI-01 smoke test loads the built bundle from disk (file://) and
    # calls the API at 127.0.0.1:8765 — different origins. Permissive CORS
    # is fine: the server only binds to localhost in this dev workflow.
    try:
        from fastapi.middleware.cors import CORSMiddleware
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"], allow_methods=["*"],
            allow_headers=["*"], allow_credentials=False,
        )
    except ImportError:  # pragma: no cover
        pass

    @app.post("/project/open")
    def open_project(path: str):
        try:
            st.open(path)
        except FileNotFoundError as e:
            raise HTTPException(404, f"工程不存在: {path}") from e
        return {"project": st.core.project.name, "path": str(st.core.path)}

    @app.post("/project/new")
    def new_project(root: str, name: str, goal: str = ""):
        intent = {"goal": goal} if goal else {}
        st.new(root, name, intent=intent)
        return {"project": st.core.project.name, "path": str(st.core.path)}

    def guard(fn):
        try:
            return fn()
        except CommandError as e:
            raise HTTPException(400, str(e)) from e

    def require_revision(fn):
        """Wrap mutation: verify baseRevision query param matches server, else 409."""
        def _do(*args, **kwargs):
            base_rev = kwargs.pop('baseRevision', None)
            # args/kwargs may have baseRevision for endpoints that take it
            if base_rev is None and len(args) > 0 and isinstance(args[0], (int, float)):
                # Try to read from query-like position
                pass
            return fn(*args, **kwargs)
        return _do

    def _check_rev(baseRevision, fn):
        """Decorator-equivalent: check revision before calling fn, return 409 on conflict."""
        def _do(*args, **kwargs):
            if baseRevision is not None:
                try:
                    check_project_revision(st.core, baseRevision)
                except ProjectRevisionConflict as e:
                    raise HTTPException(409, str(e)) from e
            return fn(*args, **kwargs)
        return _do


    @app.get("/project")
    def get_project():
        return st.core.project

    # ----------------------------------------------------------------
    # GUI-02.3: Media conformance — gate-exempt (read-only).
    # ----------------------------------------------------------------
    @app.get("/project/validate_media_conformance")
    def validate_media_conformance():
        """Return AssetConformanceResult for every asset.

        Read-only — does NOT mutate project state. The GUI uses
        this to display "frame-editable" badges per clip and to
        warn the user before touching clips whose assets are
        VFR / FPS-mismatched / unknown-source.
        """
        from yroll.core.models import AssetConformanceResult
        results = st.core.project.validate_media_conformance()
        return {
            "sequence_fps": {
                "num": st.core.project.sequence.fps.num,
                "den": st.core.project.sequence.fps.den,
            },
            "results": [
                {
                    "asset_id": r.asset_id,
                    "status": r.status,
                    "reason": r.reason,
                    "sequence_fps": {
                        "num": r.sequence_fps.num, "den": r.sequence_fps.den,
                    },
                    "source_fps": (
                        {"num": r.source_fps.num, "den": r.source_fps.den}
                        if r.source_fps is not None else None
                    ),
                    "source_is_cfr": r.source_is_cfr,
                    "recommended_action": r.recommended_action,
                }
                for r in results
            ],
            "frame_editable_asset_ids": [
                r.asset_id for r in results if r.is_frame_editable
            ],
            "unsupported_asset_ids": [
                r.asset_id for r in results if not r.is_frame_editable
            ],
        }

    @app.get("/operations")
    def get_operations():
        return st.core.operations()

    @app.get("/costs")
    def costs():
        """成本聚合（蓝图 §2.9/§6：每条 Operation 的 cost 按工具/角色/路由汇总）。"""
        by_tool: dict[str, dict] = {}
        by_who: dict[str, float] = {}
        total = 0.0
        for o in st.core.operations():
            c = o.cost or 0.0
            total += c
            tool = o.tool or o.type
            e = by_tool.setdefault(tool, {"count": 0, "cost": 0.0})
            e["count"] += 1
            e["cost"] = round(e["cost"] + c, 4)
            who = o.who.value if hasattr(o.who, "value") else str(o.who)
            by_who[who] = round(by_who.get(who, 0.0) + c, 4)
        return {"total": round(total, 2), "currency": "CNY",
                "by_tool": by_tool, "by_who": by_who}

    @app.post("/versions")
    def commit(note: str = ""):
        return st.core.commit(note=note)

    @app.get("/versions")
    def versions():
        return st.core.versions()

    @app.post("/clips")
    def add_clip(req: AddClipReq, sessionId: str = "", baseRevision: int = None):
        def _do():
            if sessionId:
                require_edit_right(st.core, sessionId)
            return st.cmd.add_clip(**req.model_dump())
        return guard(_check_rev(baseRevision, _do))

    @app.post("/clips/add_image")
    def add_image_clip(req: AddImageClipReq, sessionId: str = "",
                        baseRevision: int = None):
        """GUI-03B: add an IMAGE clip with frame-native coordinates.

        Body: {asset_id, timeline_start_frame, timeline_duration_frames,
        track_id?, why?}. The image's source range is fixed at
        (0, 1/seq_fps); the timeline duration is user-controlled.
        """
        def _do():
            if sessionId:
                require_edit_right(st.core, sessionId)
            return st.cmd.add_image_clip(
                asset_id=req.asset_id,
                timeline_start_frame=req.timeline_start_frame,
                timeline_duration_frames=req.timeline_duration_frames,
                track_id=req.track_id,
                why=req.why,
            )
        return guard(_check_rev(baseRevision, _do))

    @app.post("/clips/{clip_id}/trim_image")
    def trim_image_clip(clip_id: str, req: TrimImageClipReq,
                        sessionId: str = "", baseRevision: int = None):
        """GUI-03B: trim an IMAGE clip's on-screen duration.

        Body: {timeline_start_frame?, timeline_end_frame?, why?}.
        Image source side is NOT adjustable (1-frame source range).
        """
        def _do():
            if sessionId:
                require_edit_right(st.core, sessionId)
            return st.cmd.trim_image_clip_frame(
                clip_id,
                timeline_start_frame=req.timeline_start_frame,
                timeline_end_frame=req.timeline_end_frame,
                why=req.why,
            )
        return guard(_check_rev(baseRevision, _do))

    @app.post("/tracks")
    def add_track(kind: str, track_id: str | None = None):
        from yroll.core.manifest import TrackKind

        return guard(lambda: st.cmd.add_track(TrackKind(kind), track_id))

    @app.post("/tracks/{track_id}/mute")
    def track_mute(track_id: str, muted: bool = True, why: str = ""):
        return guard(lambda: st.cmd.set_track_muted(track_id, muted, why=why))

    @app.post("/tracks/{track_id}/lock")
    def track_lock(track_id: str, locked: bool = True, why: str = ""):
        return guard(lambda: st.cmd.set_track_locked(track_id, locked, why=why))

    @app.post("/tracks/{track_id}/hide")
    def track_hide(track_id: str, hidden: bool = True, why: str = ""):
        return guard(lambda: st.cmd.set_track_hidden(track_id, hidden, why=why))

    @app.post("/clips/{clip_id}/transform")
    def set_transform(clip_id: str, transform: dict, why: str = ""):
        return guard(lambda: st.cmd.set_transform(clip_id, transform, why=why))

    @app.post("/clips/{clip_id}/color")
    def set_color(clip_id: str, params: dict, why: str = ""):
        return guard(lambda: st.cmd.set_color(clip_id, **params, why=why))

    @app.post("/clips/{clip_id}/flip")
    def flip(clip_id: str, horizontal: bool = False, vertical: bool = False,
             why: str = ""):
        return guard(lambda: st.cmd.set_flip(clip_id, horizontal, vertical, why=why))

    @app.post("/clips/{clip_id}/opacity")
    def opacity(clip_id: str, opacity: float, why: str = ""):
        return guard(lambda: st.cmd.set_opacity(clip_id, opacity, why=why))

    @app.post("/clips/{clip_id}/crop")
    def crop(clip_id: str, left: float = 0, top: float = 0,
             right: float = 0, bottom: float = 0, why: str = ""):
        return guard(lambda: st.cmd.set_crop(clip_id, left, top, right, bottom, why=why))

    @app.post("/clips/{clip_id}/reverse")
    def reverse(clip_id: str, why: str = ""):
        return guard(lambda: st.cmd.set_reverse(clip_id, why=why))

    @app.post("/clips/{clip_id}/transform2d")
    def transform2d(clip_id: str, params: dict, why: str = ""):
        return guard(lambda: st.cmd.set_transform2d(clip_id, **params, why=why))

    @app.post("/clips/{clip_id}/reset-visual")
    def reset_visual(clip_id: str, why: str = ""):
        return guard(lambda: st.cmd.set_color2_reset(clip_id, why=why))

    @app.post("/clips/{clip_id}/fade")
    def set_fade(clip_id: str, fade_in: float = 0.0, fade_out: float = 0.0,
                 why: str = ""):
        return guard(lambda: st.cmd.set_fade(clip_id, fade_in, fade_out, why=why))

    @app.post("/clips/{clip_id}/dissolve")
    def set_dissolve(clip_id: str, duration: float = 0.5, kind: str = "fade",
                     why: str = ""):
        return guard(lambda: st.cmd.set_dissolve(clip_id, duration, kind, why=why))

    @app.delete("/clips/{clip_id}")
    def remove_clip(clip_id: str, why: str = "", ripple: bool = False):
        if ripple:
            return guard(lambda: st.cmd.ripple_delete_clip(clip_id, why=why))
        return guard(lambda: st.cmd.remove_clip(clip_id, why=why))

    @app.post("/clips/{clip_id}/trim")
    def trim(clip_id: str, req: TrimReq, baseRevision: int = None):
        # GUI-02: frame-native. Body: {new_source_start_frame,
        # new_source_end_frame, why}. Reject any legacy seconds fields.
        for legacy in ("new_source_start", "new_source_end"):
            if legacy in req.model_fields_set:
                raise HTTPException(400, f"GUI-02: '{legacy}' (seconds) is no longer accepted; use 'new_source_{legacy.replace('new_source_','')}_frame'")
        return guard(_check_rev(baseRevision, lambda: st.cmd.trim_clip_frame(
            clip_id,
            src_start_frame=req.new_source_start_frame,
            src_end_frame=req.new_source_end_frame,
            why=req.why,
        )))

    @app.post("/clips/{clip_id}/split")
    def split(clip_id: str, req: SplitReq, baseRevision: int = None):
        # GUI-02: body {at_timeline_frame, why}. Core's TimeMap
        # converts timeline_frame -> source_frame.
        if "at_source_time" in req.model_fields_set:
            raise HTTPException(400, "GUI-02: 'at_source_time' (seconds) is no longer accepted; use 'at_timeline_frame'")
        left, right = guard(_check_rev(baseRevision, lambda: st.cmd.split_clip_frame(
            clip_id, at_timeline_frame=req.at_timeline_frame, why=req.why)))
        return {"left": left, "right": right}

    @app.post("/clips/{clip_id}/move")
    def move(clip_id: str, req: MoveReq, baseRevision: int = None):
        if "new_timeline_start" in req.model_fields_set:
            raise HTTPException(400, "GUI-02: 'new_timeline_start' (seconds) is no longer accepted; use 'new_timeline_start_frame'")
        return guard(_check_rev(baseRevision, lambda: st.cmd.move_clip_frame(
            clip_id,
            new_timeline_start_frame=req.new_timeline_start_frame,
            new_track_id=req.new_track_id,
            why=req.why,
        )))

    @app.get("/clip/{clip_id}/timemap")
    def get_timemap(clip_id: str, fps_num: int = None, fps_den: int = None,
                    src_fps_num: int = None, src_fps_den: int = None):
        """GUI-02: returns TimeMap.for_clip(clip, fps, source_fps) as a
        JSON object. The GUI must not construct TimeMap locally; it
        consumes Core's result via this endpoint.

        GUI-02.3: the response now includes BOTH sequence_fps (the
        project's timeline timebase) and source_fps (the asset's
        source timebase). The two are explicitly distinct; the GUI
        must not assume they are equal.

        If `src_fps_num`/`src_fps_den` are not given, the asset's
        source_fps is used (resolved via `asset.source_fps_rational`).
        If the asset has no source FPS set, an explicit 422 is
        returned — frame-native editing never assumes source_fps ==
        sequence_fps.
        """
        from yroll.core.timebase import Rational
        from yroll.core.timemap import TimeMap
        clip = st.core.project.clips.get(clip_id)
        if clip is None:
            raise HTTPException(404, f"clip 不存在: {clip_id}")
        num = fps_num if fps_num is not None else st.core.project.fps_num
        den = fps_den if fps_den is not None else (st.core.project.fps_den or 1)
        fps = Rational(num or 30, den)
        # Resolve source_fps: explicit query params → asset's stored
        # source_fps → 422 if neither available.
        if src_fps_num is not None and src_fps_den is not None:
            src_fps = Rational(src_fps_num, src_fps_den)
        else:
            asset = next((a for a in st.core.project.assets
                          if a.asset_id == clip.asset_id), None)
            if asset is None or asset.source_fps is None:
                raise HTTPException(
                    422,
                    f"asset for clip {clip_id!r} has no source FPS set; "
                    f"call /project/validate_media_conformance and "
                    f"populate Asset.source_fps before frame-native edits",
                )
            src_fps = asset.source_fps
        tm = TimeMap.for_clip(clip, fps, src_fps)
        return {
            "source_start_frame": tm.source_start_frame,
            "source_end_frame": tm.source_end_frame,
            "timeline_start_frame": tm.timeline_start_frame,
            "speed": tm.speed,
            "sequence_fps": {"num": fps.num, "den": fps.den},
            "source_fps": {"num": src_fps.num, "den": src_fps.den},
            # legacy alias for `fps` — prefer sequence_fps above
            "fps": {"num": num, "den": den},
            "duration_frames": tm.source_range.duration_frames,
        }

    @app.get("/clip/{clip_id}/timemap/at_frame")
    def timemap_at_frame(clip_id: str, timeline_frame: int,
                          fps_num: int = None, fps_den: int = None,
                          src_fps_num: int = None, src_fps_den: int = None):
        """GUI-02.5: resolve a TimelineFrame → SourceFrame using Core's
        TimeMap. The GUI must NOT compute this locally (forbidden
        TimeMap business math). Per-call lookup; modern browsers
        buffer video so this is not on the per-frame critical path
        for playback.

        Reuses the same source_fps resolution rules as /clip/{id}/timemap.
        """
        from yroll.core.timebase import Rational
        from yroll.core.timemap import TimeMap
        clip = st.core.project.clips.get(clip_id)
        if clip is None:
            raise HTTPException(404, f"clip 不存在: {clip_id}")
        num = fps_num if fps_num is not None else st.core.project.fps_num
        den = fps_den if fps_den is not None else (st.core.project.fps_den or 1)
        fps = Rational(num or 30, den)
        if src_fps_num is not None and src_fps_den is not None:
            src_fps = Rational(src_fps_num, src_fps_den)
        else:
            asset = next((a for a in st.core.project.assets
                          if a.asset_id == clip.asset_id), None)
            if asset is None or asset.source_fps is None:
                raise HTTPException(
                    422,
                    f"asset for clip {clip_id!r} has no source FPS set",
                )
            src_fps = asset.source_fps
        tm = TimeMap.for_clip(clip, fps, src_fps)
        sf = tm.source_from_timeline(timeline_frame)
        return {
            "source_frame": sf,
            "timeline_frame": timeline_frame,
            "source_fps": {"num": src_fps.num, "den": src_fps.den},
            "sequence_fps": {"num": fps.num, "den": fps.den},
        }

    @app.post("/clips/{clip_id}/speed")
    def speed(clip_id: str, req: SpeedReq):
        return guard(lambda: st.cmd.set_speed(clip_id, **req.model_dump()))

    @app.post("/clips/{clip_id}/volume")
    def volume(clip_id: str, req: VolumeReq):
        return guard(lambda: st.cmd.set_volume(clip_id, **req.model_dump()))

    @app.post("/clips/{clip_id}/adjust")
    def adjust(clip_id: str, req: AdjustReq):
        return guard(lambda: st.cmd.add_adjustment(clip_id, **req.model_dump()))

    @app.post("/clips/{clip_id}/silence-remove")
    def silence_remove(clip_id: str, noise_db: float = -35.0,
                       min_duration: float = 0.5, why: str = ""):
        return guard(lambda: st.cmd.remove_silence(clip_id, noise_db, min_duration, why=why))

    @app.post("/clips/{clip_id}/denoise")
    def denoise(clip_id: str, strength: float = 12.0, why: str = ""):
        return guard(lambda: st.cmd.denoise_clip(clip_id, strength, why=why))

    @app.post("/clips/{clip_id}/loudness")
    def loudness(clip_id: str, why: str = ""):
        return guard(lambda: st.cmd.analyze_loudness(clip_id, why=why))

    @app.post("/clips/{clip_id}/delogo")
    def delogo(clip_id: str, region: Region, why: str = ""):
        return guard(lambda: st.cmd.delogo_clip(clip_id, region, why=why))

    @app.post("/clips/{clip_id}/volume-range")
    def volume_range(clip_id: str, volume: float, start: float, end: float,
                     why: str = ""):
        return guard(lambda: st.cmd.set_volume_range(
            clip_id, volume, TimeRange(start=start, end=end), why=why))

    @app.delete("/clips/{clip_id}/adjustments/{adjustment_id}")
    def remove_adjustment(clip_id: str, adjustment_id: str, why: str = ""):
        return guard(lambda: st.cmd.remove_adjustment(clip_id, adjustment_id, why=why))

    @app.post("/revert")
    def revert(req: RevertReq):
        op = st.core.revert(req.operation_id, who=who.value, why=req.why)
        if op is None:
            raise HTTPException(404, f"operation 不存在: {req.operation_id}")
        return op

    # ---------- History API (P0-08): external undo/redo ----------
    @app.get("/history/state")
    def history_state():
        from yroll.core.history import HistoryAPI
        return HistoryAPI(st.core).state()

    @app.post("/history/undo")
    def history_undo(why: str = ""):
        from yroll.core.history import HistoryAPI
        rev = HistoryAPI(st.core).undo(who=who.value, why=why)
        if rev is None:
            raise HTTPException(400, "no operation to undo")
        return rev

    @app.post("/history/redo")
    def history_redo(why: str = ""):
        from yroll.core.history import HistoryAPI
        redone = HistoryAPI(st.core).redo(who=who.value, why=why)
        if redone is None:
            raise HTTPException(400, "no operation to redo")
        return redone

    @app.get("/history")
    def history_log():
        from yroll.core.history import HistoryAPI
        return {"operations": HistoryAPI(st.core).history()}

    _render_job: dict = {"status": "idle", "step": "", "done": 0, "total": 1,
                         "error": "", "preview": ""}

    def _render_worker(burn: bool, w: int, safe: str,
                       start: float | None, end: float | None) -> None:
        from yroll.core.render import render_preview

        def on_step(label: str, done: int, total: int) -> None:
            _render_job.update(step=label, done=done, total=total)

        try:
            if start is None and end is None:
                out = render_preview(st.core, st.core.path / safe, width=w,
                                     burn_subtitles=burn, on_step=on_step)
            else:
                import subprocess
                import tempfile

                with tempfile.TemporaryDirectory() as tmp:
                    full = render_preview(st.core, Path(tmp) / "full.mp4",
                                          width=w, burn_subtitles=burn,
                                          on_step=on_step)
                    out = st.core.path / safe
                    cmdline = ["ffmpeg", "-y", "-v", "error"]
                    if start is not None:
                        cmdline += ["-ss", f"{start:.3f}"]
                    if end is not None:
                        cmdline += ["-to", f"{end:.3f}"]
                    cmdline += ["-i", str(full), "-c", "copy", str(out)]
                    subprocess.run(cmdline, check=True, capture_output=True)
            _render_job.update(status="done", step="完成", preview=str(out))
        except Exception as e:
            _render_job.update(status="error", error=str(e))

    @app.post("/render")
    def render(burn_subtitles: bool = False, width: int = 1080,
               name: str = "preview.mp4",
               start: float | None = None, end: float | None = None):
        """后台渲染（不阻塞，GUI 轮询进度）。进度查 GET /render/status。"""
        import threading

        if _render_job.get("status") == "running":
            raise HTTPException(409, "已有渲染任务在进行中")
        safe = Path(name).name  # 防路径穿越
        if not safe.endswith(".mp4"):
            safe += ".mp4"
        _render_job.update(status="running", step="排队", done=0,
                           total=1, error="", preview="")
        threading.Thread(
            target=_render_worker,
            args=(burn_subtitles, width, safe, start, end),
            daemon=True).start()
        return {"started": True}

    @app.get("/render/status")
    def render_status():
        return _render_job

    @app.post("/export/package")
    def export_pkg(width: int = 1080, burn_subtitles: bool = False,
                   title: str = "", description: str = "",
                   tags: str = "",  # 逗号分隔
                   platform: str = "",
                   cover_offset_sec: float = 0.5):
        """发布包导出：成片 + 封面 + 字幕 SRT + 元数据 + 报告。"""
        import threading

        tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []

        if _render_job.get("status") == "running":
            raise HTTPException(409, "已有渲染任务在进行中")

        def work():
            from yroll.core.publish import export_package

            def on_step(label: str, done: int, total: int) -> None:
                _render_job.update(step=label, done=done, total=total)
            try:
                report = export_package(
                    st.core, st.core.path / "export", width=width,
                    burn_subtitles=burn_subtitles,
                    title=title, description=description,
                    tags=tag_list, platform=platform,
                    cover_offset_sec=cover_offset_sec,
                    on_step=on_step)
                _render_job.update(status="done", step="完成",
                                   preview=report["path"])
            except Exception as e:
                _render_job.update(status="error", error=str(e))

        _render_job.update(status="running", step="排队", done=0,
                           total=1, error="", preview="")
        threading.Thread(target=work, daemon=True).start()
        return {"started": True}

    @app.get("/presets")
    def get_presets():
        """所有 preset 一次性拉取（字体/字幕样式/转场/滤镜/音效/导出/视窗比例）。"""
        from yroll.core.presets import all_presets
        return all_presets()

    # ---------- GUI-02: Sequence (canonical timebase accessor) ----------
    @app.get("/sequence")
    def get_sequence():
        """Returns the canonical timebase plus the project revision
        so the GUI can invalidate caches when either changes."""
        return {
            "sequence_id": st.core.project.sequence.sequence_id,
            "fps": {"num": st.core.project.sequence.fps.num,
                     "den": st.core.project.sequence.fps.den},
            "width": st.core.project.sequence.width,
            "height": st.core.project.sequence.height,
            "timecode_format": st.core.project.sequence.timecode_format,
            "drop_frame": st.core.project.sequence.drop_frame,
            "project_revision": get_current_revision(st.core),
        }

    # ---------- Edit Lease (P0-10): editing-rights management ----------
    @app.get("/lease")
    def get_lease():
        ls = get_lease_store(st.core).get(st.core.project.project_id)
        log = get_lease_event_log(st.core)
        if ls is None:
            return {"heldBy": None, "sessionId": None, "mode": None,
                    "actor": None, "baseRevision": get_current_revision(st.core),
                    "isAlive": False, "humanLabel": "", "actorId": ""}
        return {"heldBy": ls.actor.value, "sessionId": ls.session_id,
                "mode": ls.mode.value, "actor": ls.actor.value,
                "baseRevision": ls.base_revision, "isAlive": ls.is_alive(LeaseStore.HEARTBEAT_TTL),
                "humanLabel": ls.human_label, "actorId": ls.actor_id,
                "acquiredAt": ls.acquired_at, "lastHeartbeat": ls.last_heartbeat}

    @app.post("/lease/acquire")
    def acquire_lease(actor: str = "human", mode: str = "edit",
                       baseRevision: int = -1, humanLabel: str = "",
                       actorId: str = ""):
        if baseRevision < 0:
            baseRevision = get_current_revision(st.core)
        try:
            ls = get_lease_store(st.core).acquire(
                st.core.project.project_id,
                LeaseActor(actor), LeaseMode(mode), baseRevision, humanLabel,
                actor_id=actorId)
            get_lease_event_log(st.core).record(
                "acquired", actor_id=actorId, session_id=ls.session_id,
                to_actor=ls.actor.value, to_mode=ls.mode.value,
                project_id=ls.project_id)
            return {"ok": True, "sessionId": ls.session_id,
                    "actor": ls.actor.value, "mode": ls.mode.value,
                    "baseRevision": ls.base_revision}
        except LeaseConflictError as e:
            raise HTTPException(409, str(e))

    @app.post("/lease/release")
    def release_lease(sessionId: str):
        store = get_lease_store(st.core)
        ls = store.get(st.core.project.project_id)
        ok = store.release(st.core.project.project_id, sessionId)
        if ok and ls:
            get_lease_event_log(st.core).record(
                "released", actor_id=ls.actor_id, session_id=ls.session_id,
                from_actor=ls.actor.value, from_mode=ls.mode.value,
                project_id=ls.project_id)
        return {"ok": ok}

    @app.post("/lease/heartbeat")
    def heartbeat_lease(sessionId: str):
        ok = get_lease_store(st.core).heartbeat(st.core.project.project_id, sessionId)
        return {"ok": ok}

    @app.post("/lease/handoff")
    def handoff_lease(fromSessionId: str, toActor: str = "agent",
                       toMode: str = "edit", toLabel: str = "",
                       toActorId: str = Query("", alias="toActorId")):
        try:
            # If toActorId has a parked session, prefer promoting it.
            parked = (get_lease_store(st.core).consume_parked(toActorId)
                      if toActorId else None)
            from_ls = get_lease_store(st.core).get(st.core.project.project_id)
            from_actor_val = from_ls.actor.value if from_ls else ""
            from_mode_val = from_ls.mode.value if from_ls else ""
            ls = get_lease_store(st.core).handoff(
                st.core.project.project_id, fromSessionId,
                LeaseActor(toActor), LeaseMode(toMode), toLabel,
                to_actor_id=toActorId)
            get_lease_event_log(st.core).record(
                "promote_parked" if parked else "handed_off",
                actor_id=toActorId, session_id=ls.session_id,
                from_actor=from_actor_val, to_actor=ls.actor.value,
                from_mode=from_mode_val, to_mode=ls.mode.value,
                project_id=ls.project_id,
                detail=f"session {ls.session_id[:8]} promoted from parked"
                       if parked else f"to {toActor} {toMode}",
            )
            return {"ok": True, "sessionId": ls.session_id,
                    "actor": ls.actor.value, "mode": ls.mode.value,
                    "humanLabel": ls.human_label}
        except (LeaseError, LeaseExpiredError) as e:
            raise HTTPException(409, str(e))

    @app.post("/mutation/check")
    def mutation_check(baseRevision: int, sessionId: str = ""):
        try:
            if sessionId:
                require_edit_right(st.core, sessionId)
            check_revision_match(st.core, baseRevision)
            return {"ok": True, "currentRevision": get_current_revision(st.core)}
        except (LeaseError, LeaseConflictError) as e:
            return {"ok": False, "error": str(e),
                    "currentRevision": get_current_revision(st.core)}

    # ---------- GUI-01.5: Cross-process project authority --------------
    #
    # Three endpoints that turn the LeaseStore into something MCP and GUI
    # can share safely across processes. All are Gate-exempt: they don't
    # mutate the project model — they only mutate lease state, which is
    # itself per-actor and the gate's job is to guard writes to the
    # project model, not lease plumbing.
    @app.post("/session/ensure")
    def session_ensure(req: SessionEnsureReq = Body(...)):
        """Per GUI-01.5 spec, 3-case actor_id resume.

        - Live lease's actor_id == req.actor_id → resume (the requester
          presents a new sessionId; the old is invalidated).
        - Live lease belongs to someone else (or nobody) and
          intent == "edit" with nobody holding → auto-acquire EDIT.
        - Live lease belongs to someone else and intent == "edit" →
          return mode=observe, park the new sessionId for later promotion.
        - intent == "observe" → always mode=observe, no acquire, no park.
        """
        store = get_lease_store(st.core)
        log = get_lease_event_log(st.core)
        current = store.get(st.core.project.project_id)
        actor = LeaseActor(req.actor)
        intent = req.intent
        actor_id = req.actor_id or ""

        base_rev = (req.base_revision
                    if req.base_revision >= 0
                    else get_current_revision(st.core))

        # Case A: same actor_id is alive → resume (rotate sessionId)
        if actor_id and current and current.actor_id == actor_id:
            new_sid = _uuid.uuid4().hex
            rotated = store.replace_session(
                current.project_id, current.session_id, new_sid)
            if rotated is None:
                # Race: lease died between get() and replace_session().
                # Fall through to the auto-acquire branch below.
                current = None
            else:
                log.record("ensure_resume", actor_id=actor_id,
                           session_id=new_sid, to_actor=rotated.actor.value,
                           to_mode=rotated.mode.value,
                           project_id=rotated.project_id)
                return {
                    "sessionId": new_sid,
                    "mode": rotated.mode.value,
                    "owner": rotated.actor.value,
                    "actor_id": rotated.actor_id,
                    "revision": get_current_revision(st.core),
                    "pending_agent": False,
                }

        # Case B: nobody holds + intent == edit → auto-acquire
        if current is None and intent == "edit":
            ls = store.acquire(st.core.project.project_id, actor,
                                LeaseMode.EDIT, base_rev,
                                human_label=actor_id, actor_id=actor_id)
            log.record("ensure_edit", actor_id=actor_id,
                       session_id=ls.session_id,
                       to_actor=ls.actor.value, to_mode=ls.mode.value,
                       project_id=ls.project_id)
            return {
                "sessionId": ls.session_id,
                "mode": "edit",
                "owner": ls.actor.value,
                "actor_id": ls.actor_id,
                "revision": get_current_revision(st.core),
                "pending_agent": False,
            }

        # Case C: someone else holds (or intent != edit) → observe + park
        new_sid = _uuid.uuid4().hex
        if actor_id and intent == "edit":
            store.park_session(actor_id, new_sid)
            log.record("ensure_parked", actor_id=actor_id, session_id=new_sid,
                       from_actor=(current.actor.value if current else ""),
                       to_actor=actor.value, to_mode="observe",
                       project_id=st.core.project.project_id,
                       detail="waiting for handoff to actor_id")
        else:
            log.record("ensure_observe", actor_id=actor_id, session_id=new_sid,
                       to_actor=actor.value, to_mode="observe",
                       project_id=st.core.project.project_id)
        return {
            "sessionId": new_sid,
            "mode": "observe",
            "owner": (current.actor.value if current else "free"),
            "actor_id": (current.actor_id if current else ""),
            "revision": get_current_revision(st.core),
            "pending_agent": bool(actor_id and intent == "edit"),
        }

    @app.post("/lease/request")
    def lease_request(req: LeaseRequestReq = Body(...)):
        """Pure read: 'may I edit? who holds? what mode would I get?'

        No side effect on the lease store or the event log.
        """
        store = get_lease_store(st.core)
        current = store.get(st.core.project.project_id)
        if current is None:
            return {
                "can_acquire": req.intent == "edit",
                "current_holder": None,
                "current_actor_id": "",
                "current_mode": None,
                "would_get_mode": ("edit" if req.intent == "edit" else req.intent),
            }
        would = "observe" if req.intent == "edit" else req.intent
        return {
            "can_acquire": False,
            "current_holder": current.actor.value,
            "current_actor_id": current.actor_id,
            "current_mode": current.mode.value,
            "would_get_mode": would,
        }

    @app.get("/lease/events")
    def lease_events(since: int = 0):
        events, next_seq = get_lease_event_log(st.core).since(since)
        return {
            "events": [
                {
                    "seq": e.seq, "kind": e.kind, "at": e.at,
                    "actor_id": e.actor_id, "session_id": e.session_id,
                    "from_actor": e.from_actor, "to_actor": e.to_actor,
                    "from_mode": e.from_mode, "to_mode": e.to_mode,
                    "project_id": e.project_id, "detail": e.detail,
                }
                for e in events
            ],
            "next_seq": next_seq,
        }


    # ---------- 本地字体导入 ----------
    @app.post("/fonts/import")
    async def import_font(file: UploadFile):
        """导入本地字体文件到工程 fonts/ 目录，返回字体 id（hash 前 8 位）。"""
        import hashlib
        from yroll.core.presets import FONTS
        from fastapi.responses import JSONResponse

        content = await file.read()
        if not content:
            raise HTTPException(400, "字体文件为空")
        # 校验：常见字体扩展名
        fname = file.filename or "imported.ttf"
        ext = Path(fname).suffix.lower()
        if ext not in (".ttf", ".otf", ".ttc", ".woff", ".woff2"):
            raise HTTPException(400, f"不支持的字体扩展名 {ext}")
        fonts_dir = st.core.path / "fonts"
        fonts_dir.mkdir(parents=True, exist_ok=True)
        md5 = hashlib.md5(content).hexdigest()[:8]
        out = fonts_dir / f"{md5}{ext}"
        out.write_bytes(content)
        # 推断字体名（从文件名的 stem）
        name = Path(fname).stem
        new = {"id": md5, "name": name, "file": str(out).replace("\\", "/"),
               "category": "user", "weight": 400}
        # 合并返回：内置 + 用户
        all_fonts = list(FONTS) + [new]
        return JSONResponse({"id": md5, "name": name, "file": str(out),
                             "all_fonts": all_fonts})

    @app.post("/import/jianying")
    def import_jianying(draft_dir: str):
        """剪映草稿导入：draft_content.json → 轨道/clip/素材（§4.1 兼容层）。"""
        from yroll.ingest.jianying import import_jianying_draft

        return guard(lambda: import_jianying_draft(st.cmd, draft_dir))

    # ---------- 统一会话历史（蓝图 §3.4：持久化到工程目录） ----------

    def _chat_log() -> list:
        import json as _json

        f = st.core.path / "chat_log.json"
        if not f.exists():
            return []
        try:
            return _json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            return []

    def _chat_append(who: str, text: str) -> None:
        import json as _json

        log = _chat_log()
        log.append({"who": who, "text": text})
        (st.core.path / "chat_log.json").write_text(
            _json.dumps(log[-200:], ensure_ascii=False, indent=1), encoding="utf-8")

    @app.get("/chat/history")
    def chat_history():
        return {"messages": _chat_log()}

    @app.post("/chat/history")
    def chat_history_add(who: str, text: str):
        _chat_append(who, text)
        return {"ok": True}

    @app.post("/clips/{clip_id}/mute")
    def mute(clip_id: str, muted: bool = True, why: str = ""):
        return guard(lambda: st.cmd.set_muted(clip_id, muted, why=why))

    @app.post("/clips/{clip_id}/voice-replace")
    def voice_replace(clip_id: str, text: str, voice_id: str | None = None,
                      why: str = ""):
        return guard(lambda: st.cmd.replace_clip_voice(
            clip_id, text, voice_id=voice_id, why=why))

    @app.post("/chat")
    def chat(req: ChatReq):
        # AI 对话编辑：Task 多轮循环（Session/Task/Turn），同一个 CommandLayer，who=ai
        from yroll.harness.runtime import Task
        from yroll.server.chat import _project_context, build_system

        project = st.core.project
        ctx = _project_context(project, st.core.operations())
        if req.selected_clip and req.selected_clip in project.clips:
            ctx += f"\n【用户当前选中】{req.selected_clip}"
        if req.playhead is not None:
            ctx += f"\n【播放头位置】{req.playhead:.1f}s（时间轴时间）"

        # Mutation Gate (audit §6.5): chat 是另一条 mutation path，必须强制 Lease+Revision
        task = Task(
            CommandLayer(st.core, who=Actor.AI),
            build_system(req.message),
            session_id=req.sessionId,
            expected_base_revision=req.baseRevision,
        )
        result = task.run(ctx, req.message)
        st.core.save_state()
        return result

    @app.websocket("/ws/chat")
    async def chat_ws(ws: WebSocket):
        """流式版 chat：Task 事件实时推送 + 高风险操作审批（ApprovalRequest/Response）。

        协议（借鉴 Codex Submission/Event，传输无关）：
          → {"message": "...", "selected_clip": ..., "playhead": ...}
          ← {"type": "task_started"} / {"type": "turn_started"} /
            {"type": "action_applied"} / {"type": "approval_request", "action": {...}} /
            {"type": "done", "result": {...}}
          → {"type": "approval_response", "approved": true|false}（回答审批）
        """
        import asyncio
        import threading

        from yroll.harness.runtime import Task
        from yroll.server.chat import _project_context, build_system

        await ws.accept()
        try:
            while True:
                req = await ws.receive_json()
                if req.get("type") in ("approval_response", "plan_response"):
                    continue  # 迟到的响应，忽略
                if "message" not in req:
                    continue

                project = st.core.project
                ctx = _project_context(project, st.core.operations())
                sel = req.get("selected_clip")
                if sel and sel in project.clips:
                    ctx += f"\n【用户当前选中】{sel}"
                if req.get("playhead") is not None:
                    ctx += f"\n【播放头位置】{req['playhead']:.1f}s（时间轴时间）"

                loop = asyncio.get_event_loop()
                # LLM 路由是阻塞调用，放执行器里，别卡事件循环
                system = await loop.run_in_executor(
                    None, build_system, req["message"])
                queue: asyncio.Queue = asyncio.Queue()
                pending: dict = {}  # 进行中的审批/计划确认

                def on_event(e):
                    loop.call_soon_threadsafe(queue.put_nowait, e)

                def approval_hook(action: dict) -> bool:
                    """Task 线程里阻塞等 GUI 审批（超时 120s 默认拒绝）。"""
                    ev = threading.Event()
                    pending["event"] = ev
                    pending["approved"] = False
                    on_event({"type": "approval_request", "action": action})
                    ev.wait(timeout=120)
                    pending.pop("event", None)
                    return bool(pending.get("approved"))

                async def receiver():
                    """收 GUI 的审批回答 / 计划确认。"""
                    try:
                        while True:
                            msg = await ws.receive_json()
                            if msg.get("type") == "approval_response" and "event" in pending:
                                pending["approved"] = bool(msg.get("approved"))
                                pending["event"].set()
                            elif msg.get("type") == "plan_response" and "plan_event" in pending:
                                pending["plan_apply"] = bool(msg.get("apply"))
                                pending["plan_event"].set()
                    except Exception:
                        return

                async def pump(future):
                    """把 Task 线程产生的事件实时推给 GUI，直到 future 完成。"""
                    while True:
                        try:
                            e = await asyncio.wait_for(queue.get(), timeout=0.2)
                            await ws.send_json(e)
                        except asyncio.TimeoutError:
                            if future.done():
                                while not queue.empty():
                                    await ws.send_json(queue.get_nowait())
                                break

                # Mutation Gate (audit §6.5): WS chat 也是 mutation path，必须走 Lease+Revision
                task = Task(CommandLayer(st.core, who=Actor.AI),
                            system,
                            on_event=on_event, approval_hook=approval_hook,
                            session_id=req.get("sessionId"),
                            expected_base_revision=req.get("baseRevision"))
                recv_task = asyncio.create_task(receiver())

                if req.get("plan"):
                    # Plan → Preview → Apply：先出计划，人确认后才执行
                    propose_future = loop.run_in_executor(
                        None, task.propose, ctx, req["message"])
                    await pump(propose_future)
                    plan = propose_future.result()
                    await ws.send_json({
                        "type": "plan_proposed",
                        "reply": plan["reply"],
                        "actions": plan["actions"],
                    })
                    if not plan["actions"]:
                        result = {"reply": plan["reply"], "applied": [],
                                  "errors": [], "problems_reported": []}
                    else:
                        plan_event = asyncio.Event()
                        pending["plan_event"] = plan_event
                        pending["plan_apply"] = False
                        try:
                            await asyncio.wait_for(plan_event.wait(), timeout=120)
                        except asyncio.TimeoutError:
                            pass
                        pending.pop("plan_event", None)
                        if pending.get("plan_apply"):
                            run_future = loop.run_in_executor(
                                None, task.apply_actions, plan["actions"])
                            await pump(run_future)
                            result = run_future.result()
                        else:
                            result = {"reply": "已放弃该计划，未做任何修改",
                                      "applied": [], "errors": [],
                                      "problems_reported": []}
                else:
                    run_future = loop.run_in_executor(
                        None, task.run, ctx, req["message"])
                    await pump(run_future)
                    result = run_future.result()

                recv_task.cancel()
                st.core.save_state()
                _chat_append("user", req["message"])
                if result.get("reply"):
                    _chat_append("ai", result["reply"])
                await ws.send_json({"type": "done", "result": result})
        except Exception:
            return

    # ---------- 素材导入（文件上传 → 指纹登记 → 可选自动上时间轴） ----------

    @app.post("/assets/import")
    async def import_asset(file: UploadFile, add_to_timeline: bool = True):
        """GUI/壳 导入素材：存到工程 media/，ffprobe 取指纹，登记 Asset。
        add_to_timeline 时自动作为主视频轨/音轨的一个 clip 上时间轴（导入即所见）。"""
        import hashlib
        import uuid

        from yroll.core.models import Asset, AssetIdentity, AssetType

        media_dir = st.core.path / "media"
        media_dir.mkdir(exist_ok=True)
        safe_name = Path(file.filename or "unnamed").name
        dest = media_dir / safe_name
        if dest.exists():  # 同名不覆盖，加短后缀
            dest = media_dir / f"{dest.stem}-{uuid.uuid4().hex[:4]}{dest.suffix}"

        md5 = hashlib.md5()
        size = 0
        with dest.open("wb") as f:
            while chunk := await file.read(1 << 20):
                md5.update(chunk)
                size += len(chunk)
                f.write(chunk)

        ext = dest.suffix.lower()
        atype = (AssetType.VIDEO if ext in (".mp4", ".mov", ".mkv", ".avi", ".webm")
                 else AssetType.AUDIO if ext in (".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg")
                 else AssetType.IMAGE if ext in (".jpg", ".jpeg", ".png", ".webp", ".bmp")
                 else AssetType.DOCUMENT)

        duration = width = height = None
        if atype in (AssetType.VIDEO, AssetType.AUDIO):
            import json as _json
            import subprocess

            out = subprocess.run(
                ["ffprobe", "-v", "quiet", "-print_format", "json",
                 "-show_format", "-show_streams", str(dest)],
                capture_output=True, text=True, encoding="utf-8", errors="replace")
            info = _json.loads(out.stdout or "{}")
            duration = float(info.get("format", {}).get("duration", 0)) or None
            vs = next((s for s in info.get("streams", [])
                       if s.get("codec_type") == "video"), None)
            if vs:
                width, height = vs.get("width"), vs.get("height")

        # 同 md5 已登记过 → 复用旧 Asset（Asset Identity：指纹认素材不认路径）
        digest = md5.hexdigest()
        existing = next((a for a in st.core.project.assets
                         if a.identity.md5 == digest), None)
        if existing:
            dest.unlink(missing_ok=True)
            return {"asset": existing, "clip": None, "deduped": True}

        asset = Asset(
            asset_id=f"a{uuid.uuid4().hex[:6]}",
            type=atype, path=str(dest),
            identity=AssetIdentity(md5=digest, size_bytes=size,
                                   duration_sec=duration, width=width, height=height),
        )
        # 外部 AI 产物 Adapter（§4 蓝图）：同名 sidecar 记录生成链
        # 例：video.mp4 旁边放 video.yroll-gen.json {"prompt":..., "model":..., "seed":..., "source_tool":...}
        sidecar = dest.parent / (dest.stem + ".yroll-gen.json")
        if sidecar.exists():
            import json as _json

            from yroll.core.models import AssetOrigin

            try:
                gen = _json.loads(sidecar.read_text(encoding="utf-8"))
                asset.origin = AssetOrigin.GENERATED
                asset.gen = gen
                if gen.get("prompt"):
                    asset.caption = gen["prompt"]
                if gen.get("source_tool"):
                    asset.tags.append(str(gen["source_tool"]))
            except Exception:
                pass  # sidecar 坏了不挡导入
        st.core.project.assets.append(asset)

        clip = None
        if add_to_timeline and duration and atype in (AssetType.VIDEO, AssetType.AUDIO):
            # 追加到对应轨道末尾（视频→video 轨，音频→audio 轨，无则建）
            from yroll.core.manifest import TrackKind

            kind = TrackKind.VIDEO if atype == AssetType.VIDEO else TrackKind.AUDIO
            track = next((t for t in st.core.project.timeline.tracks
                          if t.kind == kind), None)
            if track is None:
                track = st.cmd.add_track(kind)
            tl_start = max((st.core.project.clips[cid].timeline_range.end
                            for cid in track.clip_ids if cid in st.core.project.clips),
                           default=0.0)
            clip = st.cmd.add_clip(asset.asset_id, 0.0, duration,
                                timeline_start=tl_start, track_id=track.track_id,
                                why=f"导入素材 {safe_name}")

        st.core.save_state()
        return {"asset": asset, "clip": clip, "deduped": False}

    # ---------- Semantic Link / Impact Preview ----------

    @app.get("/search-transcripts")
    def search_transcripts(q: str):
        """台词搜索定位：转写文本匹配 → clip + 时间轴时间（口播剪辑的导航器）。"""
        from yroll.core.transcripts import load_transcripts

        transcripts = load_transcripts(st.core.project)
        results = []
        query = q.strip()
        if not query:
            return {"results": []}
        for track in st.core.project.timeline.tracks:
            for cid in track.clip_ids:
                clip = st.core.project.clips.get(cid)
                if not clip:
                    continue
                for seg in transcripts.get(clip.asset_id, []):
                    text = seg.get("text", "")
                    if query not in text:
                        continue
                    # 与源区间求交 → 时间轴时间（speed 映射）
                    s = max(seg["start"], clip.source_range.start)
                    if s >= clip.source_range.end:
                        continue
                    tl = clip.timeline_range.start + (
                        s - clip.source_range.start) / clip.speed
                    results.append({
                        "clip_id": cid, "timeline": round(tl, 2),
                        "text": text, "track_id": track.track_id,
                    })
        results.sort(key=lambda r: r["timeline"])
        return {"results": results[:50]}

    @app.post("/clips/{clip_id}/subtitle")
    def edit_subtitle(clip_id: str, text: str, why: str = ""):
        return guard(lambda: st.cmd.edit_subtitle(clip_id, text, why=why))

    @app.post("/clips/{clip_id}/subtitle-style")
    def subtitle_style(clip_id: str, style: dict, why: str = ""):
        return guard(lambda: st.cmd.set_subtitle_style(clip_id, style, why=why))

    @app.post("/subtitles")
    def add_subtitle(text: str, start: float, end: float, why: str = ""):
        return guard(lambda: st.cmd.add_subtitle(text, start, end, why=why))

    @app.post("/subtitles/generate")
    def generate_subtitles(clip_id: str | None = None, why: str = ""):
        return guard(lambda: st.cmd.generate_subtitles(clip_id, why=why))

    # ---------- 波形 / 缩略图（时间轴可视化，结果进 cache/ 可清理） ----------

    def _asset(asset_id: str):
        asset = next((a for a in st.core.project.assets if a.asset_id == asset_id), None)
        if asset is None or not Path(asset.path).exists():
            raise HTTPException(404, f"素材不存在: {asset_id}")
        return asset

    @app.get("/assets/{asset_id}/waveform")
    def waveform(asset_id: str, points: int = 300):
        """音频波形峰值（ffmpeg 抽 PCM → 降采样）。缓存键 = 素材指纹。"""
        asset = _asset(asset_id)
        cache = st.core.path / "cache" / f"wave-{asset.identity.md5[:12]}-{points}.json"
        if cache.exists():
            import json as _json
            return _json.loads(cache.read_text(encoding="utf-8"))

        import struct
        import subprocess

        raw = subprocess.run(
            ["ffmpeg", "-v", "error", "-i", asset.path,
             "-ac", "1", "-ar", "8000", "-f", "f32le", "-"],
            capture_output=True).stdout
        n = len(raw) // 4
        if n == 0:
            return {"peaks": []}
        samples = struct.unpack(f"<{n}f", raw[: n * 4])
        bucket = max(1, n // points)
        peaks = [max(abs(s) for s in samples[i:i + bucket])
                 for i in range(0, n, bucket)]
        peak_max = max(peaks) or 1.0
        result = {"peaks": [round(p / peak_max, 3) for p in peaks],
                  "duration": asset.identity.duration_sec}
        cache.write_text(__import__("json").dumps(result), encoding="utf-8")
        return result

    @app.get("/assets/{asset_id}/file")
    def asset_file(asset_id: str, request: Request):
        """素材原文件流（即时预览用）。支持 HTTP Range（HTML5 视频拖动必需）。"""
        asset = _asset(asset_id)
        return _ranged_file_response(Path(asset.path), request)

    @app.get("/assets/{asset_id}/thumbnail")
    def thumbnail(asset_id: str, t: float = 0.5):
        """抽一帧做缩略图（cache 可清理）。图片素材直接服务原图。"""
        import subprocess

        from fastapi.responses import FileResponse

        from yroll.core.models import AssetType

        asset = _asset(asset_id)
        if asset.type == AssetType.IMAGE:
            return FileResponse(asset.path)
        cache = st.core.path / "cache" / f"thumb-{asset.identity.md5[:12]}-{t:.1f}.jpg"
        if not cache.exists():
            r = subprocess.run(
                ["ffmpeg", "-y", "-v", "error", "-ss", f"{t:.3f}",
                 "-i", asset.path, "-frames:v", "1",
                 "-vf", "scale=160:-2", "-f", "mjpeg", str(cache)],
                capture_output=True)
            if r.returncode != 0 or not cache.exists():
                raise HTTPException(400, "无法抽帧（音频素材？）")
        return FileResponse(cache, media_type="image/jpeg")

    @app.post("/links/infer")
    def infer_links():
        from yroll.core.links import infer_relationships

        rels = infer_relationships(st.core.project)
        st.core.save_state()
        return {"inferred": len(rels), "total": len(st.core.project.relationships)}

    @app.get("/links")
    def list_links():
        return st.core.project.relationships

    @app.get("/clips/{clip_id}/impact")
    def impact(clip_id: str, op: str = "remove"):
        from yroll.core.links import impact_preview

        if clip_id not in st.core.project.clips:
            raise HTTPException(404, f"clip 不存在: {clip_id}")
        return impact_preview(st.core.project, clip_id, op)

    # ---------- Mutation Preview (P0-07 §14) ----------
    # POST /mutation/preview  body: {selection: {...}, op: "move", params: {...}}
    # Returns the projected primary/secondary effects WITHOUT committing.
    @app.post("/mutation/preview")
    def mutation_preview(req: dict):
        from yroll.core.links import preview_mutation
        from yroll.core.selection import Selection
        op = req.get("op", "move")
        params = req.get("params") or {}
        sel_data = req.get("selection") or {}
        # Accept {"clip_ids": [...]} / {"track_ids": [...]} / {"range": {...}}
        sel = Selection(
            clip_ids=sel_data.get("clip_ids", []) or [],
            track_ids=sel_data.get("track_ids", []) or [],
            range=None,  # FrameRange parsed if needed; current preview ignores it
        )
        if not sel.clip_ids and not sel.track_ids:
            raise HTTPException(400, "selection must include clip_ids or track_ids")
        return preview_mutation(st.core.project, sel, op, params)

    # ---------- L0 Frame Preview (v0.2 §30) ----------
    # GET /frame/preview?frame=N — what covers this timeline frame?
    @app.get("/frame/preview")
    def frame_preview(frame: int = 0):
        from yroll.core.frame_preview import resolve_frame
        from yroll.core.timebase import Rational
        fps = Rational(st.core.project.fps_num,
                       st.core.project.fps_den or 1)
        pv = resolve_frame(st.core.project, frame, fps)
        return {
            "timeline_frame": pv.timeline_frame,
            "is_black": pv.is_black(),
            "video": {
                "clip_id": pv.video_clip_id,
                "track_id": pv.video_track_id,
                "source_frame": pv.video_source_frame,
                "asset_path": pv.video_asset_path,
            } if pv.video_clip_id else None,
            "audio": [
                {"clip_id": cid, "source_frame": sf, "asset_path": ap}
                for cid, sf, ap in zip(pv.audio_clip_ids,
                                       pv.audio_source_frames,
                                       pv.audio_asset_paths)
            ],
            "subtitles": [
                {"clip_id": cid, "text": text}
                for cid, text in zip(pv.subtitle_clip_ids, pv.subtitle_texts)
            ],
        }

    # ---------- GUI-03D: /preview/at_frame (L1 Timeline Composite) ----------
    @app.get("/preview/at_frame")
    def preview_at_frame(frame: int = 0):
        """L1 Timeline Composite Preview. Returns ALL active visual
        + audio + subtitle layers at `frame`, z-ordered by track
        iteration order. The GUI consumes this and renders each
        layer in its z-order (image statically for the clip's full
        TimelineFrameRange; video at source_seconds; subtitle as
        text overlay; audio synced to source_seconds)."""
        from yroll.core.frame_preview import (
            composite_preview_at_frame, CompositeLayer,
        )
        from yroll.core.timebase import Rational
        fps = Rational(st.core.project.fps_num,
                       st.core.project.fps_den or 1)
        pv = composite_preview_at_frame(st.core.project, frame, fps)

        def _layer_to_dict(l: CompositeLayer):
            return {
                "track_id": l.track_id,
                "layer_index": l.layer_index,
                "kind": l.kind,
                "clip_id": l.clip_id,
                "asset_id": l.asset_id,
                "asset_path": l.asset_path,
                "source_frame": l.source_frame,
                "source_seconds": l.source_seconds,
                "source_fps": (
                    {"num": l.source_fps.num, "den": l.source_fps.den}
                    if l.source_fps is not None else None
                ),
                "timeline_start_frame": l.timeline_start_frame,
                "timeline_end_frame": l.timeline_end_frame,
                "transform": l.transform,
            }

        return {
            "timeline_frame": pv.timeline_frame,
            "fps": {"num": pv.fps.num, "den": pv.fps.den},
            "is_black": pv.is_black,
            "visual_layers": [_layer_to_dict(l) for l in pv.visual_layers],
            "audio_layers": [_layer_to_dict(l) for l in pv.audio_layers],
            "subtitle_texts": list(pv.subtitle_texts),
        }

    # ---------- GUI-02: /snap (Core SnapEngine over HTTP) ----------
    @app.post("/snap")
    def snap(req: dict, threshold: int = 8):
        """GUI-02: authoritative Core SnapEngine. Threshold is in FRAMES,
        bounded, and zoom-independent (default 8). The GUI does NOT
        POST this on every pointermove — only on drag-end. Local
        integer-frame candidate calculation during drag is fine.
        """
        from yroll.core.snap import (
            SnapEngine, SnapTarget, SnapKind,
        )
        from yroll.core.timebase import Rational
        from yroll.core.timemap import TimeMap
        fps = Rational(st.core.project.fps_num,
                       st.core.project.fps_den or 1)
        engine = SnapEngine(threshold_frames=threshold)
        ctx = req or {}
        candidates: list = []
        # Playhead
        ph = ctx.get("playhead_frame")
        if ph is not None:
            candidates.append(SnapTarget(int(ph), SnapKind.PLAYHEAD, "playhead", ""))
        # Clips
        for cid in ctx.get("clip_ids", []) or []:
            c = st.core.project.clips.get(cid)
            if not c:
                continue
            # GUI-02.3: snap is timeline-frame work; source_fps is not
            # needed for CLIP_START (uses timeline_start_frame directly).
            # For CLIP_END we use source_end_frame which IS in source_fps
            # — pass the asset's source_fps (fall back to sequence fps
            # only in the conformant case where the two are equal).
            asset = next((a for a in st.core.project.assets
                          if a.asset_id == c.asset_id), None)
            src_fps = (asset.source_fps if asset and asset.source_fps is not None
                       else fps)
            tm = TimeMap.for_clip(c, fps, src_fps)
            # clip boundaries in TIMELINE frames
            candidates.append(SnapTarget(tm.timeline_start_frame, SnapKind.CLIP_START, cid, cid))
            candidates.append(SnapTarget(tm.timeline_from_source(tm.source_end_frame), SnapKind.CLIP_END, cid, cid))
        # Tracks
        for tid in ctx.get("track_ids", []) or []:
            track = next((t for t in st.core.project.timeline.tracks if t.track_id == tid), None)
            if not track:
                continue
            for cid in track.clip_ids:
                c = st.core.project.clips.get(cid)
                if not c:
                    continue
                asset = next((a for a in st.core.project.assets
                              if a.asset_id == c.asset_id), None)
                src_fps = (asset.source_fps if asset and asset.source_fps is not None
                           else fps)
                tm = TimeMap.for_clip(c, fps, src_fps)
                candidates.append(SnapTarget(tm.timeline_start_frame, SnapKind.CLIP_START, cid, cid))
                candidates.append(SnapTarget(tm.timeline_from_source(tm.source_end_frame), SnapKind.CLIP_END, cid, cid))
        # Markers
        if ctx.get("include_markers", True):
            for m in getattr(st.core.project, "markers", []) or []:
                candidates.append(SnapTarget(int(m.get("timeline_frame", 0)),
                                           SnapKind.MARKER, m.get("label", ""), ""))
        # Beats
        if ctx.get("include_beats", True):
            for b in getattr(st.core.project, "beats", []) or []:
                # beats may use start_frame or timeline_frame depending on version
                f = b.get("start_frame", b.get("timeline_frame", 0))
                candidates.append(SnapTarget(int(f), SnapKind.BEAT, b.get("label", ""), ""))

        frame = int(req.get("frame", 0)) if isinstance(req.get("frame"), (int, float)) else 0
        result = engine.snap(frame, candidates)
        if result is None:
            return {"snapped_frame": None, "target": None, "delta_frames": 0}
        return {
            "snapped_frame": result.frame,
            "target": {
                "frame": result.target.frame,
                "kind": result.target.kind.value,
                "label": result.target.label,
                "clip_id": result.target.clip_id,
            },
            "delta_frames": result.delta_frames,
        }

    # ---------- Markers (P1 §38) ----------
    @app.get("/markers")
    def list_markers():
        from yroll.core.markers import list_markers as _lm
        return {"markers": [m.to_dict() for m in _lm(st.core.project)]}

    @app.post("/markers")
    def create_marker(timeline_frame: int, label: str,
                       color: str = "#ffd400", note: str = ""):
        from yroll.core.markers import add_marker
        m = add_marker(st.core.project, timeline_frame, label,
                       color=color, note=note)
        st.core.save_state()
        return m.to_dict()

    @app.delete("/markers/{marker_id}")
    def delete_marker(marker_id: str):
        from yroll.core.markers import remove_marker
        if not remove_marker(st.core.project, marker_id):
            raise HTTPException(404, f"marker 不存在: {marker_id}")
        st.core.save_state()
        return {"ok": True}

    @app.patch("/markers/{marker_id}")
    def patch_marker(marker_id: str, label: str | None = None,
                      color: str | None = None, note: str | None = None):
        from yroll.core.markers import update_marker
        m = update_marker(st.core.project, marker_id,
                          label=label, color=color, note=note)
        if m is None:
            raise HTTPException(404, f"marker 不存在: {marker_id}")
        st.core.save_state()
        return m.to_dict()

    # ---------- Keyboard keymap (P1 §34) ----------
    @app.get("/keyboard/keymap")
    def keyboard_keymap():
        from yroll.core.keyboard import describe_keymap
        return {"bindings": describe_keymap()}

    # ---------- Mutation Proposal (v0.2 §3 P3 + §29) ----------
    @app.post("/proposals")
    def create_proposal(req: dict):
        from yroll.core.proposals import get_proposal_store
        from yroll.core.selection import Selection
        sel = Selection.from_clip_or_id(req.get("selection") or {})
        store = get_proposal_store(st.core)
        p = store.propose(st.core.project, sel,
                          op=req.get("op", "move"),
                          params=req.get("params") or {},
                          reason=req.get("reason", ""))
        return {"proposal_id": p.proposal_id,
                "preview": p.preview,
                "expires_at": p.expires_at,
                "reason": p.reason}

    @app.get("/proposals")
    def list_proposals():
        from yroll.core.proposals import get_proposal_store
        store = get_proposal_store(st.core)
        return {"pending": [
            {"proposal_id": p.proposal_id,
             "preview": p.preview,
             "reason": p.reason,
             "expires_at": p.expires_at}
            for p in store.list_pending()
        ]}

    @app.post("/proposals/{proposal_id}/approve")
    def approve_proposal(proposal_id: str, approved_by: str = "human"):
        from yroll.core.proposals import get_proposal_store
        store = get_proposal_store(st.core)
        if not store.approve(proposal_id, approved_by=approved_by):
            raise HTTPException(400, "proposal not pending or expired")
        return {"ok": True, "proposal_id": proposal_id}

    @app.post("/proposals/{proposal_id}/reject")
    def reject_proposal(proposal_id: str, rejected_by: str = "human"):
        from yroll.core.proposals import get_proposal_store
        store = get_proposal_store(st.core)
        if not store.reject(proposal_id, rejected_by=rejected_by):
            raise HTTPException(400, "proposal not pending or already approved")
        return {"ok": True, "proposal_id": proposal_id}

    # ---------- Story / Beat Model (v0.2 §13, §39 P2) ----------
    @app.get("/beats")
    def list_beats():
        from yroll.core.story import list_beats as _lb
        return {"beats": [b.to_dict() for b in _lb(st.core.project)]}

    @app.post("/beats")
    def create_beat(label: str, kind: str,
                     start_frame: int, end_frame: int,
                     intent: str = "", color: str = "#a78bfa",
                     note: str = ""):
        from yroll.core.story import add_beat
        b = add_beat(st.core.project, label, kind,
                     start_frame, end_frame,
                     intent=intent, color=color, note=note)
        st.core.save_state()
        return b.to_dict()

    @app.delete("/beats/{beat_id}")
    def delete_beat(beat_id: str):
        from yroll.core.story import remove_beat
        if not remove_beat(st.core.project, beat_id):
            raise HTTPException(404, f"beat 不存在: {beat_id}")
        st.core.save_state()
        return {"ok": True}

    @app.get("/beats/at/{frame}")
    def beat_at_frame(frame: int):
        from yroll.core.story import beat_at_frame
        b = beat_at_frame(st.core.project, frame)
        return b.to_dict() if b else {"beat": None}

    @app.post("/beats/suggest")
    def suggest_beats():
        from yroll.core.story import suggest_beat_boundaries
        from yroll.core.timebase import Rational
        fps = Rational(st.core.project.fps_num,
                       st.core.project.fps_den or 1)
        return {"suggestions": [
            b.to_dict() for b in suggest_beat_boundaries(st.core.project, fps)
        ]}

    # ---------- Lease Status (v0.2 §24-27) ----------
    @app.get("/ui/status")
    def ui_status(client_known_revision: int | None = None):
        from yroll.core.lease_status import lease_status
        return lease_status(st.core,
                            client_known_revision=client_known_revision)

    # ---------- Agent Action Audit (v0.2 §28 + P2 Evaluation) ----------
    @app.get("/audit/since/{operation_id}")
    def audit_since_endpoint(operation_id: str,
                              previewed: bool = False):
        from yroll.core.audit import audit_since
        return audit_since(st.core, since_operation_id=operation_id,
                            previewed=previewed)

    @app.get("/audit/last")
    def audit_last(n: int = 1, previewed: bool = False):
        """Audit the last n operations as a single batch."""
        from yroll.core.audit import audit_batch
        ops = st.core.operations()
        batch = ops[-n:] if n > 0 else []
        if not batch:
            return {"actor": "agent", "operations": 0,
                    "summary": "no-op", "details": []}
        return audit_batch(st.core, batch, previewed=previewed)

    # ---------- Problem → Solution（产品灵魂） ----------

    @app.post("/problems")
    def create_problem(req: ProblemReq):
        from yroll.core.manifest import ProblemCategory
        from yroll.core.problems import recommend, report_problem

        p = report_problem(
            st.core.project, req.description, ProblemCategory(req.category),
            target_clip=req.target_clip, time_range=req.time_range, region=req.region,
        )
        sols = recommend(st.core.project, p)
        st.core.save_state()
        return {"problem": p, "solutions": sols}

    @app.get("/problems")
    def list_problems():
        return {"problems": st.core.project.problems,
                "solutions": st.core.project.solutions}

    @app.post("/solutions/execute")
    def execute_solution(req: ExecuteReq):
        from yroll.core.problems import execute

        sol = next((s for s in st.core.project.solutions
                    if s.solution_id == req.solution_id), None)
        if sol is None:
            raise HTTPException(404, f"solution 不存在: {req.solution_id}")
        prob = next((p for p in st.core.project.problems
                     if p.problem_id == sol.problem_id), None)
        if prob is None:
            raise HTTPException(404, f"problem 不存在: {sol.problem_id}")
        try:
            result = execute(CommandLayer(st.core, who=Actor.AI), sol, prob)
        except CommandError as e:
            raise HTTPException(400, str(e)) from e
        st.core.save_state()
        return result

    @app.get("/preview.mp4")
    def preview():
        from fastapi.responses import FileResponse

        p = st.core.path / "preview.mp4"
        if not p.exists():
            raise HTTPException(404, "尚未渲染，先 POST /render")
        return FileResponse(p, media_type="video/mp4")

    # ---------- 生产部署：托管 GUI 构建产物（单进程全栈，无需 Docker/nginx） ----------
    # API/WS 路由优先；剩下的 GET 落到 gui/dist 静态文件（html=True 处理 SPA 入口）。
    # 两个候选：源码树（开发/服务器部署）与 PyInstaller 解包目录（桌面壳 sidecar）。
    import sys as _sys

    candidates = [Path(__file__).resolve().parents[2] / "gui" / "dist"]
    if getattr(_sys, "frozen", False):
        candidates.append(Path(_sys._MEIPASS) / "gui" / "dist")  # type: ignore[attr-defined]
    gui_dist = next((d for d in candidates if d.is_dir()), None)
    if gui_dist:
        from fastapi.staticfiles import StaticFiles

        app.mount("/", StaticFiles(directory=gui_dist, html=True), name="gui")

    return app


def serve(project_path: str | Path, host: str = "127.0.0.1", port: int = 8765) -> None:
    import uvicorn

    uvicorn.run(create_app(project_path), host=host, port=port)
