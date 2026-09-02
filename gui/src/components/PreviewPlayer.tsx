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

import { useEffect, useMemo, useRef, useState } from "react";
import { api, Project } from "../api";
import {
  activeLayerAt,
  activeSubtitleAt,
  PreviewLayer,
  sourceSecondsAt,
  usePreviewPlan,
} from "../preview-plan";
import { computeCanvasSize, parseAspect } from "../preview-aspect";
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
import { useProjectSequence } from "../sequence";
import {
  badgeColorForKind,
} from "../composite-multilayer";
import {
  resolveLayerTransform,
  layerCssTransform,
  zOrderedLayers,
} from "../preview-layer";
import { clipFramesFromSec, type Rational } from "../frames";

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
  // GUI-03E-3: scope the L1 plan cache to the active Timeline so
  // Preview cannot leak content between Timelines. Falls back to
  // "main" if unset (legacy single-Timeline projects still work).
  timelineId?: string;
  // R6.1-D: external invalidation counter. App.tsx owns this and
  // bumps it after every successful mutation; the hook refetches
  // immediately instead of waiting for the 5-second /sequence poll.
  planInvalidationVersion?: number;
  // GUI-03R3-W-A.4: expose the playback transport so the parent
  // (App.tsx) can wire Spacebar / K (the keymap's local-action
  // `_toggle_play` binding) to the PreviewPlayer's FrameClock
  // toggle. The FrameClock is internal to PreviewPlayer; the
  // parent never sees it directly. `onTransportReady` is called
  // once per (clockRef, mount) pair. The toggle function is
  // stable for the lifetime of this PreviewPlayer instance.
  onTransportReady?: (api: { toggle: () => void }) => void;
}

const ASPECTS: { id: AspectRatio; label: string; w: number; h: number; tooltip: string }[] = [
  { id: "16:9", label: "16:9", w: 16, h: 9, tooltip: "横屏 (YouTube / B站)" },
  { id: "9:16", label: "9:16", w: 9, h: 16, tooltip: "竖屏 (抖音 / 快手)" },
  { id: "1:1",  label: "1:1",  w: 1,  h: 1,  tooltip: "方形 (小红书 / 朋友圈)" },
  { id: "4:3",  label: "4:3",  w: 4,  h: 3,  tooltip: "传统电视" },
  { id: "3:4",  label: "3:4",  w: 3,  h: 4,  tooltip: "竖版传统" },
];

