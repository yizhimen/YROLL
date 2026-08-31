// GUI-01: Unified Project Session Store
//
// Per YROLL-Editor-Foundation-v0.2.md §二 (Batch 01: GUI Mutation Gate 接通):
//
//   "不要再让 EditLease.tsx 自己持有一点状态，api.ts 再自己从 localStorage 猜。
//    应该有一个统一 useProjectSession() / sessionId / owner / mode /
//    revision / leaseStatus / conflict"
//
// This module owns the canonical client-side session state:
//
//   - sessionId       our lease session id (persisted in localStorage)
//   - owner / mode    who holds the lease, server-truth
//   - revision        server's current revision (= operation count)
//   - conflict        server revision moved without us
//   - gateError       last Mutation Gate rejection, for the top bar
//
// Server truth comes from a single call — GET /ui/status (yroll/core/
// lease_status.py, v0.2 §24-27) — not from stitching /lease + /operations
// together on the client. Liveness is kept with POST /lease/heartbeat.
// localStorage is owned here; no component touches it.

import { useEffect, useState } from "react";
import { api } from "./api";

const STORAGE_KEY = "yroll.session.v1";

/** Poll cadence. Server lease TTL is 5 min (LeaseStore.HEARTBEAT_TTL). */
const POLL_MS = 5000;

export type SessionOwner = "human" | "agent" | "observe" | "free" | null;
export type SessionMode = "edit" | "propose" | "observe" | null;

/** Why the Mutation Gate turned a write away. Mirrors the four rejection
 *  branches of _MutationGateMiddleware in yroll/server/app.py. */
export type GateError =
  | "no_session"        // 403 sessionId required for mutations
  | "no_revision"       // 400 baseRevision query param required
  | "lease_rejected"    // 403 lease rejected: <reason>
  | "revision_conflict" // 409 revision mismatch
  | null;

export interface ProjectSession {
  sessionId: string | null;
  /** Server-truth holder. "free" = nobody holds it. */
  owner: SessionOwner;
  mode: SessionMode;
  /** Server's current revision (operation count). */
  revision: number;
  /** True when the lease holder's session id is ours. */
  mine: boolean;
  humanLabel: string;
  agentLabel: string;
  /** Lease exists and its heartbeat is fresh. */
  alive: boolean;
  /** Server revision moved while we were away. Writes will 409. */
  conflict: boolean;
  gateError: GateError;
  gateMessage: string;
  /** Populated once the first poll lands; until then the top bar is "连接中". */
  loaded: boolean;
  /** GUI-03R5-B1: derived editor state. The single source of truth for
   *  "is the GUI allowed to mutate?". Components consult this — never
   *  the raw fields — when deciding whether a write can fire. */
  editorState: EditorState;
}

/** GUI-03R5-B1: Editor state machine. Three legal states; no other.
 *
 *   CONNECTING — initial; sessionId unknown; reads allowed; writes
 *               blocked. Resolves to EDIT (lease free → acquire)
 *               or OBSERVE (someone else holds).
 *   OBSERVE    — somebody else (human or agent) holds the lease;
 *               reads + scrub + play allowed; writes blocked.
 *   EDIT       — we hold the lease; reads + writes + transport all
 *               enabled. The Mutation Gate is then the only
 *               guard against stale revision / dropped lease.
 *
 *  Transitions:
 *    CONNECTING → EDIT       when acquire() succeeds
 *    CONNECTING → OBSERVE    when first refresh sees alive=mine=false
 *    OBSERVE    → EDIT       when acquire() / handoffToAgent() wins
 *    EDIT       → OBSERVE    when release() / handoffToAgent() / TTL
 *    *          → CONNECTING when the poll loses contact (offline) */
export type EditorState = "CONNECTING" | "OBSERVE" | "EDIT";

/** GUI-03R5-B1: a write is permitted iff state === "EDIT" AND
 *  the sessionId is non-null. Components MUST consult this — never
 *  roll their own check against the raw `mine` / `loaded` flags. */
export function canMutate(s: ProjectSession): boolean {
  return s.editorState === "EDIT" && s.sessionId !== null;
}

/** GUI-03R5-B1: reads + transport (play/scrub/seek) are permitted in
 *  every state — including CONNECTING. The Viewer must work even
 *  before the first /ui/status lands. */
export function canRead(s: ProjectSession): boolean {
  return s.loaded || s.editorState !== "OBSERVE" || s.editorState !== "CONNECTING";
}

/** GUI-03R5-B1: one-shot promise that resolves once the editor is
 *  ready for the FIRST mutation in this tab. Two paths:
 *
 *   a) We already hold the lease (reloaded tab). Resolves on the
 *      next refresh() that confirms `alive && mine`.
 *
 *   b) Nobody holds the lease. Resolves once acquire() succeeds.
 *
 *  Used by api.gated() / api.mutate() to gate the very first write
 *  after mount. After the first resolution, calls are sync (the
 *  cached state machine answer). The promise rejects ONLY on:
 *    - a hard timeout (default 8s) — surfaced as a session-not-ready
 *    - an explicit release / handoff by the user mid-wait — surfaced
 *      so the caller can present an OBSERVE-mode status.
 *
 *  Concurrent calls share a single in-flight promise so we don't
 *  fire N acquire() roundtrips for N concurrent mutations. */
