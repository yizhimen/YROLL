// 预览播放器：即时模式（直读源素材）/ 成片模式（渲染结果）。
//
// 即时模式 = 抓主视频轨播放头下的 clip，直接播它的源文件区间。
// 视窗比例：16:9/9:16/1:1/4:3/3:4，CSS 比例决定容器形状。

import { useEffect, useRef, useState } from "react";
import { Project } from "../api";

export type AspectRatio = "16:9" | "9:16" | "1:1" | "4:3" | "3:4";

interface Props {
  project: Project;
  playheadFrame: number;
  renderedUrl: string | null;
  onPlayhead: (t: number) => void;
  onStatus: (ok: boolean, text: string) => void;
  overrideSrc?: { url: string; isImage: boolean; label: string } | null;
  durationHint?: number;
  onClearOverride?: () => void;
  aspect?: AspectRatio;
  onAspect?: (a: AspectRatio) => void;
}

const ASPECTS: { id: AspectRatio; label: string; w: number; h: number }[] = [
  { id: "16:9", label: "16:9", w: 16, h: 9 },
  { id: "9:16", label: "9:16", w: 9, h: 16 },
  { id: "1:1",  label: "1:1",  w: 1,  h: 1 },
  { id: "4:3",  label: "4:3",  w: 4,  h: 3 },
  { id: "3:4",  label: "3:4",  w: 3,  h: 4 },
];

