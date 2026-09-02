// GUI-02.4: ClipBlock is FRAME-ONLY.
//
// All user edits are expressed as integer frame intent. No local
// source/timeline TimeMap business math. Three frame spaces, always
// explicit:
//
//   TimelineFrame — position in the project sequence timebase
//   ClipFrame     — position inside a clip's source range (asset's source FPS)
//   SourceFrame   — position in the source asset (asset's source FPS)
//
// The GUI never computes `* clip.speed` or / `* clip.speed` to convert
// between them. Core's TimeMap owns that conversion.
//
//   pixelDeltaToFrameDelta() and roundHalfAwayFromZero() are the only
//   coordinate-rounding primitives used here. Math.round() is forbidden
//   for edit coordinates.
//
// Edit geometry:
//   - Drag move: pointermove computes integer TimelineFrame candidate;
//     drag-end performs the authoritative /snap call and commits the
//     final frame mutation. No HTTP per pointermove.
//   - Trim:      pointermove computes integer source-frame deltas (no
//     `* clip.speed`); drag-end commits via the existing onTrimCommit
//     callback. The visual preview reflects the source-frame delta;
//     timeline geometry stays stable until Core commits.
//
// Sequence-fps parameter (seqFps) is used ONLY for display labels
// (framesToTimecode) and pxPerFrame derivation at the parent — never
// for source-frame math (asset.source_fps would be needed there).

import { useEffect, useRef, useState } from "react";
import { api, Clip } from "../api";
import {
  framesToTimecode,
  pixelDeltaToFrameDelta,
  roundHalfAwayFromZero,
} from "../frames";
import { DragAutoScroll } from "../drag-autoscroll";


/** Local helper: convert a pixel delta to a frame delta given the
 *  ALREADY-DERIVED pxPerFrame (frame-domain parameter naming). This
 *  avoids the legacy `pxPerSec` variable name leaking into the
 *  ClipBlock scope. The pxPerFrame is already in the destination
 *  timebase (e.g. timeline frames per pixel), so no FPS conversion
 *  is needed here. The caller is responsible for choosing which
 *  timebase's pxPerFrame to pass in (timeline or source). */
function pxPerFrameToFrameDelta(
  pixelDelta: number, pxPerFrame: number,
): number {
  return roundHalfAwayFromZero(pixelDelta / pxPerFrame);
}

// Waveform cache — same shape as before.
const waveCache = new Map<string, Promise<{ peaks: number[]; duration: number | null }>>();

function loadWave(assetId: string) {
  if (!waveCache.has(assetId)) {
    waveCache.set(
      assetId,
      fetch(`/assets/${assetId}/waveform?points=300`)
        .then((r) => (r.ok ? r.json() : { peaks: [], duration: null }))
        .catch(() => ({ peaks: [], duration: null }))
    );
  }
  return waveCache.get(assetId)!;
}