export function ensureReady(timeoutMs: number = 8000): Promise<void> {
  const s0 = sessionStore.get();
  if (canMutate(s0)) return Promise.resolve();
  // GUI-03R5-B1: degenerate states that will never resolve via
  // subscription — surface immediately so the caller's await
  // doesn't hang for the full timeout.
  if (s0.editorState === "EDIT" && s0.sessionId === null) {
    return Promise.reject(
      new Error("session in EDIT but no sessionId; mutations blocked"));
  }
  if (s0.editorState === "OBSERVE") {
    return Promise.reject(
      new Error("session in OBSERVE mode; mutations blocked"));
  }
  if (sessionStore._readyPromise) return sessionStore._readyPromise;
  const ready = new Promise<void>((resolve, reject) => {
    const unsub = sessionStore.subscribe(() => {
      const cur = sessionStore.get();
      if (canMutate(cur)) { unsub(); clearTimeout(timer); resolve(); return; }
      // GUI-03R5-B1: if EDIT mode but no sessionId, we're in a
      // degenerate state — no subscription will ever fire to fix
      // it (the state won't change on its own). Surface the
      // no_session error immediately so callers don't hang.
      if (cur.editorState === "EDIT" && cur.sessionId === null) {
        unsub(); clearTimeout(timer);
        reject(new Error("session in EDIT but no sessionId; mutations blocked"));
        return;
      }
      if (cur.editorState === "OBSERVE") {
        unsub(); clearTimeout(timer);
        reject(new Error("session in OBSERVE mode; mutations blocked"));
        return;
      }
    });
    const timer = setTimeout(() => {
      unsub();
      reject(new Error("session ready timeout"));
    }, timeoutMs);
    // Only kick the connection when we're actually in CONNECTING.
    // A test that pre-seeds editorState === EDIT via set({loaded:true,
    // mine:true, alive:true}) should NOT have us re-refresh and clobber
    // that state with whatever /ui/status returns (which won't know
    // about the test's mock session id). The subscribe above already
    // saw canMutate(s0) === true at the very first state check below.
    if (s0.editorState === "CONNECTING") {
      if (!sessionStore._pollTimerActive()) sessionStore.startPolling();
      void sessionStore.refresh().catch(() => { /* ignore */ });
  }
  });
  // After subscribing, check the current state again — the caller may
  // have transitioned to EDIT between the pre-check and the subscribe
  // (e.g., via a synchronous set() in a test setup).
  if (canMutate(sessionStore.get())) {
    unsub(); clearTimeout(timer);
    return Promise.resolve();
  }
  sessionStore._readyPromise = ready;
  ready.finally(() => { sessionStore._readyPromise = null; });
  return ready;
}

const EMPTY: ProjectSession = {
  sessionId: null,
  owner: null,
  mode: null,
  revision: 0,
  mine: false,
  humanLabel: "",
  agentLabel: "",
  alive: false,
  conflict: false,
  gateError: null,
  gateMessage: "",
  loaded: false,
  editorState: "CONNECTING",
};

// Singleton — exactly one project session per app load.
class SessionStore {
  private state: ProjectSession = { ...EMPTY };
  private listeners = new Set<() => void>();
  private pollTimer: ReturnType<typeof setInterval> | null = null;
  private ticking = false;
  // GUI-03R5-B1: a single in-flight ensureReady() promise. Subsequent
  // callers piggyback on it; cleared on settle.
  _readyPromise: Promise<void> | null = null;
  // Internal accessor used by ensureReady() above.
  _pollTimerActive(): boolean { return this.pollTimer !== null; }

  get(): ProjectSession {
    return this.state;
  }

  subscribe(fn: () => void): () => void {
    this.listeners.add(fn);
    return () => {
      this.listeners.delete(fn);
    };
  }

  private set(patch: Partial<ProjectSession>): void {
    // GUI-03R5-B1: every state patch re-derives editorState from the
    // raw fields. Components MUST consult editorState (via
    // canMutate(s)) rather than reasoning about mine/alive/loaded
    // themselves — that way the state machine is centralized and
    // cannot drift. If a patch tries to set editorState explicitly,
    // it is IGNORED (the derivation wins).
    const merged = { ...this.state, ...patch };
    merged.editorState = this._deriveEditorState(merged);
    this.state = merged;
    for (const fn of this.listeners) fn();
  }

  /** GUI-03R5-B1: pure derivation from raw fields. */
  private _deriveEditorState(s: ProjectSession): EditorState {
    if (!s.loaded) return "CONNECTING";
    if (s.conflict) return "OBSERVE";  // we are stale; can't trust writes
    if (s.mine && s.alive) return "EDIT";
    return "OBSERVE";
  }

  /** Restore sessionId from localStorage. Called once from App on mount.
   *  Does NOT acquire — acquisition happens on the first poll, so a
   *  reloaded tab that still holds a live lease keeps it. */
  initLocal(): void {
    if (this.state.sessionId) return;
    let sid: string | null = null;
    try {
      sid = localStorage.getItem(STORAGE_KEY);
    } catch {
      /* private mode / storage disabled — run without persistence */
    }
    if (sid) this.set({ sessionId: sid });
  }

