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
  /** GUI-03R3-W-D: pixel width of the LEFT track-header column.
   *  Persisted in localStorage by App.tsx. Range 80–300, default 160.
   *  Resizing this column does NOT alter the Timeline Content Origin
   *  (frame 0 stays at x=0 inside .timeline-content); it only changes
   *  the physical width of the OUTSIDE-coord-space label column. */
  headerWidth?: number;
  snapMode?: "always" | "alt" | "off";
  highlightRel?: boolean;
  /** GUI-03R3-W-D: callback that exposes the .timeline-content
   *  element to App.tsx so the keyboard dispatcher can scroll the
   *  ContentViewport (Home = center playhead). The Content Origin
   *  (frame 0 = x=0) is preserved — this only adjusts scrollLeft. */
  onContentRef?: (el: HTMLDivElement | null) => void;
  /** GUI-03R3-W-D: resize-handle drag delta. App owns the width
   *  (clamp + persist in localStorage). Range 80–300px. */
  onHeaderWidthDelta?: (deltaPx: number) => void;
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
  /** GUI-03R3-W-C: drop onto the "新建轨道" zone below all visible
   *  tracks. The GUI resolves pointer geometry to a structural
   *  intent: `insertAfterTrackId` is the last visible track (Core
   *  decides the new track's id; existing tracks never rename).
   *  `kindHint` is the visual track kind to show in the drop zone
   *  label (V/A/T). */
  onAssetDropNewTrack?: (
    assetId: string,
    insertAfterTrackId: string,
    timelineStartFrame: number,
  ) => void;
  /** GUI-03R3-W-C: the kind of asset currently being dragged (or
   *  null when no drag is in flight). Drives the drop zone label
   *  ("新建视频轨" / "新建音频轨" / "新建字幕轨"). The Timeline
   *  never reads from a global drag state — App.tsx sets this
   *  prop explicitly on dragstart/dragend. */
  draggingAssetKind?: "video" | "image" | "audio" | "subtitle" | "text" | null;
  /** GUI-03C: when true, the Timeline renders tracks with no clips
   *  (default false — empty tracks are hidden). */
  showEmptyTracks?: boolean;
}

// GUI-03R3-2 P1-3: Default labels for common track kinds, matching
// the spec's "V1 主画面 / V2 B-roll / A1 旁白 / T1 字幕" pattern.
// We override per-id: V1 = 主画面, V2 = B-roll, A1 = 旁白, T1 = 字幕.
// All other ids fall back to a kind-based default.
const TRACK_ROLE: Record<string, string> = {
  V1: "主画面", V2: "B-roll", V3: "B-roll", V4: "B-roll",
  A1: "旁白", A2: "音效", A3: "环境音",
  T1: "字幕", T2: "字幕",
};
const trackRoleLabel = (track: { track_id: string; kind: string }): string =>
  TRACK_ROLE[track.track_id] || ({ video: "视频", image: "图像",
    audio: "音频", text: "字幕", subtitle: "字幕" }[track.kind] || track.kind);

// GUI-03R3-W-D: semantic track-kind icons. Inline SVG so they
// render identically across systems (emoji can vary). Three
// semantic shapes:
//   text / subtitle → "T" inside a rounded square (the standard
//     "text track" glyph in NLEs).
//   video / image → triangle "play" (visual track, whether the
//     underlying asset is video or image).
//   audio → music note (audio track).
const TrackKindIcon = ({ kind }: { kind: string }) => {
  const k = kind;
  if (k === "text" || k === "subtitle") {
    return (
      <svg viewBox="0 0 16 16" width="14" height="14"
        aria-label="字幕轨" role="img"
        data-track-kind-icon="text">
        <rect x="1" y="1" width="14" height="14" rx="2" ry="2"
          fill="none" stroke="currentColor" strokeWidth="1.2" />
        <path d="M5 4.5h6 M8 4.5v8 M5.5 11.5l2.5 -2 2.5 2"
          fill="none" stroke="currentColor" strokeWidth="1.4"
          strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    );
  }
  if (k === "video" || k === "image") {
    return (
      <svg viewBox="0 0 16 16" width="14" height="14"
        aria-label="视频轨" role="img"
        data-track-kind-icon="video">
        <rect x="1.5" y="2.5" width="13" height="11" rx="1.5" ry="1.5"
          fill="none" stroke="currentColor" strokeWidth="1.2" />
        <path d="M6.5 5.5 L11 8 L6.5 10.5 Z"
          fill="currentColor" />
      </svg>
    );
  }
  if (k === "audio") {
    return (
      <svg viewBox="0 0 16 16" width="14" height="14"
        aria-label="音频轨" role="img"
        data-track-kind-icon="audio">
        <path d="M6 12V4l6-1v8"
          fill="none" stroke="currentColor" strokeWidth="1.4"
          strokeLinejoin="round" strokeLinecap="round" />
        <circle cx="4.5" cy="12" r="1.8"
          fill="none" stroke="currentColor" strokeWidth="1.4" />
        <circle cx="10.5" cy="11" r="1.8"
          fill="none" stroke="currentColor" strokeWidth="1.4" />
      </svg>
    );
  }
  // Unknown kind: render a generic dot so the row never collapses.
  return (
    <svg viewBox="0 0 16 16" width="14" height="14"
      aria-label={kind} role="img"
      data-track-kind-icon="unknown">
      <circle cx="8" cy="8" r="3" fill="currentColor" />
    </svg>
  );
};

