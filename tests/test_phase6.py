"""Phase 6 测试：L1 新接线（denoise/inpaint）+ L3 云端生成（假 transport 全链路）。"""

import subprocess
from pathlib import Path

import pytest

from yroll.core.commands import CommandLayer
from yroll.core.manifest import (
    Actor,
    ProblemCategory,
    Region,
    SolutionRoute,
)
from yroll.core.models import Asset, AssetIdentity, AssetType
from yroll.core.problems import execute, recommend, report_problem
from yroll.core.project import ProjectCore


@pytest.fixture
def cmd_with_clip(tmp_path: Path):
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error",
         "-f", "lavfi", "-i", "color=blue:s=320x240:d=2:r=30",
         "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
         "-map", "0:v", "-map", "1:a", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-shortest", str(tmp_path / "v.mp4")],
        check=True, capture_output=True)
    core = ProjectCore.create(tmp_path, "phase6-demo")
    core.project.assets.append(Asset(
        asset_id="a1", type=AssetType.VIDEO, path=str(tmp_path / "v.mp4"),
        identity=AssetIdentity(md5="x" * 32, size_bytes=1, duration_sec=2.0),
    ))
    cmd = CommandLayer(core, who=Actor.AI)
    clip = cmd.add_clip("a1", 0.0, 2.0, timeline_start=0.0)
    return cmd, clip


def _solution_for(cmd, problem, tool):
    return next(s for s in cmd.core.project.solutions
                if s.problem_id == problem.problem_id and s.tool == tool)


def test_l1_denoise_via_solution(cmd_with_clip):
    cmd, clip = cmd_with_clip
    p = report_problem(cmd.core.project, "底噪大", ProblemCategory.AUDIO,
                       target_clip=clip.clip_id)
    recommend(cmd.core.project, p)
    sol = _solution_for(cmd, p, "audio.denoise")
    assert sol.route == SolutionRoute.L1_LOCAL_AI

    result = execute(cmd, sol, p)
    assert result["status"] == "applied"
    c = cmd.core.project.clips[clip.clip_id]
    assert c.adjustments[-1]["kind"] == "denoise"


def test_l1_inpaint_via_solution(cmd_with_clip):
    cmd, clip = cmd_with_clip
    p = report_problem(cmd.core.project, "右上角有台标", ProblemCategory.TEXT,
                       target_clip=clip.clip_id,
                       region=Region(x=0.85, y=0.03, w=0.13, h=0.08))
    recommend(cmd.core.project, p)
    sol = _solution_for(cmd, p, "video.inpaint")

    result = execute(cmd, sol, p)
    assert result["status"] == "applied"
    assert cmd.core.project.clips[clip.clip_id].adjustments[-1]["kind"] == "delogo"


def test_l1_inpaint_requires_region(cmd_with_clip):
    from yroll.core.commands import CommandError

    cmd, clip = cmd_with_clip
    p = report_problem(cmd.core.project, "有水印", ProblemCategory.TEXT,
                       target_clip=clip.clip_id)  # 无 region
    recommend(cmd.core.project, p)
    sol = _solution_for(cmd, p, "video.inpaint")
    with pytest.raises(CommandError, match="region"):
        execute(cmd, sol, p)


