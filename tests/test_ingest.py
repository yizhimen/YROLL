"""Phase 0 冒烟测试：生成合成视频 → 扫描 → 镜头切分 → 关键帧。"""

import subprocess
from pathlib import Path

from yroll.core.models import ProjectMemory
from yroll.core.store import load, save
from yroll.ingest.scanner import scan_dir
from yroll.ingest.shots import detect_shots, extract_keyframes


def _make_test_video(path: Path, seconds: int = 4) -> None:
    """生成一个包含两次画面突变的测试视频（触发镜头切分）。"""
    subprocess.run(
        [
            "ffmpeg", "-y", "-v", "error",
            "-f", "lavfi", "-i", f"color=red:s=320x240:d={seconds/2}",
            "-f", "lavfi", "-i", f"color=blue:s=320x240:d={seconds/2}",
            "-filter_complex", "[0:v][1:v]concat=n=2:v=1[out]",
            "-map", "[out]", "-pix_fmt", "yuv420p", str(path),
        ],
        check=True, capture_output=True,
    )


def test_scan_detect_keyframe_roundtrip(tmp_path: Path):
    _make_test_video(tmp_path / "clip.mp4")

    assets = scan_dir(tmp_path)
    assert len(assets) == 1
    asset = assets[0]
    assert asset.identity.duration_sec and asset.identity.duration_sec > 3
    assert len(asset.identity.md5) == 32

    shots = detect_shots(asset)
    assert len(shots) >= 2  # 红→蓝 至少切出 2 个镜头

    kf_dir = tmp_path / "kf"
    for s in shots:
        kfs = extract_keyframes(s, asset.path, kf_dir)
        assert kfs, "关键帧抽取失败"
        assert all(Path(k).exists() for k in kfs)

    memory = ProjectMemory(project_id="t", name="t", root=str(tmp_path),
                           assets=assets, shots=shots)
    out = save(memory)
    assert out.exists()
    loaded = load(tmp_path, "t")
    assert len(loaded.shots) == len(shots)
    assert loaded.shots[0].keyframes
