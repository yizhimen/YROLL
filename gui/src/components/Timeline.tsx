// GUI-02 + GUI-03R2: Timeline — frame-px layout with UNIFIED ContentViewport origin.
//
// GUI-03R2 P0-A: the timeline pane is split into TWO columns:
//   - .timeline-headers (sticky left, OUTSIDE coord space) → track-name labels
//   - .timeline-content (scrollable right, INSIDE coord space) → ruler + tracks + ONE PlayheadOverlay
// Inside .timeline-content, frame 0 is EXACTLY x=0. No arbitrary +/- gutter
// offsets are applied to ruler / playhead / clip / drop coords. The
// LABEL_GUTTER_PX constant is now ONLY used to size the sticky header column
// (it's still the physical track-name column width, but it lives OUTSIDE the
// coordinate space).
//
// Seconds exist only in the server's `clip.timeline_range`. Layout converts
// seconds → frames → pixels via frames.ts and the project's sequence fps.

import { useMemo, useRef, useState } from "react";
import { Project } from "../api";
import { useProjectSequence } from "../sequence";
import {
  chooseTickStep,
  chooseZoomProfile,
  frameToRulerSeconds,
  frameRulerLabel,
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
  onDragMove: (clipId: string, newStartFrame: number, ghostSnapFrame?: number | null) => void;
  /** GUI-03R3-1E: ghost-snap frame per active drag, keyed by clipId.
   *  Rendered as a thin vertical line inside the clip's track-content
   *  row at `ghostFrame * pxPerFrame`. Visual only — never modifies
   *  the dragged clip's preview position. */
  dragGhost?: Record<string, number | null>;
  /** Drag-end move commit. Final integer TimelineFrame (post-snap +
   *  post-clamp). If the drag also resolved a vertical-track-drop
   *  target (the pointer ended over a different track-content row),
   *  the new track id is passed too — the parent performs ONE
   *  transactional move (frame + track). */
  onMoveCommit: (
    clipId: string,
    newStartFrame: number,
    targetTrackId?: string,
  ) => void;
  onZoomPx: (px: number) => void;
  onRangeSelect: (r: [number, number] | null) => void;
  /** Trim commit. `newStart` / `newEnd` are integer SOURCE frames. */
  onTrimCommit: (clipId: string, newStart: number | null, newEnd: number | null) => void;
  onDropOnTrack?: (clipId: string, trackId: string) => void;
  onTrackMute?: (trackId: string, muted: boolean) => void;
  onTrackLock?: (trackId: string, locked: boolean) => void;
  onTrackHide?: (trackId: string, hidden: boolean) => void;
  onAssetDrop?: (assetId: string, trackId: string, timelineStartFrame: number) => void;
  /** GUI-03C: when true, the Timeline renders tracks with no clips
   *  (default false — empty tracks are hidden). */
  showEmptyTracks?: boolean;
}

const TRACK_NAME: Record<string, string> = {
  video: "视频", audio: "音频", text: "字幕", subtitle: "字幕",
};