class _FakeHTTP:
    """模拟 MiniMax 生成 API：submit→task_id，poll→Success+file_id，retrieve→url，stream→内容。"""
    def post(self, url, headers=None, json=None, timeout=None):
        assert url.endswith("/video_generation")
        assert "重新生成" in json["prompt"] or json["prompt"]
        return type("R", (), {"json": lambda s: {"task_id": "task-123"}})()

    def get(self, url, headers=None, params=None, timeout=None):
        if url.endswith("/query/video_generation"):
            return type("R", (), {"json": lambda s: {
                "status": "Success", "file_id": "file-9"}})()
        if url.endswith("/files/retrieve"):
            return type("R", (), {"json": lambda s: {
                "file": {"download_url": "https://cdn.example/x.mp4"}}})()
        raise AssertionError(url)

    def stream(self, method, url, timeout=None):
        import io

        class Resp(io.BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def iter_bytes(self, n):
                yield b"\x00\x00\x00\x18ftypmp42fake-video-bytes"

        return Resp()


def test_l3_generate_via_solution(cmd_with_clip, monkeypatch):
    cmd, clip = cmd_with_clip
    monkeypatch.setenv("YROLL_API_KEY", "test-key")

    # problems 内部 `from yroll.tools.cloud_gen import generate_shot`，
    # 打源头模块的属性即可拦截
    import yroll.tools.cloud_gen as cg

    def _fake_generate(prompt, dest, **kw):
        assert prompt  # prompt 非空（来自问题描述）
        dest.write_bytes(b"\x00\x00\x00\x18ftypmp42fake-video-bytes")
        return dest

    monkeypatch.setattr(cg, "generate_shot", _fake_generate)

    p = report_problem(cmd.core.project, "这个镜头不对", ProblemCategory.SEMANTIC,
                       target_clip=clip.clip_id)
    recommend(cmd.core.project, p)
    sol = _solution_for(cmd, p, "video.generate")
    assert sol.route == SolutionRoute.L3_REGENERATE

    result = execute(cmd, sol, p)
    assert result["status"] == "applied"

    # 生成物落 generated/ + 登记 Asset(origin=generated) + 新 clip 跟在问题 clip 后
    gen_asset = next(a for a in cmd.core.project.assets
                     if a.asset_id == result["asset_id"])
    assert gen_asset.origin.value == "generated"
    assert "generated" in gen_asset.path
    new_clip = cmd.core.project.clips[result["clip_id"]]
    assert new_clip.timeline_range.start == clip.timeline_range.end
    track = next(t for t in cmd.core.project.timeline.tracks
                 if new_clip.clip_id in t.clip_ids)
    assert track.track_id == clip.track_id


def test_cloud_gen_client_flow():
    """cloud_gen 客户端协议：submit → poll → retrieve → download（假 transport）。"""
    from yroll.tools.cloud_gen import (
        download_file,
        poll_task,
        submit_video_generation,
    )

    http = _FakeHTTP()
    tid = submit_video_generation("一个镜头", base_url="https://x/v1",
                                  api_key="k", http=http)
    assert tid == "task-123"
    fid = poll_task(tid, base_url="https://x/v1", api_key="k",
                    interval=0.01, http=http)
    assert fid == "file-9"
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        out = download_file(fid, Path(d) / "g.mp4", base_url="https://x/v1",
                            api_key="k", http=http)
        assert out.read_bytes().startswith(b"\x00\x00\x00\x18ftyp")


def test_cloud_gen_failure_raises():
    from yroll.tools.cloud_gen import CloudGenError, poll_task

    class FailHTTP:
        def get(self, *a, **kw):
            return type("R", (), {"json": lambda s: {"status": "Fail",
                                                     "reason": "内容违规"}})()

    with pytest.raises(CloudGenError, match="生成失败"):
        poll_task("t", base_url="https://x/v1", api_key="k",
                  interval=0.01, http=FailHTTP())


def test_l2_voice_replace(cmd_with_clip, monkeypatch):
    """L2 TTS 重配：合成语音 → 新音频 clip 对齐 → 原 clip 静音；撤销完整还原。"""
    cmd, clip = cmd_with_clip
    monkeypatch.setenv("YROLL_API_KEY", "test-key")

    import yroll.tools.tts as tts_mod

    class TTSHTTP:
        def post(self, url, headers=None, json=None, timeout=None):
            assert url.endswith("/t2a_v2")
            assert json["text"] == "正确的台词"
            fake = b"ID3fake-mp3-audio-bytes"
            return type("R", (), {"json": lambda s: {
                "data": {"audio": fake.hex()}}})()

    # commands 里是函数内 import，打源头模块即可
    real = tts_mod.tts_generate

    def _fake_tts(text, dest, **kw):
        return real(text, dest, http=TTSHTTP())

    monkeypatch.setattr(tts_mod, "tts_generate", _fake_tts)

    op = cmd.replace_clip_voice(clip.clip_id, "正确的台词")
    assert op.type == "voice_replace"
    c = cmd.core.project.clips[clip.clip_id]
    assert c.context.get("muted") == "1"  # 原声静音
    # TTS 音频 clip 在音频轨对齐
    aid = op.after["asset_id"]
    tts_clip = next(x for x in cmd.core.project.clips.values() if x.asset_id == aid)
    assert tts_clip.timeline_range.start == clip.timeline_range.start
    atrack = next(t for t in cmd.core.project.timeline.tracks
                  if tts_clip.clip_id in t.clip_ids)
    assert atrack.kind.value == "audio"
    # 音频文件真实落 generated/
    from pathlib import Path as P
    assert P(cmd.core.project.assets[-1].path).read_bytes() == b"ID3fake-mp3-audio-bytes"

    # 撤销：原声恢复 + TTS clip/素材移除
    cmd.core.revert(op.operation_id)
    assert "muted" not in cmd.core.project.clips[clip.clip_id].context
    assert not any(x.asset_id == aid for x in cmd.core.project.clips.values())
    assert not any(a.asset_id == aid for a in cmd.core.project.assets)
