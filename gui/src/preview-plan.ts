// GUI-03D.1: Preview Plan cache for the L1 Timeline Composite.
//
// During continuous playback, the FrameClock advances the current
// TimelineFrame. The plan cache (fetched ONCE per project_revision)
// is queried LOCALLY to find the active layer on each track at the
// current frame. No per-frame HTTP.
//
// The plan is invalidated when /ui/status's `base_revision`
// changes (any Core mutation bumps the revision). The GUI checks
// the revision before each playback frame and refetches the plan
// when it changes.

import { useEffect, useRef, useState } from "react";
import { api } from "./api";

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

/** Hook: load + cache the Preview Plan. Invalidates when the
 *  project's revision changes. */
export function usePreviewPlan(
  projectRevision: number | null,
  timelineId: string = "main",
): {
  plan: PreviewPlan | null;
  loading: boolean;
  error: string | null;
  fetchCount: number;
} {
  const [plan, setPlan] = useState<PreviewPlan | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const lastRevRef = useRef<number | null>(null);
  const fetchCountRef = useRef(0);

  useEffect(() => {
    if (projectRevision === null) return;
    if (lastRevRef.current === projectRevision) return;
    lastRevRef.current = projectRevision;
    setLoading(true);
    setError(null);
    fetchCountRef.current += 1;
    api.previewPlan()
      .then((data) => {
        setPlan({
          project_revision: data.project_revision,
          timeline_id: data.timeline_id,
          fps: data.fps,
          tracks: data.tracks,
          subtitle_ranges: data.subtitle_ranges,
        });
      })
      .catch((e) => {
        setError(String(e));
      })
      .finally(() => setLoading(false));
  }, [projectRevision, timelineId]);

  return { plan, loading, error, fetchCount: fetchCountRef.current };
}
