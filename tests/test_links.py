"""Semantic Link + Impact Preview 测试。"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from yroll.core.commands import CommandLayer
from yroll.core.links import impact_preview, infer_relationships
from yroll.core.manifest import TrackKind
from yroll.core.project import ProjectCore
from yroll.server.app import create_app


@pytest.fixture()
def project_with_tracks(tmp_path: Path):
    core = ProjectCore.create(tmp_path, "link-demo")
    cmd = CommandLayer(core)
    v = cmd.add_clip("a1", 0.0, 10.0, timeline_start=0.0, track_id="v1")
    cmd.add_track(TrackKind.TEXT, "t1")
    cmd.add_track(TrackKind.AUDIO, "a1-track")
    # 字幕与 v 重叠（0-4s）
    sub = cmd.add_clip("", 0.0, 4.0, timeline_start=0.0, track_id="t1")
    # 人声只覆盖这个 clip
    voice = cmd.add_clip("a2", 0.0, 10.0, timeline_start=0.0, track_id="a1-track")
    return core, cmd, v, sub, voice


def test_infer_caption_and_voice(project_with_tracks):
    core, cmd, v, sub, voice = project_with_tracks
    rels = infer_relationships(core.project)
    kinds = {(r.source, r.kind): r for r in rels}
    assert (sub.clip_id, "caption_of") in kinds
    assert (voice.clip_id, "voice_of") in kinds
    assert kinds[(sub.clip_id, "caption_of")].relation.value == "strong"


def test_bgm_spanning_multiple_clips_is_independent(project_with_tracks):
    core, cmd, v, sub, voice = project_with_tracks
    # 再加一个视频 clip，然后放一条横跨两者的 BGM（在 a3 轨，避免同人声轨道重叠）
    cmd.add_clip("a3", 0.0, 10.0, timeline_start=10.0, track_id="v1")
    bgm = cmd.add_clip("a4", 0.0, 20.0, timeline_start=0.0, track_id="a3")
    rels = infer_relationships(core.project)
    bgm_rels = [r for r in rels if r.source == bgm.clip_id]
    assert bgm_rels and all(r.kind == "bgm_of" for r in bgm_rels)
    assert all(r.relation.value == "independent" for r in bgm_rels)


def test_infer_is_idempotent(project_with_tracks):
    core, *_ = project_with_tracks
    n1 = len(infer_relationships(core.project))
    n2 = len(infer_relationships(core.project))
    assert n1 == n2 == len(core.project.relationships)  # 不重复累积


def test_impact_preview(project_with_tracks):
    core, cmd, v, sub, voice = project_with_tracks
    infer_relationships(core.project)
    impact = impact_preview(core.project, v.clip_id, "remove")
    synced = {d["clip_id"] for d in impact["will_sync"]}
    assert sub.clip_id in synced   # 字幕会同步删除
    assert voice.clip_id in synced  # 人声会同步删除


def test_links_api(tmp_path: Path):
    core = ProjectCore.create(tmp_path, "link-api")
    cmd = CommandLayer(core)
    v = cmd.add_clip("a1", 0.0, 10.0, timeline_start=0.0)
    cmd.add_track(TrackKind.TEXT, "t1")
    sub = cmd.add_clip("", 0.0, 4.0, timeline_start=0.0, track_id="t1")
    sub.context["text"] = "字幕内容"
    core.save_state()  # server 从磁盘重开工程，需落盘

    from tests.conftest import _AuthedClient
    client = _AuthedClient(TestClient(create_app(core.path)))
    r = client.post("/links/infer")
    assert r.status_code == 200 and r.json()["inferred"] == 1

    r = client.get(f"/clips/{v.clip_id}/impact", params={"op": "remove"})
    assert r.status_code == 200
    impact = r.json()
    assert impact["will_sync"][0]["clip_id"] == sub.clip_id
    assert impact["will_sync"][0]["text"] == "字幕内容"
