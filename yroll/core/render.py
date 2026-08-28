"""最小渲染器：按 current.json 的 Timeline 用 FFmpeg 合成预览视频。

原则：版本/状态只存元数据（Operation/diff），渲染是实时的——
只在需要预览/导出时才真正处理媒体。

V0.3 支持：
- v 轨道视频/图片 Clip 按 timeline 顺序切取 source_range → 统一分辨率 → 拼接
- 变速（speed）、音量（volume）、denoise/volume_range/delogo 调整图层
- 无音轨素材自动补静音，保证 concat 流一致
- a 轨道音频 Clip（BGM/旁白）：切取+变速+音量 → 按 timeline 偏移 adelay → amix 混音
- text 轨道 Clip → 生成 SRT 字幕并软封装进 mp4（不烧录，保持可编辑原则）
- 限制（V0）：主视频轨 clip 需连续无间隙；第二条视频轨不参与合成（待 overlay）
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

from yroll.core.manifest import Clip, TrackKind
from yroll.core.models import Asset, AssetType
from yroll.core.project import ProjectCore


def _has_audio(path: str | Path) -> bool:
    out = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json",
         "-show_streams", str(path)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    return any(s.get("codec_type") == "audio"
               for s in json.loads(out.stdout or "{}").get("streams", []))


def _video_size(path: str | Path) -> tuple[int, int] | None:
    out = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json",
         "-show_streams", str(path)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    for s in json.loads(out.stdout or "{}").get("streams", []):
        if s.get("codec_type") == "video" and s.get("width") and s.get("height"):
            return int(s["width"]), int(s["height"])
    return None


def _srt_time(sec: float) -> str:
    ms = int(round(sec * 1000))
    h, ms = divmod(ms, 3600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


_FONT_CANDIDATES = (
    "C:/Windows/Fonts/msyh.ttc",      # 微软雅黑
    "C:/Windows/Fonts/simhei.ttf",    # 黑体
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
)


def _find_font() -> str | None:
    return next((f for f in _FONT_CANDIDATES if Path(f).exists()), None)


def _drawtext_escape(text: str) -> str:
    return (text.replace("\\", "\\\\").replace(":", "\\:")
            .replace("'", "\\'").replace("%", "\\%"))


def _burn_subtitles(text_clips: list[Clip], base: Path, out: Path,
                    shift=None) -> bool:
    """drawtext 烧录字幕（不依赖 libass，带 CJK 字体发现）。无字体返回 False。"""
    font = _find_font()
    if font is None:
        return False
    font_esc = font.replace(":", "\\:")  # Windows 盘符冒号会断滤镜解析
    shift = shift or (lambda t: t)
    filters = []
    for c in sorted(text_clips, key=lambda c: c.timeline_range.start):
        text = c.context.get("text", "")
        if not text:
            continue
        # 字幕样式（clip.context.style：size/color/position）
        st = c.context.get("style", {}) or {}
        size = int(st.get("size", 38))
        color = st.get("color", "white")
        y = "40" if st.get("position") == "top" else "h-90"
        s, e = shift(c.timeline_range.start), shift(c.timeline_range.end)
        filters.append(
            f"drawtext=fontfile='{font_esc}':text='{_drawtext_escape(text)}'"
            f":fontsize={size}:fontcolor={color}:borderw=2:bordercolor=black"
            f":x=(w-text_w)/2:y={y}"
            f":enable='between(t,{s:.3f},{e:.3f})'")
    if not filters:
        return False
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-i", str(base),
         "-vf", ",".join(filters),
         "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
         "-c:a", "copy", str(out)],
        check=True, capture_output=True)
    return True


def _render_part(clip: Clip, asset: Asset, out: Path,
                 width: int, fps: int) -> None:
    """渲染单个主轨 clip：切取 + 画面调整 + 变换 + 变速 + 音量；无音轨补静音。
    图片素材：-loop 1 按 source_range 时长静帧输出。

    调整图层 → 滤镜链（全部非破坏，顺序即下）：
      reverse → crop → flip → color(eq/colortemp/unsharp) → rotate →
      transform2d(模糊背景+缩放定位合成) / 普通 scale → opacity(压暗) →
      delogo → fade → speed/fps
    """
    asset_path = asset.path
    is_image = asset.type == AssetType.IMAGE
    has_audio = (not is_image) and _has_audio(asset_path)
    src_len = clip.source_range.end - clip.source_range.start
    dur = src_len / clip.speed

    def _adj(kind: str) -> dict | None:
        return next((a for a in reversed(clip.adjustments)
                     if a.get("kind") == kind), None)

    # ---------- 视频链（输入级，缩放前） ----------
    pre: list[str] = []
    if _adj("reverse"):
        pre.append("reverse")
    if (a := _adj("crop")):
        p = a.get("params", {})
        l, t = float(p.get("left", 0)), float(p.get("top", 0))
        r, b = float(p.get("right", 0)), float(p.get("bottom", 0))
        pre.append(f"crop=iw*{1 - l - r:.4f}:ih*{1 - t - b:.4f}:iw*{l:.4f}:ih*{t:.4f}")
    if (a := _adj("flip")):
        p = a.get("params", {})
        if p.get("h"):
            pre.append("hflip")
        if p.get("v"):
            pre.append("vflip")
    if (a := _adj("color")):
        p = a.get("params", {})
        eq = []
        if "brightness" in p:
            eq.append(f"brightness={p['brightness']}")
        if "contrast" in p:
            eq.append(f"contrast={p['contrast']}")
        if "saturation" in p:
            eq.append(f"saturation={p['saturation']}")
        if eq:
            pre.append("eq=" + ":".join(eq))
        if "temperature" in p:
            pre.append(f"colortemperature=temperature={p['temperature']}")
        if "sharpen" in p:
            pre.append(f"unsharp=5:5:{p['sharpen']}")
    t2d = _adj("transform2d")
    if t2d and t2d.get("params", {}).get("rotation"):
        import math
        deg = float(t2d["params"]["rotation"])
        pre.append(f"rotate={deg * math.pi / 180:.5f}:fillcolor=none")

    # ---------- 帧尺寸合成 ----------
    use_complex = t2d is not None
    size = _video_size(asset_path) or (width, width * 9 // 16)
    out_h = int(width * size[1] / size[0]) & ~1  # 与 scale=-2 取整一致

    tail: list[str] = []  # 帧尺寸之后的链（delogo/opacity/fade/fps/speed）
    delogos = [a for a in clip.adjustments if a.get("kind") == "delogo"]
    for a in delogos:
        p = a.get("params", {})
        x = max(0, int(p.get("x", 0) * width))
        y = max(0, int(p.get("y", 0) * out_h))
        w = min(int(p.get("w", 0) * width), width - x - 1)
        h = min(int(p.get("h", 0) * out_h), out_h - y - 1)
        if w > 1 and h > 1:
            tail.append(f"delogo=x={x}:y={y}:w={w}:h={h}")
    if (a := _adj("opacity")):
        v = float(a.get("params", {}).get("value", 1.0))
        tail.append(f"colorchannelmixer=rr={v}:gg={v}:bb={v}")
    fades = [a for a in clip.adjustments if a.get("kind") == "fade"]
    if fades:
        p = fades[-1].get("params", {})
        fi, fo = float(p.get("in", 0)), float(p.get("out", 0))
        if fi > 0:
            tail.append(f"fade=t=in:st=0:d={fi:.3f}")
        if fo > 0:
            tail.append(f"fade=t=out:st={max(0.0, dur - fo):.3f}:d={fo:.3f}")
    tail.append(f"fps={fps}")
    if clip.speed != 1.0:
        tail.insert(0, f"setpts=PTS/{clip.speed}")

    if use_complex:
        p = t2d.get("params", {})
        sc = float(p.get("scale", 1.0))
        ox = float(p.get("x", 0.0))
        oy = float(p.get("y", 0.0))
        bg_blur = bool(p.get("bg_blur", True))
        w2 = max(16, int(width * sc)) & ~1
        bg_f = f"scale={width}:{out_h},gblur=sigma=20" if bg_blur \
            else f"scale={width}:{out_h},colorchannelmixer=rr=0:gg=0:bb=0"
        pre_s = ",".join(pre) + "," if pre else ""
        fc = (f"[0:v]{pre_s}scale={width}:{out_h}[pre0];"
              f"[pre0]{bg_f}[bg];"
              f"[pre0]scale={w2}:-2[fg];"
              f"[bg][fg]overlay=(W-w)/2+{ox}*W/2:(H-h)/2+{oy}*H/2[out0];"
              f"[out0]{','.join(tail)}[vout]")
        video_args = ["-filter_complex", fc + (";[0:a]anull[aout]" if False else ""),
                      "-map", "[vout]"]
    else:
        vf = ",".join([*pre, f"scale={width}:-2", *tail])
        video_args = ["-vf", vf]

    # 输入全部在前，滤镜/编码参数在后
    if is_image:
        cmd = ["ffmpeg", "-y", "-v", "error",
               "-loop", "1", "-t", f"{src_len:.3f}", "-i", asset_path]
    else:
        cmd = [
            "ffmpeg", "-y", "-v", "error",
            "-ss", f"{clip.source_range.start:.3f}",
            "-i", asset_path,
        ]
    if not has_audio:
        # 补静音，保证 concat 时流结构一致
        cmd += ["-f", "lavfi", "-t", f"{dur:.3f}",
                "-i", "anullsrc=channel_layout=stereo:sample_rate=44100"]
    cmd += ["-t", f"{src_len:.3f}", *video_args]
    if has_audio:
        # 调整图层（denoise → afftdn）→ 变速 → 音量；范围音量用 enable 局部生效
        af_parts = []
        if _adj("reverse"):
            af_parts.append("areverse")
        for adj in clip.adjustments:
            if adj.get("kind") == "denoise":
                nr = adj.get("params", {}).get("nr", 12)
                af_parts.append(f"afftdn=nr={nr}")
        if clip.speed != 1.0:
            af_parts.append(f"atempo={min(max(clip.speed, 0.5), 2.0)}")
        af_parts.append("volume=0" if clip.context.get("muted")
                        else f"volume={clip.volume}")
        for adj in clip.adjustments:
            if adj.get("kind") == "volume_range" and adj.get("time_range"):
                # 时间轴时间 → 本 clip 分片内相对时间
                tr = adj["time_range"]
                s = max(0.0, tr["start"] - clip.timeline_range.start)
                e = min(dur, tr["end"] - clip.timeline_range.start)
                v = adj.get("params", {}).get("volume", 1.0)
                if e > s:
                    af_parts.append(f"volume={v}:enable='between(t,{s:.3f},{e:.3f})'")
        for adj in clip.adjustments:
            if adj.get("kind") == "fade":
                p = adj.get("params", {})
                fi, fo = float(p.get("in", 0)), float(p.get("out", 0))
                if fi > 0:
                    af_parts.append(f"afade=t=in:st=0:d={fi:.3f}")
                if fo > 0:
                    af_parts.append(
                        f"afade=t=out:st={max(0.0, dur - fo):.3f}:d={fo:.3f}")
        cmd += ["-af", ",".join(af_parts), "-c:a", "aac"]
    else:
        cmd += ["-c:a", "aac", "-shortest"]
    cmd += ["-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", str(out)]
    subprocess.run(cmd, check=True, capture_output=True)


def _concat_dissolve(parts: list[Path], durs: list[float],
                     boundaries: list[tuple[float, str]], out: Path) -> None:
    """xfade/acrossfade 链拼接（有叠化时替代 concat demuxer）。
    boundaries[i] = (重叠时长, 转场类型)（硬切给 1 帧的微小 fade 统一链路）。"""
    cmd = ["ffmpeg", "-y", "-v", "error"]
    for p in parts:
        cmd += ["-i", str(p)]
    vf, af = [], []
    ds = [d for d, _ in boundaries]
    for k in range(1, len(parts)):
        d, ttype = boundaries[k - 1]
        offset = sum(durs[:k]) - sum(ds[:k])
        prev_v = "[0:v]" if k == 1 else f"[v{k - 1}]"
        prev_a = "[0:a]" if k == 1 else f"[a{k - 1}]"
        vlabel = f"[v{k}]"
        alabel = f"[a{k}]"
        vf.append(f"{prev_v}[{k}:v]xfade=transition={ttype}:duration={d:.3f}"
                  f":offset={offset:.3f}{vlabel}")
        af.append(f"{prev_a}[{k}:a]acrossfade=d={d:.3f}{alabel}")
    n = len(parts) - 1
    cmd += ["-filter_complex", ";".join(vf + af),
            "-map", f"[v{n}]", "-map", f"[a{n}]",
            "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
            "-c:a", "aac", str(out)]
    subprocess.run(cmd, check=True, capture_output=True)


def _render_gap(duration: float, out: Path, width: int, fps: int) -> None:
    """主轨间隙填充：黑场 + 静音（时间轴上的空洞也得占住时长）。"""
    h = (width * 9 // 16) & ~1
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error",
         "-f", "lavfi", "-i", f"color=black:s={width}x{h}:d={duration:.3f}:r={fps}",
         "-f", "lavfi", "-t", f"{duration:.3f}",
         "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
         "-vf", f"scale={width}:-2,fps={fps}",
         "-c:a", "aac", "-shortest",
         "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", str(out)],
        check=True, capture_output=True)


def _render_audio_clip(clip: Clip, asset: Asset, out: Path) -> bool:
    """渲染音频轨 clip → wav（切取 + 变速 + 音量）。无音轨素材返回 False。"""
    if asset.type == AssetType.IMAGE or not _has_audio(asset.path):
        return False
    src_len = clip.source_range.end - clip.source_range.start
    af_parts = []
    if clip.speed != 1.0:
        af_parts.append(f"atempo={min(max(clip.speed, 0.5), 2.0)}")
    af_parts.append("volume=0" if clip.context.get("muted")
                    else f"volume={clip.volume}")
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error",
         "-ss", f"{clip.source_range.start:.3f}",
         "-t", f"{src_len:.3f}",
         "-i", asset.path,
         "-af", ",".join(af_parts),
         "-ar", "44100", "-ac", "2", "-c:a", "pcm_s16le", str(out)],
        check=True, capture_output=True)
    return True


def _mix_audio_tracks(base: Path, audio_parts: list[tuple[Path, float]],
                      out: Path) -> None:
    """主视频音轨 + 音频轨 clip 按 timeline 偏移混音（adelay + amix）。"""
    cmd = ["ffmpeg", "-y", "-v", "error", "-i", str(base)]
    for wav, _ in audio_parts:
        cmd += ["-i", str(wav)]
    filters = []
    labels = ["[0:a]"]
    for i, (_, delay) in enumerate(audio_parts, start=1):
        ms = int(delay * 1000)
        filters.append(f"[{i}:a]adelay={ms}|{ms}[a{i}]")
        labels.append(f"[a{i}]")
    filters.append(
        f"{''.join(labels)}amix=inputs={len(labels)}:duration=first:normalize=0[aout]")
    cmd += ["-filter_complex", ";".join(filters),
            "-map", "0:v", "-map", "[aout]",
            "-c:v", "copy", "-c:a", "aac", str(out)]
    subprocess.run(cmd, check=True, capture_output=True)


def _render_overlay_part(clip: Clip, asset: Asset, out: Path,
                         base_width: int, fps: int) -> None:
    """画中画分片：按 clip.transform.scale 缩放（默认 0.3），纯视频无音频。"""
    scale = float((clip.transform or {}).get("scale", 0.3))
    w = max(16, int(base_width * scale)) & ~1
    src_len = clip.source_range.end - clip.source_range.start
    if asset.type == AssetType.IMAGE:
        cmd = ["ffmpeg", "-y", "-v", "error",
               "-loop", "1", "-t", f"{src_len:.3f}", "-i", asset.path]
    else:
        cmd = ["ffmpeg", "-y", "-v", "error",
               "-ss", f"{clip.source_range.start:.3f}",
               "-t", f"{src_len:.3f}", "-i", asset.path]
    vf = f"scale={w}:-2,fps={fps}"
    if clip.speed != 1.0:
        vf = f"setpts=PTS/{clip.speed},{vf}"
    cmd += ["-vf", vf, "-an", "-c:v", "libx264", "-preset", "veryfast",
            "-pix_fmt", "yuv420p", str(out)]
    subprocess.run(cmd, check=True, capture_output=True)


def _overlay_pips(base: Path, pip_parts: list[tuple[Path, Clip]],
                  out: Path, base_size: tuple[int, int],
                  shift=None) -> None:
    """把第二视频轨的 clip 按 timeline 区间 overlay 到主画面上（PiP/B-roll）。
    位置来自 clip.transform（x/y/scale 归一化，默认右下 30% PiP）。"""
    bw, bh = base_size
    cmd = ["ffmpeg", "-y", "-v", "error", "-i", str(base)]
    for p, _ in pip_parts:
        cmd += ["-i", str(p)]
    filters = []
    for i, (_, clip) in enumerate(pip_parts, start=1):
        prev = "[0:v]" if i == 1 else f"[v{i - 1}]"
        label = f"[v{i}]"
        tr = clip.transform or {}
        x = int(float(tr.get("x", 0.68)) * bw)
        y = int(float(tr.get("y", 0.68)) * bh)
        s = shift(clip.timeline_range.start) if shift else clip.timeline_range.start
        e = shift(clip.timeline_range.end) if shift else clip.timeline_range.end
        filters.append(
            f"{prev}[{i}:v]overlay={x}:{y}:enable='between(t,{s:.3f},{e:.3f})'{label}")
    cmd += ["-filter_complex", ";".join(filters),
            "-map", f"[v{len(pip_parts)}]", "-map", "0:a?",
            "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
            "-c:a", "copy", str(out)]
    subprocess.run(cmd, check=True, capture_output=True)


def _write_srt(clips: list[Clip], texts: dict[str, str], out: Path,
               shift=None) -> Path | None:
    """text 轨道 → SRT。clip.context['text'] 存字幕内容。
    shift：叠化时把时间轴时间换算成成片输出时间。"""
    shift = shift or (lambda t: t)
    entries = []
    for c in sorted(clips, key=lambda c: c.timeline_range.start):
        text = c.context.get("text") or texts.get(c.clip_id, "")
        if text:
            entries.append((shift(c.timeline_range.start),
                            shift(c.timeline_range.end), text))
    if not entries:
        return None
    lines = []
    for i, (start, end, text) in enumerate(entries, 1):
        lines.append(f"{i}\n{_srt_time(start)} --> {_srt_time(end)}\n{text}\n")
    out.write_text("\n".join(lines), encoding="utf-8")
    return out


def render_preview(core: ProjectCore, out_path: str | Path,
                   width: int = 1080, fps: int = 30,
                   burn_subtitles: bool = False,
                   on_step=None) -> Path:
    """on_step(label, done, total)：渲染进度回调（GUI 进度条用）。"""
    def step(label: str, done: int, total: int) -> None:
        if on_step:
            on_step(label, done, total)
    project = core.project
    assets_by_id = {a.asset_id: a for a in project.assets}
    total_steps = 0  # 先算总步数（分片 + 合成 + 可选 overlay/混音/烧录）

    video_tracks = [t for t in project.timeline.tracks if t.kind == TrackKind.VIDEO]
    video_track = video_tracks[0] if video_tracks else None
    if video_track is None or not video_track.clip_ids:
        raise RuntimeError("Timeline 上没有视频轨道或 clip")

    clips = sorted(
        (project.clips[cid] for cid in video_track.clip_ids),
        key=lambda c: c.timeline_range.start,
    )
    # 第二及以后的视频轨 → PiP/叠化 overlay（静音轨跳过）
    pip_clips = sorted(
        (project.clips[cid]
         for t in video_tracks[1:] if not t.muted
         for cid in t.clip_ids if cid in project.clips),
        key=lambda c: c.timeline_range.start,
    )
    text_track = next(
        (t for t in project.timeline.tracks if t.kind == TrackKind.TEXT), None
    )
    text_clips = [project.clips[cid] for cid in text_track.clip_ids] if text_track else []
    audio_clips = sorted(
        (project.clips[cid]
         for t in project.timeline.tracks
         if t.kind == TrackKind.AUDIO and not t.muted
         for cid in t.clip_ids if cid in project.clips),
        key=lambda c: c.timeline_range.start,
    )

    out_path = Path(out_path)
    with tempfile.TemporaryDirectory() as tmp:
        # 分片：(path, kind[clip|gap], dur, clip|None)
        part_meta: list[tuple[Path, str, float, Clip | None]] = []
        cursor = 0.0
        for i, clip in enumerate(clips):
            asset = assets_by_id.get(clip.asset_id)
            if asset is None or not Path(asset.path).exists():
                continue  # 素材缺失：跳过（正式版走 Asset Resolver 找回）
            # 时间轴间隙 → 黑场静音填充（占住时长，混音/字幕才对得齐）
            gap = clip.timeline_range.start - cursor
            if gap > 0.05:
                gap_part = Path(tmp) / f"gap{i:03d}.mp4"
                _render_gap(gap, gap_part, width, fps)
                part_meta.append((gap_part, "gap", gap, None))
            part = Path(tmp) / f"part{i:03d}.mp4"
            step(f"分片 {i + 1}/{len(clips)}", i, len(clips) + 3)
            _render_part(clip, asset, part, width, fps)
            dur = (clip.source_range.end - clip.source_range.start) / clip.speed
            part_meta.append((part, "clip", dur, clip))
            cursor = max(cursor, clip.timeline_range.end)
        if not part_meta:
            raise RuntimeError("没有可渲染的 clip（素材文件可能缺失）")

        # 叠化边界：相邻都是真实 clip 且后者带 dissolve 调整图层
        dissolves: dict[int, tuple[float, str]] = {}
        for k in range(1, len(part_meta)):
            _, kind_prev, dur_prev, _ = part_meta[k - 1]
            _, kind_cur, dur_cur, clip_cur = part_meta[k]
            if kind_prev != "clip" or kind_cur != "clip" or clip_cur is None:
                continue
            adj = next((a for a in clip_cur.adjustments
                        if a.get("kind") == "dissolve"), None)
            if adj:
                d = float(adj.get("params", {}).get("duration", 0))
                ttype = str(adj.get("params", {}).get("type", "fade"))
                if d > 0:
                    dissolves[k] = (min(d, dur_prev, dur_cur), ttype)

        # 叠化让成片比时间轴短：字幕/混音/PiP 按累计重叠量同步偏移
        boundaries = sorted(
            (part_meta[k][3].timeline_range.start, d)  # type: ignore[union-attr]
            for k, (d, _) in dissolves.items())

        def shift(t: float) -> float:
            return t - sum(d for b, d in boundaries if b <= t)

        concat_out = Path(tmp) / "concat.mp4"
        step("合成主轨", len(clips), len(clips) + 3)
        if dissolves:
            _concat_dissolve(
                [m[0] for m in part_meta],
                [m[2] for m in part_meta],
                [dissolves.get(k, (1 / fps, "fade"))
                 for k in range(1, len(part_meta))],
                concat_out)
        else:
            concat_list = Path(tmp) / "concat.txt"
            concat_list.write_text(
                "\n".join(f"file '{m[0].as_posix()}'" for m in part_meta),
                encoding="utf-8"
            )
            subprocess.run(
                ["ffmpeg", "-y", "-v", "error",
                 "-f", "concat", "-safe", "0", "-i", str(concat_list),
                 "-c", "copy", str(concat_out)],
                check=True, capture_output=True)

        # 第二视频轨 overlay（PiP/B-roll）：重编码视频，必须在混音（-c:v copy）之前
        if pip_clips:
            pip_parts = []
            for k, clip in enumerate(pip_clips):
                asset = assets_by_id.get(clip.asset_id)
                if asset is None or not Path(asset.path).exists():
                    continue
                part = Path(tmp) / f"pip{k:02d}.mp4"
                _render_overlay_part(clip, asset, part, width, fps)
                pip_parts.append((part, clip))
            if pip_parts:
                size = _video_size(concat_out) or (width, width * 9 // 16)
                overlaid = Path(tmp) / "overlaid.mp4"
                _overlay_pips(concat_out, pip_parts, overlaid, size, shift=shift)
                concat_out = overlaid

        # 音频轨（BGM/旁白）混音
        step("混音/字幕", len(clips) + 1, len(clips) + 3)
        audio_parts = []
        for j, clip in enumerate(audio_clips):
            asset = assets_by_id.get(clip.asset_id)
            if asset is None or not Path(asset.path).exists():
                continue
            wav = Path(tmp) / f"audio{j:02d}.wav"
            if _render_audio_clip(clip, asset, wav):
                audio_parts.append((wav, shift(clip.timeline_range.start)))
        if audio_parts:
            mixed = Path(tmp) / "mixed.mp4"
            _mix_audio_tracks(concat_out, audio_parts, mixed)
            concat_out = mixed

        srt = _write_srt(text_clips, {}, Path(tmp) / "subs.srt", shift=shift)
        cmd = ["ffmpeg", "-y", "-v", "error", "-i", str(concat_out)]
        if srt and burn_subtitles:
            # 烧录进画面（不可编辑，用于分发成片；工程里仍保留软字幕数据）
            burned = Path(tmp) / "burned.mp4"
            if _burn_subtitles(text_clips, concat_out, burned, shift=shift):
                cmd = ["ffmpeg", "-y", "-v", "error", "-i", str(burned),
                       "-c", "copy"]
            else:
                cmd += ["-c", "copy"]  # 无字体/无字幕：原样输出
        elif srt:
            cmd += ["-i", str(srt)]
            cmd += ["-c:v", "copy", "-c:a", "copy", "-c:s", "mov_text",
                    "-metadata:s:s:0", "language=chi"]
        else:
            cmd += ["-c", "copy"]
        cmd.append(str(out_path))
        subprocess.run(cmd, check=True, capture_output=True)
    step("完成", len(clips) + 3, len(clips) + 3)
    return out_path
