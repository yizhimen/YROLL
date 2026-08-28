"""Server 测试：Command Layer over HTTP（人机共用同一套 API 的验证）。"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from yroll.core.manifest import Actor
from yroll.core.project import ProjectCore
from yroll.server.app import create_app
from tests.conftest import _AuthedClient


@pytest.fixture()
def client(tmp_path: Path) -> TestClient:
    """Raw TestClient (no auto-lease)."""
    core = ProjectCore.create(tmp_path, "api-demo")
    app = create_app(core.path, who=Actor.AI)
    return TestClient(app)


@pytest.fixture()
def authed_client(tmp_path: Path) -> _AuthedClient:
    """TestClient wrapper that auto-attaches sessionId + baseRevision to mutations."""
    core = ProjectCore.create(tmp_path, "api-demo")
    app = create_app(core.path, who=Actor.AI)
    return _AuthedClient(TestClient(app))


def test_full_edit_flow_over_http(authed_client):
    # 初始为空工程
    assert authed_client.get("/project").json()["clips"] == {}

    # AI 通过 HTTP 加 clip（与 GUI 走同一 Command）
    r = authed_client.post("/clips", json={
        "asset_id": "a1", "source_start": 0, "source_end": 10,
        "timeline_start": 0, "why": "AI 初剪",
    })
    assert r.status_code == 200
    clip_id = r.json()["clip_id"]

    # trim / speed / volume
    assert authed_client.post(f"/clips/{clip_id}/trim",
                       json={"new_source_start": 2.0}).status_code == 200
    assert authed_client.post(f"/clips/{clip_id}/speed", json={"speed": 2.0}).status_code == 200
    assert authed_client.post(f"/clips/{clip_id}/volume", json={"volume": 0.8}).status_code == 200

    # 状态正确：trim 后源 2-10s（timeline 2-10s），2 倍速后 timeline 2-6s
    proj = authed_client.get("/project").json()
    clip = proj["clips"][clip_id]
    assert clip["source_range"] == {"start": 2.0, "end": 10.0}
    assert clip["timeline_range"]["start"] == pytest.approx(2.0)
    assert clip["timeline_range"]["end"] == pytest.approx(6.0)
    assert clip["volume"] == 0.8

    # Operation Log 完整可查（工程黑匣子）
    ops = authed_client.get("/operations").json()
    # 默认 v1 轨已存在，所以 add_clip 不会触发 add_track
    assert [o["type"] for o in ops] == ["add_clip", "trim", "speed", "volume"]
    assert all(o["who"] == "ai" for o in ops)

    # 语义化撤销
    vol_op = ops[-1]
    r = authed_client.post("/revert", json={"operation_id": vol_op["operation_id"]})
    assert r.status_code == 200
    assert r.json()["type"] == "revert:volume"

    # 版本
    assert authed_client.post("/versions", params={"note": "v1"}).status_code == 200
    assert len(authed_client.get("/versions").json()) == 1


def test_errors(authed_client):
    r = authed_client.post("/clips/bad-id/trim", json={"new_source_start": 1.0})
    assert r.status_code == 400
    r = authed_client.post("/revert", json={"operation_id": "op99999"})
    assert r.status_code == 404


def test_gui_static_hosting(client):
    """生产部署：FastAPI 托管 gui/dist，API 路由不被静态文件覆盖。"""
    r = client.get("/")
    assert r.status_code == 200
    assert "<div id=\"root\">" in r.text or "id=\"root\"" in r.text  # Vite SPA 入口
    # API 依然优先于静态挂载
    assert client.get("/project").status_code == 200


def test_import_asset_upload(authed_client, tmp_path: Path):
    """导入素材：上传 → media/ 落盘 → 指纹登记 → 自动上时间轴；同 md5 去重。"""
    import subprocess

    src = tmp_path / "clip.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error",
         "-f", "lavfi", "-i", "color=red:s=320x240:d=2:r=30",
         "-pix_fmt", "yuv420p", str(src)],
        check=True, capture_output=True)

    r = authed_client.post("/assets/import",
                    files={"file": ("clip.mp4", src.read_bytes(), "video/mp4")})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["deduped"] is False
    assert body["asset"]["identity"]["duration_sec"] == pytest.approx(2.0, abs=0.2)
    assert body["asset"]["identity"]["width"] == 320
    assert body["clip"] is not None  # 导入即上时间轴

    proj = authed_client.get("/project").json()
    assert len(proj["assets"]) == 1
    assert len(proj["clips"]) == 1

    # 重复上传同文件 → 指纹去重，不产生第二个 Asset
    r2 = authed_client.post("/assets/import",
                     files={"file": ("clip.mp4", src.read_bytes(), "video/mp4")})
    assert r2.json()["deduped"] is True
    assert len(authed_client.get("/project").json()["assets"]) == 1


def test_track_and_transform_api(authed_client):
    r = authed_client.post("/tracks", params={"kind": "video", "track_id": "v2"})
    assert r.status_code == 200
    clip = authed_client.post("/clips", json={
        "asset_id": "a1", "source_start": 0, "source_end": 5,
        "timeline_start": 0, "track_id": "v2"}).json()
    r2 = authed_client.post(f"/clips/{clip['clip_id']}/transform",
                     json={"x": 0.1, "y": 0.1, "scale": 0.5})
    assert r2.status_code == 200
    proj = authed_client.get("/project").json()
    assert proj["clips"][clip["clip_id"]]["transform"]["scale"] == 0.5
    # 撤销 transform
    authed_client.post("/revert", json={"operation_id": r2.json()["operation_id"]})
    assert authed_client.get("/project").json()["clips"][clip["clip_id"]]["transform"] == {}


def test_project_switch_and_chat_history(authed_client, tmp_path: Path):
    """多工程切换 + 会话历史持久化。"""
    # 新建第二个工程并切换
    r = authed_client.post("/project/new", params={"root": str(tmp_path), "name": "proj-b", "goal": "测试"})
    assert r.status_code == 200
    assert authed_client.get("/project").json()["name"] == "proj-b"
    # 会话历史写读
    authed_client.post("/chat/history", params={"who": "user", "text": "你好"})
    authed_client.post("/chat/history", params={"who": "ai", "text": "在的"})
    msgs = authed_client.get("/chat/history").json()["messages"]
    assert [m["text"] for m in msgs] == ["你好", "在的"]
    # 历史落盘在工程目录
    assert (tmp_path / "proj-b" / "chat_log.json").exists()
    # 切回第一个工程
    first = authed_client.get("/project").json()
    r2 = authed_client.post("/project/open", params={"path": str(tmp_path / "api-demo")})
    assert r2.status_code == 200
    assert authed_client.get("/project").json()["name"] == "api-demo"
    # 打开不存在的工程 → 404
    assert authed_client.post("/project/open", params={"path": "D:/nope"}).status_code == 404


def test_import_ai_gen_sidecar(authed_client, tmp_path: Path):
    """外部 AI 产物 Adapter：同名 .yroll-gen.json sidecar → 生成链登记。"""
    import json as _json
    import subprocess

    src = tmp_path / "gen.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error",
         "-f", "lavfi", "-i", "color=purple:s=320x240:d=1:r=30",
         "-pix_fmt", "yuv420p", str(src)],
        check=True, capture_output=True)
    # sidecar 要预先放到工程 media/（模拟外部产物连元数据一起放入）
    media_dir = tmp_path / "api-demo" / "media"
    media_dir.mkdir(parents=True, exist_ok=True)
    (media_dir / "gen.yroll-gen.json").write_text(_json.dumps({
        "prompt": "一只柴烧茶杯特写", "model": "Kling-2.0",
        "seed": 42, "source_tool": "kling",
    }), encoding="utf-8")

    r = authed_client.post("/assets/import",
                    files={"file": ("gen.mp4", src.read_bytes(), "video/mp4")})
    assert r.status_code == 200
    asset = r.json()["asset"]
    assert asset["origin"] == "generated"
    assert asset["gen"]["prompt"] == "一只柴烧茶杯特写"
    assert asset["gen"]["source_tool"] == "kling"
    assert "kling" in asset["tags"]
