"""Problem→Solution 引擎测试。"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from yroll.core.commands import CommandLayer
from yroll.core.manifest import Actor, ProblemCategory, SolutionRoute, TimeRange
from yroll.core.problems import execute, recommend, report_problem
from yroll.core.project import ProjectCore
from yroll.server.app import create_app


@pytest.fixture()
def setup(tmp_path: Path):
    core = ProjectCore.create(tmp_path, "prob-demo")
    cmd = CommandLayer(core, who=Actor.HUMAN)
    clip = cmd.add_clip("a1", 0.0, 10.0, timeline_start=0.0)
    return core, cmd, clip


def test_report_and_recommend_lowest_cost_first(setup):
    core, cmd, clip = setup
    p = report_problem(core.project, "这个壶太大", ProblemCategory.SPATIAL_OBJECT,
                       target_clip=clip.clip_id,
                       time_range=TimeRange(start=2.0, end=4.0))
    sols = recommend(core.project, p)
    assert len(sols) >= 3
    # 默认最低成本优先：第一个是 L0 免费方案
    assert sols[0].route == SolutionRoute.L0_TRANSFORM
    assert sols[0].cost == 0.0
    # 重生成在最后且最贵
    assert sols[-1].route == SolutionRoute.L3_REGENERATE
    assert sols[-1].cost > 0


def test_execute_l0_speed(setup):
    core, cmd, clip = setup
    p = report_problem(core.project, "节奏太慢", ProblemCategory.TEMPORAL,
                       target_clip=clip.clip_id)
    sols = recommend(core.project, p)
    speed_sol = next(s for s in sols if s.tool == "video.speed")
    result = execute(cmd, speed_sol, p)
    assert result["status"] == "applied"
    assert clip.speed == 1.5
    assert clip.timeline_range.end == pytest.approx(10 / 1.5)
    assert speed_sol.selected
    # 操作落日志，who=human（这里 cmd 是 human 角色）
    assert cmd.core.operations()[-1].type == "speed"


def test_execute_l1_pending(setup):
    core, cmd, clip = setup
    # 仍未接入的 L2 能力 → pending（接口预留，未假装实现）
    p = report_problem(core.project, "这句说得不好", ProblemCategory.AUDIO,
                       target_clip=clip.clip_id)
    sols = recommend(core.project, p)
    l2 = next(s for s in sols if s.route == SolutionRoute.L2_CLOUD_AI)
    result = execute(cmd, l2, p)
    assert result["status"] == "pending"


def test_problem_api(tmp_path: Path):
    core = ProjectCore.create(tmp_path, "api-prob")
    cmd = CommandLayer(core)
    clip = cmd.add_clip("a1", 0.0, 10.0, timeline_start=0.0)

    client = TestClient(create_app(core.path))
    r = client.post("/problems", json={
        "description": "声音太小", "category": "audio",
        "target_clip": clip.clip_id,
    })
    assert r.status_code == 200
    data = r.json()
    assert data["problem"]["description"] == "声音太小"
    sols = data["solutions"]
    assert sols[0]["route"] == "L0_transform"  # 最低成本优先

    # 执行第一个方案（audio.gain → volume 提升）
    r2 = client.post("/solutions/execute", json={"solution_id": sols[0]["solution_id"]})
    assert r2.status_code == 200
    assert r2.json()["status"] == "applied"
    assert client.get("/project").json()["clips"][clip.clip_id]["volume"] == 1.3

    # 问题与方案可查询（产品知识库的一部分）
    listed = client.get("/problems").json()
    assert len(listed["problems"]) == 1
    assert len(listed["solutions"]) == len(sols)
