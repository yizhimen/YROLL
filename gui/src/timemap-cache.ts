// GUI-02.5: timemap-cache — Core TimeMap response cache.
//
// The GUI must NEVER compute TimelineFrame↔SourceFrame locally (that's
// TimeMap business math, forbidden per the closure invariant). Instead,
// it asks Core via `/clip/{id}/timemap` for the static mapping data
// (sequence_fps, source_fps, source_start_frame, source_end_frame,
// timeline_start_frame, speed) and `/clip/{id}/timemap/at_frame`
// for the per-frame `source_frame_for_timeline` lookup.
//
// The cache is keyed by (clipId, projectRevision, sequenceFps,
// sourceFps). A new revision or fps mismatch invalidates the entry.
//
// The cache holds an in-flight Promise to dedupe concurrent fetches
// for the same key. After the cache resolves, per-frame lookups hit
// the network per-call (modern browsers handle this transparently
// during video playback — the video element buffers locally).

import { api } from "./api";
import type { Fps } from "./frame-clock";

export interface TimeMapCacheEntry {
  clipId: string;
  projectRevision: number;
  sequenceFps: Fps;
  sourceFps: Fps;
  sourceStartFrame: number;
  sourceEndFrame: number;
  timelineStartFrame: number;
  speed: number;
}

interface PendingEntry {
  promise: Promise<TimeMapCacheEntry>;
  entry?: TimeMapCacheEntry;
  error?: unknown;
}

const cache = new Map<string, PendingEntry>();

function cacheKey(
  clipId: string, projectRevision: number, sequenceFps: Fps, sourceFps: Fps,
): string {
  return `${clipId}|${projectRevision}|${sequenceFps.num}/${sequenceFps.den}|${sourceFps.num}/${sourceFps.den}`;
}

/** Fetch (and cache) the static TimeMap data for a clip.
 *  Subsequent calls with the same key return the same Promise. */
export async function fetchTimeMap(
  clipId: string,
  projectRevision: number,
  sequenceFps: Fps,
  sourceFps?: Fps,
): Promise<TimeMapCacheEntry> {
  const fps = sourceFps ?? sequenceFps;
  const key = cacheKey(clipId, projectRevision, sequenceFps, fps);
  const existing = cache.get(key);
  if (existing) return existing.promise;
  const promise = (async (): Promise<TimeMapCacheEntry> => {
    const url = sourceFps
      ? `/clip/${clipId}/timemap?fps_num=${sequenceFps.num}&fps_den=${sequenceFps.den}` +
        `&src_fps_num=${sourceFps.num}&src_fps_den=${sourceFps.den}`
      : `/clip/${clipId}/timemap?fps_num=${sequenceFps.num}&fps_den=${sequenceFps.den}`;
    const data = await api.getTimemapRaw(url);
    // The server response uses `fps` (legacy) AND `sequence_fps` +
    // `source_fps` (GUI-02.3 contract). Prefer the explicit fields.
    const seqFps = (data as { sequence_fps?: { num: number; den: number } }).sequence_fps
      ?? data.fps;
    const srcFps = (data as { source_fps?: { num: number; den: number } }).source_fps
      ?? data.fps;
    return {
      clipId,
      projectRevision,
      sequenceFps: seqFps,
      sourceFps: srcFps,
      sourceStartFrame: data.source_start_frame,
      sourceEndFrame: data.source_end_frame,
      timelineStartFrame: data.timeline_start_frame,
      speed: data.speed,
    };
  })();
  cache.set(key, { promise });
  try {
    const entry = await promise;
    cache.set(key, { promise, entry });
    return entry;
  } catch (e) {
    // Allow retry: drop the failed promise from the cache.
    cache.delete(key);
    throw e;
  }
}

/** Look up the SourceFrame for a given TimelineFrame via Core. The
 *  Core endpoint applies TimeMap business math (clip.speed + source/
 *  sequence fps); the GUI never computes this locally. */
export async function sourceFromTimeline(
  entry: TimeMapCacheEntry,
  timelineFrame: number,
): Promise<number> {
  const url = `/clip/${entry.clipId}/timemap/at_frame?` +
    `timeline_frame=${timelineFrame}` +
    `&src_fps_num=${entry.sourceFps.num}&src_fps_den=${entry.sourceFps.den}`;
  const data = await api.getTimemapAtFrameRaw(url);
  return data.source_frame;
}

/** Convert a SourceFrame (integer) to media seconds using the asset's
 *  source timebase. This is the only local arithmetic the GUI is
 *  allowed to do on SourceFrame integers — it's the canonical unit
 *  conversion from source frames to source seconds (analogous to
 *  inches→cm). It is NOT TimeMap business math. */
export function sourceFrameToMediaSeconds(
  sourceFrame: number, sourceFps: Fps,
): number {
  return sourceFrame * sourceFps.den / sourceFps.num;
}

/** Invalidate the cache (e.g. on project mutation). Safe to call
 *  even if no entries exist. */
export function invalidateTimeMapCache(): void {
  cache.clear();
}

/** Test-only hook: clear the cache between tests. */
export function _resetTimeMapCacheForTests(): void {
  cache.clear();
}