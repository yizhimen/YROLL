// GUI-02: Timeline — frame-px layout.
//
// Frame is the canonical coordinate. Seconds exist only in the
// server's `clip.timeline_range` (TimeRange in seconds). The layout
// here converts seconds → frames → pixels via the canonical
// TimeMap (when needed) and frames.ts (for px math).
//
// LABEL_GUTTER_PX is the left margin so the "0" tick label and
// playhead at frame 0 do NOT collide with the track-name column
// (封面 / 配乐 / 字幕).

import { useMemo, useRef, useState } from "react";
import { Project } from "../api";
import { useProjectSequence } from "../sequence";
import {
  LABEL_GUTTER_PX,
  chooseTickStep,
  chooseZoomProfile,
  framesToTimecode,
  pixelToPlayheadFrame,
  playheadFrameToPixel,
  pxPerFrame,
} from "../frames";
import ClipBlock from "./ClipBlock";

interface Props {
  project: Project;
  selectedIds: Set<string>;
  playheadFrame: number;
  pxPerSec: number;  // perceived-px-per-second slider
  selRange: [number, number] | null;  // seconds (legacy, kept for in-flight ref)
  inPoint?: number | null;
  outPoint?: number | null;
  height?: number;
  snapMode?: "always" | "alt" | "off";
  highlightRel?: boolean;
  onSeek: (frame: number) => void;
  onSelect: (clipId: string, viaAiZone: boolean, ctrl?: boolean) => void;
  /** Pointermove preview. `newStartFrame` is an INTEGER TimelineFrame. */
  onDragMove: (clipId: string, newStartFrame: number) => void;
  /** Drag-end move commit. Final integer TimelineFrame (post-snap). */
  onMoveCommit: (clipId: string, newStartFrame: number) => void;
  onZoomPx: (px: number) => void;
  onRangeSelect: (r: [number, number] | null) => void;
  /** Trim commit. `newStart` / `newEnd` are integer SOURCE frames. */
  onTrimCommit: (clipId: string, newStart: number | null, newEnd: number | null) => void;
  onDropOnTrack?: (clipId: string, trackId: string) => void;
  onTrackMute?: (trackId: string, muted: boolean) => void;
  onTrackLock?: (trackId: string, locked: boolean) => void;
  onTrackHide?: (trackId: string, hidden: boolean) => void;
  onAssetDrop?: (assetId: string, trackId: string, timelineStartFrame: number) => void;
}

const TRACK_NAME: Record<string, string> = { video: "视频", audio: "音频", text: "字幕" };