export default function PreviewPlayer({
  project, playheadFrame, renderedUrl, onPlayhead, onStatus,
  overrideSrc, onClearOverride,
  aspect = "16:9", onAspect,
  durationHint = 120,
  timelineId,
  planInvalidationVersion = 0,
  onTransportReady,
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

  // GUI-03R3-W-A.4: stable playback toggle. Both the toolbar
  // button and the parent's Spacebar/K keydown handler invoke
  // this same closure so the FrameClock is the single source of
  // truth — neither path bypasses the other.
  const togglePlay = () => {
    const c = clockRef.current;
    if (!c) return;
    frameClockTogglePlay(c);
    forceRender((n) => n + 1);
  };

  // Publish the transport handle to the parent (App.tsx) so the
  // keydown handler can reach it. Called once per clockRef lifetime
  // (the FrameClock is recreated when durationHint changes, so we
  // re-publish on every clock creation).
  useEffect(() => {
    if (!onTransportReady) return;
    onTransportReady({ toggle: togglePlay });
    // Intentionally only on clockRef mount / durationHint change.
    // The togglePlay closure captures the current clockRef (which
    // is stable across renders until durationHint changes).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [clockRef.current, onTransportReady]);

  // RAF render loop. Computes the integer TimelineFrame from the
  // FrameClock (pure function of performance.now()), pushes it via
  // onPlayhead, and re-renders. The clock itself never accumulates
  // from RAF — RAF is purely a render trigger.
  //
  // GUI-03R2 P0-E: re-schedule the RAF loop whenever the play state
  // changes. The original implementation scheduled one RAF at mount
  // and bailed if the clock wasn't playing yet — so play() could
  // never re-arm the loop. We now run while `playing` is true, and
  // ALSO start the loop when it flips to true.
  useEffect(() => {
    if (!playing) return;
    let rafId = 0;
    let stopped = false;
    const tick = () => {
      if (stopped) return;
      const c = clockRef.current;
      if (c && c.playing) {
        const f = frameClockCurrentFrame(c);
        onPlayhead(f);
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
    return () => {
      stopped = true;
      if (rafId) cancelAnimationFrame(rafId);
    };
  }, [playing, onPlayhead]);

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
  //
  // R6-A: /project returns `timeline_range.start/end` in SECONDS
  // (legacy model storage). The half-open membership check uses
  // playheadFrame (integer FRAMES). We must convert at the
  // boundary — comparing the two units directly returns 0 hits
  // for any clip that doesn't start at frame 0. clipFramesFromSec
  // is the ONE sanctioned helper for this boundary (rounds via
  // roundHalfAwayFromZero, not Math.round). `seqFps` is declared
  // above (line ~102).
  //
  // R6.2-B2/B3: the L0 fallback must filter `track.hidden`. The
  // previous code used `t.kind === "video"` only, which let the
  // first hidden video track resurrect its clips in the preview
  // even though the L1 composite (PreviewPlan) correctly excluded
  // them. Invariant: Track.hidden == true → no renderer layer for
  // that track. The L0 fallback now skips hidden tracks.
  const vtrack = (project.timelines?.find(
    (tl) => tl.timeline_id === project.active_timeline_id,
  ) ?? project.timelines?.[0])?.tracks.find(
    (t) => t.kind === "video" && !t.hidden,
  );
  const clips = (vtrack?.clip_ids ?? [])
    .map((id) => project.clips[id])
    .filter(Boolean)
    .map((c) => ({ clip: c, ...clipFramesFromSec(c, seqFps) }))
    .sort((a, b) => a.startFrame - b.startFrame);
  const clip = clips.find(
    (cf) => playheadFrame >= cf.startFrame && playheadFrame < cf.endFrame,
  )?.clip ?? null;
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
  // GUI-03R3-2 P0-4: project?.sequence?.project_revision is NOT
  // populated by the /project endpoint — the server returns
  // sequence.project_revision only from /sequence. Pull it from
  // useProjectSequence() (already polling) so usePreviewPlan
  // actually fires and the L1 composite renders.
  const liveSeq = useProjectSequence();
  const projectRevision =
    mode === "instant" ? (liveSeq.projectRevision || null) : null;
  const { plan, loading: planLoading } = usePreviewPlan(
    projectRevision,
    timelineId ?? "main",
    planInvalidationVersion,
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

  const audioNow = mode === "instant" ? ((project.timelines?.find(
    (tl) => tl.timeline_id === project.active_timeline_id,
  ) ?? project.timelines?.[0])?.tracks
    .filter((t) => t.kind === "audio" && !t.muted)
    .flatMap((t) => t.clip_ids)
    .map((id) => project.clips[id]) ?? [])
    .filter((c) => {
      if (!c || c.context?.muted) return false;
      // R6-A: c.timeline_range is seconds; playheadFrame is frames.
      // Convert at the boundary via clipFramesFromSec.
      const f = clipFramesFromSec(c, seqFps);
      return playheadFrame >= f.startFrame && playheadFrame < f.endFrame;
    })
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

  // GUI-03R4-R6: explicit canvas dimensions from a ResizeObserver on
  // .preview-stage. Inner-dimension rule: longest side =
  // min(stageWidth, stageHeight × aspect); other side = longest /
  // aspect. This replaces CSS `aspectRatio` magic so resizing the
  // inspector pane visibly resizes the canvas.
  const stageRef = useRef<HTMLDivElement | null>(null);
  const [stageSize, setStageSize] = useState<{ width: number; height: number }>({ width: 1, height: 1 });
  useEffect(() => {
    const el = stageRef.current;
    if (!el) return;
    const update = () => {
      const rect = el.getBoundingClientRect();
      setStageSize({ width: rect.width, height: rect.height });
    };
    update();
    const ro = new ResizeObserver(update);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const stageStyle: React.CSSProperties = {
    width: "100%",
    height: "100%",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    background: "#000",
    overflow: "hidden",
  };
  // R6.1-C: explicit width/height from a ResizeObserver on
  // .preview-stage, using the standard "contain" / letterbox rule
  // (pick the smaller axis scale so the rectangle fits BOTH
  // dimensions). The pre-R6.1 formula at this site used
  // `availW / aspectW` as the height — that was dimensionally wrong
  // (it gave pixels/pixel, not pixels). 16:9 on a 720×405 stage
  // produced 720×45 (a flat strip) instead of 720×405. The pure
  // helper `computeCanvasSize` is in `preview-aspect.ts` and is
  // pinned by `preview-aspect.test.ts` for the 5 standard aspects.
  const { canvas: { width: canvasW, height: canvasH } } = computeCanvasSize({
    stageWidth: stageSize.width,
    stageHeight: stageSize.height,
    inset: 16,
    aspect,
  });
  const frameStyle: React.CSSProperties = {
    width: canvasW,
    height: canvasH,
    background: "#000",
    position: "relative",
    overflow: "hidden",
    display: "flex",
    // GUI-03R3-2 P1-4: visible canvas boundary. A 2px outline
    // marks the actual output aspect ratio so the user can SEE
    // the output canvas limits — anything outside the outline
    // (letterboxing) is clearly distinguishable.
    outline: "2px solid #ffd479",
    outlineOffset: "-2px",
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
        <div className="preview-stage" ref={stageRef}>
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
    <div className="preview-player" data-layer="viewer-container">
      {/* GUI-03R5-B2 (Decision 3): the 4 layers are explicit siblings:
       *   .preview-toolbar   → "viewer-toolbar" (transport mode + aspect)
       *   .preview-stage     → "output-canvas"   (the rendered frames)
       *   .preview-progress  → "transport"      (progress bar overlay)
       *   Timeline is OUTSIDE this component (sibling of .preview-pane).
       * The data-layer attribute is the audit/test contract. */}
      <div className="preview-toolbar" data-layer="viewer-toolbar">
        <button
          className="play-btn"
          onClick={togglePlay}
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
            title={`${a.tooltip} — ${a.w}:${a.h}`}>{a.label}</button>
        ))}
      </div>
      <div className="preview-stage" data-layer="output-canvas" ref={stageRef}>
        {/* GUI-03R2 P0-F: visible TimelineFrame progress indicator.
            TimelineFrame is authoritative; HTMLMediaElement.currentTime
            is NEVER read for state (per closure invariant §02-5).
            The bar visualizes playheadFrame / max(1, endFrame). */}
        <div
          className="preview-progress"
          data-layer="transport"
          aria-label="Preview progress"
        >
          <div
            className="preview-progress-fill"
            style={{ width: `${Math.min(100, Math.max(0, (playheadFrame / Math.max(1, clockRef.current?.endFrame ?? 1)) * 100))}%` }}
          />
          <div
            className="preview-progress-thumb"
            style={{ left: `${Math.min(100, Math.max(0, (playheadFrame / Math.max(1, clockRef.current?.endFrame ?? 1)) * 100))}%` }}
          />
        </div>
        <div style={frameStyle}>
          {/* GUI-03R4-R6: playhead-in-canvas marker. TimelineFrame
              is authoritative; we render a 1px vertical line at
              (playheadFrame / endFrame) × canvasWidth. Color
              matches the timeline .playhead-overlay (#ff5050). */}
          {clockRef.current?.endFrame && clockRef.current.endFrame > 0 && (
            <div
              data-testid="preview-playhead-marker"
              style={{
                position: "absolute",
                top: 0, bottom: 0,
                left: `${Math.min(100, Math.max(0,
                  (playheadFrame / Math.max(1, clockRef.current.endFrame)) * 100))}%`,
                width: "1px",
                background: "#ff5050",
                pointerEvents: "none",
                zIndex: 9998,
                boxShadow: "0 0 4px rgba(255, 80, 80, 0.6)",
              }}
            />
          )}
          {mode === "rendered" && renderedUrl ? (
            <video key={renderedUrl} ref={videoRef} src={renderedUrl}
              controls onTimeUpdate={onTimeUpdate} style={videoStyle} />
          ) : mode === "instant" && composite && !composite.is_black ? (
            // GUI-04 04-05: render the L1 composite with EACH layer's
            // own Clip.transform (x, y, scale, rotation, opacity).
            // NO PiP heuristic. Track identity is z-order, not layout.
            // Stable z-order via layer_index ascending.
            <div className="composite-stage" style={{ position: "relative", width: "100%", height: "100%" }}>
              {(() => {
                // composite.visual_layers is already a flat list
                // ordered by layer_index (Core's build_preview_plan).
                // We still re-sort defensively to guarantee a stable
                // z-order regardless of any future Core change.
                const layers = zOrderedLayers(composite.visual_layers);
                return (
                  <>
                    {layers.map((l) => {
                      // Per-layer transform. Defaults applied for
                      // missing fields (centered, no extra scale, no
                      // rotation, full opacity). The renderer MUST
                      // NOT base visual size on track index.
                      const tr = resolveLayerTransform(l);
                      const cssT = layerCssTransform(tr);
                      const inner = l.kind === "image" ? (
                        <img
                          style={{
                            position: "absolute", inset: 0,
                            width: "100%", height: "100%",
                            objectFit: "contain",
                          }}
                          src={`/assets/${l.asset_id}/file`}
                          alt=""
                          data-layer-kind={l.kind}
                          data-track-id={l.track_id}
                        />
                      ) : (
                        <video
                          style={{
                            position: "absolute", inset: 0,
                            width: "100%", height: "100%",
                            objectFit: "contain",
                          }}
                          ref={(el) => {
                            if (!el) return;
                            const secs = sourceSecondsAt(l, playheadFrame);
                            if (Math.abs(el.currentTime - secs) > 0.4) {
                              el.currentTime = secs;
                            }
                          }}
                          src={`/assets/${l.asset_id}/file`}
                          data-layer-kind={l.kind}
                          data-track-id={l.track_id}
                          muted
                          playsInline
                        />
                      );
                      return (
                        <div
                          key={`layer:${l.track_id}:${l.clip_id}`}
                          className="composite-layer"
                          style={{
                            position: "absolute", inset: 0,
                            width: "100%", height: "100%",
                            transform: cssT.transform,
                            transformOrigin: "50% 50%",
                            opacity: cssT.opacity,
                            zIndex: l.layer_index,
                          }}
                          data-layer-transform-x={tr.x}
                          data-layer-transform-y={tr.y}
                          data-layer-transform-scale={tr.scale}
                          data-layer-transform-rotation={tr.rotation}
                          data-layer-transform-opacity={tr.opacity}
                        >
                          {inner}
                          <div
                            className="layer-badge"
                            style={{
                              position: "absolute", top: 8, left: 8,
                              padding: "2px 8px",
                              background: "rgba(0,0,0,0.65)",
                              color: badgeColorForKind(l.kind),
                              fontSize: 11, fontWeight: 600,
                              borderRadius: 3,
                              pointerEvents: "none",
                              zIndex: 9999,
                            }}
                            data-track-id={l.track_id}
                          >
                            {l.track_id.toUpperCase()}
                          </div>
                        </div>
                      );
                    })}
                  </>
                );
              })()}
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
          ) : clip && asset ? (
            // Fallback L0 single-clip path. The membership comparison
            // was already verified in FRAMES at line 226-228 (no unit
            // mismatch — clipFramesFromSec converts seconds→frames at
            // the storage→edit boundary).
            //
            // The L0 render branches on asset.type:
            //   image → render the asset URL directly. Images have no
            //          source timebase; the TimeMap fetch above returns
            //          422 for image clips and sourceFrame stays null.
            //          We MUST NOT require sourceFrame/timeMapEntry
            //          here — doing so made the L0 fallback unreachable
            //          for images, which caused the "in-gap" placeholder
            //          to fire on frames that DO have an image clip
            //          (audit finding #7). The image's sourceFrame is
            //          implicitly 0 (single source frame).
            //   video → additionally require sourceFrame + timeMapEntry
            //          (loaded async via fetchTimeMap). When those are
            //          still in flight, show a "loading" placeholder —
            //          NOT the misleading "in-gap" text, since the
            //          membership DID match.
            asset.type === "image" ? (
              <img style={videoStyle}
                src={`/assets/${asset.asset_id}/file`}
                alt=""
                data-layer-kind={asset.type} />
            ) : sourceFrame !== null && timeMapEntry ? (
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
            ) : (
              // Video clip membership matched, but the TimeMap fetch
              // is still in flight. Genuine "loading" state — the
              // clip IS there (frame-domain membership matched);
              // we just haven't derived SourceFrame yet.
              <div className="placeholder">⏳ 加载中…</div>
            )
          ) : (
            // No clip at this playhead frame. This is the ONLY case
            // where "in-gap" is truthful — the membership comparison
            // at line 226-228 found zero clips at playheadFrame. The
            // playback position is genuinely outside every visible
            // clip's range on this Timeline.
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