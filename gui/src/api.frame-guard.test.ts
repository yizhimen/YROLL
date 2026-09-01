// R6.1-A: static architectural guard for the frame-native mutation
// wrappers. The runtime guard at `api.ts:assertIntFrame` catches a
// regression in the live session (the offending call throws before
// reaching the network), but we also pin the contract here:
//
//   1. Every frame-native wrapper (move / trim / split / addClip /
//      addImageClip / trimImageClip) REJECTS non-integer arguments.
//   2. `null` and `undefined` are allowed (the server treats them
//      as "no change" for optional edge arguments).
//   3. Integer arguments (including 0, negative for some, very large)
//      are accepted (the call still fails at the network / server
//      gate for unrelated reasons, but the wrapper does NOT throw).
//
// The test mocks `fetch` so the wrapper never reaches the network
// when the integer path is exercised. When the integer path throws,
// we never get to `fetch` (the wrapper throws synchronously).

import { describe, it, expect, beforeEach, vi } from "vitest";
import { api } from "./api";

describe("R6.1-A frame-native mutation wrappers reject non-integer operands", () => {
  beforeEach(() => {
    // Mock fetch so successful integer calls don't reach the network.
    // (The lease + baseRevision gate will reject them anyway, but the
    // important assertion here is "no synchronous throw".)
    vi.spyOn(globalThis, "fetch").mockImplementation(async () =>
      new Response(JSON.stringify({ ok: true, sessionId: "test" }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
  });

  it("api.move rejects 1080.2549999999999 (the user's reported value)", () => {
    expect(() => api.move("c1", 1080.2549999999999, "test")).toThrow(
      /R6\.1-A frame-native contract violation.*move\.newTimelineStartFrame/,
    );
  });
  it("api.move rejects 0.5 (the trim-button bug class)", () => {
    expect(() => api.move("c1", 0.5, "test")).toThrow(/R6\.1-A/);
  });
  it("api.move accepts an integer", async () => {
    // Will fail at the gate, but must NOT throw the contract violation.
    await expect(api.move("c1", 1080, "test")).rejects.not.toThrow(/R6\.1-A/);
  });

  it("api.trim rejects seconds in newSourceStartFrame (the actual bug)", () => {
    expect(() => api.trim("c1", 0.5, undefined, "test")).toThrow(
      /R6\.1-A frame-native contract violation.*trim\.newSourceStartFrame/,
    );
  });
  it("api.trim rejects seconds in newSourceEndFrame", () => {
    expect(() => api.trim("c1", undefined, 14.5, "test")).toThrow(/R6\.1-A/);
  });
  it("api.trim accepts integer frames in both edges", async () => {
    await expect(api.trim("c1", 0, 30, "test")).rejects.not.toThrow(/R6\.1-A/);
  });
  it("api.trim accepts null for either edge (no-change semantic)", async () => {
    await expect(api.trim("c1", null, null, "test")).rejects.not.toThrow(/R6\.1-A/);
    await expect(api.trim("c1", undefined, undefined, "test")).rejects.not.toThrow(/R6\.1-A/);
  });

  it("api.split rejects seconds (the App.tsx:1008 bug class)", () => {
    // Pre-R6.1 code passed `atSource` (a float seconds value) to
    // api.split (a frame-native wrapper). The guard catches it.
    expect(() => api.split("c1", 14.5, "test")).toThrow(
      /R6\.1-A frame-native contract violation.*split\.atTimelineFrame/,
    );
  });
  it("api.split accepts an integer frame", async () => {
    await expect(api.split("c1", 450, "test")).rejects.not.toThrow(/R6\.1-A/);
  });

  it("api.addClip rejects non-integer source range (paste bug class)", () => {
    expect(() => api.addClip("a1", 0.5, 30, 100, "v1", "test")).toThrow(
      /R6\.1-A frame-native contract violation.*addClip\.sourceStartFrame/,
    );
    expect(() => api.addClip("a1", 0, 30.1, 100, "v1", "test")).toThrow(/R6\.1-A/);
    expect(() => api.addClip("a1", 0, 30, 100.5, "v1", "test")).toThrow(/R6\.1-A/);
  });
  it("api.addClip accepts integer frames", async () => {
    await expect(api.addClip("a1", 0, 30, 100, "v1", "test")).rejects.not.toThrow(/R6\.1-A/);
  });

  it("api.addImageClip rejects non-integer timeline frames", () => {
    expect(() => api.addImageClip("a1", 0.5, 150, "v1", "test")).toThrow(/R6\.1-A/);
    expect(() => api.addImageClip("a1", 0, 150.1, "v1", "test")).toThrow(/R6\.1-A/);
  });
  it("api.addImageClip accepts integer frames", async () => {
    await expect(api.addImageClip("a1", 0, 150, "v1", "test")).rejects.not.toThrow(/R6\.1-A/);
  });

  it("api.trimImageClip accepts null edges (the canonical 'no change' semantic)", async () => {
    await expect(api.trimImageClip("c1", null, null, "test")).rejects.not.toThrow(/R6\.1-A/);
  });
  it("api.trimImageClip rejects non-integer timeline frames", () => {
    expect(() => api.trimImageClip("c1", 0.5, null, "test")).toThrow(/R6\.1-A/);
  });
});

describe("R6.1-A seconds-native wrappers do NOT require integers", () => {
  // `addSubtitle` and `volumeRange` are seconds-native by design.
  // Pinning the negative case here means a future "make everything
  // integer" refactor will not silently break subtitle insertion.
  beforeEach(() => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async () =>
      new Response(JSON.stringify({ ok: true }), { status: 200 }));
  });

  it("api.addSubtitle accepts seconds (its contract)", async () => {
    await expect(api.addSubtitle("hi", 0.5, 2.5, "test")).rejects.not.toThrow(/R6\.1-A/);
  });
});
