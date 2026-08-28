"""Stage 0：本地媒体扫描（ffprobe，成本 0）+ Asset Identity 指纹。"""

from __future__ import annotations

import hashlib
import json
import subprocess
import uuid
from datetime import datetime
from pathlib import Path

from yroll.core.models import Asset, AssetIdentity, AssetOrigin, AssetType

VIDEO_EXT = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v", ".3gp"}
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".bmp", ".tiff"}
AUDIO_EXT = {".mp3", ".wav", ".aac", ".m4a", ".flac", ".ogg"}


def _md5(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        while b := f.read(chunk):
            h.update(b)
    return h.hexdigest()


def _ffprobe(path: Path) -> dict:
    out = subprocess.run(
        [
            "ffprobe", "-v", "quiet", "-print_format", "json",
            "-show_format", "-show_streams", str(path),
        ],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    return json.loads(out.stdout or "{}")


def _asset_type(path: Path) -> AssetType | None:
    ext = path.suffix.lower()
    if ext in VIDEO_EXT:
        return AssetType.VIDEO
    if ext in IMAGE_EXT:
        return AssetType.IMAGE
    if ext in AUDIO_EXT:
        return AssetType.AUDIO
    return None


def scan_asset(path: Path) -> Asset | None:
    atype = _asset_type(path)
    if atype is None:
        return None

    duration = width = height = None
    if atype in (AssetType.VIDEO, AssetType.AUDIO):
        info = _ffprobe(path)
        duration = float(info.get("format", {}).get("duration", 0) or 0) or None
        for s in info.get("streams", []):
            if s.get("codec_type") == "video":
                width, height = s.get("width"), s.get("height")
                break
    elif atype is AssetType.IMAGE:
        from PIL import Image

        with Image.open(path) as im:
            width, height = im.size

    stat = path.stat()
    return Asset(
        asset_id=uuid.uuid4().hex[:12],
        type=atype,
        origin=AssetOrigin.UNKNOWN,
        path=str(path),
        identity=AssetIdentity(
            md5=_md5(path),
            size_bytes=stat.st_size,
            duration_sec=duration,
            width=width,
            height=height,
            created_at=datetime.fromtimestamp(stat.st_mtime),
        ),
    )


def has_audio_stream(path: str | Path) -> bool:
    """检查媒体文件是否含音频流（无音轨视频跳过 ASR）。"""
    info = _ffprobe(Path(path))
    return any(s.get("codec_type") == "audio" for s in info.get("streams", []))


def scan_dir(root: str | Path) -> list[Asset]:
    """扫描目录下全部媒体文件，生成 Asset 清单。"""
    root = Path(root)
    assets = []
    for p in sorted(root.rglob("*")):
        if p.is_file() and ".yroll" not in p.parts:
            asset = scan_asset(p)
            if asset:
                assets.append(asset)
    return assets
