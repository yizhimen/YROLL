// GUI-02.6: Keymap Drift + Missing-Keymap vitest tests.
//
// These pin the contract: useCoreKeymap() exposes Core's `delta_frames`
// directly, with NO transformation. If Core changes the step size for
// the "J" binding from 1 to 5 (or any other value), the GUI sees the
// new value WITHOUT any code change. And if Core removes a binding,
// useCoreKeymap() returns an empty list — the GUI must treat this as
// "no binding" (no-op), not fall back to a magic step size.

import { describe, expect, it, vi, beforeEach } from "vitest";

// Mock the api module BEFORE importing keymap so the mock takes
// effect at module load.
vi.mock("./api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("./api")>();
  return {
    ...actual,
    api: {
      ...actual.api,
      getKeymap: vi.fn(),
    },
  };
});

import { api } from "./api";
import { useCoreKeymap, type KeymapAction } from "./keymap";
import { act, renderHook } from "@testing-library/react";

const FAULT_KEYMAP = {
  bindings: [
    { key: "J",  description: "step back 1 frame",      mutation_op: "_nudge_playhead", params: { delta_frames: -1 } },
    { key: "L",  description: "step forward 1 frame",   mutation_op: "_nudge_playhead", params: { delta_frames:  1 } },
    { key: "Space", description: "toggle play",          mutation_op: "_toggle_play",     params: {} },
  ],
};

beforeEach(() => {
  vi.mocked(api.getKeymap).mockReset();
});

describe("Keymap Drift: GUI follows Core without code changes", () => {
  it("Core changes J's delta_frames from -1 to -5 → GUI sees -5", async () => {
    vi.mocked(api.getKeymap).mockResolvedValueOnce({
      bindings: [
        // Simulate Core deciding J should step -5 instead of -1.
        { key: "J", description: "step back 5 frames", mutation_op: "_nudge_playhead", params: { delta_frames: -5 } },
      ],
    });
    const { result } = renderHook(() => useCoreKeymap());
    // Wait for the useEffect fetch to resolve.
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(result.current).toHaveLength(1);
    const j = result.current.find((a) => a.key === "J");
    expect(j).toBeTruthy();
    expect(j?.deltaFrames).toBe(-5);  // <-- Core's value, no GUI transformation
    expect(j?.name).toBe("_nudge_playhead");
  });

  it("Core changes Space's params → GUI sees the new params", async () => {
    vi.mocked(api.getKeymap).mockResolvedValueOnce({
      bindings: [
        // Simulate Core adding a new param (e.g. "rate") to a binding.
        { key: "Space", description: "toggle play", mutation_op: "_toggle_play", params: { rate: 1.5 } },
      ],
    });
    const { result } = renderHook(() => useCoreKeymap());
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });
    const space = result.current.find((a) => a.key === "Space");
    expect(space?.params).toEqual({ rate: 1.5 });
  });

  it("multiple bindings of the same name expose distinct delta_frames", async () => {
    vi.mocked(api.getKeymap).mockResolvedValueOnce({
      bindings: [
        { key: "J",      description: "back 1",  mutation_op: "_nudge_playhead", params: { delta_frames: -1 } },
        { key: "Shift+J", description: "back 10", mutation_op: "_nudge_playhead", params: { delta_frames: -10 } },
        { key: "L",      description: "fwd 1",   mutation_op: "_nudge_playhead", params: { delta_frames:  1 } },
        { key: "Shift+L", description: "fwd 10",  mutation_op: "_nudge_playhead", params: { delta_frames:  10 } },
      ],
    });
    const { result } = renderHook(() => useCoreKeymap());
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });
    const lookup = (k: string) => result.current.find((a) => a.key === k);
    expect(lookup("J")?.deltaFrames).toBe(-1);
    expect(lookup("Shift+J")?.deltaFrames).toBe(-10);
    expect(lookup("L")?.deltaFrames).toBe(1);
    expect(lookup("Shift+L")?.deltaFrames).toBe(10);
  });
});

describe("Missing-Keymap: absent binding produces no actions", () => {
  it("empty keymap → useCoreKeymap returns []", async () => {
    vi.mocked(api.getKeymap).mockResolvedValueOnce({ bindings: [] });
    const { result } = renderHook(() => useCoreKeymap());
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(result.current).toEqual([]);
  });

  it("keymap with bindings that lack delta_frames → deltaFrames=0 (not fallback to 1)", async () => {
    vi.mocked(api.getKeymap).mockResolvedValueOnce({
      bindings: [
        // No delta_frames param — typical for non-nudge bindings.
        { key: "Space", description: "toggle play", mutation_op: "_toggle_play", params: {} },
      ],
    });
    const { result } = renderHook(() => useCoreKeymap());
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });
    const space = result.current.find((a) => a.key === "Space");
    expect(space?.deltaFrames).toBe(0);  // <-- not ?? 1 fallback
  });

  it("keymap fetch fails → actions stays [] (no fake defaults)", async () => {
    vi.mocked(api.getKeymap).mockRejectedValueOnce(new Error("network"));
    const { result } = renderHook(() => useCoreKeymap());
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(result.current).toEqual([]);
  });

  it("bindings array is missing → actions stays []", async () => {
    vi.mocked(api.getKeymap).mockResolvedValueOnce(
      { bindings: [] as unknown[] as Array<{ key: string; description: string; mutation_op: string; params: Record<string, unknown> }> },
    );
    const { result } = renderHook(() => useCoreKeymap());
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(result.current).toEqual([]);
  });
});