export default function Timeline({
  project, selectedIds, playheadFrame, pxPerSec, selRange, inPoint, outPoint,
  height = 240,
  snapMode = "always",
  highlightRel = false,
  onSeek, onSelect, onDragMove, onMoveCommit, onZoomPx, onRangeSelect, onTrimCommit, onTrackMute, onTrackLock, onTrackHide, onAssetDrop,
  dragGhost,
  showEmptyTracks = false,
}: Props) {
  // GUI-03R: resolve the active Timeline once. All render-time track
  // reads go through this — never `project.timeline` (singular, the
  // deprecated legacy alias).
  const activeTimelineTracks = (project.timelines?.find(
    (tl) => tl.timeline_id === project.active_timeline_id,
  ) ?? project.timelines?.[0])?.tracks ?? [];
  const visibleTracks = useMemo(
    // GUI-03C: hide empty tracks by default. The Core still
    // owns them; the GUI just chooses not to render them.
    // Toggle via the showEmptyTracks prop (default false).
    () => [...activeTimelineTracks].reverse().filter(
      (track) => showEmptyTracks || track.clip_ids.length > 0 || track.hidden,
    ),
    [activeTimelineTracks, showEmptyTracks],
  );
  const paneRef = useRef<HTMLDivElement | null>(null);   // .timeline-pane (outer flex container)
  const contentRef = useRef<HTMLDivElement | null>(null); // .timeline-content (SCROLLABLE; the coord space)
  const [viewport, setViewport] = useState({ left: 0, width: 1 });
  // Sequence (canonical timebase) — provides fps for frame↔px math
  const seq = useProjectSequence();
  // pxPerFrame derived from perceived pxPerSec and the project's fps.
  const pxPerF = useMemo(
    () => pxPerFrame(pxPerSec, seq.fps),
    [pxPerSec, seq.fps],
  );
  // Total content width in pixels: frame pixels + small tail.
  // Inside .timeline-content the coord space starts at x=0 for frame 0,
  // so we DO NOT add any gutter offset here.
  const contentWidth = pxPerF * 30 * 60 + 40;  // assume >=30 min
  const syncViewport = () => {
    const c = contentRef.current;
    if (!c) return;
    setViewport({
      left: c.scrollLeft / Math.max(1, contentWidth),
      width: Math.min(1, c.clientWidth / Math.max(1, contentWidth)),
    });
  };

  // The timeline width is derived from the latest clip end (in frames).
  const durationFrames = Math.max(
    300,  // 10s @ 30fps; ensures ruler isn't squished when empty
    ...Object.values(project.clips).map((c) => Math.round(c.timeline_range.end * seq.fps.num / seq.fps.den)),
  );
  // Width in pixels inside ContentViewport: durationFrames * pxPerF + 40
  // (NO gutter offset — frame 0 is at x=0 inside ContentViewport).
  const width = durationFrames * pxPerF + 40;

  // Ruler ticks. Use chooseTickStep + chooseZoomProfile to pick a
  // step that lands ticks 60-120 px apart. Labels are timecode strings.
  const profile = chooseZoomProfile(pxPerSec);
  const tickStepFrames = chooseTickStep(profile, seq.fps, pxPerSec);
  const ticks: number[] = [];
  for (let t = 0; t <= durationFrames; t += tickStepFrames) ticks.push(t);

  // Mouse → frame helper. mouseX is in ContentViewport coords (x=0 at frame 0).
  // No gutter offset — the headers column lives OUTSIDE this coord space.
  const mouseXToFrame = (mouseXInContent: number): number => {
    return pixelToPlayheadFrame(mouseXInContent, pxPerSec, seq.fps, 0);
  };

  // Wheel zoom: keep mouse position stable.
  // GUI-03R2 P1-G: step reduced from 1.25/0.8 → 1.08/1/1.08
  // (≈8% per notch, much less aggressive). Anchor frame is preserved
  // by adjusting .timeline-content scrollLeft after the zoom applies.
  const onWheel = (e: React.WheelEvent) => {
    if (!e.ctrlKey && Math.abs(e.deltaY) < Math.abs(e.deltaX)) return;
    const content = contentRef.current;
    if (!content) return;
    e.preventDefault();
    const rect = content.getBoundingClientRect();
    const mouseXInContent = e.clientX - rect.left + content.scrollLeft;
    const anchorFrame = mouseXToFrame(mouseXInContent);
    const factor = e.deltaY < 0 ? 1.08 : 1 / 1.08;
    const next = Math.min(120, Math.max(4, pxPerSec * factor));
    onZoomPx(next);
    requestAnimationFrame(() => {
      const newPxPerF = pxPerFrame(next, seq.fps);
      content.scrollLeft = anchorFrame * newPxPerF - (e.clientX - rect.left);
    });
  };

  // Ruler drag = time-range select; click = seek.
  // GUI-03R2 P0-A: ruler lives INSIDE ContentViewport. ruler rect.left
  // is the ContentViewport's left edge (where frame 0 sits), so
  // e.clientX - rect.left is already the ContentViewport x — NO
  // gutter offset needed.
  const dragStartFrame = useRef<number | null>(null);
  const onRulerDown = (e: React.PointerEvent) => {
    const rect = (e.currentTarget as HTMLElement).getBoundingClientRect();
    const localX = e.clientX - rect.left;
    dragStartFrame.current = mouseXToFrame(localX);
    const move = (ev: PointerEvent) => {
      if (dragStartFrame.current === null) return;
      const lx = ev.clientX - rect.left;
      const t = mouseXToFrame(lx);
      const thresholdFrames = Math.max(1, Math.round(4 / Math.max(0.001, pxPerF)));
      if (Math.abs(t - dragStartFrame.current) > thresholdFrames) {
        const fps = seq.fps.num / seq.fps.den;
        onRangeSelect([
          Math.min(dragStartFrame.current, t) / fps,
          Math.max(dragStartFrame.current, t) / fps,
        ]);
      }
    };
    const up = (ev: PointerEvent) => {
      if (dragStartFrame.current !== null) {
        const lx = ev.clientX - rect.left;
        const t = mouseXToFrame(lx);
        const thresholdFrames = Math.max(1, Math.round(4 / Math.max(0.001, pxPerF)));
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

  // Playhead at frame 0 sits at ContentViewport x=0 (NO gutter offset).
  const playheadX = playheadFrameToPixel(playheadFrame, pxPerSec, seq.fps, 0);

  return (
    <div className="timeline-pane" ref={paneRef} onWheel={onWheel}
      style={{ height, flexShrink: 0 }}>
      {/* ── LEFT STICKY: track-name headers (OUTSIDE coord space) ─────────── */}
      <div className="timeline-headers">
        {/* Spacer above the tracks, matching the minimap height */}
        <div className="timeline-headers-spacer" />
        {visibleTracks.map((track) => (
          <div
            key={track.track_id}
            className={`track-label-row ${track.hidden ? "track-hidden" : ""}`}
            data-track-id={track.track_id}
            style={{ display: track.hidden ? "none" : "flex" }}
          >
            <div className="track-label-title">{TRACK_NAME[track.kind] || track.kind} · {track.track_id}</div>
            <div className="track-label-buttons">
              {track.kind !== "text" && (
                <button
                  className={track.muted ? "muted" : ""}
                  title={track.muted ? "取消轨道静音" : "轨道静音"}
                  onClick={() => onTrackMute?.(track.track_id, !track.muted)}
                >
                  {track.muted ? "取消静音" : "静音"}
                </button>
              )}
              <button
                className={track.locked ? "locked" : ""}
                title={track.locked ? "解锁轨道" : "锁定轨道（禁拖动）"}
                onClick={() => onTrackLock?.(track.track_id, !track.locked)}
              >
                {track.locked ? "解锁" : "锁定"}
              </button>
              <button
                className={track.hidden ? "hidden-active" : ""}
                title={track.hidden ? "显示轨道（点击恢复）" : "隐藏轨道（仅 GUI 不显示，渲染仍参与）"}
                onClick={() => onTrackHide?.(track.track_id, !track.hidden)}
              >
                {track.hidden ? "显示" : "隐藏"}
              </button>
            </div>
          </div>
        ))}
      </div>

      {/* ── RIGHT: ContentViewport (scrollable; frame 0 = x=0) ─────────────── */}
      <div className="timeline-content" ref={contentRef} onScroll={syncViewport}>
        {/* Minimap: click/drag to jump. Top of ContentViewport. */}
        <div
          className="minimap"
          onPointerDown={(e) => {
            const content = contentRef.current;
            const rect = (e.currentTarget as HTMLElement).getBoundingClientRect();
            const jump = (clientX: number) => {
              const ratio = Math.min(1, Math.max(0, (clientX - rect.left) / rect.width));
              const targetFrame = Math.round(ratio * durationFrames);
              onSeek(targetFrame);
              if (content) {
                const newPxPerF = pxPerFrame(pxPerSec, seq.fps);
                content.scrollLeft = targetFrame * newPxPerF - content.clientWidth / 2;
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
          {activeTimelineTracks.flatMap((track) =>
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
          <div className="minimap-playhead" style={{ left: `${(playheadFrame / durationFrames) * 100}%` }} />
        </div>

        {/* Ruler (frame 0 = x=0, NO gutter offset) */}
        <div className="ruler" style={{ width }} onPointerDown={onRulerDown}>
          {ticks.map((t) => {
            const x = Math.round(t * pxPerF);
            const seconds = frameToRulerSeconds(t, seq.fps);
            const precise = pxPerSec >= 24;
            const label = precise
              ? `${seconds} · ${frameRulerLabel(t)}`
              : seconds;
            return (
              <div key={t} className="tick" style={{ left: x }}>
                {label}
              </div>
            );
          })}
          {selRange && (() => {
            const startF = selRange[0] * seq.fps.num / seq.fps.den;
            const endF = selRange[1] * seq.fps.num / seq.fps.den;
            const startX = Math.round(startF * pxPerF);
            const w = Math.max(0, Math.round((endF - startF) * pxPerF));
            return (
              <div className="range-sel" style={{ left: startX, width: w }} />
            );
          })()}
          {inPoint != null && (() => {
            const f = inPoint * seq.fps.num / seq.fps.den;
            return (
              <div className="io-marker" style={{ left: Math.round(f * pxPerF) }}>I</div>
            );
          })()}
          {outPoint != null && (() => {
            const f = outPoint * seq.fps.num / seq.fps.den;
            return (
              <div className="io-marker out" style={{ left: Math.round(f * pxPerF) }}>O</div>
            );
          })()}
        </div>

        {/* Tracks (frame 0 = x=0) */}
        <div className="tracks">
          {visibleTracks.map((track) => (
            <div
              key={track.track_id}
              className={`track-row ${track.hidden ? "track-hidden" : ""}`}
              style={{ width, display: track.hidden ? "none" : "flex" }}
              data-track-id={track.track_id}
            >
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
                  // track-content rect.left is the ContentViewport's x=0 edge.
                  const frame = Math.max(0, pixelToPlayheadFrame(
                    e.clientX - rect.left, pxPerSec, seq.fps, 0));
                  onAssetDrop?.(assetId, track.track_id, frame);
                }}
                data-track-content={track.track_id}
              >
                {/* GUI-03R3-1E: visual snap-target ghost line.
                    Rendered inside the source track's track-content
                    row at `ghostFrame * pxPerFrame`. Visual only —
                    never modifies the dragged clip's preview. */}
                {dragGhost && Object.entries(dragGhost).map(([cid, ghostFrame]) => {
                  if (ghostFrame == null) return null;
                  // Only render in the source track's row (where the
                  // dragged clip lives).
                  if (project.clips[cid]?.track_id !== track.track_id) return null;
                  return (
                    <div
                      key={`__ghost_${cid}`}
                      className="clip-ghost"
                      style={{ left: ghostFrame * pxPerF }}
                      data-ghost-for={cid}
                      title={`Snap target · frame ${ghostFrame}`}
                    />
                  );
                })}
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
                    />
                  );
                })}
              </div>
            </div>
          ))}
        </div>

        {/* ONE absolute PlayheadOverlay — spans ruler + all tracks.
            pointer-events: none. position = canonical frameToPixel. */}
        <div className="playhead-overlay" style={{ left: playheadX }} />
      </div>
    </div>
  );
}
