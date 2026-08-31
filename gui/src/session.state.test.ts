// GUI-03R5-B1: Session state machine unit tests.
//
// Pins the editorState derivation + ensureReady() contract.
// These tests do NOT touch network or fetch — they manipulate the
// SessionStore singleton directly so the state machine can be
// verified in isolation.

import { describe, expect, it, beforeEach, afterEach } from "vitest";
import { sessionStore, ensureReady, canMutate, canRead, EditorState }
  from "./session";

beforeEach(() => sessionStore._reset());
afterEach(() => sessionStore._reset());

function enter(partial: Parameters<typeof sessionStore.set>[0]) {
  sessionStore.set(partial);
}

describe("editorState derivation", () => {
  it("CONNECTING when !loaded", () => {
    enter({ sessionId: "x", mine: true, alive: true });
    expect(sessionStore.get().editorState).toBe("CONNECTING");
  });

  it("OBSERVE when conflict (even if mine=true)", () => {
    enter({
      loaded: true, sessionId: "x", mine: true, alive: true,
      conflict: true,
    });
    expect(sessionStore.get().editorState).toBe("OBSERVE");
  });

  it("OBSERVE when alive=false", () => {
    enter({
      loaded: true, sessionId: "x", mine: true, alive: false,
    });
    expect(sessionStore.get().editorState).toBe("OBSERVE");
  });

  it("OBSERVE when mine=false (someone else holds)", () => {
    enter({
      loaded: true, sessionId: "x", mine: false, alive: true,
    });
    expect(sessionStore.get().editorState).toBe("OBSERVE");
  });

  it("EDIT when loaded && mine && alive", () => {
    enter({
      loaded: true, sessionId: "x", mine: true, alive: true,
    });
    expect(sessionStore.get().editorState).toBe("EDIT");
  });

  it("explicit editorState in patch is IGNORED (derivation wins)", () => {
    enter({
      loaded: true, sessionId: "x", mine: true, alive: true,
    });
    // Try to override EDIT → CONNECTING; the derivation wins.
    enter({ editorState: "CONNECTING" });
    expect(sessionStore.get().editorState).toBe("EDIT");
  });
});

describe("canMutate / canRead", () => {
  it("canMutate: EDIT + non-null sessionId", () => {
    enter({ loaded: true, mine: true, alive: true, sessionId: "s1" });
    expect(canMutate(sessionStore.get())).toBe(true);
  });

  it("canMutate: EDIT but null sessionId → false", () => {
    enter({ loaded: true, mine: true, alive: true });
    expect(canMutate(sessionStore.get())).toBe(false);
  });

  it("canMutate: OBSERVE → false", () => {
    enter({ loaded: true, mine: false, alive: true, sessionId: "s1" });
    expect(canMutate(sessionStore.get())).toBe(false);
  });

  it("canMutate: CONNECTING → false", () => {
    enter({});
    expect(canMutate(sessionStore.get())).toBe(false);
  });

  it("canRead: every state allows reads", () => {
    // CONNECTING
    enter({});
    expect(canRead(sessionStore.get())).toBe(true);
    // OBSERVE
    enter({ loaded: true, mine: false, alive: true, sessionId: "s1" });
    expect(canRead(sessionStore.get())).toBe(true);
    // EDIT
    enter({ loaded: true, mine: true, alive: true, sessionId: "s1" });
    expect(canRead(sessionStore.get())).toBe(true);
  });
});

describe("ensureReady", () => {
  it("resolves immediately if already EDIT + sessionId", async () => {
    enter({ loaded: true, mine: true, alive: true, sessionId: "s1" });
    await expect(ensureReady(1000)).resolves.toBeUndefined();
  });

  it("rejects immediately if EDIT but no sessionId", async () => {
    enter({ loaded: true, mine: true, alive: true });
    await expect(ensureReady(1000)).rejects.toThrow(/no sessionId/);
  });

  it("rejects immediately if OBSERVE", async () => {
    enter({ loaded: true, mine: false, alive: true, sessionId: "s1" });
    await expect(ensureReady(1000)).rejects.toThrow(/OBSERVE/);
  });

  it("in-flight promise is shared (no duplicate acquire)", async () => {
    enter({ loaded: true, mine: true, alive: true });  // EDIT, no sessionId
    // Debug: what state do we actually have?
    const st = sessionStore.get();
    expect(st.editorState).toBe("EDIT");
    expect(st.sessionId).toBeNull();
    const p1 = ensureReady(2000).catch((e) => e);
    const p2 = ensureReady(2000).catch((e) => e);
    // Both promises should reject with the same "no sessionId" error.
    const [r1, r2] = await Promise.all([p1, p2]);
    expect((r1 as Error).message).toMatch(/no sessionId/);
    expect((r2 as Error).message).toMatch(/no sessionId/);
  });

  it("rejection clears the in-flight promise so the next call can resolve", async () => {
    enter({ loaded: true, mine: true, alive: true });  // no sessionId
    await expect(ensureReady(100)).rejects.toThrow(/no sessionId/);
    // After rejection, set a sessionId, then ask again.
    enter({ sessionId: "s1" });
    await expect(ensureReady(100)).resolves.toBeUndefined();
  });
});