export default function PreviewPlayer({
  project, playheadFrame, renderedUrl, onPlayhead, onStatus,
  overrideSrc, onClearOverride,
  aspect = "16:9", onAspect,
  durationHint = 120,
}: Props) {
  const [mode, setMode] = useState<"instant" | "rendered">("instant");
  const videoRef = useRef<HTMLVideoElement | null>(null);

  // 内部播放控制：用 setInterval 推进 playheadFrame，无论有没有 video 元素
  const [playing, setPlaying] = useState(false);
  const playStartRef = useRef<{ startTime: number; startHead: number } | null>(null);

  useEffect(() => {
    if (!playing) return;
    playStartRef.current = { startTime: performance.now(), startHead: playheadFrame };
    const timer = setInterval(() => {
      const s = playStartRef.current;
      if (!s) return;
      const elapsed = (performance.now() - s.startTime) / 1000;
      const newHead = s.startHead + elapsed;
      if (newHead >= durationHint) {
        onPlayhead(durationHint);
        setPlaying(false);
        clearInterval(timer);
      } else {
        onPlayhead(newHead);
      }
    }, 33);  // 30 fps
    return () => clearInterval(timer);
  }, [playing]);

  // 同步 video 元素：play/pause 跟 playing 状态走
  useEffect(() => {
    const v = videoRef.current;
    if (!v) return;
    if (playing) v.play().catch(() => undefined);
    else v.pause();
  }, [playing]);

  useEffect(() => {
    if (renderedUrl) setMode("rendered");
  }, [renderedUrl]);

  const vtrack = project.timeline.tracks.find((t) => t.kind === "video");
  const clips = (vtrack?.clip_ids ?? [])
    .map((id) => project.clips[id])
    .filter(Boolean)
    .sort((a, b) => a.timeline_range.start - b.timeline_range.start);
  const clip = clips.find(
    (c) => playheadFrame >= c.timeline_range.start && playheadFrame < c.timeline_range.end
  ) ?? null;
  const asset = clip
    ? project.assets.find((a) => a.asset_id === clip.asset_id)
    : null;

  const srcTime = clip
    ? clip.source_range.start + (playheadFrame - clip.timeline_range.start) * clip.speed
    : 0;

  useEffect(() => {
    const v = videoRef.current;
    if (!v) return;
    if (mode === "instant" && clip) {
      if (Math.abs(v.currentTime - srcTime) > 0.4) v.currentTime = srcTime;
      v.playbackRate = clip.speed;
      v.volume = Math.min(1, clip.volume);
    } else if (mode === "rendered") {
      if (Math.abs(v.currentTime - playheadFrame) > 0.4) v.currentTime = playheadFrame;
      v.playbackRate = 1;
      v.volume = 1;
    }
  }, [playheadFrame, mode, clip?.clip_id]);

  const onTimeUpdate = (e: React.SyntheticEvent<HTMLVideoElement>) => {
    const v = e.currentTarget;
    if (mode === "rendered") {
      onPlayhead(v.currentTime);
      return;
    }
    if (!clip) return;
    const t = clip.timeline_range.start + (v.currentTime - clip.source_range.start) / clip.speed;
    if (v.currentTime >= clip.source_range.end - 0.05) {
      const next = clips.find((c) => c.timeline_range.start >= clip.timeline_range.end - 0.01
        && c.clip_id !== clip.clip_id);
      if (next) {
        onPlayhead(next.timeline_range.start);
      } else {
        v.pause();
        onPlayhead(clip.timeline_range.end);
      }
    } else {
      onPlayhead(Math.max(clip.timeline_range.start, t));
    }
  };

  const audioNow = mode === "instant" ? project.timeline.tracks
    .filter((t) => t.kind === "audio" && !t.muted)
    .flatMap((t) => t.clip_ids)
    .map((id) => project.clips[id])
    .filter((c) => c && !c.context?.muted
      && playheadFrame >= c.timeline_range.start && playheadFrame < c.timeline_range.end)
    : [];

  const audioRefs = useRef<Map<string, HTMLAudioElement>>(new Map());

  useEffect(() => {
    for (const c of audioNow) {
      const el = audioRefs.current.get(c.clip_id);
      if (!el) continue;
      const t = c.source_range.start + (playheadFrame - c.timeline_range.start) * c.speed;
      if (Math.abs(el.currentTime - t) > 0.4) el.currentTime = t;
      el.volume = Math.min(1, c.volume);
      el.playbackRate = c.speed;
      if (playing && el.paused) el.play().catch(() => undefined);
      if (!playing && !el.paused) el.pause();
    }
  }, [playheadFrame, playing, audioNow.map((c) => c.clip_id).join(",")]);

  // 视窗比例：外层 stage 全填，内层 frame 用 aspect-ratio
  const stageStyle: React.CSSProperties = {
    width: "100%",
    height: "100%",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    background: "#000",
    overflow: "hidden",
  };
  const frameStyle: React.CSSProperties = {
    aspectRatio: aspect.replace(":", " / "),
    maxWidth: "100%",
    maxHeight: "100%",
    background: "#000",
    position: "relative",
    overflow: "hidden",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
  };

  const videoStyle: React.CSSProperties = {
    width: "100%",
    height: "100%",
    objectFit: "contain",
  };

  if (overrideSrc) {
    return (
      <div className="preview-player">
        <div className="preview-toolbar">
          <span className="preview-asset-label">素材预览：{overrideSrc.label}</span>
          <button onClick={onClearOverride}>返回时间轴</button>
        </div>
        <div className="preview-stage">
          <div style={frameStyle}>
            {overrideSrc.isImage ? (
              <img style={videoStyle} src={overrideSrc.url} alt="" />
            ) : (
              <video key={overrideSrc.url} ref={videoRef} src={overrideSrc.url}
                controls autoPlay style={videoStyle} />
            )}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="preview-player">
      <div className="preview-toolbar">
        <button
          className="play-btn"
          onClick={() => setPlaying((p) => !p)}
          title="播放/暂停（空格键）"
        >
          {playing ? "⏸" : "▶"}
        </button>
        <button className={mode === "instant" ? "active" : ""}
          onClick={() => setMode("instant")}
          title="直读源素材（无 BGM/字幕/PiP）">即时</button>
        <button className={mode === "rendered" ? "active" : ""}
          disabled={!renderedUrl}
          onClick={() => renderedUrl ? setMode("rendered") :
            onStatus(false, "先「渲染预览」生成成片")}
          title="渲染产物（完整合成）">成片</button>
        <span className="preview-spacer" />
        <span className="preview-aspect-label">视窗：</span>
        {ASPECTS.map((a) => (
          <button key={a.id}
            className={`aspect-btn ${aspect === a.id ? "active" : ""}`}
            onClick={() => onAspect?.(a.id)}
            title={`${a.w}:${a.h}`}>{a.label}</button>
        ))}
      </div>
      <div className="preview-stage">
        <div style={frameStyle}>
          {mode === "rendered" && renderedUrl ? (
            <video key={renderedUrl} ref={videoRef} src={renderedUrl}
              controls onTimeUpdate={onTimeUpdate} style={videoStyle} />
          ) : clip && asset ? (
            asset.type === "image" ? (
              <img style={videoStyle} src={`/assets/${asset.asset_id}/file`} alt="" />
            ) : (
              <video key={clip.clip_id} ref={videoRef}
                src={`/assets/${asset.asset_id}/file`}
                controls autoPlay muted
                onTimeUpdate={onTimeUpdate}
                onPlay={() => setPlaying(true)}
                onPause={() => setPlaying(false)}
                onLoadedMetadata={(e) => {
                  e.currentTarget.currentTime = srcTime;
                  e.currentTarget.playbackRate = clip.speed;
                  e.currentTarget.volume = Math.min(1, clip.volume);
                  // 确保自动播放（muted 是浏览器要求）
                  e.currentTarget.play().catch(() => undefined);
                }}
                style={videoStyle} />
            )
          ) : (
            <div className="placeholder">
              {clips.length === 0
                ? "📭 时间轴是空的——从素材库拖到 V1 轨"
                : `⏰ 播放头在间隙里（${playheadFrame.toFixed(1)}s）`}
            </div>
          )}
        </div>
      </div>
      {/* 即时模式音频轨 */}
      {audioNow.map((c) => (
        <audio key={c.clip_id}
          ref={(el) => {
            if (el) audioRefs.current.set(c.clip_id, el);
            else audioRefs.current.delete(c.clip_id);
          }}
          src={`/assets/${c.asset_id}/file`} />
      ))}
    </div>
  );
}
