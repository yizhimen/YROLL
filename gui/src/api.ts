// YROLL Manifest v0.1 对应的 TS 类型（与 yroll/core/manifest.py 对齐）

import { sessionStore, currentGate, GateError } from "./session";

export interface TimeRange { start: number; end: number }

export interface Asset {
  asset_id: string;
  type: "video" | "image" | "audio" | "subtitle" | "document";
  path: string;
  origin?: "camera" | "generated" | "screen_record" | "unknown";
  gen?: Record<string, unknown> | null;
  identity: { duration_sec?: number; width?: number; height?: number };
}

export interface Clip {
  clip_id: string;
  asset_id: string;
  source_range: TimeRange;
  timeline_range: TimeRange;
  track_id: string;
  speed: number;
  volume: number;
  transform: Record<string, unknown>;
  adjustments: Array<Record<string, unknown>>;
  context: Record<string, string>;
}

export interface Track {
  track_id: string;
  kind: "video" | "audio" | "text";
  clip_ids: string[];
  muted?: boolean;
  locked?: boolean;
  hidden?: boolean;
}

export interface Operation {
  operation_id: string;
  who: "human" | "ai";
  type: string;
  target: string;
  why: string;
  at: string;
  cost: number;
}

export interface Problem {
  problem_id: string;
  target_clip?: string;
  time_range?: TimeRange;
  category: string;
  description: string;
  source: string;
}

export interface Solution {
  solution_id: string;
  problem_id: string;
  route: "L0_transform" | "L1_local_ai" | "L2_cloud_ai" | "L3_regenerate";
  tool: string;
  label?: string;
  params: Record<string, unknown>;
  cost: number;
  duration_ms: number;
  risk: string;
  selected: boolean;
}

export interface Project {
  project_id: string;
  name: string;
  intent: Record<string, string>;
  assets: Asset[];
  timeline: { timeline_id: string; tracks: Track[] };
  clips: Record<string, Clip>;
}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!r.ok) throw new Error(`${r.status}: ${await r.text()}`);
  return r.json();
}

// --- Mutation Gate envelope (YROLL-Editor-Foundation-v0.2.md §二) ---
//
// Every write goes through mutate(). It injects sessionId + baseRevision
// so a new mutation can never be added without the Gate — that was the
// whole point of §二.2 ("增加一个新的 mutation，忘了传 Gate 参数").
//
// Mirrors _MutationGateMiddleware in yroll/server/app.py:
//   403 "sessionId required for mutations"   -> no_session
//   400 "baseRevision query param required"  -> no_revision
//   403 "lease rejected: ..."                -> lease_rejected
//   409 "revision conflict: ..."             -> revision_conflict
// On success the local revision is re-read from /ui/status, because a
// single call can log more than one operation (ripple delete, split).

/** A Mutation Gate rejection, carrying the machine-readable reason so the
 *  top bar can offer the right recovery ("获取编辑权" vs "刷新"). */
export class GateRejection extends Error {
  readonly kind: Exclude<GateError, null>;
  readonly status: number;
  constructor(kind: Exclude<GateError, null>, status: number, detail: string) {
    super(detail);
    this.name = "GateRejection";
    this.kind = kind;
    this.status = status;
  }
}

function classifyGate(status: number, detail: string): Exclude<GateError, null> | null {
  if (status === 409 || detail.includes("revision mismatch")
      || detail.includes("revision conflict")) return "revision_conflict";
  if (status === 403 && detail.includes("sessionId required")) return "no_session";
  if (status === 403 && detail.includes("lease rejected")) return "lease_rejected";
  if (status === 400 && detail.includes("baseRevision")) return "no_revision";
  return null;
}

/** Re-read the server's current revision after a successful write. */
async function syncRevision(): Promise<void> {
  try {
    const r = await fetch("/ui/status");
    if (!r.ok) return;
    const st = await r.json();
    if (typeof st?.base_revision === "number") {
      sessionStore.bumpRevision(st.base_revision);
    }
  } catch {
    /* the mutation already landed; a stale local revision self-heals on
       the next poll, and the worst case is one retryable 409 */
  }
}

