// R5 audit (2026-09-01): Hidden-Track UI regression.
//
// Background: the R5 acceptance spec (Decision 1) says a track hidden
// via the visibility button MUST stay visible in the Timeline — only
// its Preview/Composite participation is suppressed. The pre-audit
// implementation used `display: track.hidden ? "none" : "flex"` on
// both .track-label-row (header) and .track-row (content), which
// collapsed the entire row + header from the DOM.
//
// These tests pin the corrected semantics:
//   1. The .track-label-row for a hidden track is rendered.
//   2. The .track-row for a hidden track is rendered.
//   3. The hidden row's clip is rendered (NOT just the header).
//   4. Both rows have the .track-hidden class (the CSS visual cue).
//   5. Neither row has computed display: none.
//   6. The header's visibility button still reads "显示轨道（点击恢复）"
//      (so the user can toggle back).

import { describe, expect, it, vi, afterEach } from "vitest";
import { cleanup, render } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";

import Timeline from "./Timeline";
import type { Project, Track, Clip } from "../api";

// Mock ../sequence so the component does not try to fetch /sequence.
vi.mock("../sequence", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../sequence")>();
  return {
    ...actual,
    useProjectSequence: () => ({
      sequenceId: "seq",
      fps: { num: 30, den: 1 },
      width: 1920,
      height: 1080,
      timecodeFormat: "SMPTE" as const,
      dropFrame: false,
      projectRevision: 0,
    }),
  };
});

function makeProject(tracks: Track[], clips: Record<string, Clip>): Project {
  return {
    project_id: "p1",
    name: "audit",
    intent: {},
    assets: [],
    timeline: { timeline_id: "main", tracks },
    clips,
    sequence: { fps: { num: 30, den: 1 }, project_revision: 0 },
    timelines: [{ timeline_id: "main", name: "main", tracks }],
    active_timeline_id: "main",
    default_timeline_id: "main",
  } as Project;
}

afterEach(() => cleanup());

