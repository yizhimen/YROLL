// GUI-03R4.1 P1-5: Editorial content bounds vs. playback duration
// vs. view extent — Fit Content must use editorial, not stale/test.
//
// The Project model mixes three distinct concepts that all reduce
// to "how wide is the timeline":
//
//   1. PLAYBACK DURATION — every clip on every visible track, plus
//      gaps, plus any stale/test debris that landed on visible
//      tracks. Used by the transport (e.g., "duration: 41:23").
//      Computed as `max(clip.timeline_range.end)` over ALL clips
//      whose track is not hidden.
//
//   2. EDITORIAL CONTENT BOUNDS — the canonical editorial portion
//      of the timeline. This is what Fit Content zooms to. Stale
//      test debris (e.g., the 600-608s clips on Sanlihe) and
//      outliers (e.g., a stray 1368s tail) MUST NOT be counted.
//
//      Detection strategy:
//        a. If the project carries `intent.editorial_track_ids`
//           (an explicit list of track ids), use clips on those
//           tracks. The clean fixture sets this to ["v1"].
//        b. Otherwise fall back to: V1 if it exists and is
//           visible and has clips. V1 is the primary story track
//           in every fixture we've shipped.
//        c. As a last resort: the longest visible track by clip
//           total duration (heuristic).
//
//   3. VIEW EXTENT — what the user is currently looking at. Equals
//      `clientWidth / pxPerSec` of the .timeline-content area.
//      Mutated by zoom + scroll. This helper does NOT touch it.
//
// The single source of truth: `editorialEndSec(clipMap, project,
// activeTimelineId)`. Returns 0 if no editorial content was
// found, in which case the caller can fall back to playback
// duration.

export interface ClipLike {
  track_id: string;
  timeline_range: { start: number; end: number };
}

export interface TrackLike {
  track_id: string;
  hidden?: boolean;
  clip_ids?: string[];
}

export interface TimelineLike {
  timeline_id: string;
  tracks: TrackLike[];
}

export interface ProjectLike {
  timelines?: TimelineLike[];
  active_timeline_id?: string;
  clips: Record<string, ClipLike>;
  intent?: {
    editorial_track_ids?: string[];
  };
}

/** Find the active Timeline. The Timeline with the active id wins;
 *  if it's missing, the first Timeline is used. */
export function activeTimeline(project: ProjectLike): TimelineLike | null {
  const tll = project.timelines ?? [];
  if (tll.length === 0) return null;
  const active = project.active_timeline_id;
  if (active) {
    const hit = tll.find((t) => t.timeline_id === active);
    if (hit) return hit;
  }
  return tll[0];
}

/** Compute the editorial content end (seconds). Returns 0 when
 *  no editorial content is found — caller should fall back to
 *  playback duration in that case. */
export function editorialEndSec(project: ProjectLike): number {
  const tl = activeTimeline(project);
  if (!tl) return 0;
  const clipMap = project.clips;

  // (a) Explicit intent.editorial_track_ids wins.
  const declared = project.intent?.editorial_track_ids;
  if (Array.isArray(declared) && declared.length > 0) {
    let end = 0;
    for (const cid of Object.keys(clipMap)) {
      const c = clipMap[cid];
      if (!c) continue;
      if (declared.includes(c.track_id) && c.timeline_range.end > end) {
        end = c.timeline_range.end;
      }
    }
    if (end > 0) return end;
  }

  // (b) V1 if it exists and is visible and has clips.
  const v1 = tl.tracks.find(
    (t) => t.track_id.toLowerCase() === "v1" && !t.hidden);
  if (v1) {
    let end = 0;
    for (const cid of v1.clip_ids ?? []) {
      const c = clipMap[cid];
      if (c && c.timeline_range.end > end) end = c.timeline_range.end;
    }
    if (end > 0) return end;
  }

  // (c) Longest visible track by clip total duration.
  let bestEnd = 0;
  for (const t of tl.tracks) {
    if (t.hidden) continue;
    let trackEnd = 0;
    for (const cid of t.clip_ids ?? []) {
      const c = clipMap[cid];
      if (c && c.timeline_range.end > trackEnd) trackEnd = c.timeline_range.end;
    }
    if (trackEnd > bestEnd) bestEnd = trackEnd;
  }
  return bestEnd;
}

/** Compute playback duration: max end across all clips on any
 *  NON-hidden track. Stale/test debris on visible tracks DOES
 *  count here (it's real content, just not editorial). */
export function playbackDurationSec(project: ProjectLike): number {
  const tl = activeTimeline(project);
  if (!tl) return 0;
  const visibleTrackIds = new Set(
    tl.tracks.filter((t) => !t.hidden).map((t) => t.track_id));
  let end = 0;
  for (const cid of Object.keys(project.clips)) {
    const c = project.clips[cid];
    if (!c) continue;
    if (visibleTrackIds.has(c.track_id) &&
        c.timeline_range.end > end) {
      end = c.timeline_range.end;
    }
  }
  return end;
}

/** The single helper that the GUI calls for Fit Content.
 *  Returns editorial end with a fallback to playback duration. */
export function fitContentEndSec(project: ProjectLike): number {
  const ed = editorialEndSec(project);
  if (ed > 0) return ed;
  return playbackDurationSec(project);
}