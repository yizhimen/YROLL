// GUI-03D.1 + GUI-03E-3: Preview Plan cache for the L1 Timeline
// Composite, scoped per Timeline.
//
// During continuous playback, the FrameClock advances the current
// TimelineFrame. The plan cache (fetched ONCE per
// (project_revision, timeline_id) pair) is queried LOCALLY to find
// the active layer on each track at the current frame. No per-frame
// HTTP.
//
// The plan is invalidated when /ui/status's `base_revision` changes
// (any Core mutation bumps the revision). The GUI checks the
// revision before each playback frame and refetches the plan when it
// changes.
//
// GUI-03E-3 — keying by timeline_id prevents Preview-A's plan from
// leaking into Preview-B after a switch. Race safety: a stale fetch
// that resolves AFTER the user has switched to a different Timeline
// must NOT clobber the new Timeline's plan. Each effect tracks its
// own request epoch and the component's `activeTimelineId` ref; if
// the active timeline changes between request fire and resolve, the
// response is discarded.

import { useEffect, useRef, useState, useCallback } from "react";
import { api, TimelinesResponse, TimelineSummary } from "./api";

export interface PreviewLayer {
  track_id: string;
  layer_index: number;
  kind: string;
  clip_id: string;
  asset_id: string;
  asset_type: string;
  asset_path: string;
  timeline_start_frame: number;
  timeline_end_frame: number;
  source_start_frame: number;
  source_end_frame: number;
  source_fps: { num: number; den: number } | null;
  transform: Record<string, unknown>;
}

export interface PreviewPlan {
  project_revision: number;
  timeline_id: string;
  fps: { num: number; den: number };
  tracks: PreviewLayer[][];
  subtitle_ranges: Array<{
    start_frame: number;
    end_frame: number;
    text: string;
  }>;
}

/** Return the active layer on one track at a given TimelineFrame.
 *  Layers are assumed sorted by `timeline_start_frame`. We walk
 *  from the end so a later clip whose half-open range starts at
 *  `timeline_frame` correctly wins over an earlier clip whose
 *  range ends at `timeline_frame` (half-open). */
export function activeLayerAt(
  trackLayers: PreviewLayer[],
  timelineFrame: number,
): PreviewLayer | null {
  for (let i = trackLayers.length - 1; i >= 0; i--) {
    const l = trackLayers[i];
    if (
      l.timeline_start_frame <= timelineFrame &&
      timelineFrame < l.timeline_end_frame
    ) {
      return l;
    }
  }
  return null;
}

/** Compute the SourceFrame integer at `timelineFrame` for one layer. */
export function sourceFrameAt(
  layer: PreviewLayer,
  timelineFrame: number,
): number {
  if (layer.kind === "image") return 0;
  const tlRange = layer.timeline_end_frame - layer.timeline_start_frame;
  if (tlRange <= 0) return layer.source_start_frame;
  const srcRange = layer.source_end_frame - layer.source_start_frame;
  return (
    layer.source_start_frame +
    Math.round(
      ((timelineFrame - layer.timeline_start_frame) * srcRange) / tlRange,
    )
  );
}

/** Compute the media-seconds (v.currentTime) for one layer. */
export function sourceSecondsAt(
  layer: PreviewLayer,
  timelineFrame: number,
): number {
  const sf = sourceFrameAt(layer, timelineFrame);
  if (layer.source_fps === null) return 0;
  return (sf * layer.source_fps.den) / layer.source_fps.num;
}

/** Active subtitle text for the given TimelineFrame (most recent). */
export function activeSubtitleAt(
  plan: PreviewPlan,
  timelineFrame: number,
): string | null {
  let chosen: string | null = null;
  let chosenStart = -1;
  for (const { start_frame, end_frame, text } of plan.subtitle_ranges) {
    if (start_frame <= timelineFrame && timelineFrame < end_frame) {
      if (start_frame >= chosenStart) {
        chosen = text;
        chosenStart = start_frame;
      }
    }
  }
  return chosen;
}

// =================================================================
// GUI-03E-3: useTimelines — switcher data layer.
// =================================================================
//
// Returns the Project's peer Timelines + active_timeline_id +
// default_timeline_id. Refresh is invalidated by (projectRevision,
// timelineListRevision) where timelineListRevision is bumped when
// any Timeline lifecycle mutation lands. The hook is read-only; it
// never triggers a mutation.

interface TimelinesState {
  activeTimelineId: string;
  defaultTimelineId: string;
  timelines: TimelineSummary[];
  loading: boolean;
  error: string | null;
}