interface Props {
  clip: Clip;
  selected: boolean;
  locked?: boolean;
  /** Pixels per TIMELINE frame (sequence-fps based). Replaces the old
   *  pxPerSec prop — layout is in frame coordinates. Subpixel precision
   *  is permitted (per GUI-02.4 invariant). */
  pxPerFrame: number;
  /** Sequence FPS — used ONLY for display labels (framesToTimecode). */
  seqFps: { num: number; den: number };
  /** Asset's source FPS — used for waveform slicing math (the
   *  waveform index is a normalized source position) and for the
   *  thumbnail `t=` query. NEVER assumed equal to seqFps. */
  sourceFps?: { num: number; den: number };
  snapMode?: "always" | "alt" | "off";
  highlightRel?: boolean;
  siblings?: Array<{ id: string; start: number; end: number }>;
  isRelated?: boolean;
  onSelect: (clipId: string, viaAiZone: boolean, ctrl?: boolean) => void;
  /** R6-E: client-side UX gate. When false (CONNECTING / OBSERVE),
   *  pointerdown is a no-op. The server Mutation Gate remains
   *  authoritative; this prop is a hint that prevents the user from
   *  starting a drag gesture that would only be rejected at commit
   *  time. */
  canEdit?: boolean;
  /** Pointermove preview. `newTimelineStartFrame` is an INTEGER
   *  TimelineFrame. The parent uses this for visual feedback only;
   *  the authoritative commit happens via onMoveCommit. */
  onDragMove: (clipId: string, newTimelineStartFrame: number, ghostSnapFrame?: number | null) => void;
  /** R6.1-B: clamp-boundary flag. `true` when the last pointermove
   *  produced a clamped preview different from the pointer-raw
   *  candidate (the user's pointer is inside a sibling's range and
   *  the clamp teleported the preview to the boundary). The parent
   *  renders a dashed red outline + cursor:not-allowed to mark
   *  the visual distinction. The math is unchanged; this is a
   *  presentation-only signal. */
  onClampBoundary?: (clipId: string, onBoundary: boolean) => void;
  /** R6.1-B: parent's current view of whether THIS clip is on the
   *  clamp boundary. Used to apply the CSS class. Independent of
   *  the callback so the parent can drive the visual from
   *  external state (e.g. an external reset). */
  clampBoundary?: boolean;
  /** Drag-end move commit. The final TimelineFrame (post-snap +
   *  post-clamp) is passed; the parent forwards to `api.move`. If
   *  the drag also resolved a vertical-track-drop target (the
   *  pointer ended over a different track-content row), the new
   *  track id is passed too — the parent performs ONE transactional
   *  move (frame + track) instead of two. */
  onMoveCommit: (
    clipId: string,
    newTimelineStartFrame: number,
    targetTrackId?: string,
  ) => void;
  /** Trim commit. `srcStartFrame` / `srcEndFrame` are integer
   *  SourceFrame values (NOT seconds). Either may be null meaning
   *  "don't change this edge". */
  onTrimCommit: (
    clipId: string,
    srcStartFrame: number | null,
    srcEndFrame: number | null,
  ) => void;
  onDropOnTrack?: (clipId: string, trackId: string) => void;
}

/** GUI-02.4 invariant: the edit-coordinate snap radius is in FRAMES.
 *  Default 8 frames = ~0.27s at 30fps. Per the spec, snap thresholds
 *  must be expressed in the same coordinate space as the edit. */
const DEFAULT_SNAP_RADIUS_FRAMES = 8;

/** Minimum trim delta in source frames. Below this we ignore the
 *  drag (noise filter). 1 frame is the meaningful quantum. */
const MIN_TRIM_DELTA_FRAMES = 1;

