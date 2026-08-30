// GUI-03E-3 — preview-plan hook tests.
//
// Covers the contract the TimelineSwitcher / PreviewPlayer depend on:
//   1. useTimelines reflects server response (active_timeline_id).
//   2. usePreviewPlan race safety: a stale fetch resolves AFTER the
//      user switched to a different Timeline must NOT clobber the
//      newer plan.
//   3. Per-timeline plan cache: switching Timeline produces a new
//      fetch; identical (rev, timeline_id) does not refetch.

import { describe, expect, it, vi, beforeEach } from "vitest";
import { renderHook, act, waitFor } from "@testing-library/react";

vi.mock("./api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("./api")>();
  return {
    ...actual,
    api: {
      ...actual.api,
      listTimelines: vi.fn(),
      previewPlan: vi.fn(),
    },
  };
});

import { api } from "./api";
import { usePreviewPlan, useTimelines } from "./preview-plan";

beforeEach(() => {
  vi.mocked(api.listTimelines).mockReset();
  vi.mocked(api.previewPlan).mockReset();
});

describe("useTimelines", () => {
  it("returns active + list from server", async () => {
    vi.mocked(api.listTimelines).mockResolvedValueOnce({
      active_timeline_id: "tlB",
      default_timeline_id: "tlA",
      timelines: [
        { timeline_id: "tlA", name: "Full", track_count: 1, clip_count: 3, marker_count: 0, beat_count: 0 },
        { timeline_id: "tlB", name: "Seed", track_count: 1, clip_count: 0, marker_count: 0, beat_count: 0 },
      ],
    });

    const { result } = renderHook(() => useTimelines(1));
    await waitFor(() => {
      expect(result.current.activeTimelineId).toBe("tlB");
    });
    expect(result.current.timelines.map((t) => t.timeline_id))
      .toEqual(["tlA", "tlB"]);
    expect(result.current.loading).toBe(false);
    expect(result.current.error).toBeNull();
  });
});

describe("usePreviewPlan race safety", () => {
  it("discards a stale response when user switches Timeline mid-fetch", async () => {
    // Timeline A's response: intentionally slow.
    let resolveA: (v: any) => void = () => {};
    const planA = {
      project_revision: 1,
      timeline_id: "tlA",
      fps: { num: 30, den: 1 },
      tracks: [],
      subtitle_ranges: [],
    };
    const planB = {
      project_revision: 1,
      timeline_id: "tlB",
      fps: { num: 30, den: 1 },
      tracks: [],
      subtitle_ranges: [],
    };
    vi.mocked(api.previewPlan).mockImplementation(async (opts: any) => {
      if (opts.timeline_id === "tlA") {
        return new Promise<any>((res) => { resolveA = res; });
      }
      return Promise.resolve(planB);
    });

    const { result, rerender } = renderHook(
      ({ rev, tid }) => usePreviewPlan(rev, tid),
      { initialProps: { rev: 1, tid: "tlA" } },
    );
    // Wait for the A fetch to be in-flight.
    await waitFor(() => {
      expect(vi.mocked(api.previewPlan)).toHaveBeenCalledWith(
        expect.objectContaining({ timeline_id: "tlA" }),
      );
    });

    // User switches to tlB BEFORE A resolves.
    rerender({ rev: 1, tid: "tlB" });
    await waitFor(() => {
      expect(result.current.plan?.timeline_id).toBe("tlB");
    });

    // Now A's stale response arrives. The hook MUST ignore it.
    await act(async () => {
      resolveA(planA);
    });
    // Plan must still be B's, not A's.
    expect(result.current.plan?.timeline_id).toBe("tlB");
    // The hook re-wraps the response so identity comparison would
    // be brittle; assert the structural field instead.
    expect(result.current.plan?.timeline_id).not.toBe("tlA");
  });

  it("does not refetch for identical (rev, timeline_id)", async () => {
    vi.mocked(api.previewPlan).mockResolvedValue({
      project_revision: 1,
      timeline_id: "tlA",
      fps: { num: 30, den: 1 },
      tracks: [],
      subtitle_ranges: [],
    } as any);

    const { rerender } = renderHook(
      ({ rev, tid }) => usePreviewPlan(rev, tid),
      { initialProps: { rev: 1, tid: "tlA" } },
    );
    await waitFor(() =>
      expect(vi.mocked(api.previewPlan)).toHaveBeenCalledTimes(1),
    );

    // Same key — no refetch.
    rerender({ rev: 1, tid: "tlA" });
    rerender({ rev: 1, tid: "tlA" });
    expect(vi.mocked(api.previewPlan)).toHaveBeenCalledTimes(1);
  });

  it("refetches when timeline_id changes even if revision is same", async () => {
    vi.mocked(api.previewPlan).mockImplementation(async (opts: any) => ({
      project_revision: 1,
      timeline_id: opts.timeline_id,
      fps: { num: 30, den: 1 },
      tracks: [],
      subtitle_ranges: [],
    }) as any);

    const { rerender } = renderHook(
      ({ rev, tid }) => usePreviewPlan(rev, tid),
      { initialProps: { rev: 1, tid: "tlA" } },
    );
    await waitFor(() =>
      expect(vi.mocked(api.previewPlan)).toHaveBeenCalledTimes(1),
    );
    rerender({ rev: 1, tid: "tlB" });
    await waitFor(() =>
      expect(vi.mocked(api.previewPlan)).toHaveBeenCalledTimes(2),
    );
    expect(vi.mocked(api.previewPlan)).toHaveBeenLastCalledWith(
      expect.objectContaining({ timeline_id: "tlB" }),
    );
  });
});