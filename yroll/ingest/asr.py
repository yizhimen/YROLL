"""ASR 支路：faster-whisper 本地转写（词级时间戳，成本 0）。"""

from __future__ import annotations

from functools import lru_cache
import os
from pathlib import Path

from yroll.core.models import TranscriptSegment

# 本地模型目录（ModelScope 下载，避免 HF 网络问题）；也可用环境变量覆盖
_LOCAL_MODEL = Path(__file__).resolve().parents[2] / "models" / "faster-whisper-small"


@lru_cache(maxsize=1)
def _model(model_size: str = "small"):
    from faster_whisper import WhisperModel

    if model_size == "small" and _LOCAL_MODEL.exists() and (_LOCAL_MODEL / "model.bin").exists():
        return WhisperModel(str(_LOCAL_MODEL), device="auto", compute_type="int8")
    path = os.environ.get("YROLL_WHISPER_MODEL_PATH")
    if path:
        return WhisperModel(path, device="auto", compute_type="int8")
    # int8 CPU 推理，够用即可；有 GPU 时自动可用 float16
    return WhisperModel(model_size, device="auto", compute_type="int8")


def transcribe(
    media_path: str, model_size: str = "small", language: str | None = None
) -> list[TranscriptSegment]:
    model = _model(model_size)
    segments, _info = model.transcribe(
        media_path, word_timestamps=True, language=language, vad_filter=True
    )
    return [
        TranscriptSegment(
            start=s.start,
            end=s.end,
            text=s.text.strip(),
            words=[{"w": w.word, "s": w.start, "e": w.end} for w in (s.words or [])],
        )
        for s in segments
    ]