describe("KeymapAction.params is the raw Core params (no transformation)", () => {
  it("preserves unknown param keys (forward-compat)", async () => {
    vi.mocked(api.getKeymap).mockResolvedValueOnce({
      bindings: [
        { key: "X", description: "future key", mutation_op: "_future_op",
          params: { foo: "bar", baz: 42, nested: { a: 1 } } },
      ],
    });
    const { result } = renderHook(() => useCoreKeymap());
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });
    const x = result.current.find((a) => a.key === "X");
    expect(x?.params).toEqual({ foo: "bar", baz: 42, nested: { a: 1 } });
  });
});

// ---------------------------------------------------------------------------
// GUI-03R3-W-A: pinned contract for Delete / Shift+Delete / Space / K / ↑↓.
// These tests pin the on-the-wire keymap shape so the App.tsx dispatch
// (in App.keyboard.test.tsx) can rely on these names + params.
// ---------------------------------------------------------------------------

describe("W-A.2 keymap contract for Delete / Shift+Delete / Space / ↑↓", () => {
  const keymap = () => ({
    bindings: [
      { key: "Delete",       description: "remove selected clip",
        mutation_op: "delete_selection",           params: { ripple: false } },
      { key: "Shift+Delete", description: "ripple-remove selected clip",
        mutation_op: "delete_selection",           params: { ripple: true } },
      { key: "Space",        description: "toggle play/pause",
        mutation_op: "_toggle_play",               params: {} },
      { key: "K",            description: "toggle play/pause",
        mutation_op: "_toggle_play",               params: {} },
      { key: "ArrowUp",      description: "jump to previous boundary",
        mutation_op: "_nudge_playhead_boundary",   params: { direction: -1 } },
      { key: "ArrowDown",    description: "jump to next boundary",
        mutation_op: "_nudge_playhead_boundary",   params: { direction: 1 } },
    ],
  });

  it("Delete → mutation_op=delete_selection, params.ripple=false", async () => {
    vi.mocked(api.getKeymap).mockResolvedValueOnce(keymap());
    const { result } = renderHook(() => useCoreKeymap());
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });
    const del = result.current.find((a) => a.key === "Delete");
    expect(del).toBeTruthy();
    expect(del?.name).toBe("delete_selection");
    expect((del?.params as { ripple?: boolean })?.ripple).toBe(false);
  });

  it("Shift+Delete → params.ripple=true", async () => {
    vi.mocked(api.getKeymap).mockResolvedValueOnce(keymap());
    const { result } = renderHook(() => useCoreKeymap());
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });
    const del = result.current.find((a) => a.key === "Shift+Delete");
    expect(del).toBeTruthy();
    expect(del?.name).toBe("delete_selection");
    expect((del?.params as { ripple?: boolean })?.ripple).toBe(true);
  });

  it("Space + K → _toggle_play local action (no fake Core mutation)", async () => {
    vi.mocked(api.getKeymap).mockResolvedValueOnce(keymap());
    const { result } = renderHook(() => useCoreKeymap());
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });
    const space = result.current.find((a) => a.key === "Space");
    const k = result.current.find((a) => a.key === "K");
    expect(space?.name).toBe("_toggle_play");
    expect(k?.name).toBe("_toggle_play");
    // Local action: deltaFrames=0 (no seek). GUI must NOT interpret
    // this as a Core mutation — it's a transport toggle.
    expect(space?.deltaFrames).toBe(0);
    expect(k?.deltaFrames).toBe(0);
  });

  it("ArrowUp/Down → _nudge_playhead_boundary with direction ±1", async () => {
    vi.mocked(api.getKeymap).mockResolvedValueOnce(keymap());
    const { result } = renderHook(() => useCoreKeymap());
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });
    const up = result.current.find((a) => a.key === "ArrowUp");
    const down = result.current.find((a) => a.key === "ArrowDown");
    expect(up?.name).toBe("_nudge_playhead_boundary");
    expect(down?.name).toBe("_nudge_playhead_boundary");
    expect((up?.params as { direction?: number })?.direction).toBe(-1);
    expect((down?.params as { direction?: number })?.direction).toBe(1);
  });
});