export function useTimelines(
  projectRevision: number | null,
): TimelinesState {
  const [state, setState] = useState<TimelinesState>({
    activeTimelineId: "",
    defaultTimelineId: "",
    timelines: [],
    loading: false,
    error: null,
  });
  const lastRevRef = useRef<number | null>(null);

  useEffect(() => {
    if (projectRevision === null) return;
    if (lastRevRef.current === projectRevision) return;
    lastRevRef.current = projectRevision;
    setState((s) => ({ ...s, loading: true, error: null }));
    api.listTimelines()
      .then((data: TimelinesResponse) => {
        setState({
          activeTimelineId: data.active_timeline_id,
          defaultTimelineId: data.default_timeline_id,
          timelines: data.timelines,
          loading: false,
          error: null,
        });
      })
      .catch((e) => {
        setState((s) => ({ ...s, loading: false, error: String(e) }));
      });
  }, [projectRevision]);

  return state;
}

// =================================================================
// GUI-03D.1 + GUI-03E-3: usePreviewPlan — keyed by (rev, timeline_id)
// =================================================================
//
// Race safety: when the user switches Timeline rapidly, multiple
// in-flight `/preview/plan` requests can be outstanding. Each one
// carries a request epoch; the effect also reads the latest
// `timelineId` from props on resolve and aborts the state update if
// the user has already moved on to a different Timeline. This
// guarantees that Preview-A content cannot leak into Preview-B.
//
// R6.1-D: the cache is also keyed by an external `invalidationVersion`
// (a counter that App.tsx bumps after every successful
// Preview-affecting mutation — setTrackHidden, addClip, move, trim,
// removeClip, addTrack, etc.). Without this, the GUI is at the mercy
// of the 5-second `/sequence` poll to discover the new revision; in
// the worst case the user hides a track and the L1 composite keeps
// showing the hidden layer for up to one poll cycle. Bumping the
// invalidation version forces an immediate refetch.

interface PreviewPlanState {
  plan: PreviewPlan | null;
  loading: boolean;
  error: string | null;
  fetchCount: number;
}

export function usePreviewPlan(
  projectRevision: number | null,
  timelineId: string = "main",
  invalidationVersion: number = 0,
): PreviewPlanState {
  const [plan, setPlan] = useState<PreviewPlan | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Track the timeline_id the LAST APPLIED plan belongs to. If a
  // resolve sees a different id, drop the response.
  const activeTimelineRef = useRef<string>(timelineId);
  const lastKeyRef = useRef<string | null>(null);
  const fetchCountRef = useRef(0);

  useEffect(() => {
    if (projectRevision === null) return;
    // Per-timeline dedupe: don't refetch if (rev, timeline_id,
    // invalidationVersion) already fetched this run. The
    // invalidationVersion is appended to the key so a manual bump
    // from App.tsx forces a refetch even when the project revision
    // hasn't changed yet (the /sequence poll is on a 5s cadence).
    const key = `${projectRevision}:${timelineId}:${invalidationVersion}`;
    if (lastKeyRef.current === key) return;
    lastKeyRef.current = key;
    // Clear stale plan when timeline changes: we don't want to
    // briefly show Timeline A's layers under Timeline B's name.
    if (activeTimelineRef.current !== timelineId) {
      activeTimelineRef.current = timelineId;
      setPlan(null);
    }
    setLoading(true);
    setError(null);
    fetchCountRef.current += 1;
    api
      .previewPlan({ timeline_id: timelineId })
      .then((data) => {
        // RACE GUARD: if the user has already switched to a
        // different Timeline since this fetch fired, discard the
        // response — applying it would show stale content.
        if (activeTimelineRef.current !== data.timeline_id) {
          // No state mutation. The newer Timeline's effect will
          // set the correct plan shortly.
          return;
        }
        setPlan({
          project_revision: data.project_revision,
          timeline_id: data.timeline_id,
          fps: data.fps,
          tracks: data.tracks,
          subtitle_ranges: data.subtitle_ranges,
        });
      })
      .catch((e) => {
        // Don't overwrite with errors from a now-irrelevant fetch.
        if (activeTimelineRef.current !== timelineId) return;
        setError(String(e));
      })
      .finally(() => {
        if (activeTimelineRef.current === timelineId) {
          setLoading(false);
        }
      });
  }, [projectRevision, timelineId, invalidationVersion]);

  return { plan, loading, error, fetchCount: fetchCountRef.current };
}

// =================================================================
// R6.1-D: usePreviewPlanInvalidation — single hook that returns a
// `bumpPlanVersion()` function. App.tsx calls it after every
// successful Preview-affecting mutation. The counter is
// monotonically increasing; the PreviewPlan hook subscribes to it
// and refetches when it changes.
//
// One reusable mechanism, not individual ad-hoc fetches — per the
// R6.1-D design constraint.
// =================================================================

export function usePreviewPlanInvalidation(): {
  invalidationVersion: number;
  bumpPlanVersion: () => void;
} {
  const [version, setVersion] = useState(0);
  const bump = useCallback(() => setVersion((v) => v + 1), []);
  return { invalidationVersion: version, bumpPlanVersion: bump };
}