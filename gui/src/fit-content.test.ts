// GUI-03R4.1 P1-5: Tests for editorial content bounds vs. playback
// duration vs. view extent.

import { describe, it, expect } from "vitest";
import {
  editorialEndSec,
  playbackDurationSec,
  fitContentEndSec,
  activeTimeline,
  type ProjectLike,
} from "./fit-content";

function mkProject(opts: {
  v1End?: number;
  visibleStaleClip?: { track_id: string; end: number };
  intentEditorialTrackIds?: string[];
  activeTimelineId?: string;
  v1Hidden?: boolean;
  hiddenTracks?: string[];
}): ProjectLike {
  // The timeline the project owns is always "main" — `activeTimelineId`
  // is the project's *active pointer*, which may not match any timeline
  // (that's the test for "unknown id falls back to first timeline").
  const tracks: { track_id: string; hidden?: boolean; clip_ids?: string[] }[] = [];
  if (opts.v1End !== undefined) {
    tracks.push({
      track_id: "v1", hidden: !!opts.v1Hidden,
      clip_ids: ["v1_clip_a"],
    });
  }
  if (opts.visibleStaleClip) {
    tracks.push({
      track_id: opts.visibleStaleClip.track_id,
      hidden: opts.hiddenTracks?.includes(opts.visibleStaleClip.track_id) ?? false,
      clip_ids: ["stale_clip"],
    });
  }
  const clips: Record<string, { track_id: string; timeline_range: { start: number; end: number } }> = {};
  if (opts.v1End !== undefined) {
    clips["v1_clip_a"] = {
      track_id: "v1",
      timeline_range: { start: 0, end: opts.v1End },
    };
  }
  if (opts.visibleStaleClip) {
    clips["stale_clip"] = {
      track_id: opts.visibleStaleClip.track_id,
      timeline_range: { start: 600, end: opts.visibleStaleClip.end },
    };
  }
  return {
    timelines: [{ timeline_id: "main", tracks }],
    active_timeline_id: opts.activeTimelineId ?? "main",
    clips,
    intent: opts.intentEditorialTrackIds
      ? { editorial_track_ids: opts.intentEditorialTrackIds }
      : undefined,
  };
}

describe("activeTimeline", () => {
  it("returns the timeline whose id matches active_timeline_id", () => {
    const p = mkProject({ v1End: 49.51, activeTimelineId: "main" });
    expect(activeTimeline(p)?.timeline_id).toBe("main");
  });
  it("falls back to first timeline when active id is unknown", () => {
    const p = mkProject({ v1End: 49.51, activeTimelineId: "ghost" });
    expect(activeTimeline(p)?.timeline_id).toBe("main");
  });
  it("returns null when there are no timelines", () => {
    const p: ProjectLike = { clips: {} };
    expect(activeTimeline(p)).toBeNull();
  });
});

describe("editorialEndSec", () => {
  it("returns V1's max end when V1 exists, is visible, and has clips", () => {
    const p = mkProject({ v1End: 49.51 });
    expect(editorialEndSec(p)).toBe(49.51);
  });

  it("IGNORES visible stale/test clips (e.g., 600s debris) on other tracks", () => {
    // Sanlihe-style: V1 ends at 49.51s (editorial); a stale clip
    // at 600-608.5s sits on a visible track. editorialEndSec
    // MUST return 49.51s, not 608.5s.
    const p = mkProject({
      v1End: 49.51,
      visibleStaleClip: { track_id: "v3", end: 608.5 },
    });
    expect(editorialEndSec(p)).toBe(49.51);
  });

  it("returns 0 when V1 is hidden", () => {
    const p = mkProject({ v1End: 49.51, v1Hidden: true });
    // V1 hidden → falls back to longest visible track.
    // No other visible tracks → 0.
    expect(editorialEndSec(p)).toBe(0);
  });

  it("honors intent.editorial_track_ids when set", () => {
    const p = mkProject({
      v1End: 49.51,
      visibleStaleClip: { track_id: "v9", end: 18.5 },
      intentEditorialTrackIds: ["v9"],
    });
    // intent explicitly says editorial = ["v9"]. v9's clip ends
    // at 18.5s. Editorial end = 18.5.
    expect(editorialEndSec(p)).toBe(18.5);
  });

  it("falls through from intent to V1 if intent yields 0", () => {
    const p = mkProject({
      v1End: 49.51,
      intentEditorialTrackIds: ["ghost_track"],  // doesn't exist
    });
    expect(editorialEndSec(p)).toBe(49.51);
  });

  it("falls back to longest visible track when V1 missing", () => {
    const p: ProjectLike = {
      timelines: [{
        timeline_id: "main",
        tracks: [
          { track_id: "v9", clip_ids: ["a"] },
          { track_id: "v3", clip_ids: ["b"] },
        ],
      }],
      active_timeline_id: "main",
      clips: {
        a: { track_id: "v9", timeline_range: { start: 0, end: 18.5 } },
        b: { track_id: "v3", timeline_range: { start: 0, end: 5.0 } },
      },
    };
    // No V1 → longest visible track by clip end wins (v9 at 18.5).
    expect(editorialEndSec(p)).toBe(18.5);
  });
});

describe("playbackDurationSec", () => {
  it("includes visible stale/test clips (the playback engine sees them all)", () => {
    const p = mkProject({
      v1End: 49.51,
      visibleStaleClip: { track_id: "v3", end: 608.5 },
    });
    // Stale clip on a visible track contributes to playback.
    expect(playbackDurationSec(p)).toBe(608.5);
  });

  it("excludes clips on HIDDEN tracks", () => {
    const p = mkProject({
      v1End: 49.51,
      visibleStaleClip: { track_id: "v10", end: 1368.5 },
      hiddenTracks: ["v10"],
    });
    // v10 is hidden → its 1368.5s clip is NOT in playback duration.
    expect(playbackDurationSec(p)).toBe(49.51);
  });
});

describe("fitContentEndSec", () => {
  it("uses editorial end when editorial content exists", () => {
    const p = mkProject({
      v1End: 49.51,
      visibleStaleClip: { track_id: "v3", end: 608.5 },
    });
    // Even though playback is 608.5s, Fit Content zooms to 49.51s
    // (V1's editorial end). The stale 600s debris is invisible.
    expect(fitContentEndSec(p)).toBe(49.51);
  });

  it("falls back to playback duration when no editorial content found", () => {
    // V1 hidden AND no visible editorial → fallback.
    const p = mkProject({
      v1End: 49.51,
      v1Hidden: true,
      visibleStaleClip: { track_id: "v3", end: 608.5 },
    });
    // editorialEndSec returns 0; falls back to playback (608.5).
    expect(fitContentEndSec(p)).toBe(608.5);
  });
});