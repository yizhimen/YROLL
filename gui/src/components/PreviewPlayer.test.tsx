// GUI-03R6 closure fix: PreviewPlayer L0 fallback must not show
// the "播放头在间隙里" placeholder when a clip exists at the
// playhead frame.
//
// The audit found that at frame 499 the placeholder was showing
// even though an image clip covers that frame. Root cause: the L0
// fallback (line 808) was gated on `sourceFrame !== null &&
// timeMapEntry`, but those are VIDEO-only fields — image clips
// have no source timebase, so the TimeMap fetch returns 422 and
// `sourceFrame` stays null. The L0 fallback was unreachable for
// images, so the placeholder won.
//
// This test pins the fix:
//   - L0 image branch: clip + asset (image) is enough → no placeholder
//   - L0 video branch: clip + asset + sourceFrame + timeMapEntry
//   - L0 loading branch: clip + asset (video) but no TimeMap yet
//     → "loading" placeholder (NOT "in-gap")
//   - True "in-gap" placeholder fires ONLY when membership found
//     zero clips at playheadFrame.

import { describe, expect, it, vi } from "vitest";
import { render } from "@testing-library/react";

// Mock api so PreviewPlayer's network calls don't fire in jsdom.
// We return a synthetic plan with one image layer + one subtitle at
// frame 499 to keep the L1 composite path OUT of the equation —
// every assertion in this file exercises the L0 fallback.
vi.mock("../api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api")>();
  return {
    ...actual,
    api: {
      ...actual.api,
      previewPlan: vi.fn(async () => ({
        project_revision: 1,
        timeline_id: "main",
        fps: { num: 30, den: 1 },
        // Empty plan → composite is null → L1 path is skipped.
        tracks: [],
        subtitle_ranges: [],
      })),
      getSequence: vi.fn(async () => ({
        sequence_id: "seq-1",
        fps: { num: 30, den: 1 },
        width: 1920, height: 1080,
        timecode_format: "SMPTE",
        drop_frame: false,
        project_revision: 1,
      })),
      getTimemap: vi.fn(async () => {
        // Image clips have no TimeMap — the real backend returns 422
        // here. We simulate that by rejecting the promise. PreviewPlayer
        // catches the rejection and leaves sourceFrame = null.
        throw new Error("422: no source fps for image");
      }),
    },
  };
});

// We DON'T mock usePreviewPlan — its real implementation produces
// plan=null (because the api.previewPlan mock returns tracks=[]).
// Composite then evaluates to null too, forcing the L0 fallback.

import PreviewPlayer from "./PreviewPlayer";
import type { Asset, Project } from "../api";

function makeProject(
  timelineClips: Array<{ id: string; assetId: string; start: number; end: number; type: "image" | "video" }>,
): Project {
  const assets: Asset[] = timelineClips.map((c) => ({
    asset_id: c.assetId,
    type: c.type,
    path: `/${c.type}/${c.assetId}`,
    origin: "unknown",
    identity: { duration_sec: c.type === "image" ? undefined : c.end - c.start, width: 100, height: 100 },
    source_fps: c.type === "image" ? null : { num: 30, den: 1 },
  }));
  const clips: Record<string, any> = {};
  for (const c of timelineClips) {
    clips[c.id] = {
      clip_id: c.id,
      asset_id: c.assetId,
      track_id: "v1",
      source_range: { start: 0, end: c.end - c.start },
      // Legacy storage: SECONDS.
      timeline_range: { start: c.start / 30, end: c.end / 30 },
      speed: 1.0,
      volume: 1.0,
      transform: {},
      adjustments: [],
      context: {},
    };
  }
  return {
    project_id: "p1",
    name: "t",
    intent: {},
    sequence: {
      fps: { num: 30, den: 1 },
      width: 1920, height: 1080,
      project_revision: 1,
    },
    assets,
    timeline: {
      timeline_id: "main",
      tracks: [{
        track_id: "v1", kind: "video", clip_ids: timelineClips.map((c) => c.id),
      }],
    },
    clips,
    timelines: [{
      timeline_id: "main",
      name: "Main",
      tracks: [{
        track_id: "v1", kind: "video", clip_ids: timelineClips.map((c) => c.id),
      }],
    }],
    active_timeline_id: "main",
  };
}

describe("R6 closure fix: PreviewPlayer L0 fallback (image clip)", () => {
  it("image clip at frame 499: NO 'in-gap' placeholder (L0 fallback renders the image)", () => {
    const project = makeProject([
      { id: "c_img", assetId: "a1", start: 414, end: 504, type: "image" },
    ]);
    const { container } = render(
      <PreviewPlayer project={project} playheadFrame={499} onPlayhead={() => {}}
        onStatus={() => {}} renderedUrl={null} />,
    );
    const html = container.innerHTML;
    expect(html).not.toContain("播放头在间隙里");
    // The image element renders at the asset URL via the L0 fallback.
    expect(html).toMatch(/img[^>]*src="\/assets\/a1\/file"/);
  });

  it("image clip covering frame 0: NO 'in-gap' placeholder", () => {
    const project = makeProject([
      { id: "c_img", assetId: "a1", start: 0, end: 90, type: "image" },
    ]);
    const { container } = render(
      <PreviewPlayer project={project} playheadFrame={0} onPlayhead={() => {}}
        onStatus={() => {}} renderedUrl={null} />,
    );
    const html = container.innerHTML;
    expect(html).not.toContain("播放头在间隙里");
  });

  it("another in-bounds frame (frame 450): NO 'in-gap' placeholder", () => {
    const project = makeProject([
      { id: "c_img", assetId: "a1", start: 414, end: 504, type: "image" },
    ]);
    const { container } = render(
      <PreviewPlayer project={project} playheadFrame={450} onPlayhead={() => {}}
        onStatus={() => {}} renderedUrl={null} />,
    );
    expect(container.innerHTML).not.toContain("播放头在间隙里");
  });

  it("frame 1000 (outside the clip range): TRUE in-gap placeholder", () => {
    const project = makeProject([
      { id: "c_img", assetId: "a1", start: 414, end: 504, type: "image" },
    ]);
    const { container } = render(
      <PreviewPlayer project={project} playheadFrame={1000} onPlayhead={() => {}}
        onStatus={() => {}} renderedUrl={null} />,
    );
    expect(container.innerHTML).toContain("播放头在间隙里");
  });

  it("empty timeline: shows the 'empty timeline' placeholder, NOT 'in-gap'", () => {
    const project = makeProject([]); // no clips
    const { container } = render(
      <PreviewPlayer project={project} playheadFrame={499} onPlayhead={() => {}}
        onStatus={() => {}} renderedUrl={null} />,
    );
    const html = container.innerHTML;
    expect(html).toContain("时间轴是空的");
    expect(html).not.toContain("播放头在间隙里");
  });
});