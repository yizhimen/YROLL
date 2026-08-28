"""云端 TTS（L2 路由）：MiniMax 语音合成，文字 → 语音文件。

用途（蓝图 Problem→Solution L2 voice.clone_replace）：
某句说错了不用重拍——输入正确文本，AI 合成语音替换原句。
V0 用 MiniMax 系统音色（不需用户克隆声音）；自定义音色走 YROLL_VOICE_ID。

MiniMax T2A v2 同步返回 hex 编码音频；传输层可注入（测试 mock）。
"""

from __future__ import annotations

import os
from pathlib import Path

from yroll.tools.cloud_gen import CloudGenError, _headers

# MiniMax 预置系统音色（无需克隆即可用）
DEFAULT_VOICE = "male-qn-qingse"


def tts_generate(text: str, dest: str | Path, *,
                 voice_id: str | None = None,
                 model: str | None = None,
                 fmt: str = "mp3",
                 http=None) -> Path:
    """文字合成语音落盘。凭据/端点走环境变量（与文本/视频模型同平台）。"""
    if not text.strip():
        raise CloudGenError("TTS 文本为空")
    base_url = os.environ.get("YROLL_BASE_URL", "https://api.minimaxi.com/v1")
    api_key = os.environ.get("YROLL_API_KEY", "")
    if not api_key:
        raise CloudGenError("未配置 YROLL_API_KEY")
    http = http or __import__("httpx")

    body = {
        "model": model or os.environ.get("YROLL_TTS_MODEL", "speech-02-hd"),
        "text": text,
        "stream": False,
        "voice_setting": {
            "voice_id": voice_id or os.environ.get("YROLL_VOICE_ID", DEFAULT_VOICE),
            "speed": 1.0, "vol": 1.0, "pitch": 0,
        },
        "audio_setting": {"format": fmt, "sample_rate": 32000, "bitrate": 128000},
    }
    resp = http.post(f"{base_url}/t2a_v2", headers=_headers(api_key),
                     json=body, timeout=120)
    data = resp.json()
    hex_audio = (data.get("data") or {}).get("audio")
    if not hex_audio:
        raise CloudGenError(f"TTS 失败: {data}")
    dest = Path(dest)
    dest.write_bytes(bytes.fromhex(hex_audio))
    return dest
