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
};

// Singleton — exactly one project session per app load.
class SessionStore {
  private state: ProjectSession = { ...EMPTY };
  private listeners = new Set<() => void>();
  private pollTimer: ReturnType<typeof setInterval> | null = null;
  private ticking = false;

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
    this.state = { ...this.state, ...patch };
    for (const fn of this.listeners) fn();
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
