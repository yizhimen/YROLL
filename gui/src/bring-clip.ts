// GUI-03R6-C: pure planning helper for `bringClipIntoView`.
//
// R6-C follow-up: the original wrapper read `project?.clips[clipId]`
// from the React closure. After a successful mutation, `refresh()`
// calls `setProject(fresh)` — but the next render hasn't happened
// yet when `bringClipIntoView` runs, so the closure value is stale.
// For `addImageClip` / `addClip` / paste / duplicate the new clip is
// not in the stale `project.clips`, so the helper silently no-ops.
//
// Splitting the helper into a pure planner + a thin wrapper lets the
// GUI compute the scroll target from CANONICAL data (the mutation
// response or the move intent) without touching the stale project
// closure. The wrapper is in `gui/src/App.tsx`; this file owns the
// pure logic and its tests.

export type BringRange = {
  /** INTEGER TimelineFrame where the clip starts (after the mutation). */
  startFrame: number;
  /** INTEGER TimelineFrame where the clip ends (after the mutation). */
  endFrame: number;
};

export type BringOpts = {
  /** The clip's id. Must be the post-mutation clip id. */
  clipId: string;
  /** Canonical TimelineFrame range the clip occupies AFTER the
   *  mutation. MUST be supplied by the call site — either from the
   *  mutation response (timeline_range.start/end × fps) or from the
   *  move intent (newStartFrame + lenFrames). The helper cannot
   *  read this from the React closure (stale until next render). */
  rangeFrames?: BringRange;
  /** Seek playhead to `rangeFrames.startFrame`. Default false.
   *  Volume / speed / mute / cross-track-keep must NOT jump the
   *  playhead; only `seek: true` paths (add / move / duplicate) do. */
  seek?: boolean;
  /** Scroll strategy:
   *    "always"       — scroll even if the clip is in view
   *    "if-offscreen" — scroll only when out of view (default)
   *    "never"        — never scroll (still select / optionally seek) */
  scroll?: "always" | "if-offscreen" | "never";
};

export type BringPlan = {
  /** The id the GUI should select + add to selectedSet. */
  selectClipId: string;
  /** Frame to seek the playhead to, or null if no seek. */
  setPlayheadFrame: number | null;
  /** Value to assign to .timeline-content.scrollLeft, or null
   *  if no scroll is required (clip is in view, or scroll:"never"). */
  scrollLeft: number | null;
};

export type BringMeasurements = {
  /** pxPerSec at call time (stable across a single user gesture). */
  pxPerSec: number;
  /** Sequence fps at call time (project invariant — does not change
   *  between mutations, so a closure value is safe). */
  seqFps: { num: number; den: number };
  /** The Timeline's `.timeline-content` element, or null if not in
   *  the DOM (the helper can't scroll in that case). */
  contentEl: {
    clientWidth: number;
    getBoundingClientRect: () => {
      left: number; right: number; top: number; bottom: number;
      width: number; height: number; x: number; y: number;
    };
  } | null;
  /** The clip's rendered `.clip` element, or null if it has not yet
   *  rendered (post-refresh, pre-render case). The helper falls back
   *  to rangeFrames for the scroll computation when clipEl is null. */
  clipEl: {
    getBoundingClientRect: () => {
      left: number; right: number; top: number; bottom: number;
      width: number; height: number; x: number; y: number;
    };
  } | null;
};

/** Pure planner: turn BringOpts + DOM measurements into the concrete
 *  side-effects the React wrapper should apply. No project lookup,
 *  no setState — just a plan object the wrapper applies. Idempotent
 *  for the same inputs (a stable mutation result + the same
 *  measurements yields the same plan).
 *
 *  Frame semantics:
 *    - rangeFrames.startFrame / endFrame are INTEGER TimelineFrames.
 *    - We never compare to seconds or do `* fps` here.
 *    - pxPerF = pxPerSec × (seqFps.den / seqFps.num) — pure unit math. */
export function computeBringPlan(
  opts: BringOpts,
  measurements: BringMeasurements,
): BringPlan {
  // 1. Selection — always the post-mutation clip id (no closure lookup).
  const selectClipId = opts.clipId;

  // 2. Seek — only if explicitly requested AND we have a canonical range.
  //    Default seek:false means volume / speed / mute / track ops never
  //    jump the playhead. Seek on `seek: true` requires rangeFrames —
  //    without it we have no frame to seek to.
  const setPlayheadFrame =
    opts.seek === true && opts.rangeFrames
      ? opts.rangeFrames.startFrame
      : null;

  // 3. Scroll — controlled by opts.scroll + DOM measurements.
  let scrollLeft: number | null = null;
  if (opts.scroll !== "never" && measurements.contentEl) {
    const pxPerF = measurements.pxPerSec
      * (measurements.seqFps.den / measurements.seqFps.num);
    const contentRect = measurements.contentEl.getBoundingClientRect();

    if (measurements.clipEl) {
      // Element is rendered: detect offscreen vs in-view.
      const clipRect = measurements.clipEl.getBoundingClientRect();
      const offscreen = clipRect.left < contentRect.left
        || clipRect.right > contentRect.right;
      if (opts.scroll === "always" || offscreen) {
        // Center the canonical frame in the viewport. RangeFrames is
        // the source of truth even when the element is rendered, so
        // the scroll target is identical to the post-refresh case.
        const startFrame = opts.rangeFrames?.startFrame ?? 0;
        scrollLeft = Math.max(0,
          startFrame * pxPerF - measurements.contentEl.clientWidth / 2);
      }
    } else if (opts.rangeFrames) {
      // Element not yet rendered (post-refresh, pre-render). The
      // R6-C follow-up case: we cannot rely on the React project
      // closure (it doesn't contain the new clip yet), so we use
      // rangeFrames directly. We always scroll because we can't
      // detect offscreen without a rendered element — the user's
      // mental model is "I just dropped something here, bring it
      // into view".
      scrollLeft = Math.max(0,
        opts.rangeFrames.startFrame * pxPerF
          - measurements.contentEl.clientWidth / 2);
    }
    // else: clipEl null AND rangeFrames undefined → no scroll.
    //       This only happens for ops that have no canonical frame
    //       range (e.g., volume / speed) and is fine — those ops
    //       shouldn't be passed bring at all.
  }

  return { selectClipId, setPlayheadFrame, scrollLeft };
}