export default function Timeline({
  project, selectedIds, playheadFrame, pxPerSec, selRange, inPoint, outPoint,
  height = 240,
  headerWidth = 160,
  snapMode = "always",
  highlightRel = false,
  onContentRef,
  onHeaderWidthDelta,
  onSeek, onSelect, onDragMove, onMoveCommit, onZoomPx, onRangeSelect, onTrimCommit, onTrackMute, onTrackLock, onTrackHide, onAssetDrop, onAssetDropNewTrack,
  dragGhost,
  draggingAssetKind = null,
  showEmptyTracks = false,
}: Props) {
  // GUI-03R: resolve the active Timeline once. All render-time track
  // reads go through this — never `project.timeline` (singular, the
  // deprecated legacy alias).
  const activeTimelineTracks = (project.timelines?.find(
    (tl) => tl.timeline_id === project.active_timeline_id,
  ) ?? project.timelines?.[0])?.tracks ?? [];
  // GUI-03R3-2 P1-2: semantic track order. Sort by class then by
  // natural numeric suffix of track_id (v1, v2, v10 — NOT
  // lexical v1, v10, v11, v2). Class order is:
  //   text/subtitle  →  video/visual  →  audio
  // The result array is rendered top-to-bottom in the DOM. With
  // the ascending KIND_RANK below, the first track in the array
  // renders at the TOP of the timeline (text on top, audio at
  // bottom) — the standard video-editor convention.
  const KIND_RANK: Record<string, number> = { text: 0, video: 1, image: 1, audio: 2 };
  const trackKey = (tid: string) => {
    const m = tid.match(/(\d+)\s*$/);
    return m ? parseInt(m[1], 10) : 9999;
  };
  const visibleTracks = useMemo(
    // GUI-03C: hide empty tracks by default. The Core still
    // owns them; the GUI just chooses not to render them.
    // Toggle via the showEmptyTracks prop (default false).
    () => [...activeTimelineTracks]
      .sort((a, b) => {
        const ra = KIND_RANK[a.kind] ?? 9;
        const rb = KIND_RANK[b.kind] ?? 9;
        if (ra !== rb) return ra - rb;
        return trackKey(a.track_id) - trackKey(b.track_id);
      })
      .filter(
        (track) => showEmptyTracks || track.clip_ids.length > 0 || track.hidden,
      ),
    [activeTimelineTracks, showEmptyTracks],
  );
  const paneRef = useRef<HTMLDivElement | null>(null);   // .timeline-pane (outer flex container)
  const contentRef = useRef<HTMLDivElement | null>(null); // .timeline-content (SCROLLABLE; the coord space)
  const headersRef = useRef<HTMLDivElement | null>(null); // .timeline-headers (vertical-scroll-synced)
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
    // GUI-03R3-2 P0-2/P0-3: sync the LEFT track-header column with
    // the content's vertical scroll. The header column lives
    // OUTSIDE .timeline-content (it's a sibling in .timeline-pane),
    // so it doesn't scroll with the content — we mirror scrollTop
    // explicitly. Direction is vertical only; horizontal scroll of
    // .timeline-content does NOT affect the headers.
    if (headersRef.current) {
      headersRef.current.scrollTop = c.scrollTop;
    }
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
      {/* GUI-03R3-W-D: width is now controlled by the `headerWidth`
          prop (App owns it + persists it in localStorage). The
          header column lives OUTSIDE the ContentViewport coord
          space — resizing it does not shift frame 0. */}
      <div
        className="timeline-headers"
        ref={headersRef}
        style={{ width: headerWidth }}
      >
        {/* Spacer above the tracks, matching the minimap height */}
        <div className="timeline-headers-spacer" />
        {visibleTracks.map((track) => (
          <div
            key={track.track_id}
            className={`track-label-row ${track.hidden ? "track-hidden" : ""}`}
            data-track-id={track.track_id}
            style={{ display: track.hidden ? "none" : "flex" }}
          >
            <div className="track-label-title">
              {/* GUI-03R3-W-D: semantic kind icon + track id +
                  role label. The icon is an inline SVG so it
                  renders identically across systems. Color is
                  driven by `kind` (text/subtitle → yellow,
                  video/image → blue, audio → green) so the user
                  can scan track kinds at a glance. */}
              <span className={`track-kind-icon kind-${track.kind}`}>
                <TrackKindIcon kind={track.kind} />
              </span>
              <span className="track-id">{track.track_id}</span>
              <span className="track-role-label">{trackRoleLabel(track)}</span>
            </div>
            {/* GUI-03R3-W-D: mute/lock/visibility are ALWAYS
                visible at reduced opacity so the user can see
                the current state without hovering. Hover/focus
                lifts the opacity to 1.0. Visibility uses an eye
                icon (not a prohibition sign) so "currently
                visible" reads as 👁 and "currently hidden" reads
                as 👁‍🗨 / "hide". */}
            <div className="track-label-buttons">
              {track.kind !== "text" && (
                <button
                  className={`track-icon-btn ${track.muted ? "active" : ""}`}
                  title={track.muted ? "取消轨道静音" : "轨道静音"}
                  onClick={() => onTrackMute?.(track.track_id, !track.muted)}
                  aria-label="mute"
                >
                  {track.muted ? "🔇" : "🔊"}
                </button>
              )}
              <button
                className={`track-icon-btn ${track.locked ? "active" : ""}`}
                title={track.locked ? "解锁轨道" : "锁定轨道（禁拖动）"}
                onClick={() => onTrackLock?.(track.track_id, !track.locked)}
                aria-label="lock"
              >
                {track.locked ? "🔒" : "🔓"}
              </button>
              <button
                className={`track-icon-btn ${track.hidden ? "active" : ""}`}
                title={track.hidden ? "显示轨道（点击恢复）" : "隐藏轨道（仅 GUI 不显示，渲染仍参与）"}
                onClick={() => onTrackHide?.(track.track_id, !track.hidden)}
                aria-label="hide"
              >
                {/* GUI-03R3-W-D: eye icon (open vs crossed-out),
                    never a prohibition sign. The open eye means
                    "currently visible — click to hide"; the
                    crossed-out eye means "currently hidden —
                    click to show". Inline SVG for cross-system
                    consistency. */}
                <svg viewBox="0 0 16 16" width="14" height="14"
                  aria-hidden="true" data-visibility={track.hidden ? "hidden" : "visible"}>
                  <path d="M1.5 8 C3.5 4.5 5.5 3 8 3 C10.5 3 12.5 4.5 14.5 8 C12.5 11.5 10.5 13 8 13 C5.5 13 3.5 11.5 1.5 8 Z"
                    fill="none" stroke="currentColor" strokeWidth="1.2"
                    strokeLinejoin="round" />
                  <circle cx="8" cy="8" r="2" fill="currentColor" />
                  {track.hidden && (
                    <path d="M2 2 L14 14"
                      stroke="currentColor" strokeWidth="1.4"
                      strokeLinecap="round" />
                  )}
                </svg>
              </button>
            </div>
          </div>
        ))}
      </div>

      {/* ── GUI-03R3-W-D: drag handle between header and content.
          Resizes the OUTSIDE-coord-space label column only. Frame 0
          stays at x=0 inside .timeline-content (Content Origin
          invariant preserved). Range 80–300px enforced by App. */}
      {onHeaderWidthDelta && (
        <div
          className="resize-handle vertical"
          onPointerDown={(e) => {
            // Capture the element up-front. The native pointerup
            // listener we register on `window` outlives any React
            // re-render of this element; `e.currentTarget` may
            // already be null by the time it fires.
            const el = e.currentTarget as HTMLElement;
            let lastX = e.clientX;
            el.classList.add("hover");
            document.body.style.cursor = "col-resize";
            document.body.style.userSelect = "none";
            const onMove = (ev: PointerEvent) => {
              const delta = ev.clientX - lastX;
              lastX = ev.clientX;
              onHeaderWidthDelta(delta);
              ev.preventDefault();
            };
            const onUp = () => {
              el.classList.remove("hover");
              document.body.style.cursor = "";
              document.body.style.userSelect = "";
              window.removeEventListener("pointermove", onMove);
              window.removeEventListener("pointerup", onUp);
            };
            window.addEventListener("pointermove", onMove);
            window.addEventListener("pointerup", onUp);
          }}
          title="拖动调整轨道标题列宽度（80–300px）"
        />
      )}

      {/* ── RIGHT: ContentViewport (scrollable; frame 0 = x=0) ─────────────── */}
      <div className="timeline-content" ref={(el) => {
        // GUI-03R3-W-D: expose the .timeline-content element to App
        // so the keyboard dispatcher (Home = _center_playhead) can
        // scroll the ContentViewport. The element's geometry is
        // identical to before — frame 0 stays at x=0; we only
        // hand the element out, not transform it.
        contentRef.current = el;
        onContentRef?.(el);
      }} onScroll={syncViewport}>
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
                // GUI-03R3-W-C: drag-over highlight. The user sees
                // WHERE the clip will land before they release.
                // On drop, the GUI emits explicit "use existing
                // track" intent to App.tsx (which calls add_clip
                // with track_id = this row's id). Core preserves
                // the track id and rejects overlap.
                onDragOver={(e) => {
                  if (e.dataTransfer.types.includes("text/yroll-asset")) {
                    e.preventDefault();
                    e.dataTransfer.dropEffect = "copy";
                    (e.currentTarget as HTMLElement).classList.add("drag-over");
                  }
                }}
                onDragLeave={(e) => {
                  (e.currentTarget as HTMLElement).classList.remove("drag-over");
                }}
                onDrop={(e) => {
                  const assetId = e.dataTransfer.getData("text/yroll-asset");
                  if (!assetId) return;
                  e.preventDefault();
                  (e.currentTarget as HTMLElement).classList.remove("drag-over");
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
          {/* GUI-03R3-W-C: drop zone BELOW all visible tracks.
              When the user drags an asset below the last track-row,
              the GUI emits "create new track" intent: it sends
              `insertAfterTrackId = lastVisibleTrackId` to App.tsx
              which calls `api.ensureTrackForDrop` and then places
              the clip on the new track. Core decides the new track's
              id; existing tracks never rename. */}
          {visibleTracks.length > 0 && onAssetDropNewTrack && (
            <div
              className="drop-zone-new-track"
              data-drop-zone="below-tracks"
              onDragOver={(e) => {
                if (e.dataTransfer.types.includes("text/yroll-asset")) {
                  e.preventDefault();
                  e.dataTransfer.dropEffect = "copy";
                  (e.currentTarget as HTMLElement).classList.add("drag-over");
                }
              }}
              onDragLeave={(e) => {
                (e.currentTarget as HTMLElement).classList.remove("drag-over");
              }}
              onDrop={(e) => {
                const assetId = e.dataTransfer.getData("text/yroll-asset");
                if (!assetId) return;
                e.preventDefault();
                (e.currentTarget as HTMLElement).classList.remove("drag-over");
                const rect = (e.currentTarget as HTMLElement).getBoundingClientRect();
                // Drop x in ContentViewport coords → frame.
                const frame = Math.max(0, pixelToPlayheadFrame(
                  e.clientX - rect.left, pxPerSec, seq.fps, 0));
                // Last visible track id becomes the `insert_after` anchor.
                const lastTrack = visibleTracks[visibleTracks.length - 1];
                if (lastTrack) {
                  onAssetDropNewTrack(assetId, lastTrack.track_id, frame);
                }
              }}
            >
              <span className="drop-zone-label">
                {draggingAssetKind === "audio"
                  ? "新建音频轨 ▾"
                  : draggingAssetKind === "subtitle" || draggingAssetKind === "text"
                    ? "新建字幕轨 ▾"
                    : "新建视频轨 ▾"}
              </span>
            </div>
          )}
        </div>

        {/* ONE absolute PlayheadOverlay — spans ruler + all tracks.
            pointer-events: none. position = canonical frameToPixel. */}
        <div className="playhead-overlay" style={{ left: playheadX }} />
      </div>
    </div>
  );
}
