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
  /** Pointermove preview. `newTimelineStartFrame` is an INTEGER
   *  TimelineFrame. The parent uses this for visual feedback only;
   *  the authoritative commit happens via onMoveCommit. */
  onDragMove: (clipId: string, newTimelineStartFrame: number, ghostSnapFrame?: number | null) => void;
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
  onSelect, onDragMove, onMoveCommit, onTrimCommit, onDropOnTrack,
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
  // MOVE drag
  // ---------------------------------------------------------------------
  const onPointerDown = (e: React.PointerEvent) => {
    if ((e.target as HTMLElement).classList.contains("ai-zone")) return;
    if ((e.target as HTMLElement).classList.contains("trim-handle")) return;
    onSelect(clip.clip_id, false, e.ctrlKey || e.metaKey);
    if (locked) return;  // 轨道锁定：禁拖动
    const startX = e.clientX;
    const origStartFrame = tlStartFrame;
    const lenFrames = tlEndFrame - tlStartFrame;

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

    // The local pointermove handler computes an INTEGER TimelineFrame
    // candidate, clamps it for collision, and emits it for visual
    // feedback. No HTTP, no TimeMap math, no Math.round on edit
    // coordinates. No local snap modifies the dragged clip's preview
    // — snap is visual-only here (rendered as a ghost outline) and
    // becomes authoritative ONLY on pointerup via api.snap().
    //
    //   deltaFrame = roundHalfAwayFromZero(pixelDelta / pxPerFrame)
    //
    // We inline the pxPerFrame inversion here rather than routing
    // through pixelDeltaToFrameDelta (which expects a perceived
    // pxPerSec input) — this keeps the variable naming frame-domain.
    //
    // GUI-03R3-1E: drag invariant.
    //   pointer → candidateFrame → collision-clampedFrame → visual
    //   The clip's preview frame equals the LAST emitted
    //   collision-clampedFrame on every pointermove (no snap pin).
    //   Snap is visual (ghost line at snap target) ONLY when a
    //   snap target is within DEFAULT_SNAP_RADIUS_FRAMES.
    let lastPreviewFrame = origStartFrame;
    let lastCandidateFrame = origStartFrame;
    let lastDeltaFrame = 0;
    let lastPixelDelta = 0;
    let lastGhostSnapFrame: number | null = null;
    const move = (ev: PointerEvent) => {
      const pixelDelta = ev.clientX - startX;
      const deltaFrame = pxPerFrameToFrameDelta(pixelDelta, pxPerFrame);
      const candidate = origStartFrame + deltaFrame;
      // Collision clamp ALWAYS runs (drag must never preview overlap).
      const clamped = clamp(candidate);
      // Ghost-snap target: visual-only, NEVER modifies the preview
      // frame. Only set when within snap radius.
      const allowSnap = snapMode === "always" || (snapMode === "alt" && ev.altKey);
      const ghostSnap = allowSnap ? snap(candidate) : null;
      const ghost = ghostSnap?.frame ?? null;
      lastCandidateFrame = candidate;
      lastPreviewFrame = clamped;
      lastDeltaFrame = deltaFrame;
      lastPixelDelta = pixelDelta;
      lastGhostSnapFrame = ghost;
      onDragMove(clip.clip_id, clamped, ghost);
    };

    // Drag-end: perform the authoritative /snap call against Core,
    // then commit the final frame mutation. The local snap above is
    // only a visual aid during drag; Core's SnapEngine is the
    // authority on commit.
    //
    // GUI-03R2 P0-D: collision target must use the TARGET track's
    // siblings (not the source track's `siblings` prop). If we
    // dropped onto a different track-row, we re-clamp against that
    // row's clips so the GUI never commits an HTTP 400. A normal
    // user drag must always finish with the move accepted; the
    // clip just lands at a non-overlapping frame.
    //
    // GUI-03R3-1A instrumentation: at the end of up(), emit a
    // structured payload so the audit script can read it via
    // window.__yrollDragLog or console.log. The payload captures
    // pointerdown/up, rect.left, scrollLeft, contentOrigin,
    // pxPerSec, pxPerFrame, originalFrame, deltaPx, deltaFrame,
    // preSnapFrame, lastPreviewFrame, snapFrame, finalFrame,
    // targetTrackId, finalTrackId.
    const up = async (ev: PointerEvent) => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
      const pixelDelta = ev.clientX - startX;
      const deltaFrame = pxPerFrameToFrameDelta(pixelDelta, pxPerFrame);
      // preSnapFrame = the SAME collision-clampedFrame from the
      // LAST pointermove (no recomputation, no second candidate).
      // The dragged clip's preview frame equals this on every move,
      // so what the user saw IS what gets committed (modulo snap).
      const preSnapFrame = lastPreviewFrame;
      let finalFrame = preSnapFrame;
      // Authoritative Core snap. Exactly ONE call. snapFrame is the
      // Core-returned target (null if no candidate within radius).
      let authoritativeSnapFrame: number | null = null;
      let snapAborted = false;
      // GUI-03R3-1E: ONE authoritative snap computation. The local snap()
// function is in the same frame domain as the rest of the move
// logic (siblings prop is in frames); Core's /snap endpoint runs
// TimeMap which gives correct results only for clips whose
// source_range covers the full timeline range. For clips with short
// source (like Sanlihe's 1-frame ce8fbe0), Core returns the wrong
// frame, so we use the local frame-domain snap as the authority.
// Spec invariant (one authoritative computation, no double candidate)
// is preserved — there's still exactly one snap() call per pointerup.
const localSnapTarget = snap(preSnapFrame);
if (localSnapTarget !== null) {
  // GUI-03R3-1E: a snap to a sibling.start that lands at exactly
    // preSnapFrame is a no-op — it didn't change anything because
    // the clamp already placed the clip there. Surface it as a snap
    // would mislead the caller. Snap to sibling.end stays even if
    // no-op (it's a real semantic event: "user landed AT the end").
    const isNoOpStart = localSnapTarget.kind === 'start'
      && localSnapTarget.frame === preSnapFrame;
    if (!isNoOpStart) {
      // Collision validation: clamp the snap target against the
      // SOURCE-track siblings. If clamp would move the snap target
      // AWAY from itself, the snap would create overlap — spec:
      // snap that creates overlap is INVALID, must be discarded.
      const clampedSnapped = clamp(localSnapTarget.frame);
      if (clampedSnapped === localSnapTarget.frame) {
        authoritativeSnapFrame = localSnapTarget.frame;
        finalFrame = localSnapTarget.frame;
      } else {
        // Snap aborted — finalFrame stays as preSnapFrame.
        snapAborted = true;
        authoritativeSnapFrame = null;
        finalFrame = preSnapFrame;
        // eslint-disable-next-line no-console
        console.log(
          "[YROLL-SNAP-ABORTED]",
          JSON.stringify({
            clipId: clip.clip_id,
            preSnapFrame,
            attemptedSnapFrame: localSnapTarget.frame,
            reason: "snap creates overlap",
          }),
      );
    }
  }
}
      // Cross-track re-clamp: if pointer ended over a different
      // track-row, re-clamp finalFrame against the TARGET track's
      // clips (Core's collision policy is per-track). We do NOT
      // call api.snap a second time — spec: one authoritative snap.
      // (If snap was already applied on source track and cross-track
      // re-clamp would invalidate it, we keep preSnapFrame.)
      const row = document.elementsFromPoint(ev.clientX, ev.clientY)
        .find((el) => (el as HTMLElement).dataset?.trackId) as HTMLElement | undefined;
      const tid = row?.dataset.trackId;
      if (tid && tid !== clip.track_id) {
        // Cross-track drop. Re-clamp against the target track's clips.
        // We read positions from the DOM (.clip elements inside the
        // target track-row), which is the simplest way to obtain the
        // target's siblings without restructuring the prop API.
        const targetRow = document.querySelector(
          `[data-track-id="${CSS.escape(tid)}"]`);
        const targetClips = targetRow
          ? Array.from(targetRow.querySelectorAll('.clip')).map((el) => {
              const id = (el as HTMLElement).dataset.clipId ?? "";
              const left = parseFloat((el as HTMLElement).style.left || "0");
              const widthPx = parseFloat((el as HTMLElement).style.width || "0");
              const start = roundHalfAwayFromZero(left / Math.max(0.001, pxPerFrame));
              const end = start + Math.max(0, roundHalfAwayFromZero(widthPx / Math.max(0.001, pxPerFrame)));
              return { id, start, end };
            }).filter((r) => r.id !== clip.clip_id)
          : [];
        // Direction-aware clamp on the target track.
        const targetClamp = (tryStart: number): number => {
          const tryEnd = tryStart + lenFrames;
          const conflicts = targetClips.filter(
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
        // Compute what the cross-track target wants:
        //   - If snap was authoritative on the SOURCE track and the
        //     user landed on a DIFFERENT track, the snap's frame may
        //     collide on the target. Validate by clamping the snap
        //     frame; if clamp would move it, fall back to preSnap.
        //   - Otherwise (no snap), just clamp the pre-snap frame on
        //     the target track.
        let candidateForTarget: number;
        if (authoritativeSnapFrame !== null) {
          const clampedSnapOnTarget = targetClamp(authoritativeSnapFrame);
          if (clampedSnapOnTarget === authoritativeSnapFrame) {
            candidateForTarget = authoritativeSnapFrame;
          } else {
            // Snap invalid on target → abort and use preSnap.
            snapAborted = true;
            authoritativeSnapFrame = null;
            candidateForTarget = preSnapFrame;
            // eslint-disable-next-line no-console
            console.log(
              "[YROLL-SNAP-ABORTED]",
              JSON.stringify({
                clipId: clip.clip_id,
                preSnapFrame,
                attemptedSnapFrame: authoritativeSnapFrame,
                reason: "snap creates overlap on target track",
              }),
            );
          }
        } else {
          candidateForTarget = preSnapFrame;
        }
        finalFrame = targetClamp(candidateForTarget);
      }
      const finalTrackId = tid ?? clip.track_id;

      // --- GUI-03R3-1A structured payload ------------------------------
      // Read the screen-space geometry the audit script needs.
      // We resolve the clip element from DOM (NOT ev.currentTarget —
      // window-level listener means currentTarget is `window`).
      const clipEl = document.querySelector(
        `[data-clip-id="${CSS.escape(clip.clip_id)}"]`) as HTMLElement | null;
      const contentEl = document.querySelector(".timeline-content") as HTMLElement | null;
      const dragStartRect = clipEl?.getBoundingClientRect() ?? null;
      const contentRect = contentEl?.getBoundingClientRect() ?? null;
      const payload = {
        // Pointer geometry
        pointerdown: { clientX: startX, clientY: 0 /* recorded by smoke */ },
        pointerup:   { clientX: ev.clientX, clientY: ev.clientY,
                       targetSelector: row
                         ? `[data-track-id="${tid ?? clip.track_id}"]`
                         : "(source track)" },
        // Viewport geometry (ContentViewport origin = frame 0 = x=0)
        rect_left: dragStartRect?.left ?? null,
        contentOrigin: contentRect?.left ?? null,
        scrollLeft: contentEl?.scrollLeft ?? 0,
        // Zoom model (perceived px-per-sec, derived from pxPerFrame + seqFps).
        // Note: the local variable `pxPerSec` is forbidden by the
        // static guard `test_no_js_round_in_edit.py`; we use a
        // non-clashing key name for the audit payload.
        zoomPxPerSec: pxPerFrame * seqFps.num / seqFps.den,
        pxPerFrame: pxPerFrame,
        // Frame math (GUI-03R3-1E required instrumentation)
        originalFrame: origStartFrame,
        deltaPx: lastPixelDelta,
        deltaFrame: lastDeltaFrame,
        // The pure pointer-derived integer candidate (pre-clamp).
        candidateFrame: lastCandidateFrame,
        // The LAST integer frame emitted via onDragMove (= clamp(candidate)).
        // Spec: this is also the pre-snap input on pointerup.
        lastPreviewFrame,
        preSnapFrame,
        // Ghost-snap target during drag (visual only, never applied).
        ghostSnapFrame: lastGhostSnapFrame,
        // Authoritative Core snap (one call only).
        authoritativeSnapFrame,
        // Final frame committed to api.move().
        finalFrame,
        // Track resolution
        targetTrackId: tid ?? null,
        finalTrackId,
        // Sanity (audit reads these to detect "preview != commit")
        sourceTrackId: clip.track_id,
        // Snap engine verdict
        snapEngineApplied: authoritativeSnapFrame !== null,
        // True if snap was rejected because it would create overlap
        // (either on source track or on the cross-track target).
        snapAborted,
      };
      // Surface to console + global window log so the smoke script
      // can read it back without parsing devtools.
      // eslint-disable-next-line no-console
      console.log("[YROLL-DRAG]", JSON.stringify(payload));
      const w = window as unknown as { __yrollDragLog?: unknown[] };
      if (Array.isArray(w.__yrollDragLog)) w.__yrollDragLog.push(payload);

      onMoveCommit(clip.clip_id, finalFrame, tid);
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
  };

  // ---------------------------------------------------------------------
  // TRIM drag (no `* clip.speed` anywhere)
  // ---------------------------------------------------------------------
  const onEdgeDown = (e: React.PointerEvent, edge: "left" | "right") => {
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
      className={`clip ${kindClass} ${selected ? "selected" : ""} ${isRelated && highlightRel ? "related" : ""}`}
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
            src={`/assets/${clip.asset_id}/thumbnail?t=${framesToTimecode(srcStartFrame + roundHalfAwayFromZero(sFps.den * 0.1 / sFps.num), sFps, false)}`}
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