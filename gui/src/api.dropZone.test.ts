// GUI-03R3-W-C: pin the api.ts wiring for the new drop-zone path.
//
// This test stubs `fetch` and verifies that `api.ensureTrackForDrop`
// sends the right method, path, and body. The actual Core behavior
// is pinned by `tests/test_ensure_track_for_drop.py` (server side).
// Here we only verify the GUI client surface.

import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { sessionStore } from "./session";

// GUI-03R5-B1: every API test must put the SessionStore into EDIT
// first so api.gated()'s new ensureReady() gate doesn't reject the
// call with "session not in EDIT state".
function enterEditMode() {
  sessionStore._reset();
  sessionStore.set({
    sessionId: "test-session",
    loaded: true,
    mine: true,
    alive: true,
    owner: "human",
    mode: "edit",
  });
}

beforeEach(() => {
  vi.unstubAllGlobals();
});

afterEach(() => {
  vi.unstubAllGlobals();
  sessionStore._reset();
});

async function importApiWithStub(stub: ReturnType<typeof vi.fn>) {
  vi.stubGlobal("fetch", stub);
  // Import api AFTER the stub is in place.
  const mod = await import("./api");
  return mod.api;
}

describe("api.ensureTrackForDrop — W-C wiring", () => {
  // Capture BOTH the mutation call AND the subsequent /ui/status
  // syncRevision() call that gated() makes. The mutation call is
  // the one we want to assert on; /ui/status is a side effect.
  function makeStub(trackResponse: object): {
    stub: typeof fetch,
    calls: Array<{ url: string; init: RequestInit | undefined }>,
  } {
    const calls: Array<{ url: string; init: RequestInit | undefined }> = [];
    const stub = vi.fn(async (url: any, init?: RequestInit) => {
      const urlStr = String(url);
      calls.push({ url: urlStr, init });
      // /ui/status (called by syncRevision) returns a benign shape.
      if (urlStr.includes("/ui/status")) {
        return {
          ok: true, status: 200,
          text: async () => JSON.stringify({ base_revision: 0 }),
          json: async () => ({ base_revision: 0 }),
        } as unknown as Response;
      }
      return {
        ok: true, status: 200,
        text: async () => JSON.stringify(trackResponse),
        json: async () => trackResponse,
      } as unknown as Response;
    }) as unknown as typeof fetch;
    return { stub, calls };
  }

  it("POSTs to /tracks/ensure_for_drop with asset_type and insert_after_track_id", async () => {
    const { stub, calls } = makeStub({ track_id: "v2", kind: "video", clip_ids: [] });
    vi.stubGlobal("fetch", stub);
    enterEditMode();
    const mod = await import("./api");
    const api = mod.api;

    const result = await api.ensureTrackForDrop("image", undefined, "v1");

    // The first call is the actual mutation; the second is the
    // /ui/status syncRevision side effect. The Mutation Gate appends
    // baseRevision=0 as a query param.
    const mutationCall = calls.find((c) => c.url.includes("/tracks/ensure_for_drop"));
    expect(mutationCall, "mutation call captured").toBeDefined();
    expect(mutationCall!.url.startsWith("/tracks/ensure_for_drop")).toBe(true);
    expect(mutationCall!.init?.method).toBe("POST");
    const body = JSON.parse(String(mutationCall!.init?.body));
    expect(body).toEqual({
      asset_type: "image",
      prefer_kind: null,
      insert_after_track_id: "v1",
      why: "GUI drop zone",
    });
    expect(result.track_id).toBe("v2");
    expect(result.kind).toBe("video");
  });

  it("forwards prefer_kind when provided", async () => {
    const { stub, calls } = makeStub({ track_id: "a2", kind: "audio", clip_ids: [] });
    vi.stubGlobal("fetch", stub);
    enterEditMode();
    const mod = await import("./api");
    const api = mod.api;

    await api.ensureTrackForDrop("audio", "audio", "a1");
    const mutationCall = calls.find((c) => c.url.includes("/tracks/ensure_for_drop"));
    expect(mutationCall).toBeDefined();
    const body = JSON.parse(String(mutationCall!.init?.body));
    expect(body.asset_type).toBe("audio");
    expect(body.prefer_kind).toBe("audio");
    expect(body.insert_after_track_id).toBe("a1");
  });

  it("omits insert_after when not provided (delegates to allocator)", async () => {
    const { stub, calls } = makeStub({ track_id: "v1", kind: "video", clip_ids: [] });
    vi.stubGlobal("fetch", stub);
    enterEditMode();
    const mod = await import("./api");
    const api = mod.api;

    await api.ensureTrackForDrop("video");
    const mutationCall = calls.find((c) => c.url.includes("/tracks/ensure_for_drop"));
    expect(mutationCall).toBeDefined();
    const body = JSON.parse(String(mutationCall!.init?.body));
    expect(body.asset_type).toBe("video");
    expect(body.insert_after_track_id).toBeNull();
    expect(body.prefer_kind).toBeNull();
  });
});