describe("R5 audit: hidden Track UI semantics", () => {
  it("renders the header row for a hidden track (no display:none)", () => {
    const tracks: Track[] = [
      { track_id: "v1", kind: "video", clip_ids: ["c1"] },
      { track_id: "v2", kind: "video", clip_ids: ["c2"], hidden: true },
    ];
    const clips: Record<string, Clip> = {
      c1: {
        clip_id: "c1", asset_id: "a1", track_id: "v1",
        source_range: { start: 0, end: 5 },
        timeline_range: { start: 0, end: 5 },
        speed: 1, volume: 1, transform: {}, adjustments: [], context: {},
      },
      c2: {
        clip_id: "c2", asset_id: "a2", track_id: "v2",
        source_range: { start: 0, end: 5 },
        timeline_range: { start: 10, end: 15 },
        speed: 1, volume: 1, transform: {}, adjustments: [], context: {},
      },
    };
    const { container } = render(
      <Timeline
        project={makeProject(tracks, clips)}
        selectedIds={new Set()}
        playheadFrame={0}
        pxPerSec={30}
        selRange={null}
        onSeek={() => {}}
        onSelect={() => {}}
        onDragMove={() => {}}
        onMoveCommit={() => {}}
        onZoomPx={() => {}}
        onRangeSelect={() => {}}
        onTrimCommit={() => {}}
        onTrackHide={() => {}}
      />,
    );
    const headerV2 = container.querySelector(
      '.track-label-row[data-track-id="v2"]',
    ) as HTMLElement | null;
    expect(headerV2).not.toBeNull();
    expect(headerV2).toHaveClass("track-hidden");
    // display:none was the bug. jsdom computed style may report "block"
    // for raw elements; assert the inline-style attribute is absent.
    expect(headerV2?.getAttribute("style") ?? "").not.toMatch(/display\s*:\s*none/);
  });

  it("renders the content row for a hidden track (no display:none)", () => {
    const tracks: Track[] = [
      { track_id: "v1", kind: "video", clip_ids: ["c1"] },
      { track_id: "v2", kind: "video", clip_ids: ["c2"], hidden: true },
    ];
    const clips: Record<string, Clip> = {
      c1: {
        clip_id: "c1", asset_id: "a1", track_id: "v1",
        source_range: { start: 0, end: 5 },
        timeline_range: { start: 0, end: 5 },
        speed: 1, volume: 1, transform: {}, adjustments: [], context: {},
      },
      c2: {
        clip_id: "c2", asset_id: "a2", track_id: "v2",
        source_range: { start: 0, end: 5 },
        timeline_range: { start: 10, end: 15 },
        speed: 1, volume: 1, transform: {}, adjustments: [], context: {},
      },
    };
    const { container } = render(
      <Timeline
        project={makeProject(tracks, clips)}
        selectedIds={new Set()}
        playheadFrame={0}
        pxPerSec={30}
        selRange={null}
        onSeek={() => {}}
        onSelect={() => {}}
        onDragMove={() => {}}
        onMoveCommit={() => {}}
        onZoomPx={() => {}}
        onRangeSelect={() => {}}
        onTrimCommit={() => {}}
        onTrackHide={() => {}}
      />,
    );
    const rowV2 = container.querySelector(
      '.track-row[data-track-id="v2"]',
    ) as HTMLElement | null;
    expect(rowV2).not.toBeNull();
    expect(rowV2).toHaveClass("track-hidden");
    expect(rowV2?.getAttribute("style") ?? "").not.toMatch(/display\s*:\s*none/);
  });

  it("renders the clip block inside a hidden track's row", () => {
    const tracks: Track[] = [
      { track_id: "v1", kind: "video", clip_ids: ["c1"] },
      { track_id: "v2", kind: "video", clip_ids: ["c2"], hidden: true },
    ];
    const clips: Record<string, Clip> = {
      c1: {
        clip_id: "c1", asset_id: "a1", track_id: "v1",
        source_range: { start: 0, end: 5 },
        timeline_range: { start: 0, end: 5 },
        speed: 1, volume: 1, transform: {}, adjustments: [], context: {},
      },
      c2: {
        clip_id: "c2", asset_id: "a2", track_id: "v2",
        source_range: { start: 0, end: 5 },
        timeline_range: { start: 10, end: 15 },
        speed: 1, volume: 1, transform: {}, adjustments: [], context: {},
      },
    };
    const { container } = render(
      <Timeline
        project={makeProject(tracks, clips)}
        selectedIds={new Set()}
        playheadFrame={0}
        pxPerSec={30}
        selRange={null}
        onSeek={() => {}}
        onSelect={() => {}}
        onDragMove={() => {}}
        onMoveCommit={() => {}}
        onZoomPx={() => {}}
        onRangeSelect={() => {}}
        onTrimCommit={() => {}}
        onTrackHide={() => {}}
      />,
    );
    const clipInHiddenRow = container.querySelector(
      '.track-row[data-track-id="v2"] .clip[data-clip-id="c2"]',
    );
    expect(clipInHiddenRow).not.toBeNull();
  });

  it("hidden track's visibility button reads the restore tooltip", () => {
    const tracks: Track[] = [
      { track_id: "v1", kind: "video", clip_ids: ["c1"] },
      { track_id: "v2", kind: "video", clip_ids: ["c2"], hidden: true },
    ];
    const clips: Record<string, Clip> = {
      c1: {
        clip_id: "c1", asset_id: "a1", track_id: "v1",
        source_range: { start: 0, end: 5 },
        timeline_range: { start: 0, end: 5 },
        speed: 1, volume: 1, transform: {}, adjustments: [], context: {},
      },
      c2: {
        clip_id: "c2", asset_id: "a2", track_id: "v2",
        source_range: { start: 0, end: 5 },
        timeline_range: { start: 10, end: 15 },
        speed: 1, volume: 1, transform: {}, adjustments: [], context: {},
      },
    };
    const { container } = render(
      <Timeline
        project={makeProject(tracks, clips)}
        selectedIds={new Set()}
        playheadFrame={0}
        pxPerSec={30}
        selRange={null}
        onSeek={() => {}}
        onSelect={() => {}}
        onDragMove={() => {}}
        onMoveCommit={() => {}}
        onZoomPx={() => {}}
        onRangeSelect={() => {}}
        onTrimCommit={() => {}}
        onTrackHide={() => {}}
      />,
    );
    const btn = container.querySelector(
      '.track-label-row[data-track-id="v2"] button[title*="显示轨道"]',
    );
    expect(btn).not.toBeNull();
  });

  it("non-hidden track does NOT carry the track-hidden class", () => {
    const tracks: Track[] = [
      { track_id: "v1", kind: "video", clip_ids: ["c1"] },
      { track_id: "v2", kind: "video", clip_ids: ["c2"], hidden: true },
    ];
    const clips: Record<string, Clip> = {
      c1: {
        clip_id: "c1", asset_id: "a1", track_id: "v1",
        source_range: { start: 0, end: 5 },
        timeline_range: { start: 0, end: 5 },
        speed: 1, volume: 1, transform: {}, adjustments: [], context: {},
      },
      c2: {
        clip_id: "c2", asset_id: "a2", track_id: "v2",
        source_range: { start: 0, end: 5 },
        timeline_range: { start: 10, end: 15 },
        speed: 1, volume: 1, transform: {}, adjustments: [], context: {},
      },
    };
    const { container } = render(
      <Timeline
        project={makeProject(tracks, clips)}
        selectedIds={new Set()}
        playheadFrame={0}
        pxPerSec={30}
        selRange={null}
        onSeek={() => {}}
        onSelect={() => {}}
        onDragMove={() => {}}
        onMoveCommit={() => {}}
        onZoomPx={() => {}}
        onRangeSelect={() => {}}
        onTrimCommit={() => {}}
        onTrackHide={() => {}}
      />,
    );
    const v1Header = container.querySelector(
      '.track-label-row[data-track-id="v1"]',
    );
    expect(v1Header).not.toBeNull();
    expect(v1Header).not.toHaveClass("track-hidden");
    const v1Row = container.querySelector('.track-row[data-track-id="v1"]');
    expect(v1Row).not.toHaveClass("track-hidden");
  });
});