export default function ClipBlock({
  clip, selected, locked, pxPerFrame, seqFps, sourceFps,
  snapMode = "always", highlightRel = false, isRelated = false,
  siblings = [],
  canEdit = true,
  onSelect, onDragMove, onMoveCommit, onTrimCommit, onDropOnTrack, onClampBoundary, clampBoundary = false,
}: Props) {
  // ---- Trim preview state -------------------------------------------------
  // Source-frame deltas (integer ClipFrame). The visual preview applies
  // these to the source range ONLY — timeline geometry does not update
  // during drag (Core TimeMap owns the source↔timeline mapping on
  // commit).
  const [trimDelta, setTrimDelta] = useState<{ dStart: number; dEnd: number } | null>(null);

  const dStart = trimDelta?.dStart ?? 0;
  const dEnd = trimDelta?.dEnd ?? 0;

  // ---- Layout (integer frames; subpixel allowed at the px layer) ---------
  // tlStart / tlEnd are the COMMITTED timeline positions — they stay
  // stable during trim. Trim only changes the source range preview.
  // roundHalfAwayFromZero is the spec-mandated rounding primitive
  // (symmetric tie-breaking); Math.round is forbidden even for
  // layout conversions from the legacy seconds model.
  const tlStartFrame = roundHalfAwayFromZero(
    clip.timeline_range.start * seqFps.num / seqFps.den,
  );
  const tlEndFrame = roundHalfAwayFromZero(
    clip.timeline_range.end * seqFps.num / seqFps.den,
  );
  const srcStartFrame = roundHalfAwayFromZero(
    clip.source_range.start * (sourceFps?.num ?? seqFps.num)
      / (sourceFps?.den ?? seqFps.den),
  ) + dStart;
  const srcEndFrame = roundHalfAwayFromZero(
    clip.source_range.end * (sourceFps?.num ?? seqFps.num)
      / (sourceFps?.den ?? seqFps.den),
  ) + dEnd;

  // Layout uses pxPerFrame (which may be subpixel). Integer frames
  // multiplied by a float pxPerFrame gives subpixel pixel positions —
  // this is intentional per the GUI-02.4 invariant.
  const left = tlStartFrame * pxPerFrame;
  const width = Math.max(8, (tlEndFrame - tlStartFrame) * pxPerFrame);

  // ---- Visual classes / labels -------------------------------------------
  const kindClass = clip.track_id.startsWith("t")
    ? "kind-text"
    : clip.track_id.startsWith("a")
      ? "kind-audio"
      : "";

  // Source range as timecode (display only). uses source FPS.
  const sFps = sourceFps ?? seqFps;
  const srcStartTc = framesToTimecode(srcStartFrame, sFps, false);
  const srcEndTc = framesToTimecode(srcEndFrame, sFps, false);
  const tlDurTc = framesToTimecode(tlEndFrame - tlStartFrame, seqFps, false);

  const label =
    clip.context?.text ||
    clip.context?.scene ||
    `${srcStartTc}-${srcEndTc}`;

  // ---- Waveform background (display only) --------------------------------
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const isMedia = clip.asset_id !== "";
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !isMedia) return;
    let dead = false;
    loadWave(clip.asset_id).then(({ peaks, duration }) => {
      if (dead || !peaks.length) return;
      const ctx = canvas.getContext("2d");
      if (!ctx) return;
      const w = (canvas.width = canvas.clientWidth || 100);
      const h = (canvas.height = canvas.clientHeight || 20);
      ctx.clearRect(0, 0, w, h);
      ctx.fillStyle = "rgba(126, 201, 126, 0.55)";
      // Waveform index math: normalized source position. The wave is
      // sampled at the asset's source FPS (or seq FPS if unknown).
      // NOTE: This is a display-only slicing — it does not enter
      // edit coordinates.
      const dur = duration || clip.source_range.end;
      const srcDurF = roundHalfAwayFromZero(
        clip.source_range.end * sFps.num / sFps.den,
      );
      const srcStartF = roundHalfAwayFromZero(
        clip.source_range.start * sFps.num / sFps.den,
      );
      const i0 = Math.floor((srcStartF / Math.max(1, srcDurF)) * peaks.length);
      const i1 = Math.max(i0 + 1, Math.ceil((srcEndFrame / Math.max(1, srcDurF)) * peaks.length));
      const slice = peaks.slice(i0, i1);
      const barW = w / Math.max(1, slice.length);
      slice.forEach((p, i) => {
        const bh = Math.max(1, p * h);
        ctx.fillRect(i * barW, (h - bh) / 2, Math.max(1, barW - 0.5), bh);
      });
    });
    return () => { dead = true; };
  }, [clip.asset_id, clip.source_range.start, clip.source_range.end,
      sFps.num, sFps.den, isMedia, width, srcEndFrame]);

  // ---------------------------------------------------------------------
  // MOVE drag — single canonical DragState
  // ---------------------------------------------------------------------
  //
  // GUI-04 04-04 (Drag Interaction Consolidation):
  //
  // Hard requirements (one provable data flow, no guard stacking):
  //
  //   1. ONE DragState object. No parallel state for the same
  //      semantic (no separate "preview vs pre-snap vs final vs
  //      authoritative-snap" variables).
  //   2. pointerdown: ONLY establish DragState. No mutation,
  //      no server, no Core touch.
  //   3. pointermove: ONLY chain
  //         pointer → candidateFrame → targetTrackId →
  //         Core-compatible constraint → previewFrame →
  //         optional snapPreviewFrame
  //      NO POST /clips, NO history op, NO revision bump,
  //      NO Core timeline change.
  //   4. pointerup: ONLY chain
  //         previewFrame → optional authoritative snap →
  //         collision → finalFrame/finalTrack → exactly ONE
  //         mutation
  //      Successful drag = exactly ONE Move operation. Cancelled /
  //      invalid / unchanged = zero mutations.
  //   5. Cross-track: track_id from semantic hit-test
  //      (elementsFromPoint → data-track-id). NEVER from
  //      style.left / style.width. Target-track collision via
  //      api.trackClips (Core sibling read).
  //   6. Same-track collision: Core `[start, end)` interval
  //      semantics. pointermove shows constrained preview without
  //      touching Core. pointerup re-validates with Core-compatible
  //      collision before committing.
  //   7. Preview semantics: previewFrame always equals what the
  //      user sees on screen. committedFrame is Core's truth.
  //      No UI-vs-Core drift.
  //   8. Auto-scroll: changes viewport only; does NOT amplify
  //      DragState candidateFrame.
  //   9. Small-delta (1 px): may round to 0 frames. Treated as
  //      unchanged drag → zero mutations.
  //  10. Repeated drag 10×: every pointerup leaves
  //      Timeline == Core == Preview (no spring-back / teleport).
  //
  // Instrumentation: every pointermove logs `[YROLL-DRAG-MOVE]`
  // and every pointerup logs `[YROLL-DRAG-UP]` via the global
  // window.__yrollDragLog so the browser smoke can assert the
  // full pipeline observably.
  // ---------------------------------------------------------------------
  const onPointerDown = (e: React.PointerEvent) => {
    // R6-E: refuse to start a drag when the GUI is not in EDIT.
    // The user's mental model: a click/drag always works when the
    // badge says 🟢. When it doesn't (CONNECTING / OBSERVE), the
    // click is still allowed for SELECTION so the user can inspect
    // the clip, but no drag/trim will fire — those would only be
    // rejected at commit time.
    if (!canEdit) {
      onSelect(clip.clip_id, false, e.ctrlKey || e.metaKey);
      return;
    }
    if ((e.target as HTMLElement).classList.contains("ai-zone")) return;
    if ((e.target as HTMLElement).classList.contains("trim-handle")) return;
    onSelect(clip.clip_id, false, e.ctrlKey || e.metaKey);
    if (locked) return;  // 轨道锁定：禁拖动
    const startX = e.clientX;
    const origStartFrame = tlStartFrame;
    const lenFrames = tlEndFrame - tlStartFrame;

    // GUI-03R5-B1 (Decision 1): drag-time edge auto-scroll. The
    // ContentViewport scrolls when the pointer is in the edge zone;
    // the auto-scroll rAF loop owns that viewport state. Critically,
    // scrollLeft does NOT participate in the frame delta — only the
    // pointer's displacement from startX does. This keeps the
    // pointer-only invariant the audit locked: scroll can move the
    // viewport (and thus where the clip is rendered on screen), but
    // cannot amplify the clip's frame jump.
    const dragContentEl = document.querySelector(
      ".timeline-content",
    ) as HTMLElement | null;
    const autoScroll = new DragAutoScroll(dragContentEl);

    // Other-clip boundaries (TimelineFrames). Convert from the
    // legacy seconds at the boundary using seqFps — this is
    // sequence-fps math, not TimeMap business math.
    const otherRanges = siblings
      .filter((s) => s.id !== clip.clip_id)
      .map((s) => ({
        // Siblings prop from Timeline.tsx is already in frame
        // domain (Timeline.tsx converts seconds → frames at the
        // source). Do NOT multiply by fps here — that would double
        // the conversion. The 03R3-1E clamp uses these directly.
        start: s.start,
        end: s.end,
      }))
      .sort((a, b) => a.start - b.start);

    /** Clamp to non-overlapping range. Direction-aware: drag right →
     * snap before the next clip; drag left → snap after the previous. */
    const clamp = (tryStart: number): number => {
      const tryEnd = tryStart + lenFrames;
      const conflicts = otherRanges.filter(
        (r) => tryStart < r.end && r.start < tryEnd,
      );
      if (conflicts.length === 0) return Math.max(0, tryStart);
      if (tryStart >= origStartFrame) {
        const first = conflicts.reduce((a, b) => a.start < b.start ? a : b);
        return Math.max(0, first.start - lenFrames);
      } else {
        const last = conflicts.reduce((a, b) => a.end > b.end ? a : b);
        return Math.max(0, last.end);
      }
    };

    /** Local snap (frame domain). Radius is FRAMES, not seconds.
     *  Returns { frame, kind } where kind tells us whether the
     *  matched candidate was a sibling.start ('snap-to-end-of-prev'
     *  semantic — clean landing past the clip) or a sibling.end
     *  ('snap-to-end' — landing AT the end, also clean). Only
     *  sibling-derived candidates return a real snap; matches to
     *  0 or origStartFrame return kind='own' (filtered by caller). */
    const snap = (tryStart: number): { frame: number; kind: 'end' | 'start' | 'own' } | null => {
      const tryEnd = tryStart + lenFrames;
      // First pass: snap to a sibling.end (clean landing AT or AFTER
      // a sibling — the clip's start aligns with sibling's end).
      for (const r of otherRanges) {
        if (Math.abs(tryStart - r.end) <= DEFAULT_SNAP_RADIUS_FRAMES) {
          return { frame: r.end, kind: 'end' };
        }
      }
      // Second pass: snap to a sibling.start (clean landing BEFORE
      // a sibling — the clip's end aligns with sibling's start).
      // This is valid for collision-free positions; overlap is
      // checked by the caller.
      for (const r of otherRanges) {
        const candidateStart = r.start - lenFrames;
        if (candidateStart >= 0 &&
            Math.abs(tryStart - candidateStart) <= DEFAULT_SNAP_RADIUS_FRAMES) {
          return { frame: candidateStart, kind: 'start' };
        }
      }
      // Third pass: snap via tryEnd alignment (clip's END near a
      // sibling boundary). Prefer sibling.end → clip-end alignment.
      for (const r of otherRanges) {
        if (Math.abs(tryEnd - r.end) <= DEFAULT_SNAP_RADIUS_FRAMES) {
          return { frame: r.end - lenFrames, kind: 'end' };
        }
      }
      for (const r of otherRanges) {
        if (Math.abs(tryEnd - r.start) <= DEFAULT_SNAP_RADIUS_FRAMES) {
          return { frame: r.start - lenFrames, kind: 'start' };
        }
      }
      // No sibling snap matched. Returning 'own' lets the caller
      // distinguish from null (no candidates within radius).
      return null;
    };

    // The local pointermove handler updates the SINGLE canonical
    // DragState. No HTTP, no TimeMap math, no Math.round on edit
    // coordinates. The only writes are drag-state field assignments
    // + the parent's onDragMove callback (visual-only).
    //
    // GUI-04 04-04 (req. 3): pointermove forbidden actions —
    //   POST /clips, PATCH mutation, history op, revision bump,
    //   Core timeline change. None of those happen here.
    //
    // Pointer-only delta: how far the pointer has moved from where
    // it landed at pointerdown. Viewport scroll changes are
    // deliberately excluded (req. 8: auto-scroll changes viewport
    // only; DragState candidateFrame is pointer-only).
    //
    // The single DragState replaces the previous 8 parallel
    // variables (lastCandidateFrame, lastPreviewFrame, lastDeltaFrame,
    // lastPixelDelta, lastGhostSnapFrame, lastClampJumpFrames,
    // preSnapFrame, authoritativeSnapFrame, snapAborted).
    type DragState = {
      clipId: string;
      originFrame: number;
      originTrackId: string;
      candidateFrame: number;
      previewFrame: number;
      targetTrackId: string;
      constrained: boolean;
      snapPreviewFrame: number | null;
    };
    const drag: DragState = {
      clipId: clip.clip_id,
      originFrame: origStartFrame,
      originTrackId: clip.track_id,
      candidateFrame: origStartFrame,
      previewFrame: origStartFrame,
      targetTrackId: clip.track_id,
      constrained: false,
      snapPreviewFrame: null,
    };

    const move = (ev: PointerEvent) => {
      // GUI-03R5-B1: feed the auto-scroll loop pointer X; viewport
      // scrolling does NOT enter the frame math (req. 8).
      autoScroll.updatePointer(ev.clientX);

      const pixelDelta = ev.clientX - startX;
      const deltaFrame = pxPerFrameToFrameDelta(pixelDelta, pxPerFrame);
      const candidate = origStartFrame + deltaFrame;
      // Same-track collision clamp (req. 6): the same-track `clamp`
      // uses `otherRanges` (frame-native intervals) — Core-compatible
      // semantics. pointermove shows constrained preview without
      // touching Core.
      const clamped = clamp(candidate);
      const wasConstrained = clamped !== candidate;

      // Ghost-snap target: visual-only (snapPreviewFrame), NEVER
      // mutates previewFrame. Only set when within snap radius.
      const allowSnap = snapMode === "always" || (snapMode === "alt" && ev.altKey);
      const ghostSnap = allowSnap ? snap(candidate) : null;
      drag.snapPreviewFrame = ghostSnap?.frame ?? null;

      // Update the SINGLE canonical DragState.
      drag.candidateFrame = candidate;
      drag.previewFrame = clamped;
      drag.constrained = wasConstrained;

      // Emit a `[YROLL-DRAG-MOVE]` instrumentation event so the
      // browser smoke can assert the pipeline observably (req. 12).
      const moveLog = {
        kind: "move",
        clipId: drag.clipId,
        originFrame: drag.originFrame,
        candidateFrame: drag.candidateFrame,
        previewFrame: drag.previewFrame,
        targetTrackId: drag.targetTrackId,
        constrained: drag.constrained,
        snapPreviewFrame: drag.snapPreviewFrame,
        pixelDelta,
        deltaFrame,
      };
      // eslint-disable-next-line no-console
      console.log("[YROLL-DRAG-MOVE]", JSON.stringify(moveLog));
      const w = window as unknown as { __yrollDragLog?: unknown[] };
      if (Array.isArray(w.__yrollDragLog)) w.__yrollDragLog.push(moveLog);

      if (onClampBoundary) onClampBoundary(clip.clip_id, wasConstrained);
      onDragMove(clip.clip_id, clamped, drag.snapPreviewFrame);
    };

    // pointerup: ONLY consume the canonical DragState, perform
    // optional authoritative snap + cross-track re-clamp + final
    // collision validation, then either:
    //   - ZERO mutations (unchanged / cancelled / invalid)
    //   - EXACTLY ONE api.move mutation
    //
    // GUI-04 04-04 (req. 4): no more parallel state, no second
    // candidate, no extra clamps. Single authoritative path.
    const up = async (ev: PointerEvent) => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
      autoScroll.dispose();

      // Consume the SINGLE DragState. Re-clamp against the
      // (possibly different) target track's siblings if the pointer
      // landed on a different track-row.
      //
      // Target track_id from semantic hit-test (req. 5). NEVER from
      // style.left / style.width. Cross-track collision via
      // api.trackClips (Core sibling read).
      const row = document.elementsFromPoint(ev.clientX, ev.clientY)
        .find((el) => (el as HTMLElement).dataset?.trackId) as HTMLElement | undefined;
      const hitTrackId = row?.dataset.trackId ?? null;

      // Cross-track re-clamp: only if pointer hit a different
      // track-row. We do NOT fold scrollLeft into the frame
      // delta (req. 8). The committed frame equals the preview
      // frame (req. 7) — no UI-vs-Core drift.
      let committedFrame = drag.previewFrame;
      let committedTrackId = hitTrackId ?? drag.originTrackId;
      let snapEngineApplied = false;
      let snapAborted = false;
      let snapFrame: number | null = null;

      // Optional authoritative snap — local snap() in the frame
      // domain (siblings prop is in frames). GUI-03R3-1E: Core's
      // /snap runs TimeMap which is wrong for clips with short
      // source; the local frame-domain snap is the authority.
      const localSnapTarget = snap(drag.previewFrame);
      if (localSnapTarget !== null) {
        const isNoOpStart = localSnapTarget.kind === 'start'
          && localSnapTarget.frame === drag.previewFrame;
        if (!isNoOpStart) {
          // Snap-on-source validation: clamp against source-track
          // siblings. If clamp would move the snap target AWAY from
          // itself, the snap creates overlap → INVALID.
          const clampedSnapped = clamp(localSnapTarget.frame);
          if (clampedSnapped === localSnapTarget.frame) {
            snapFrame = localSnapTarget.frame;
            committedFrame = localSnapTarget.frame;
            snapEngineApplied = true;
          } else {
            snapAborted = true;
            snapFrame = null;
            committedFrame = drag.previewFrame;
          }
        }
      }

      // Cross-track: re-fetch target-track siblings from Core,
      // re-clamp committedFrame against the target's `[start,end)`
      // intervals. We re-validate with Core-compatible collision
      // before committing (req. 6).
      if (hitTrackId && hitTrackId !== drag.originTrackId) {
        let targetClips: Array<{ id: string; start: number; end: number }> = [];
        try {
          const resp = await api.trackClips(hitTrackId);
          targetClips = resp.clips
            .filter((s) => s.clip_id !== clip.clip_id)
            .map((s) => ({ id: s.clip_id, start: s.start_frame, end: s.end_frame }));
        } catch (e) {
          // Network or 404: leave targetClips empty. Core rejects
          // overlapping moves on commit.
          console.warn("[YROLL-R6D] api.trackClips failed:", e);
        }
        const targetClamp = (tryStart: number): number => {
          const tryEnd = tryStart + lenFrames;
          const conflicts = targetClips.filter(
            (r) => tryStart < r.end && r.start < tryEnd,
          );
          if (conflicts.length === 0) return Math.max(0, tryStart);
          if (tryStart >= drag.originFrame) {
            const first = conflicts.reduce((a, b) => a.start < b.start ? a : b);
            return Math.max(0, first.start - lenFrames);
          } else {
            const last = conflicts.reduce((a, b) => a.end > b.end ? a : b);
            return Math.max(0, last.end);
          }
        };
        // If a snap was already applied on the source track, the snap
    // frame may collide on the target. Validate by clamping; if
    // clamp would move it, abort snap and use previewFrame.
        let candidateForTarget = committedFrame;
        if (snapFrame !== null) {
          const clampedSnapOnTarget = targetClamp(snapFrame);
          if (clampedSnapOnTarget === snapFrame) {
            candidateForTarget = snapFrame;
          } else {
            snapAborted = true;
            snapFrame = null;
            snapEngineApplied = false;
            candidateForTarget = drag.previewFrame;
          }
        }
        committedFrame = targetClamp(candidateForTarget);
      }

      // Safety clamp [0, project_max_frame] (req. 6: re-validate
      // with Core-compatible bound).
      let maxBoundary = 0;
      for (const r of otherRanges) {
        if (r.end > maxBoundary) maxBoundary = r.end;
      }
      maxBoundary += lenFrames;
      if (committedFrame < 0) committedFrame = 0;
      if (committedFrame > maxBoundary) committedFrame = maxBoundary;

      // Instrumentation payload for the smoke (req. 12):
      // pointer → candidateFrame → previewFrame → finalFrame →
      // committedFrame. Single canonical path.
      const upLog = {
        kind: "up",
        clipId: drag.clipId,
        originFrame: drag.originFrame,
        originTrackId: drag.originTrackId,
        candidateFrame: drag.candidateFrame,
        previewFrame: drag.previewFrame,
        targetTrackId: hitTrackId,
        committedTrackId,
        snapFrame,
        snapEngineApplied,
        snapAborted,
        committedFrame,
        // Whether this drag will produce exactly ONE mutation.
        // small-delta (req. 9): 1 px may round to 0 frames →
        // committedFrame == originFrame AND committedTrackId ==
        // originTrackId → unchanged → ZERO mutations.
        willMutate:
          committedFrame !== drag.originFrame
          || committedTrackId !== drag.originTrackId,
      };
      // eslint-disable-next-line no-console
      console.log("[YROLL-DRAG-UP]", JSON.stringify(upLog));
      const w = window as unknown as { __yrollDragLog?: unknown[] };
      if (Array.isArray(w.__yrollDragLog)) w.__yrollDragLog.push(upLog);

      // R6.1-B: clear clamp-boundary visual at drag end.
      if (onClampBoundary) onClampBoundary(clip.clip_id, false);

      // ZERO mutations when unchanged (req. 9, 10). Otherwise
      // EXACTLY ONE api.move via onMoveCommit (req. 4).
      if (!upLog.willMutate) {
        // unchanged drag → zero mutations
        return;
      }
      onMoveCommit(clip.clip_id, committedFrame, hitTrackId ?? undefined);
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
  };

  // ---------------------------------------------------------------------
  // TRIM drag (no `* clip.speed` anywhere)
  // ---------------------------------------------------------------------
  const onEdgeDown = (e: React.PointerEvent, edge: "left" | "right") => {
    // R6-E: refuse to start a trim when the GUI is not in EDIT.
    // Same rationale as onPointerDown: a trim commit is a mutation
    // that the server Mutation Gate would reject; better UX is to
    // silently no-op the drag and surface a status hint from the
    // EditLease badge.
    if (!canEdit) {
      e.stopPropagation();
      onSelect(clip.clip_id, false, e.ctrlKey || e.metaKey);
      return;
    }
    e.stopPropagation();
    onSelect(clip.clip_id, false, e.ctrlKey || e.metaKey);
    if (locked) return;  // 轨道锁定：禁裁剪
    const startX = e.clientX;
    let cur = { dStart: 0, dEnd: 0 };
    // Compute the asset's source-frame bounds at drag start. The
    // trim drag emits SOURCE-FRAME intent — Core's TimeMap converts
    // back to timeline on commit.
    const assetFps = sourceFps ?? seqFps;
    const srcStartF0 = roundHalfAwayFromZero(clip.source_range.start * assetFps.num / assetFps.den);
    const srcEndF0 = roundHalfAwayFromZero(clip.source_range.end * assetFps.num / assetFps.den);
    const srcDurF = srcEndF0 - srcStartF0;

    const move = (ev: PointerEvent) => {
      // pixelDelta → source-frame delta. NO * clip.speed, NO / clip.speed.
      //
      // The source-timebase pxPerFrame is derived from the timeline
      // pxPerFrame and the two FPS values:
      //
      //   pxPerFrame_source = pxPerFrame × (seqFps.num/seqFps.den)
      //                                   / (sourceFps.num/sourceFps.den)
      //
      // Then deltaSrcFrame = roundHalfAwayFromZero(pixelDelta /
      // pxPerFrame_source).
      const pixelDelta = ev.clientX - startX;
      const pxPerFrameSource =
        pxPerFrame * (seqFps.num / seqFps.den) / (assetFps.num / assetFps.den);
      const deltaSrcFrame = pxPerFrameToFrameDelta(pixelDelta, pxPerFrameSource);
      if (edge === "left") {
        // source range [start, end): head can move up to (end - 1)
        // and not below 0
        const maxD = srcDurF - MIN_TRIM_DELTA_FRAMES;
        const minD = -srcStartF0;
        const d = Math.min(maxD, Math.max(minD, deltaSrcFrame));
        cur = { dStart: d, dEnd: 0 };
      } else {
        // tail: can move up to (srcDurF - 1) backward and arbitrarily forward
        const maxD = srcDurF - MIN_TRIM_DELTA_FRAMES;
        const d = Math.max(-maxD, deltaSrcFrame);
        cur = { dStart: 0, dEnd: d };
      }
      setTrimDelta({ ...cur });
    };

    const up = () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
      setTrimDelta(null);
      // Commit in SOURCE frames (integer). Convert back to absolute
      // source-frame positions to send as intent.
      if (edge === "left" && Math.abs(cur.dStart) >= MIN_TRIM_DELTA_FRAMES) {
        onTrimCommit(clip.clip_id, srcStartF0 + cur.dStart, null);
      } else if (edge === "right" && Math.abs(cur.dEnd) >= MIN_TRIM_DELTA_FRAMES) {
        onTrimCommit(clip.clip_id, null, srcEndF0 + cur.dEnd);
      }
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
  };

  return (
    <div
      className={`clip ${kindClass} ${selected ? "selected" : ""} ${isRelated && highlightRel ? "related" : ""} ${clampBoundary ? "clamp-boundary" : ""}`}
      style={{ left, width, boxShadow: isRelated && highlightRel ? "0 0 0 2px #ffd479" : undefined }}
      data-clip-id={clip.clip_id}
      onPointerDown={onPointerDown}
      title={isRelated ? "跨轨关联 clip（Semantic Link）" : undefined}
    >
      <div
        className="trim-handle left"
        title="拖动裁剪头部"
        onPointerDown={(e) => onEdgeDown(e, "left")}
      />
      <div
        className="ai-zone"
        title="AI Context 区：点击打开 Clip Workspace（Y 轴）"
        onClick={(e) => {
          e.stopPropagation();
          onSelect(clip.clip_id, true);
        }}
      >
        Y · {clip.context?.why || "AI"}
      </div>
      <div className="edit-zone" title={`源 ${srcStartTc}-${srcEndTc} · 时长 ${tlDurTc} · 速度 ${clip.speed}x · 音量 ${clip.volume}`}>
        {isMedia && <canvas ref={canvasRef} className="wave-canvas" />}
        {isMedia && !kindClass && width > 60 && (
          <img
            className="clip-thumb"
            // GUI-03R3-1 fix: server expects `t` as float SECONDS, not
            // a SMPTE timecode string. Sample at srcRange.start + 0.1s
            // to get a non-black frame.
            src={`/assets/${clip.asset_id}/thumbnail?t=${(clip.source_range.start + 0.1).toFixed(3)}`}
            alt=""
            draggable={false}
            onError={(e) => { (e.target as HTMLImageElement).style.display = "none"; }}
          />
        )}
        <span className="clip-label">
          {clip.context?.muted ? "🔇 " : ""}{label}（{tlDurTc}）
        </span>
      </div>
      <div
        className="trim-handle right"
        title="拖动裁剪尾部"
        onPointerDown={(e) => onEdgeDown(e, "right")}
      />
    </div>
  );
}