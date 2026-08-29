// 预览播放器：即时模式（直读源素材）/ 成片模式（渲染结果）。
//
// GUI-02.5 closure invariants:
//
//   - Authoritative time = TimelineFrame (integer). The FrameClock
//     derives the integer from performance.now() + a start anchor —
//     NEVER from setInterval accumulation, NEVER from
//     video.currentTime, NEVER from video.timeupdate.
//   - requestAnimationFrame is render cadence only; the clock is
//     derived independently on each tick.
//   - HTMLMediaElement.currentTime is EXTERNAL MEDIA I/O only. The
//     GUI writes it from Core's TimeMap response (TimelineFrame →
//     SourceFrame via the cached timemap-cache, then
//     SourceFrame → seconds via asset source_fps). The GUI never
//     reads v.currentTime as TimelineFrame state.
//   - No video.timeupdate → playheadFrame feedback loop. The
//     onTimeUpdate handler is only for end-of-clip detection (an
//     orthogonal event), never for state derivation.

import { useEffect, useRef, useState } from "react";
import { api, Project } from "../api";
import {
  activeLayerAt,
  activeSubtitleAt,
  PreviewLayer,
  sourceSecondsAt,
  usePreviewPlan,
} from "../preview-plan";
import {
  type FrameClock,
  createFrameClock,
  currentFrame as frameClockCurrentFrame,
  pause as frameClockPause,
  play as frameClockPlay,
  seek as frameClockSeek,
  togglePlay as frameClockTogglePlay,
} from "../frame-clock";
import {
  fetchTimeMap,
  sourceFromTimeline,
  sourceFrameToMediaSeconds,
  type TimeMapCacheEntry,
} from "../timemap-cache";

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

  // Canonical sequence (timebase). Falls back to flat fps_num/fps_den
  // for legacy v0.1 projects that lack `sequence`. Treat absent
  // sequence as 30fps default so the player still mounts.
  const seq = project.sequence ?? {
    fps: { num: project.fps_num ?? 30, den: project.fps_den ?? 1 },
    project_revision: 0,
  };
  const seqFps = { num: seq.fps.num, den: seq.fps.den };
  const videoRef = useRef<HTMLVideoElement | null>(null);

  // FrameClock: single playback-clock abstraction. We re-create it
  // when durationHint changes (timeline bounds) so the endFrame
  // clamp is correct. The clock is the authoritative TimelineFrame
  // source — see currentFrame(c, performance.now()).
  const clockRef = useRef<FrameClock | null>(null);
  if (clockRef.current === null) {
    clockRef.current = createFrameClock({
      startFrame: playheadFrame,
      fps: seqFps,
      endFrame: Math.round(durationHint * seqFps.num / seqFps.den),
    });
  }

  // [playing] is a UI state mirror; the FrameClock's `playing` is the
  // source of truth. We sync from clock to UI on every render via
  // a useEffect-free read (the render reads clockRef.current.playing).
  const [_, forceRender] = useState(0);
  const playing = clockRef.current.playing;

  // RAF render loop. Computes the integer TimelineFrame from the
  // FrameClock (pure function of performance.now()), pushes it via
  // onPlayhead, and re-renders. The clock itself never accumulates
  // from RAF — RAF is purely a render trigger.
  useEffect(() => {
    let rafId = 0;
    const tick = () => {
      const c = clockRef.current;
      if (c && c.playing) {
        const f = frameClockCurrentFrame(c);
        onPlayhead(f);
        // End-of-timeline: stop the clock if we've hit the end.
        if (f >= c.endFrame) {
          frameClockPause(c);
        }
        forceRender((n) => n + 1);
        rafId = requestAnimationFrame(tick);
      } else {
        forceRender((n) => n + 1);
      }
    };
    rafId = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(rafId);
  }, [onPlayhead]);

  // When the user drags the playhead externally (e.g. clicking on
  // the timeline ruler), the prop playheadFrame changes. We sync
  // the clock by seeking to that frame, preserving play state.
  useEffect(() => {
    const c = clockRef.current;
    if (!c) return;
    const clamped = frameClockSeek(c, playheadFrame);
    if (clamped !== playheadFrame) onPlayhead(clamped);
  }, [playheadFrame, onPlayhead]);

  // Sync HTML media element play/pause with the clock.
  useEffect(() => {
    const v = videoRef.current;
    if (!v) return;
    if (clockRef.current?.playing) v.play().catch(() => undefined);
    else v.pause();
  }, [playing]);

  useEffect(() => {
    if (renderedUrl) setMode("rendered");
  }, [renderedUrl]);

  // Find the clip covering the current playheadFrame (TimelineFrame
  // integer). The find is over the project's clip list — no time
  // math beyond the half-open interval check.
  const vtrack = project.timeline.tracks.find((t) => t.kind === "video");
  const clips = (vtrack?.clip_ids ?? [])
    .map((id) => project.clips[id])
    .filter(Boolean)
    .sort((a, b) => a.timeline_range.start - b.timeline_range.start);
  const clip = clips.find(
    (c) => playheadFrame >= c.timeline_range.start && playheadFrame < c.timeline_range.end,
  ) ?? null;
  const asset = clip
    ? project.assets.find((a) => a.asset_id === clip.asset_id)
    : null;

  // SourceFrame integer (per-asset source timebase) for the current
  // TimelineFrame. RESOLVED VIA CORE'S TimeMap (cached) — we never
  // compute this locally. The timemap-cache returns Core's answer;
  // we mirror it into React state for the sync effect below.
  const [sourceFrame, setSourceFrame] = useState<number | null>(null);
  const [timeMapEntry, setTimeMapEntry] = useState<TimeMapCacheEntry | null>(null);

  // GUI-03D.1: L1 Preview Plan cache. Replaces the per-frame
  // /preview/at_frame fetch with one cached plan per
  // project_revision. The active layer is resolved LOCALLY for
  // every TimelineFrame change, so continuous playback does NOT
  // generate per-frame HTTP.
  const projectRevision =
    project?.sequence?.project_revision ?? null;
  const { plan, loading: planLoading } = usePreviewPlan(
    mode === "instant" ? projectRevision : null,
  );

  // Active composite at the current playheadFrame, derived from
  // the cached plan. Recomputed on every render — no HTTP.
  const composite: {
    visual_layers: PreviewLayer[];
    audio_layers: PreviewLayer[];
    subtitle_texts: string[];
    is_black: boolean;
  } | null = (() => {
    if (!plan || mode !== "instant") return null;
    const visual: PreviewLayer[] = [];
    const audio: PreviewLayer[] = [];
    for (const track of plan.tracks) {
      const layer = activeLayerAt(track, playheadFrame);
      if (layer === null) continue;
      if (layer.kind === "audio") audio.push(layer);
      else visual.push(layer);
    }
    const subtitle = activeSubtitleAt(plan, playheadFrame);
    return {
      visual_layers: visual,
      audio_layers: audio,
      subtitle_texts: subtitle ? [subtitle] : [],
      is_black:
        visual.length === 0 && audio.length === 0 && subtitle === null,
    };
  })();

  useEffect(() => {
    let cancelled = false;
    if (!clip) {
      setSourceFrame(null);
      setTimeMapEntry(null);
      return;
    }
    const assetFps = asset?.source_fps
      ? { num: asset.source_fps.num, den: asset.source_fps.den }
      : undefined;
    const revision = seq.project_revision ?? 0;
    (async () => {
      try {
        const entry = await fetchTimeMap(clip.clip_id, revision, seqFps, assetFps);
        if (cancelled) return;
        setTimeMapEntry(entry);
        const sf = await sourceFromTimeline(entry, playheadFrame);
        if (cancelled) return;
        setSourceFrame(sf);
      } catch (e) {
        // If Core rejects (422 — no source fps), we leave sourceFrame
        // null; the video element is hidden / shows a placeholder.
        if (!cancelled) {
          setSourceFrame(null);
          setTimeMapEntry(null);
        }
      }
    })();
    return () => { cancelled = true; };
  }, [clip?.clip_id, playheadFrame, asset?.source_fps?.num, asset?.source_fps?.den,
      seqFps.num, seqFps.den]);

  // Sync HTML media currentTime from Core's SourceFrame + asset
  // source_fps. NEVER read v.currentTime as state.
  useEffect(() => {
    const v = videoRef.current;
    if (!v) return;
    if (mode === "instant" && clip && sourceFrame !== null && timeMapEntry) {
      // SourceFrame → media seconds via the asset's source timebase
      // (NOT the sequence FPS — per the closure invariant).
      const mediaSeconds = sourceFrameToMediaSeconds(sourceFrame, timeMapEntry.sourceFps);
      if (Math.abs(v.currentTime - mediaSeconds) > 0.4) {
        v.currentTime = mediaSeconds;
      }
      v.playbackRate = clip.speed;
      v.volume = Math.min(1, clip.volume);
    } else if (mode === "rendered") {
      // Rendered mode: the timeline time = media time (renderer
      // output is at sequence fps). This is the ONE place where
      // sequence FPS and media FPS align — explicitly because the
      // rendered file's frame rate matches the project.
      if (Math.abs(v.currentTime - playheadFrame) > 0.4) {
        v.currentTime = playheadFrame;
      }
      v.playbackRate = 1;
      v.volume = 1;
    }
  }, [sourceFrame, timeMapEntry, mode, clip?.clip_id, playheadFrame]);

  // No-op: video.timeupdate is intentionally NOT used to derive
  // playheadFrame. We keep an `onTimeUpdate` hook only for the
  // rendered mode "hit the end of the rendered file" detection
  // (orthogonal to TimelineFrame state).
  const onTimeUpdate = (e: React.SyntheticEvent<HTMLVideoElement>) => {
    const v = e.currentTarget;
    if (mode !== "rendered") return;
    // Detect end-of-file in rendered mode and stop the clock if
    // we haven't already.
    if (v.duration > 0 && v.currentTime >= v.duration - 0.05) {
      const c = clockRef.current;
      if (c && c.playing) {
        frameClockPause(c);
        forceRender((n) => n + 1);
      }
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
  const audioSourceFrames = useRef<Map<string, number>>(new Map());

  // Audio: same pattern as video — Core's TimeMap resolves the
  // SourceFrame; we mirror it to media seconds using the asset's
  // source timebase.
  useEffect(() => {
    let cancelled = false;
    const revision = seq.project_revision ?? 0;
    (async () => {
      for (const c of audioNow) {
        const a = project.assets.find((x) => x.asset_id === c.asset_id);
        const assetFps = a?.source_fps
          ? { num: a.source_fps.num, den: a.source_fps.den } : undefined;
        try {
          const entry = await fetchTimeMap(c.clip_id, revision, seqFps, assetFps);
          const sf = await sourceFromTimeline(entry, playheadFrame);
          if (!cancelled) audioSourceFrames.current.set(c.clip_id, sf);
        } catch {
          // Audio clip without source fps; skip.
        }
      }
    })();
    return () => { cancelled = true; };
  }, [audioNow.map((c) => c.clip_id).join(","), playheadFrame,
      seqFps.num, seqFps.den]);

  useEffect(() => {
    for (const c of audioNow) {
      const el = audioRefs.current.get(c.clip_id);
      if (!el) continue;
      const sf = audioSourceFrames.current.get(c.clip_id);
      if (sf === undefined) continue;
      const assetFps = project.assets.find((a) => a.asset_id === c.asset_id)?.source_fps;
      const srcFps = assetFps
        ? { num: assetFps.num, den: assetFps.den }
        : seqFps;
      const mediaSeconds = sourceFrameToMediaSeconds(sf, srcFps);
      if (Math.abs(el.currentTime - mediaSeconds) > 0.4) {
        el.currentTime = mediaSeconds;
      }
      el.volume = Math.min(1, c.volume);
      el.playbackRate = c.speed;
      if (playing && el.paused) el.play().catch(() => undefined);
      if (!playing && !el.paused) el.pause();
    }
  }, [playheadFrame, playing, audioNow.map((c) => c.clip_id).join(",")]);

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
          onClick={() => {
            const c = clockRef.current;
            if (!c) return;
            frameClockTogglePlay(c);
            forceRender((n) => n + 1);
          }}
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
          ) : mode === "instant" && composite && !composite.is_black ? (
            // GUI-03D: render the L1 composite. Visual layers are
            // z-ordered (lower index = bottom). Each layer is
            // either an <img> (for image) or a <video> (for video).
            // Subtitles are rendered as a single overlay below.
            <div className="composite-stage" style={{ position: "relative", width: "100%", height: "100%" }}>
              {composite.visual_layers
                .filter((l) => l.kind === "image")
                .map((l) => (
                  <img
                    key={`${l.track_id}:${l.clip_id}`}
                    style={{
                      position: "absolute",
                      inset: 0,
                      width: "100%",
                      height: "100%",
                      objectFit: "contain",
                      zIndex: l.layer_index,
                    }}
                    src={`/assets/${l.asset_id}/file`}
                    alt=""
                  />
                ))}
              {composite.visual_layers
                .filter((l) => l.kind === "video")
                .map((l) => (
                  <video
                    key={`${l.track_id}:${l.clip_id}`}
                    style={{
                      position: "absolute",
                      inset: 0,
                      width: "100%",
                      height: "100%",
                      objectFit: "contain",
                      zIndex: l.layer_index,
                    }}
                    ref={(el) => {
                      if (!el) return;
                      // Sync v.currentTime from Core's source_seconds.
                      // Per the closure invariant: NEVER read
                      // v.currentTime as TimelineFrame state.
                      const secs = sourceSecondsAt(l, playheadFrame);
                      if (Math.abs(el.currentTime - secs) > 0.4) {
                        el.currentTime = secs;
                      }
                    }}
                    src={`/assets/${l.asset_id}/file`}
                    muted
                    playsInline
                  />
                ))}
              {composite.subtitle_texts.length > 0 && (
                <div
                  className="composite-subtitle"
                  style={{
                    position: "absolute",
                    left: 0, right: 0, bottom: "8%",
                    textAlign: "center",
                    color: "#fff",
                    textShadow: "0 0 4px #000, 0 0 2px #000",
                    fontSize: 22,
                    fontWeight: 600,
                    pointerEvents: "none",
                    zIndex: 9999,
                  }}
                >
                  {composite.subtitle_texts[composite.subtitle_texts.length - 1]}
                </div>
              )}
              {composite.audio_layers.map((l) => (
                <audio
                  key={`audio:${l.track_id}:${l.clip_id}`}
                  ref={(el) => {
                    if (!el) return;
                    const secs = sourceSecondsAt(l, playheadFrame);
                    if (Math.abs(el.currentTime - secs) > 0.4) {
                      el.currentTime = secs;
                    }
                    if (playing && el.paused) el.play().catch(() => undefined);
                    if (!playing && !el.paused) el.pause();
                  }}
                  src={`/assets/${l.asset_id}/file`}
                />
              ))}
            </div>
          ) : clip && asset && sourceFrame !== null && timeMapEntry ? (
            // Fallback L0 single-clip path (used when the composite
            // fetch hasn't completed yet, e.g. very first render).
            asset.type === "image" ? (
              <img style={videoStyle} src={`/assets/${asset.asset_id}/file`} alt="" />
            ) : (
              <video key={clip.clip_id} ref={videoRef}
                src={`/assets/${asset.asset_id}/file`}
                controls autoPlay muted
                onTimeUpdate={onTimeUpdate}
                onPlay={() => {
                  const c = clockRef.current;
                  if (c && !c.playing) {
                    frameClockPlay(c);
                    forceRender((n) => n + 1);
                  }
                }}
                onPause={() => {
                  const c = clockRef.current;
                  if (c && c.playing) {
                    frameClockPause(c);
                    forceRender((n) => n + 1);
                  }
                }}
                onLoadedMetadata={(e) => {
                  const sf = sourceFrame;
                  const entry = timeMapEntry;
                  if (sf === null || !entry) return;
                  e.currentTarget.currentTime =
                    sourceFrameToMediaSeconds(sf, entry.sourceFps);
                  e.currentTarget.playbackRate = clip.speed;
                  e.currentTarget.volume = Math.min(1, clip.volume);
                  e.currentTarget.play().catch(() => undefined);
                }}
                style={videoStyle} />
            )
          ) : (
            <div className="placeholder">
              {clips.length === 0
                ? "📭 时间轴是空的——从素材库拖到 V1 轨"
                : `⏰ 播放头在间隙里（${playheadFrame} frames）`}
            </div>
          )}
        </div>
      </div>
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