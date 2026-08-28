"""云端生成客户端（L3 路由的真实执行体）：MiniMax 视频生成。

流程：submit（拿 task_id）→ poll（拿 file_id）→ retrieve（拿下载地址）→ 下载落盘。
生成结果进工程 generated/ 目录（蓝图：'generated/ 确认使用的生成结果'），
登记为 origin=generated 的 Asset —— 生成物也是素材，进同一套 Identity/日志体系。

传输层可注入（测试用假 transport，生产用 httpx）。
"""

from __future__ import annotations

import os
import time
from pathlib import Path


class CloudGenError(Exception):
    pass


def _headers(api_key: str) -> dict:
    return {"Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"}


def submit_video_generation(prompt: str, *, base_url: str, api_key: str,
                            model: str = "MiniMax-Hailuo-02",
                            duration: int = 6, http=None) -> str:
    """提交生成任务，返回 task_id。"""
    http = http or __import__("httpx")
    resp = http.post(
        f"{base_url}/video_generation",
        headers=_headers(api_key),
        json={"model": model, "prompt": prompt, "duration": duration},
        timeout=60,
    )
    data = resp.json()
    task_id = data.get("task_id")
    if not task_id:
        raise CloudGenError(f"提交生成失败: {data}")
    return task_id


def poll_task(task_id: str, *, base_url: str, api_key: str,
              timeout_s: float = 600, interval: float = 5.0, http=None) -> str:
    """轮询任务直到成功，返回 file_id。"""
    http = http or __import__("httpx")
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        resp = http.get(
            f"{base_url}/query/video_generation",
            headers=_headers(api_key),
            params={"task_id": task_id},
            timeout=30,
        )
        data = resp.json()
        status = data.get("status")
        if status == "Success":
            file_id = data.get("file_id")
            if not file_id:
                raise CloudGenError(f"任务成功但无 file_id: {data}")
            return file_id
        if status in ("Fail", "Failed"):
            raise CloudGenError(f"生成失败: {data}")
        time.sleep(interval)
    raise CloudGenError(f"生成超时（{timeout_s}s）: {task_id}")


def download_file(file_id: str, dest: str | Path, *, base_url: str,
                  api_key: str, http=None) -> Path:
    """retrieve 下载地址 → 落盘。"""
    http = http or __import__("httpx")
    resp = http.get(
        f"{base_url}/files/retrieve",
        headers=_headers(api_key),
        params={"file_id": file_id},
        timeout=30,
    )
    data = resp.json()
    url = (data.get("file") or {}).get("download_url")
    if not url:
        raise CloudGenError(f"取下载地址失败: {data}")
    dest = Path(dest)
    with http.stream("GET", url, timeout=300) as r, dest.open("wb") as f:
        for chunk in r.iter_bytes(1 << 20):
            f.write(chunk)
    return dest


def generate_shot(prompt: str, dest: str | Path, *,
                  model: str | None = None, duration: int = 6,
                  timeout_s: float = 600, http=None) -> Path:
    """一条龙：submit → poll → download。凭据走环境变量（与文本模型同平台）。"""
    base_url = os.environ.get("YROLL_BASE_URL", "https://api.minimaxi.com/v1")
    api_key = os.environ.get("YROLL_API_KEY", "")
    if not api_key:
        raise CloudGenError("未配置 YROLL_API_KEY")
    task_id = submit_video_generation(
        prompt, base_url=base_url, api_key=api_key,
        model=model or os.environ.get("YROLL_VIDEO_MODEL", "MiniMax-Hailuo-02"),
        duration=duration, http=http)
    file_id = poll_task(task_id, base_url=base_url, api_key=api_key,
                        timeout_s=timeout_s, http=http)
    return download_file(file_id, dest, base_url=base_url, api_key=api_key, http=http)
