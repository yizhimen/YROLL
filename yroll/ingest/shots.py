"""Stage 1+2：镜头切分（PySceneDetect，CV 算法非大模型）+ 关键帧抽取。

策略（蓝图 Stage 2）：每 Shot 取首/中/尾 3 帧，而非全帧。
500 个 5 分钟视频 ≈ 5 万 Shot ≈ 15 万帧，而不是百万级全帧。
"""

from __future__ import annotations

import subprocess
import uuid
from pathlib import Path

from scenedetect import ContentDetector, SceneManager, open_video

from yroll.core.models import Asset, Shot


def detect_shots(asset: Asset, threshold: float = 27.0) -> list[Shot]:
    """对视频 Asset 做镜头切分。单镜头视频返回一个覆盖全长的 Shot。"""
    video = open_video(asset.path)
    manager = SceneManager()
    manager.add_detector(ContentDetector(threshold=threshold))
    manager.detect_scenes(video, show_progress=False)
    scenes = manager.get_scene_list()

    shots = []
    if not scenes:
        dur = asset.identity.duration_sec or 0
        scenes = [(video.base_timecode, video.base_timecode + dur)]

    for i, (start, end) in enumerate(scenes):
        # pyscenedetect >= 0.6: FrameTimecode.get_seconds() / get_frames()
        # pyscenedetect <= 0.5: .seconds / .frame_num
        s_sec = (start.get_seconds()
                 if hasattr(start, "get_seconds") else start.seconds)
        e_sec = (end.get_seconds()
                 if hasattr(end, "get_seconds") else end.seconds)
        shots.append(
            Shot(
                shot_id=f"{asset.asset_id}-s{i:03d}",
                asset_id=asset.asset_id,
                start=s_sec,
                end=e_sec,
            )
        )
    return shots


def extract_keyframes(
    shot: Shot, asset_path: str | Path, out_dir: str | Path, n: int = 3
) -> list[str]:
    """每 Shot 抽首/中/尾 n 帧（ffmpeg 精确 seek）。"""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    span = shot.end - shot.start
    if span <= 0:
        return []
    # 首 10% / 中 50% / 尾 90%，避免黑帧过渡帧
    offsets = [span * r for r in (0.1, 0.5, 0.9)][:n]
    paths = []
    for j, off in enumerate(offsets):
        out = out_dir / f"{shot.shot_id}-k{j}.jpg"
        subprocess.run(
            [
                "ffmpeg", "-y", "-v", "error",
                "-ss", f"{shot.start + off:.3f}",
                "-i", str(asset_path),
                "-frames:v", "1", "-q:v", "3",
                "-vf", "scale=960:-1",  # 控制体积：关键帧用于理解，不需要原尺寸
                str(out),
            ],
            capture_output=True,
        )
        if out.exists():
            paths.append(str(out))
    shot.keyframes = paths
    return paths


def detect_shot_for_id() -> str:
    return uuid.uuid4().hex[:8]
