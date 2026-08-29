// GUI-01 unit tests: Mutation Gate envelope + Session store.
//
// These pin the contract described in YROLL-Editor-Foundation-v0.2.md §二:
// every write carries session_id + base_revision, and every Gate rejection
// is surfaced to the session store (so the top bar can explain it) instead
// of failing silently.
//
// The four rejection branches mirror _MutationGateMiddleware in
// yroll/server/app.py — see tests/test_gui_gate_contract.py for the
// server-side half of the same contract.

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api, GateRejection } from "./api";
import { sessionStore } from "./session";

interface Call {
  url: string;
  init: RequestInit | undefined;
}

let calls: Call[] = [];

/** Minimal fetch stub. `routes` maps a URL substring to a response. */
function stubFetch(
  routes: Array<{ match: string; status?: number; body?: unknown; text?: string }>,
) {
  const fn = vi.fn(async (input: any, init?: RequestInit) => {
    const url = String(input);
    calls.push({ url, init });
    const route = routes.find((r) => url.includes(r.match));
    const status = route?.status ?? 200;
    const text =
      route?.text ?? JSON.stringify(route?.body ?? { ok: true });
    return {
      ok: status >= 200 && status < 300,
      status,
      text: async () => text,
      json: async () => JSON.parse(text),
    } as unknown as Response;
  });
  vi.stubGlobal("fetch", fn);
  return fn;
}

/** The /ui/status response mutate() reads to resync the revision. */
const uiStatus = (rev: number, extra: Record<string, unknown> = {}) => ({
  match: "/ui/status",
  body: {
    actor: "human", human_label: "User", agent_label: "",
    session_id: "sess-1", alive: true,
    base_revision: rev, client_last_known_revision: null,
    conflict: false, ai_affected: [],
    visual_cue: { color: "green", text: "🟢" },
    ...extra,
  },
});