/** Shared core: gate params in, gate errors out, revision resynced. */
async function gated<R>(path: string, init: RequestInit): Promise<R> {
  const { sessionId, baseRevision } = currentGate();
  const url = new URL(path, window.location.origin);
  if (sessionId) url.searchParams.set("sessionId", sessionId);
  url.searchParams.set("baseRevision", String(baseRevision));

  let r: Response;
  try {
    r = await fetch(url.toString().slice(url.origin.length), init);
  } catch (e: any) {
    throw new Error(`network: ${e?.message ?? e}`);
  }

  if (!r.ok) {
    const detail = await r.text();
    const kind = classifyGate(r.status, detail);
    if (kind) {
      sessionStore.noteGateError(kind, detail);
      throw new GateRejection(kind, r.status, detail);
    }
    throw new Error(`${r.status}: ${detail}`);
  }

  await syncRevision();
  const text = await r.text();
  return (text ? JSON.parse(text) : null) as R;
}

async function mutate<R>(
  method: "POST" | "DELETE" | "PATCH" | "PUT",
  path: string,
  body?: unknown,
): Promise<R> {
  return gated<R>(path, {
    method,
    headers: { "Content-Type": "application/json" },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
}


export const api = {
  project: () => req<Project>("/project"),
  operations: () => req<Operation[]>("/operations"),
  // GUI-02: frame-native. Server rejects legacy seconds fields with 400.
  // `newSourceStart` / `newSourceEnd` are integer SOURCE FRAMES
  // (asset's source timebase, NOT sequence fps). The server converts
  // them via the asset's source_fps when applying.
  trim: (clipId: string, newSourceStartFrame?: number, newSourceEndFrame?: number, why = "") =>
    mutate(`POST`, `/clips/${clipId}/trim`, {
      new_source_start_frame: newSourceStartFrame ?? null,
      new_source_end_frame: newSourceEndFrame ?? null,
      why,
    }),
  split: (clipId: string, atTimelineFrame: number, why = "") =>
    mutate("POST", `/clips/${clipId}/split`, { at_timeline_frame: atTimelineFrame, why }),
  // `newTimelineStart` is an integer TIMELINE FRAME (sequence fps).
  move: (clipId: string, newTimelineStartFrame: number, why = "", trackId?: string) =>
    mutate("POST", `/clips/${clipId}/move`,
      { new_timeline_start_frame: newTimelineStartFrame, new_track_id: trackId ?? null, why }),
  speed: (clipId: string, speed: number, why = "") =>
    mutate("POST", `/clips/${clipId}/speed`, { speed, why }),
  volume: (clipId: string, volume: number, why = "") =>
    mutate("POST", `/clips/${clipId}/volume`, { volume, why }),
  removeClip: (clipId: string, why = "", ripple = false) =>
    mutate("DELETE",
      `/clips/${clipId}?why=${encodeURIComponent(why)}${ripple ? "&ripple=true" : ""}`),
  commit: (note: string) => mutate("POST", `/versions?note=${encodeURIComponent(note)}`),
  render: (burnSubtitles = false, width = 1080, name = "preview.mp4") =>
    mutate<{ preview: string }>("POST",
      `/render?burn_subtitles=${burnSubtitles}&width=${width}&name=${encodeURIComponent(name)}`),
  // Chat is the *other* mutation path (audit §6.5). The middleware reads the
  // gate from the query string; harness.runtime.Task re-checks it from the
  // body, so both must carry it.
  chat: (message: string, selectedClip: string | null, playhead: number) =>
    mutate<{
      reply: string;
      applied: string[];
      errors: Array<{ error: string }>;
      problems_reported: Array<{ problem: Problem; solutions: Solution[] }>;
    }>("POST", "/chat", {
      message, selected_clip: selectedClip, playhead,
      sessionId: currentGate().sessionId,
      baseRevision: currentGate().baseRevision,
    }),
  reportProblem: (description: string, category: string, targetClip: string | null,
                  timeRange?: TimeRange) =>
    mutate<{ problem: Problem; solutions: Solution[] }>("POST", "/problems", {
      description, category, target_clip: targetClip, time_range: timeRange ?? null,
    }),
  problems: () => req<{ problems: Problem[]; solutions: Solution[] }>("/problems"),
  executeSolution: (solutionId: string) =>
    mutate<{ status: string; operation_id?: string; message?: string }>(
      "POST", "/solutions/execute", { solution_id: solutionId }),
  inferLinks: () => mutate<{ inferred: number; total: number }>("POST", "/links/infer"),
  impact: (clipId: string, op = "remove") =>
    req<{
      op: string;
      will_sync: Array<{ clip_id: string; kind: string; text: string }>;
      will_prompt: Array<{ clip_id: string; kind: string; text: string }>;
      untouched: Array<{ clip_id: string; kind: string; text: string }>;
    }>(`/clips/${clipId}/impact?op=${op}`),
  delogo: (clipId: string, region: { x: number; y: number; w: number; h: number }, why = "") =>
    mutate("POST", `/clips/${clipId}/delogo?why=${encodeURIComponent(why)}`, region),
  denoise: (clipId: string, strength = 12, why = "") =>
    mutate("POST", `/clips/${clipId}/denoise?strength=${strength}&why=${encodeURIComponent(why)}`),
  loudness: (clipId: string) =>
    mutate<{ after: { mean_db: number; max_db: number } }>(
      "POST", `/clips/${clipId}/loudness`),
  silenceRemove: (clipId: string, why = "") =>
    mutate("POST", `/clips/${clipId}/silence-remove?why=${encodeURIComponent(why)}`),
  // Multipart: same gate, but the browser must set its own Content-Type
  // boundary, so this goes through gated() rather than mutate().
  importAsset: (file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    return gated<{ asset: Asset; clip: Clip | null; deduped: boolean }>(
      "/assets/import", { method: "POST", body: fd });
  },
  addClip: (assetId: string, sourceStart: number, sourceEnd: number,
            timelineStart: number, trackId: string, why = "") =>
    mutate<Clip>("POST", "/clips", {
      asset_id: assetId, source_start: sourceStart, source_end: sourceEnd,
      timeline_start: timelineStart, track_id: trackId, why,
    }),
  revert: (operationId: string, why = "") =>
    mutate("POST", "/revert", { operation_id: operationId, why }),
  volumeRange: (clipId: string, volume: number, start: number, end: number, why = "") =>
    mutate("POST",
      `/clips/${clipId}/volume-range?volume=${volume}&start=${start}&end=${end}&why=${encodeURIComponent(why)}`),
  removeAdjustment: (clipId: string, adjustmentId: string, why = "") =>
    mutate("DELETE",
      `/clips/${clipId}/adjustments/${adjustmentId}?why=${encodeURIComponent(why)}`),
  editSubtitle: (clipId: string, text: string, why = "") =>
    mutate("POST",
      `/clips/${clipId}/subtitle?text=${encodeURIComponent(text)}&why=${encodeURIComponent(why)}`),
  setSubtitleStyle: (clipId: string, style: Record<string, unknown>, why = "") =>
    mutate("POST", `/clips/${clipId}/subtitle-style?why=${encodeURIComponent(why)}`, style),
  addSubtitle: (text: string, start: number, end: number, why = "") =>
    mutate<Clip>("POST",
      `/subtitles?text=${encodeURIComponent(text)}&start=${start}&end=${end}&why=${encodeURIComponent(why)}`),
  generateSubtitles: (why = "GUI 自动字幕") =>
    mutate<{ after?: { count?: number } }>("POST",
      `/subtitles/generate?why=${encodeURIComponent(why)}`),
  addTrack: (kind: string, trackId?: string) =>
    mutate<Track>("POST", `/tracks?kind=${kind}${trackId ? `&track_id=${trackId}` : ""}`),
  setTransform: (clipId: string, transform: Record<string, number>, why = "") =>
    mutate("POST", `/clips/${clipId}/transform?why=${encodeURIComponent(why)}`, transform),
  setFade: (clipId: string, fadeIn: number, fadeOut: number, why = "") =>
    mutate("POST",
      `/clips/${clipId}/fade?fade_in=${fadeIn}&fade_out=${fadeOut}&why=${encodeURIComponent(why)}`),
  setDissolve: (clipId: string, duration: number, kind = "fade", why = "") =>
    mutate("POST",
      `/clips/${clipId}/dissolve?duration=${duration}&kind=${kind}&why=${encodeURIComponent(why)}`),
  searchTranscripts: (q: string) =>
    req<{ results: Array<{ clip_id: string; timeline: number; text: string; track_id: string }> }>(
      `/search-transcripts?q=${encodeURIComponent(q)}`),
  setMuted: (clipId: string, muted: boolean, why = "") =>
    mutate("POST", `/clips/${clipId}/mute?muted=${muted}&why=${encodeURIComponent(why)}`),
  renderRange: (start: number, end: number, burnSubtitles: boolean, width: number, name: string) =>
    mutate<{ preview: string }>("POST",
      `/render?start=${start}&end=${end}&burn_subtitles=${burnSubtitles}&width=${width}&name=${encodeURIComponent(name)}`),
  renderStatus: () =>
    req<{ status: string; step: string; done: number; total: number; error: string; preview: string }>(
      "/render/status"),
  setTrackMuted: (trackId: string, muted: boolean, why = "") =>
    mutate("POST", `/tracks/${trackId}/mute?muted=${muted}&why=${encodeURIComponent(why)}`),
  setTrackLocked: (trackId: string, locked: boolean, why = "") =>
    mutate("POST", `/tracks/${trackId}/lock?locked=${locked}&why=${encodeURIComponent(why)}`),
  setTrackHidden: (trackId: string, hidden: boolean, why = "") =>
    mutate("POST", `/tracks/${trackId}/hide?hidden=${hidden}&why=${encodeURIComponent(why)}`),
  // /project/open and /project/new are Gate-exempt by design: you cannot
  // hold a lease on a project you have not opened yet.
  openProject: (path: string) =>
    req<{ project: string; path: string }>(`/project/open?path=${encodeURIComponent(path)}`, { method: "POST" }),
  newProject: (root: string, name: string, goal = "") =>
    req<{ project: string; path: string }>(
      `/project/new?root=${encodeURIComponent(root)}&name=${encodeURIComponent(name)}&goal=${encodeURIComponent(goal)}`,
      { method: "POST" }),
  versions: () =>
    req<Array<{ version_id: string; parent: string | null; operation_ids: string[]; note: string; created_at: string }>>(
      "/versions"),
  voiceReplace: (clipId: string, text: string, why = "") =>
    mutate("POST",
      `/clips/${clipId}/voice-replace?text=${encodeURIComponent(text)}&why=${encodeURIComponent(why)}`),
  setColor: (clipId: string, params: Record<string, number>, why = "") =>
    mutate("POST", `/clips/${clipId}/color?why=${encodeURIComponent(why)}`, params),
  setFlip: (clipId: string, horizontal: boolean, vertical: boolean, why = "") =>
    mutate("POST",
      `/clips/${clipId}/flip?horizontal=${horizontal}&vertical=${vertical}&why=${encodeURIComponent(why)}`),
  setOpacity: (clipId: string, opacity: number, why = "") =>
    mutate("POST", `/clips/${clipId}/opacity?opacity=${opacity}&why=${encodeURIComponent(why)}`),
  setCrop: (clipId: string, left: number, top: number, right: number, bottom: number, why = "") =>
    mutate("POST",
      `/clips/${clipId}/crop?left=${left}&top=${top}&right=${right}&bottom=${bottom}&why=${encodeURIComponent(why)}`),
  setReverse: (clipId: string, why = "") =>
    mutate("POST", `/clips/${clipId}/reverse?why=${encodeURIComponent(why)}`),
  setTransform2d: (clipId: string, params: Record<string, number | boolean>, why = "") =>
    mutate("POST", `/clips/${clipId}/transform2d?why=${encodeURIComponent(why)}`, params),
  resetVisual: (clipId: string, why = "") =>
    mutate("POST", `/clips/${clipId}/reset-visual?why=${encodeURIComponent(why)}`),
  costs: () =>
    req<{ total: number; currency: string; by_tool: Record<string, { count: number; cost: number }>; by_who: Record<string, number> }>("/costs"),
  exportPackage: (cfg: {
    width: number; burn_subtitles: boolean; title: string;
    description: string; tags: string; platform: string;
    cover_offset_sec: number;
  }) =>
    mutate<{ started: boolean }>("POST",
      `/export/package?width=${cfg.width}&burn_subtitles=${cfg.burn_subtitles}` +
      `&title=${encodeURIComponent(cfg.title)}` +
      `&description=${encodeURIComponent(cfg.description)}` +
      `&tags=${encodeURIComponent(cfg.tags)}` +
      `&platform=${encodeURIComponent(cfg.platform)}` +
      `&cover_offset_sec=${cfg.cover_offset_sec}`),
  presets: () =>
    req<{
      fonts: Array<{ id: string; name: string; file: string; category: string; weight: number }>;
      subtitle_styles: Array<{ id: string; name: string; font_size: number;
        color: string; bold: boolean; position: "top" | "middle" | "bottom";
        align: "left" | "center" | "right"; outline_color: string; outline_width: number }>;
      transitions: Array<{ id: string; name: string; type: string; default_duration: number }>;
      filters: Array<{ id: string; name: string; params: Record<string, unknown> }>;
      sfx_categories: Array<{ id: string; name: string; tool: string; cost: number; tier: string }>;
      export_presets: Array<{ id: string; name: string; width: number; height: number;
        fps: number; platform: string; burn_subtitles: boolean }>;
      aspect_ratios: Array<{ id: string; name: string; w: number; h: number; use: string }>;
    }>("/presets"),
  importJianying: (draftDir: string) =>
    mutate<{ assets: number; clips: number; tracks: number; skipped: number }>(
      "POST", `/import/jianying?draft_dir=${encodeURIComponent(draftDir)}`),
  // === Session / Lease (P0-10, v0.2 §24-27) ===
  // All Gate-exempt: /lease* and /mutation/check bypass the middleware,
  // /ui/status is a GET.
  uiStatus: (clientKnownRevision?: number) =>
    req<{
      actor: "human" | "agent" | "observe" | "free" | "conflict";
      human_label: string; agent_label: string;
      session_id: string | null; alive: boolean;
      base_revision: number; client_last_known_revision: number | null;
      conflict: boolean;
      ai_affected: Array<{ start_frame: number; end_frame: number; reason: string }>;
      visual_cue: { color: string; text: string };
    }>("/ui/status" + (clientKnownRevision !== undefined
        ? `?client_known_revision=${clientKnownRevision}` : "")),
  // GUI-02: canonical timebase accessor
  getSequence: () =>
    req<{
      sequence_id: string;
      fps: { num: number; den: number };
      width: number; height: number;
      timecode_format: "SMPTE" | "DF" | "NDF";
      drop_frame: boolean;
      project_revision: number;
    }>("/sequence"),
  // GUI-02: Core keymap (semantic binding, no execute endpoint)
  getKeymap: () =>
    req<{ bindings: Array<{
      key: string;
      description: string;
      mutation_op: string;
      params: Record<string, unknown>;
    }> }>("/keyboard/keymap"),
  // GUI-02: Core SnapEngine. Called on drag-end (not per pointermove).
  // Threshold is in frames, bounded (default 8), zoom-independent.
  snap: (frame: number, context: Record<string, unknown>, threshold: number = 8) =>
    req<{
      snapped_frame: number | null;
      target: null | {
        frame: number;
        kind: string;
        label: string;
        clip_id: string;
      };
      delta_frames: number;
    }>("/snap?threshold=" + threshold, {
      method: "POST",
      body: JSON.stringify({ frame, ...context }),
    }),
  getTimemap: (clipId: string) =>
    req<{
      source_start_frame: number;
      source_end_frame: number;
      timeline_start_frame: number;
      speed: number;
      fps: { num: number; den: number };
      duration_frames: number;
    }>(`/clip/${clipId}/timemap`),
  getLease: () =>
    req<{ heldBy: string | null; sessionId: string | null; mode: string | null;
           actor: string | null; baseRevision: number; isAlive: boolean;
           humanLabel: string }>('/lease'),
  acquireLease: (actor: 'human' | 'agent' = 'human', mode: 'edit' | 'propose' | 'observe' = 'edit',
                  baseRevision?: number, humanLabel: string = 'User') =>
    req<{ ok: boolean; sessionId?: string; actor?: string; mode?: string; baseRevision?: number }>(
      '/lease/acquire?' + new URLSearchParams({ actor, mode,
        ...(baseRevision !== undefined ? { baseRevision: String(baseRevision) } : {}),
        humanLabel }).toString(),
      { method: 'POST' }),
  releaseLease: (sessionId: string) =>
    req<{ ok: boolean }>('/lease/release?sessionId=' + sessionId, { method: 'POST' }),
  heartbeatLease: (sessionId: string) =>
    req<{ ok: boolean }>('/lease/heartbeat?sessionId=' + sessionId, { method: 'POST' }),
  handoffLease: (fromSessionId: string, toActor: 'human' | 'agent' = 'agent',
                  toMode: 'edit' | 'propose' | 'observe' = 'edit', toLabel: string = 'Claude') =>
    req<{ ok: boolean; sessionId?: string; actor?: string; mode?: string; humanLabel?: string }>(
      '/lease/handoff?' + new URLSearchParams({ fromSessionId: fromSessionId, toActor, toMode, toLabel }).toString(),
      { method: 'POST' }),
  mutationCheck: (baseRevision: number, sessionId: string = '') =>
    req<{ ok: boolean; currentRevision?: number; error?: string }>(
      '/mutation/check?baseRevision=' + baseRevision +
      (sessionId ? '&sessionId=' + sessionId : ''),
      { method: 'POST' }),
};

