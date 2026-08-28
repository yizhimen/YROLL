"""本地确定性工具：静音/停顿检测（ffmpeg silencedetect，成本 0）。

对口播类视频的第一大高频痛点：停顿、气口、犹豫。
蓝图定位：这是"前 90% 用确定性代码"的典型——不需要 LLM。
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from yroll.core.manifest import TimeRange

# silencedetect 输出示例：
# [silencedetect @ ...] silence_start: 12.34
# [silencedetect @ ...] silence_end: 15.67 | silence_duration: 3.33
_RE_START = re.compile(r"silence_start:\s*([\d.]+)")
_RE_END = re.compile(r"silence_end:\s*([\d.]+)")
# volumedetect 输出示例：
# [Parsed_volumedetect_0 @ ...] mean_volume: -27.0 dB
# [Parsed_volumedetect_0 @ ...] max_volume: -4.4 dB
_RE_MEAN = re.compile(r"mean_volume:\s*(-?[\d.]+)\s*dB")
_RE_MAX = re.compile(r"max_volume:\s*(-?[\d.]+)\s*dB")


def measure_loudness(
    media_path: str | Path,
    within: TimeRange | None = None,
) -> dict[str, float] | None:
    """测量响度（ffmpeg volumedetect，成本 0）。返回 {"mean_db": ..., "max_db": ...}。

    给 L0 规则/AI 提供真实数据做音量平衡决策，而不是拍脑袋给 volume 值。
    """
    out = subprocess.run(
        [
            "ffmpeg", "-v", "info",
            *(["-ss", f"{within.start:.3f}", "-to", f"{within.end:.3f}"] if within else []),
            "-i", str(media_path),
            "-af", "volumedetect",
            "-f", "null", "-",
        ],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    mean = _RE_MEAN.search(out.stderr)
    peak = _RE_MAX.search(out.stderr)
    if not (mean and peak):
        return None
    return {"mean_db": float(mean.group(1)), "max_db": float(peak.group(1))}


def detect_silences(
    media_path: str | Path,
    noise_db: float = -35.0,
    min_duration: float = 0.5,
    within: TimeRange | None = None,
) -> list[TimeRange]:
    """检测静音段。within 限定源时间范围（如只查某 clip 的源区间）。"""
    out = subprocess.run(
        [
            "ffmpeg", "-v", "info",
            *(["-ss", f"{within.start:.3f}", "-to", f"{within.end:.3f}"] if within else []),
            "-i", str(media_path),
            "-af", f"silencedetect=noise={noise_db}dB:d={min_duration}",
            "-f", "null", "-",
        ],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    silences: list[TimeRange] = []
    start: float | None = None
    offset = within.start if within else 0.0
    for line in out.stderr.splitlines():
        if m := _RE_START.search(line):
            start = float(m.group(1))
        elif m := _RE_END.search(line):
            if start is not None:
                # 输入用了 -ss 时，silencedetect 时间戳是相对偏移后的，要加回来
                silences.append(TimeRange(start=start + offset, end=float(m.group(1)) + offset))
                start = None
    return silences


def complement_ranges(whole: TimeRange, cuts: list[TimeRange],
                      padding: float = 0.08) -> list[TimeRange]:
    """把静音段取反成"保留段"，并给切口留一点呼吸（padding）。
    padding：静音段首尾各内缩，避免把词的尾音切掉。
    """
    keep: list[TimeRange] = []
    cursor = whole.start
    for c in sorted(cuts, key=lambda c: c.start):
        s, e = c.start + padding, c.end - padding
        if s <= cursor:
            cursor = max(cursor, e)
            continue
        keep.append(TimeRange(start=cursor, end=min(s, whole.end)))
        cursor = e
    if cursor < whole.end:
        keep.append(TimeRange(start=cursor, end=whole.end))
    return [k for k in keep if k.end - k.start > 0.05]