export default function Timeline({
  project, selectedIds, playheadFrame, pxPerSec, selRange, inPoint, outPoint,
  height = 240,
  snapMode = "always",
  highlightRel = false,
  onSeek, onSelect, onDragMove, onMoveCommit, onZoomPx, onRangeSelect, onTrimCommit, onDropOnTrack, onTrackMute, onTrackLock, onTrackHide, onAssetDrop,
}: Props) {
  const paneRef = useRef<HTMLDivElement | null>(null);
  const [viewport, setViewport] = useState({ left: 0, width: 1 });
  // Sequence (canonical timebase) — provides fps for frame↔px math
  const seq = useProjectSequence();
  // pxPerFrame derived from perceived pxPerSec and the project's fps.
  const pxPerF = useMemo(
    () => pxPerFrame(pxPerSec, seq.fps),
    [pxPerSec, seq.fps],
  );
  // Total content width in pixels: gutter + frame pixels + small tail.
  const contentWidth = LABEL_GUTTER_PX + pxPerF * 30 * 60 + 40;  // assume >=30 min
  const syncViewport = () => {
    const pane = paneRef.current;
    if (!pane) return;
    setViewport({
      left: pane.scrollLeft / contentWidth,
      width: Math.min(1, pane.clientWidth / contentWidth),
    });
  };

  // The timeline width is derived from the latest clip end (in frames),
  // not seconds. We compute it via framesToTimecode for display.
  const durationFrames = Math.max(
    300,  // 10s @ 30fps; ensures ruler isn't squished when empty
    ...Object.values(project.clips).map((c) => Math.round(c.timeline_range.end * seq.fps.num / seq.fps.den)),
  );
  // Width in pixels: LABEL_GUTTER_PX + durationFrames * pxPerF + 40
  const width = LABEL_GUTTER_PX + durationFrames * pxPerF + 40;

  // Ruler ticks. Use chooseTickStep + chooseZoomProfile to pick a
  // step that lands ticks 60-120 px apart. Labels are timecode strings.
  const profile = chooseZoomProfile(pxPerSec);
  const tickStepFrames = chooseTickStep(profile, seq.fps, pxPerSec);
  const ticks: number[] = [];
  for (let t = 0; t <= durationFrames; t += tickStepFrames) ticks.push(t);

  // Mouse → frame helpers
  const mouseXToFrame = (mouseX: number, rect: DOMRect): number => {
    // mouseX is relative to the pane (includes gutter offset)
    return pixelToPlayheadFrame(mouseX, pxPerSec, seq.fps, 0);
  };

  // Wheel zoom: keep mouse position stable
  const onWheel = (e: React.WheelEvent) => {
    if (!e.ctrlKey && Math.abs(e.deltaY) < Math.abs(e.deltaX)) return;
    const pane = paneRef.current;
    if (!pane) return;
    e.preventDefault();
    const rect = pane.getBoundingClientRect();
    const mouseXInContent = e.clientX - rect.left + pane.scrollLeft;
    const anchorFrame = mouseXToFrame(mouseXInContent, rect);
    const factor = e.deltaY < 0 ? 1.25 : 0.8;
    const next = Math.min(60, Math.max(4, pxPerSec * factor));
    onZoomPx(next);
    requestAnimationFrame(() => {
      const newPxPerF = pxPerFrame(next, seq.fps);
      pane.scrollLeft = anchorFrame * newPxPerF - (e.clientX - rect.left);
    });
  };

  // Ruler drag = time-range select; click = seek
  const dragStartFrame = useRef<number | null>(null);
  const onRulerDown = (e: React.PointerEvent) => {
    const rect = (e.currentTarget as HTMLElement).getBoundingClientRect();
    // The ruler is offset by paddingLeft = LABEL_GUTTER_PX in CSS, so
    // the ruler's local x is e.clientX - rect.left - LABEL_GUTTER_PX.
    const localX = e.clientX - rect.left - LABEL_GUTTER_PX;
    dragStartFrame.current = pixelToPlayheadFrame(LABEL_GUTTER_PX + localX, pxPerSec, seq.fps);
    const move = (ev: PointerEvent) => {
      if (dragStartFrame.current === null) return;
      const lx = ev.clientX - rect.left - LABEL_GUTTER_PX;
      const t = pixelToPlayheadFrame(LABEL_GUTTER_PX + lx, pxPerSec, seq.fps);
      // Threshold: 4 px in the timeline. Convert to frame threshold.
      const thresholdFrames = Math.max(1, Math.round(4 / pxPerF));
      if (Math.abs(t - dragStartFrame.current) > thresholdFrames) {
        // Range in seconds for legacy selRange API.
        const a = framesToTimecode(dragStartFrame.current, seq.fps, seq.dropFrame);
        const b = framesToTimecode(t, seq.fps, seq.dropFrame);
        // For the legacy seconds API, we just store the start/end
        // as the timecode strings' second values. (This is a
        // simplification: selRange is being phased out.)
        const fps = seq.fps.num / seq.fps.den;
        onRangeSelect([
          Math.min(dragStartFrame.current, t) / fps,
          Math.max(dragStartFrame.current, t) / fps,
        ]);
        // Suppress unused-var warning
        void a; void b;
      }
    };
    const up = (ev: PointerEvent) => {
      if (dragStartFrame.current !== null) {
        const lx = ev.clientX - rect.left - LABEL_GUTTER_PX;
        const t = pixelToPlayheadFrame(LABEL_GUTTER_PX + lx, pxPerSec, seq.fps);
        const thresholdFrames = Math.max(1, Math.round(4 / pxPerF));
        if (Math.abs(t - dragStartFrame.current) <= thresholdFrames) {
          onSeek(t);
          onRangeSelect(null);
        }
      }
      dragStartFrame.current = null;
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
  };

  // Playhead at frame 0 sits at LABEL_GUTTER_PX, not at 0 — prevents
  // collision with the track-name column.
  const playheadX = playheadFrameToPixel(playheadFrame, pxPerSec, seq.fps);

  return (
    <div className="timeline-pane" ref={paneRef} onWheel={onWheel} onScroll={syncViewport}
      style={{ height, flexShrink: 0 }}>
      {/* Minimap: click/drag to jump */}
      <div
        className="minimap"
        onPointerDown={(e) => {
          const pane = paneRef.current;
          const rect = (e.currentTarget as HTMLElement).getBoundingClientRect();
          const jump = (clientX: number) => {
            const ratio = Math.min(1, Math.max(0, (clientX - rect.left) / rect.width));
            // ratio → frame → seek
            const targetFrame = Math.round(ratio * durationFrames);
            onSeek(targetFrame);
            if (pane) {
              const newPxPerF = pxPerFrame(pxPerSec, seq.fps);
              pane.scrollLeft = targetFrame * newPxPerF - pane.clientWidth / 2;
            }
          };
          jump(e.clientX);
          const move = (ev: PointerEvent) => jump(ev.clientX);
          const up = () => {
            window.removeEventListener("pointermove", move);
            window.removeEventListener("pointerup", up);
          };
          window.addEventListener("pointermove", move);
          window.addEventListener("pointerup", up);
        }}
      >
        {project.timeline.tracks.flatMap((track) =>
          track.clip_ids.map((cid) => {
            const c = project.clips[cid];
            if (!c) return null;
            const cStartF = Math.round(c.timeline_range.start * seq.fps.num / seq.fps.den);
            const cEndF = Math.round(c.timeline_range.end * seq.fps.num / seq.fps.den);
            const w = Math.max(0, cEndF - cStartF);
            return (
              <div
                key={cid}
                className={`minimap-clip ${track.kind}`}
                style={{
                  left: `${(cStartF / durationFrames) * 100}%`,
                  width: `${(w / durationFrames) * 100}%`,
                }}
              />
            );
          })
        )}
        <div
          className="minimap-viewport"
          style={{ left: `${viewport.left * 100}%`, width: `${viewport.width * 100}%` }}
        />
        <div className="minimap-playheadFrame" style={{ left: `${(playheadFrame / durationFrames) * 100}%` }} />
      </div>
      <div className="timeline-body">
        {/* Playhead spans ruler + all tracks (剪映/Premiere style).
            playheadX is the frame-anchored x; LABEL_GUTTER_PX keeps
            frame 0 off the leftmost edge. */}
        <div className="playheadFrame-full" style={{ left: playheadX }} />
        <div className="ruler" style={{ width, paddingLeft: LABEL_GUTTER_PX }} onPointerDown={onRulerDown}>
          {ticks.map((t) => {
            const x = LABEL_GUTTER_PX + Math.round(t * pxPerF);
            const label = framesToTimecode(t, seq.fps, seq.dropFrame);
            return (
              <div key={t} className="tick" style={{ left: x }}>
                {label}
              </div>
            );
          })}
          {selRange && (() => {
            // selRange is in seconds (legacy). Convert to frame-space
            // pixel positions for display.
            const startF = selRange[0] * seq.fps.num / seq.fps.den;
            const endF = selRange[1] * seq.fps.num / seq.fps.den;
            const startX = LABEL_GUTTER_PX + Math.round(startF * pxPerF);
            const w = Math.max(0, Math.round((endF - startF) * pxPerF));
            return (
              <div className="range-sel" style={{ left: startX, width: w }} />
            );
          })()}
          {inPoint != null && (() => {
            const f = inPoint * seq.fps.num / seq.fps.den;
            return (
              <div className="io-marker" style={{ left: LABEL_GUTTER_PX + Math.round(f * pxPerF) }}>I</div>
            );
          })()}
          {outPoint != null && (() => {
            const f = outPoint * seq.fps.num / seq.fps.den;
            return (
              <div className="io-marker out" style={{ left: LABEL_GUTTER_PX + Math.round(f * pxPerF) }}>O</div>
            );
          })()}
        </div>
        <div className="tracks">
        {[...project.timeline.tracks].reverse().map((track) => (
          <div
            key={track.track_id}
            className={`track-row ${track.hidden ? "track-hidden" : ""}`}
            style={{ width, display: track.hidden ? "none" : "flex" }}
            data-track-id={track.track_id}
          >
            <div className="track-label-gutter"
                 style={{ width: LABEL_GUTTER_PX, minWidth: LABEL_GUTTER_PX, maxWidth: LABEL_GUTTER_PX }}
                 onDragOver={(e) => { e.preventDefault(); e.dataTransfer.dropEffect = "none"; }}>
              <span className="track-label-title">{TRACK_NAME[track.kind] || track.kind} · {track.track_id}</span>
              <div className="track-label-buttons">
              {track.kind !== "text" && (
                <button
                  className={track.muted ? "muted" : ""}
                  title={track.muted ? "取消轨道静音" : "轨道静音"}
                  onClick={(e) => {
                    e.stopPropagation();
                    onTrackMute?.(track.track_id, !track.muted);
                  }}
                >
                  {track.muted ? "取消静音" : "静音"}
                </button>
              )}
              <button
                className={track.locked ? "locked" : ""}
                title={track.locked ? "解锁轨道" : "锁定轨道（禁拖动）"}
                onClick={(e) => {
                  e.stopPropagation();
                  onTrackLock?.(track.track_id, !track.locked);
                }}
              >
                {track.locked ? "解锁" : "锁定"}
              </button>
              <button
                className={track.hidden ? "hidden-active" : ""}
                title={track.hidden ? "显示轨道（点击恢复）" : "隐藏轨道（仅 GUI 不显示，渲染仍参与）"}
                onClick={(e) => {
                  e.stopPropagation();
                  onTrackHide?.(track.track_id, !track.hidden);
                }}
              >
                {track.hidden ? "显示" : "隐藏"}
              </button>
              </div>
            </div>
            <div
              className="track-content"
              onDragOver={(e) => {
                if (e.dataTransfer.types.includes("text/yroll-asset")) {
                  e.preventDefault();
                  e.dataTransfer.dropEffect = "copy";
                }
              }}
              onDrop={(e) => {
                const assetId = e.dataTransfer.getData("text/yroll-asset");
                if (!assetId) return;
                e.preventDefault();
                const rect = (e.currentTarget as HTMLElement).getBoundingClientRect();
                const frame = Math.max(0, pixelToPlayheadFrame(
                  e.clientX - rect.left, pxPerSec, seq.fps));
                onAssetDrop?.(assetId, track.track_id, frame);
              }}
              data-track-content={track.track_id}
            >
            {track.clip_ids.map((cid) => {
              const clip = project.clips[cid];
              if (!clip) return null;
              const siblings = track.clip_ids
                .filter((sid) => sid !== cid)
                .map((sid) => {
                  const s = project.clips[sid];
                  if (!s) return null;
                  const sStart = s.timeline_range.start * seq.fps.num / seq.fps.den;
                  const sEnd = s.timeline_range.end * seq.fps.num / seq.fps.den;
                  return { id: sid, start: sStart, end: sEnd };
                })
                .filter(Boolean) as Array<{ id: string; start: number; end: number }>;
              return (
                <ClipBlock
                  key={cid}
                  clip={clip}
                  locked={track.locked}
                  selected={selectedIds.has(cid)}
                  pxPerFrame={pxPerF}
                  seqFps={seq.fps}
                  // GUI-02.3: ClipBlock degrades gracefully when the
                  // asset's source FPS is unknown. Per the closure
                  // invariant, we never ASSUME source_fps == sequence_fps
                  // for TimeMap business math — but display labels
                  // (timecode, waveform slicing) need SOME fps and
                  // falling back to seq fps with a "// display fallback"
                  // marker is acceptable here.
                  // TODO(02-7): hook up ProjectSequence.assetSourceFps
                  // populated from /project/validate_media_conformance.
                  sourceFps={undefined}
                  snapMode={snapMode}
                  highlightRel={highlightRel}
                  isRelated={highlightRel && selectedIds.size > 0 && Array.from(selectedIds).some((selId) => {
                    const sel = project.clips[selId];
                    if (!sel || sel.track_id === clip.track_id) return false;
                    return clip.timeline_range.start < sel.timeline_range.end &&
                           sel.timeline_range.start < clip.timeline_range.end;
                  })}
                  siblings={siblings}
                  onSelect={onSelect}
                  onDragMove={onDragMove}
                  onMoveCommit={onMoveCommit}
                  onTrimCommit={onTrimCommit}
                  onDropOnTrack={onDropOnTrack}
                />
              );
            })}
            </div>
          </div>
        ))}
        </div>
      </div>
    </div>
  );
}
