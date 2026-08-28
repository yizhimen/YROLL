// GUI-01: Unified Project Session Store
//
// Per YROLL-Editor-Foundation-v0.2.md §二 (Batch 01: GUI Mutation Gate 接通):
//
//   "不要再让 EditLease.tsx 自己持有一点状态，api.ts 再自己从 localStorage 猜。
//    应该有一个统一 useProjectSession() / sessionId / owner / mode /
//    revision / leaseStatus / conflict"
//
// This module owns the canonical client-side session state. Components
// read it via the `useProjectSession()` hook. api.ts `mutate()` reads
// from it to inject sessionId + baseRevision on every mutation call.
// localStorage is owned here too — no other component touches it.

import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "./api";

const STORAGE_KEY = "yroll.session.v1";

export type SessionOwner = "human" | "agent" | null;
export type SessionMode = "edit" | "propose" | "observe" | null;

export interface ProjectSession {
  sessionId: string | null;        // our local candidate session id (may not yet be acquired)
  owner: SessionOwner;             // who actually holds the lease (server-truth)
  mode: SessionMode;
  revision: number;                // our last known server revision
  humanLabel: string;              // label shown in the top bar
  agentLabel: string;              // label shown when AI holds lease
  alive: boolean;                  // server-side heartbeat still fresh?
  conflict: boolean;               // client revision != server revision
  leaseExpiresAt: number | null;   // ms epoch; null when not held
}

const EMPTY: ProjectSession = {
  sessionId: null,
  owner: null,
  mode: null,
  revision: 0,
  humanLabel: "",
  agentLabel: "",
  alive: false,
  conflict: false,
  leaseExpiresAt: null,
};

// Singleton state — there is exactly one project session per app load.
// Components subscribe via the hook below.
class SessionStore {
  private state: ProjectSession = { ...EMPTY };
  private listeners = new Set<() => void>();
  private pollTimer: number | null = null;

  get(): ProjectSession {
    return this.state;
  }

  subscribe(fn: () => void): () => void {
    this.listeners.add(fn);
    return () => this.listeners.delete(fn);
  }

  // Init from localStorage on first mount; called once from App.
  initLocal(): void {
    if (this.state.sessionId) return;
    let s = localStorage.getItem(STORAGE_KEY);
    if (!s) {
      // crypto.randomUUID is browser-provided
      s = (crypto as Crypto).randomUUID();
      localStorage.setItem(STORAGE_KEY, s);
    }
    try {
      const parsed = JSON.parse(s);
      // New schema is JSON; old schema was just a UUID string — accept both
      this.state = { ...EMPTY, ...(parsed.session || {}), sessionId: parsed.sessionId ?? parsed };
    } catch {
      this.state = { ...EMPTY, sessionId: s };
    }
    this.emit();
  }

  setLocal(sessionId: string): void {
    this.state = { ...this.state, sessionId };
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ sessionId }));
    this.emit();
  }

  // Called after every mutation (or refresh) so subsequent requests
  // use the post-mutation revision.
  bumpRevision(rev: number): void {
    if (rev === this.state.revision) return;
    this.state = {
      ...this.state,
      revision: rev,
      // After successful mutation, server revision advances; client
      // is in sync → no conflict.
      conflict: false,
    };
    this.emit();
  }

  markConflict(serverRevision: number): void {
    this.state = {
      ...this.state,
      revision: serverRevision,
      conflict: true,
    };
    this.emit();
  }

  setOwner(owner: SessionOwner, mode: SessionMode,
             humanLabel: string, agentLabel: string,
             alive: boolean, leaseExpiresAt: number | null,
             serverRevision: number): void {
    this.state = {
      ...this.state,
      owner, mode,
      humanLabel, agentLabel, alive,
      leaseExpiresAt,
      revision: serverRevision,
      conflict: false,
    };
    this.emit();
  }

  private emit(): void {
    for (const fn of this.listeners) fn();
  }

  // Begin / stop polling /lease; started by App once on mount.
  startPolling(): void {
    if (this.pollTimer !== null) return;
    const tick = async () => {
      try {
        const data = await api.getLease();
        // Owner + mode from server
        const owner: SessionOwner =
          data.heldBy === "human" ? "human" :
          data.heldBy === "agent" ? "agent" : null;
        const mode: SessionMode =
          (data.mode as SessionMode) ?? null;
        const alive = !!data.isAlive;
        // If lease is held by us and dead, release so we can re-acquire.
        if (data.sessionId && data.sessionId === this.state.sessionId && !alive) {
          await api.releaseLease(data.sessionId).catch(() => {});
          // Re-acquire below
          const r = await api.acquireLease("human", "edit", undefined, "User");
          if (r.ok && r.sessionId) {
            this.setLocal(r.sessionId);
          }
        } else if ((!data.sessionId || data.sessionId !== this.state.sessionId)
                   && this.state.sessionId) {
          // Lease is free or held by another session — try to take it.
          try {
            const r = await api.acquireLease("human", "edit", undefined, "User");
            if (r.ok && r.sessionId) {
              this.setLocal(r.sessionId);
            }
          } catch { /* conflict; just observe */ }
        }
        // Reconcile with server revision for conflict detection
        const ops = await api.operations();
        const serverRev = ops.length;
        this.setOwner(owner, mode,
                      data.humanLabel ?? "",
                      data.humanLabel ?? "", // agent label uses same field per current server schema
                      alive,
                      null, // server doesn't expose expiry ms yet
                      serverRev);
      } catch (e) {
        // network blip — ignore
      }
    };
    tick();
    this.pollTimer = window.setInterval(tick, 5000);
  }

  stopPolling(): void {
    if (this.pollTimer !== null) {
      clearInterval(this.pollTimer);
      this.pollTimer = null;
    }
  }
}

export const sessionStore = new SessionStore();

// React hook — components subscribe to the singleton.
export function useProjectSession(): ProjectSession {
  const [snap, setSnap] = useState<ProjectSession>(sessionStore.get());
  useEffect(() => {
    const unsub = sessionStore.subscribe(() => setSnap(sessionStore.get()));
    return () => { unsub(); };
  }, []);
  return snap;
}

// Imperative refresh after mutations — call this from api.mutate wrapper.
export function refreshSessionFromServer(rev: number | null): void {
  if (rev === null) {
    sessionStore.markConflict(sessionStore.get().revision + 1);
    return;
  }
  sessionStore.bumpRevision(rev);
}

// Helper for callers that just want to grab current sessionId+revision.
export function currentGate(): { sessionId: string | null;
                                baseRevision: number } {
  const s = sessionStore.get();
  return { sessionId: s.sessionId, baseRevision: s.revision };
}