beforeEach(() => {
  calls = [];
  localStorage.clear();
  sessionStore._reset();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("mutation gate envelope", () => {
  it("injects sessionId and baseRevision into every write", async () => {
    sessionStore.setSessionId("sess-1");
    sessionStore.bumpRevision(7);
    stubFetch([uiStatus(8), { match: "/trim" }]);

    await api.trim("clip-1", 0, 5, "test");

    const write = calls.find((c) => c.url.includes("/trim"))!;
    expect(write.url).toContain("sessionId=sess-1");
    expect(write.url).toContain("baseRevision=7");
    expect(write.init?.method).toBe("POST");
  });

  it("resyncs the revision from the server after a successful write", async () => {
    sessionStore.setSessionId("sess-1");
    sessionStore.bumpRevision(7);
    // A split logs more than one operation, so the client cannot just +1.
    stubFetch([uiStatus(9), { match: "/split" }]);

    await api.split("clip-1", 2.5);

    expect(sessionStore.get().revision).toBe(9);
  });

  it("classifies 403 sessionId-required as no_session", async () => {
    stubFetch([
      { match: "/clips/clip-1/move", status: 403,
        text: '{"detail":"sessionId required for mutations (call /lease/acquire first)"}' },
    ]);

    await expect(api.move("clip-1", 3)).rejects.toBeInstanceOf(GateRejection);
    expect(sessionStore.get().gateError).toBe("no_session");
  });

  it("classifies 400 baseRevision-required as no_revision", async () => {
    sessionStore.setSessionId("sess-1");
    stubFetch([
      { match: "/volume", status: 400,
        text: '{"detail":"baseRevision query param required for mutations"}' },
    ]);

    await expect(api.volume("clip-1", 0.5)).rejects.toBeInstanceOf(GateRejection);
    expect(sessionStore.get().gateError).toBe("no_revision");
  });

  it("classifies 403 lease-rejected as lease_rejected", async () => {
    sessionStore.setSessionId("sess-1");
    stubFetch([
      { match: "/speed", status: 403,
        text: '{"detail":"lease rejected: no active lease for session sess-1"}' },
    ]);

    await expect(api.speed("clip-1", 2)).rejects.toBeInstanceOf(GateRejection);
    expect(sessionStore.get().gateError).toBe("lease_rejected");
  });

  it("classifies 409 as revision_conflict and raises the conflict flag", async () => {
    sessionStore.setSessionId("sess-1");
    sessionStore.bumpRevision(5);
    stubFetch([
      { match: "/clips/clip-1?", status: 409,
        text: '{"detail":"revision conflict: revision mismatch: client has r5, server is r7"}' },
    ]);

    const err = await api.removeClip("clip-1", "why").catch((e) => e);
    expect(err).toBeInstanceOf(GateRejection);
    expect((err as GateRejection).kind).toBe("revision_conflict");
    expect(sessionStore.get().conflict).toBe(true);
  });

  it("leaves non-gate errors as plain errors", async () => {
    sessionStore.setSessionId("sess-1");
    stubFetch([{ match: "/split", status: 400, text: '{"detail":"clip 不存在"}' }]);

    const err = await api.split("nope", 1).catch((e) => e);
    expect(err).not.toBeInstanceOf(GateRejection);
    expect(sessionStore.get().gateError).toBeNull();
  });

  it("sends the gate in both query and body for chat (audit §6.5)", async () => {
    sessionStore.setSessionId("sess-1");
    sessionStore.bumpRevision(4);
    stubFetch([uiStatus(4), {
      match: "/chat",
      body: { reply: "ok", applied: [], errors: [], problems_reported: [] },
    }]);

    await api.chat("把第三个镜头短一点", "clip-3", 12.5);

    const chat = calls.find((c) => c.url.includes("/chat"))!;
    expect(chat.url).toContain("sessionId=sess-1");
    expect(chat.url).toContain("baseRevision=4");
    // harness.runtime.Task re-checks the gate from the body.
    const body = JSON.parse(String(chat.init?.body));
    expect(body.sessionId).toBe("sess-1");
    expect(body.baseRevision).toBe(4);
  });

  it("gates multipart asset import without forcing a JSON content-type", async () => {
    sessionStore.setSessionId("sess-1");
    sessionStore.bumpRevision(2);
    stubFetch([uiStatus(3), {
      match: "/assets/import", body: { asset: {}, clip: null, deduped: false },
    }]);

    await api.importAsset(new File(["x"], "a.mp4"));

    const imp = calls.find((c) => c.url.includes("/assets/import"))!;
    expect(imp.url).toContain("sessionId=sess-1");
    expect(imp.url).toContain("baseRevision=2");
    // The browser must set its own multipart boundary.
    expect((imp.init?.headers as any)?.["Content-Type"]).toBeUndefined();
  });

  it("does not gate reads", async () => {
    sessionStore.setSessionId("sess-1");
    stubFetch([{ match: "/project", body: { project_id: "p" } }]);

    await api.project();

    expect(calls[0].url).not.toContain("sessionId");
  });
});

describe("session store", () => {
  it("restores the sessionId from localStorage on init", () => {
    localStorage.setItem("yroll.session.v1", "sess-restored");
    sessionStore.initLocal();
    expect(sessionStore.get().sessionId).toBe("sess-restored");
  });

  it("marks the lease as ours when the server session id matches", async () => {
    sessionStore.setSessionId("sess-1");
    stubFetch([uiStatus(3), { match: "/lease/heartbeat", body: { ok: true } }]);

    await sessionStore.refresh();

    expect(sessionStore.get().mine).toBe(true);
    expect(sessionStore.get().revision).toBe(3);
    // A live lease must be heartbeaten, not released-and-reacquired.
    expect(calls.some((c) => c.url.includes("/lease/heartbeat"))).toBe(true);
  });

  it("reports a conflict when someone else moved the revision", async () => {
    sessionStore.setSessionId("sess-mine");
    stubFetch([uiStatus(9, {
      session_id: "sess-other", actor: "conflict", conflict: true,
    })]);

    await sessionStore.refresh();

    expect(sessionStore.get().mine).toBe(false);
    expect(sessionStore.get().conflict).toBe(true);
    expect(sessionStore.get().revision).toBe(9);
  });

  it("forgets the local sessionId after handing off to the agent", async () => {
    sessionStore.setSessionId("sess-1");
    stubFetch([
      { match: "/lease/handoff", body: { ok: true, sessionId: "sess-agent" } },
      uiStatus(3, { session_id: "sess-agent", actor: "agent" }),
    ]);

    await sessionStore.handoffToAgent("Claude");

    // Keeping the old id would 403 every subsequent write.
    expect(sessionStore.get().sessionId).toBeNull();
    expect(sessionStore.get().mine).toBe(false);
    expect(localStorage.getItem("yroll.session.v1")).toBeNull();
  });

  it("clears the conflict flag once our own write lands", () => {
    sessionStore.noteGateError("revision_conflict", "r5 vs r7");
    expect(sessionStore.get().conflict).toBe(true);

    sessionStore.bumpRevision(7);

    expect(sessionStore.get().conflict).toBe(false);
    expect(sessionStore.get().gateError).toBeNull();
  });

  it("persists an acquired sessionId so a reload keeps the lease", async () => {
    stubFetch([
      { match: "/lease/acquire", body: { ok: true, sessionId: "sess-new" } },
      uiStatus(1, { session_id: "sess-new" }),
      { match: "/lease/heartbeat", body: { ok: true } },
    ]);

    await sessionStore.acquire("User");

    expect(localStorage.getItem("yroll.session.v1")).toBe("sess-new");
    expect(sessionStore.get().mine).toBe(true);
  });
});