  private persist(sessionId: string | null): void {
    try {
      if (sessionId) localStorage.setItem(STORAGE_KEY, sessionId);
      else localStorage.removeItem(STORAGE_KEY);
    } catch {
      /* ignore */
    }
  }

  setSessionId(sessionId: string | null): void {
    this.persist(sessionId);
    this.set({ sessionId });
  }

  /** Adopt a server revision after a successful mutation. Clears conflict:
   *  our write landed, so we are by definition in sync. */
  bumpRevision(rev: number): void {
    this.set({ revision: rev, conflict: false, gateError: null, gateMessage: "" });
  }

  /** Record a Mutation Gate rejection so the top bar can explain it. */
  noteGateError(kind: GateError, message: string): void {
    this.set({
      gateError: kind,
      gateMessage: message,
      conflict: kind === "revision_conflict" ? true : this.state.conflict,
    });
  }

  clearGateError(): void {
    if (!this.state.gateError) return;
    this.set({ gateError: null, gateMessage: "" });
  }

  /** One reconcile against server truth. Safe to call directly (the
   *  "刷新" button does). */
  async refresh(): Promise<void> {
    const st = await api.uiStatus(
      this.state.loaded ? this.state.revision : undefined,
    );
    const mine = !!(st.session_id && st.session_id === this.state.sessionId);
    // /ui/status collapses actor to "conflict" when the revision moved, so
    // read the holder from alive+session_id rather than actor alone.
    const owner: SessionOwner =
      st.actor === "conflict"
        ? this.state.owner
        : (st.actor as SessionOwner) ?? "free";
    this.set({
      owner,
      mine,
      alive: !!st.alive,
      humanLabel: st.human_label ?? "",
      agentLabel: st.agent_label ?? "",
      revision: st.base_revision,
      // Conflict only matters while someone else could be writing. Our own
      // successful mutations clear it via bumpRevision.
      conflict: !!st.conflict && !mine,
      loaded: true,
    });
    if (mine) {
      // Keep the lease from expiring while the tab is open.
      await api.heartbeatLease(this.state.sessionId!).catch(() => {});
      this.clearGateError();
    }
  }

  /** Take the edit lease for the human. Returns the new session id. */
  async acquire(label = "User"): Promise<string | null> {
    const r = await api.acquireLease("human", "edit", undefined, label);
    if (r.ok && r.sessionId) {
      this.setSessionId(r.sessionId);
      this.set({
        owner: "human",
        mode: "edit",
        mine: true,
        alive: true,
        gateError: null,
        gateMessage: "",
      });
      await this.refresh();
      return r.sessionId;
    }
    return null;
  }

  async release(): Promise<void> {
    const sid = this.state.sessionId;
    if (!sid) return;
    await api.releaseLease(sid).catch(() => {});
    this.setSessionId(null);
    this.set({ owner: "free", mode: null, mine: false, alive: false });
    await this.refresh();
  }

  async handoffToAgent(label = "Claude"): Promise<void> {
    const sid = this.state.sessionId;
    if (!sid) return;
    const r = await api.handoffLease(sid, "agent", "edit", label);
    // Handoff mints a NEW session id owned by the agent. Ours is now dead:
    // forget it, otherwise every subsequent write 403s with a stale id.
    if (r.ok) this.setSessionId(null);
    await this.refresh();
  }

  /** Start reconciling with the server. Called once from App on mount. */
  startPolling(): void {
    if (this.pollTimer !== null) return;
    const tick = async () => {
      if (this.ticking) return; // don't stack ticks on a slow server
      this.ticking = true;
      try {
        await this.refresh();
        // Nobody holds an edit lease and we don't have one → take it, so a
        // fresh tab is immediately able to edit.
        const s = this.state;
        if (!s.mine && (!s.alive || s.owner === "free")) {
          await this.acquire().catch(() => {});
        }
      } catch {
        // network blip — leave last known state, retry next tick
      } finally {
        this.ticking = false;
      }
    };
    void tick();
    this.pollTimer = setInterval(() => void tick(), POLL_MS);
  }

  stopPolling(): void {
    if (this.pollTimer !== null) {
      clearInterval(this.pollTimer);
      this.pollTimer = null;
    }
  }

  /** Test seam. */
  _reset(): void {
    this.stopPolling();
    this.state = { ...EMPTY };
    this.listeners.clear();
    this.ticking = false;
  }
}

export const sessionStore = new SessionStore();

/** React hook — components subscribe to the singleton. */
export function useProjectSession(): ProjectSession {
  const [snap, setSnap] = useState<ProjectSession>(sessionStore.get());
  useEffect(() => sessionStore.subscribe(() => setSnap(sessionStore.get())), []);
  return snap;
}

/** Gate parameters injected by api.mutate() on every write. */
export function currentGate(): { sessionId: string | null; baseRevision: number } {
  const s = sessionStore.get();
  return { sessionId: s.sessionId, baseRevision: s.revision };
}
