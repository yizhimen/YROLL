// YROLL Manifest v0.1 对应的 TS 类型（与 yroll/core/manifest.py 对齐）

import {
  sessionStore, currentGate, ensureReady, canMutate, GateError,
} from "./session";

export interface TimeRange { start: number; end: number }

export interface Asset {
  asset_id: string;
  type: "video" | "image" | "audio" | "subtitle" | "document";
  path: string;
  origin?: "camera" | "generated" | "screen_record" | "unknown";
  gen?: Record<string, unknown> | null;
  identity: { duration_sec?: number; width?: number; height?: number };
  // GUI-02.3: explicit source timebase (asset's frame rate). May be
  // null if the asset's container has no fps metadata. Distinct
  // from sequence fps (project's timeline timebase).
  source_fps?: { num: number; den: number } | null;
  source_is_cfr?: boolean | null;
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
  // GUI-02: canonical timebase accessor. Falls back to fps_num/fps_den
  // for legacy v0.1 projects that lack `sequence`.
  sequence?: {
    sequence_id?: string;
    fps: { num: number; den: number };
    width?: number;
    height?: number;
    timecode_format?: "SMPTE" | "DF" | "NDF";
    drop_frame?: boolean;
    project_revision?: number;
  };
  fps_num?: number;
  fps_den?: number;
  // GUI-03E: multiple peer Timelines. `timeline` (singular above) is
  // the deprecated legacy accessor (returns the active Timeline);
  // new code MUST go through `timelines[]` + `active_timeline_id`.
  timelines?: Array<{
    timeline_id: string;
    name: string;
    derived_from?: string | null;
    created_at?: string;
    tracks: Track[];
    markers?: Array<Record<string, unknown>>;
    beats?: Array<Record<string, unknown>>;
  }>;
  active_timeline_id?: string;
  default_timeline_id?: string;
  schema_version?: string;
}

// GUI-03E-3: switcher data layer. Lightweight view used by the
// TimelineSwitcher / NewTimelineDialog; the heavy `Project.timelines`
// above is for the editor (carries Track/Marker/Beat payloads).
export interface TimelineSummary {
  timeline_id: string;
  name: string;
  derived_from?: string | null;
  created_at?: string | null;
  track_count: number;
  clip_count: number;
  marker_count: number;
  beat_count: number;
}

export interface TimelinesResponse {
  active_timeline_id: string;
  default_timeline_id: string;
  timelines: TimelineSummary[];
}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const method = (init?.method ?? "GET").toUpperCase();
  const r = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!r.ok) {
    // GUI-03R: surface METHOD + path + status + server detail so a
    // refused write is never silent (the previous "404" only told
    // the user a number, not which call failed).
    const detail = await r.text();
    throw new Error(`${method} ${path} → ${r.status} ${r.statusText} | ${detail}`);
  }
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
  const method = (init.method ?? "GET").toUpperCase();
  const isMutation = method !== "GET" && method !== "HEAD" && method !== "OPTIONS";

  // GUI-03R5-B1: every mutation AWAITS ensureReady() before issuing
  // the request. This closes the "sessionId required for mutations"
  // race that R5-A1 audit found (the window between App mount and
  // the first acquire() resolving).
  if (isMutation) {
    try {
      await ensureReady();
    } catch (e: any) {
      const msg = e?.message ?? "session not ready";
      sessionStore.noteGateError("no_session", msg);
      throw new GateRejection("no_session", 0, msg);
    }
    if (!canMutate(sessionStore.get())) {
      const msg = "session not in EDIT state";
      sessionStore.noteGateError("no_session", msg);
      throw new GateRejection("no_session", 0, msg);
    }
  }

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
    // GUI-03R: same shape as the read path — METHOD + path → status
    // + server detail.
    throw new Error(`${method} ${path} → ${r.status} ${r.statusText} | ${detail}`);
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
  // GUI-03R3-W-A: selection-level delete. ONE Core Operation per
  // user intent (preserves "one user intent = one Operation" rule
  // even for multi-clip actions). The GUI MUST use this path
  // instead of looping removeClip for multi-selection delete.
  //   - ripple=false (default): Delete — remove the clips, preserve gap.
  //   - ripple=true:  Shift+Delete / "Ripple 删除" — remove the
  //                  clips and shift same-track neighbors left.
  // timeline_id is not passed here; the server resolves to the
  // active Timeline (matching the existing removeClip behavior).
  deleteSelection: (
    clipIds: string[],
    ripple: boolean,
    why = "GUI selection delete",
  ) =>
    mutate<{
      deleted: string[];
      ripple: boolean;
      operation_id?: string;
    }>("POST", "/selection/delete", {
      clip_ids: clipIds,
      ripple,
      why,
    }),
  // GUI-03R4-R5: Close Gap + Batch Close Gaps.
  closeGap: (trackId: string, startFrame: number, endFrame: number,
              why = "GUI close gap") =>
    mutate<{
      operation_id: string;
      shifted_clips: number;
      track_id: string;
    }>("POST", "/tracks/close_gap", {
      track_id: trackId,
      start_frame: startFrame,
      end_frame: endFrame,
      why,
    }),
  closeGapsBatch: (trackIds: string[], why = "GUI batch close gaps") =>
    mutate<{
      operation_ids: string[];
      track_count: number;
    }>("POST", "/tracks/close_gaps_batch", {
      track_ids: trackIds,
      why,
    }),
  // GUI-03R3-W-C: resolve or create a track for a drop. Takes
  // STRUCTURAL INTENT ONLY — no pixel coordinates. The GUI has
  // resolved pointer geometry into this intent before calling.
  //   - assetType: 'video' | 'image' | 'audio' | 'subtitle' | 'text'
  //   - preferKind: optional kind hint (one of "video" | "audio" |
  //                  "subtitle" | "text"). When omitted, the asset
  //                  type's primary kind drives.
  //   - insertAfterTrackId: if provided, create a NEW track of the
  //                        right kind (existing tracks keep their
  //                        ids; Core never renumbers).
  ensureTrackForDrop: (
    assetType: string,
    preferKind?: string,
    insertAfterTrackId?: string,
  ) =>
    mutate<{
      track_id: string;
      kind: string;
      clip_ids: string[];
      // and other Track fields, returned as JSON
    }>("POST", "/tracks/ensure_for_drop", {
      asset_type: assetType,
      prefer_kind: preferKind ?? null,
      insert_after_track_id: insertAfterTrackId ?? null,
      why: "GUI drop zone",
    }),
  // R6-D: canonical sibling read API. Returns frame-native intervals
// for every clip on the track so the GUI's cross-track re-clamp
// uses Core state (not DOM-derived style.left). GET, not a
// mutation — does not go through mutate/gated.
trackClips: (trackId: string, timelineId?: string) =>
    req<{
      track_id: string;
      timeline_id: string;
      clips: Array<{ clip_id: string; start_frame: number; end_frame: number }>;
    }>(`/tracks/${trackId}/clips${timelineId ? `?timeline_id=${encodeURIComponent(timelineId)}` : ""}`),
  commit: (note: string) => mutate("POST", `/versions?note=${encodeURIComponent(note)}`),
  // GUI-03D: L1 Timeline Composite Preview. Returns z-ordered
  // visual + audio + subtitle layers at the given timeline frame.
  compositePreview: (timelineFrame: number) =>
    req<{
      timeline_frame: number;
      fps: { num: number; den: number };
      is_black: boolean;
      visual_layers: Array<{
        track_id: string;
        layer_index: number;
        kind: string;
        clip_id: string;
        asset_id: string;
        asset_path: string;
        source_frame: number;
        source_seconds: number;
        source_fps: { num: number; den: number } | null;
        timeline_start_frame: number;
        timeline_end_frame: number;
        transform: Record<string, unknown>;
      }>;
      audio_layers: Array<{
        track_id: string;
        layer_index: number;
        kind: string;
        clip_id: string;
        asset_id: string;
        asset_path: string;
        source_frame: number;
        source_seconds: number;
        source_fps: { num: number; den: number } | null;
        timeline_start_frame: number;
        timeline_end_frame: number;
        transform: Record<string, unknown>;
      }>;
      subtitle_texts: string[];
    }>(`/preview/at_frame?frame=${timelineFrame}`),
  // GUI-03D.1: Preview Plan snapshot for caching. Returns the
  // structural layout of all clips per track (timeline-frame
  // range, source-frame range, source_fps, etc.) for a given
  // project_revision. The GUI caches this locally; per-frame
  // playback resolves the active layer via `active_layer_at`
  // (no per-frame HTTP).
  // GUI-03E-3: switcher data layer.
  //
  // listTimelines():  gate-exempt (GET); returns {active_timeline_id,
  //   default_timeline_id, timelines[]} with lightweight summaries.
  // addTimeline / switchActiveTimeline / duplicateTimeline /
  // deleteTimeline: all mutations go through `mutate()` so the
  // Mutation Gate is enforced (sessionId + baseRevision injected).
  // Every Timeline-lifecycle response includes the Core-resolved
  // `active_timeline_id` so the GUI can verify the call's effect —
  // this is the defense against stale-response races (see
  // GUI-03E-3-F).
  listTimelines: () => req<TimelinesResponse>("/timelines"),
  addTimeline: (name: string, derivedFrom?: string) =>
    mutate<{
      timeline_id: string;
      name: string;
      derived_from: string | null;
    }>("POST", "/timelines", {
      name,
      derived_from: derivedFrom ?? "",
    }),
  switchActiveTimeline: (timelineId: string) =>
    mutate<{ active_timeline_id: string }>(
      "POST", `/timelines/${encodeURIComponent(timelineId)}/switch`),
  duplicateTimeline: (timelineId: string, newName?: string) =>
    mutate<{
      timeline_id: string;
      name: string;
      active_timeline_id: string;
    }>("POST", `/timelines/${encodeURIComponent(timelineId)}/duplicate`, {
      new_name: newName ?? "",
    }),
  deleteTimeline: (timelineId: string) =>
    mutate<{
      ok: boolean;
      active_timeline_id: string;
      default_timeline_id: string;
    }>("DELETE", `/timelines/${encodeURIComponent(timelineId)}`),

  previewPlan: (opts: { timeline_id?: string } = {}) => {
    const qs = new URLSearchParams();
    if (opts.timeline_id) qs.set("timeline_id", opts.timeline_id);
    return req<{
      project_revision: number;
      timeline_id: string;
      fps: { num: number; den: number };
      tracks: Array<Array<{
        track_id: string;
        layer_index: number;
        kind: string;
        clip_id: string;
        asset_id: string;
        asset_type: string;
        asset_path: string;
        timeline_start_frame: number;
        timeline_end_frame: number;
        source_start_frame: number;
        source_end_frame: number;
        source_fps: { num: number; den: number } | null;
        transform: Record<string, unknown>;
      }>>;
      subtitle_ranges: Array<{
        start_frame: number;
        end_frame: number;
        text: string;
      }>;
    }>(`/preview/plan${qs.toString() ? `?${qs}` : ""}`);
  },
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
  // GUI-03R6: frame-native addClip. Mirrors addImageClip — all three
// time fields are integer frames. The Core converts to seconds at
// the storage boundary. The GUI MUST pass frames; passing seconds
// into these fields is a contract violation that the server rejects.
addClip: (assetId: string,
          sourceStartFrame: number,
          sourceEndFrame: number,
          timelineStartFrame: number,
          trackId: string | null,
          why = "") =>
    mutate<Clip>("POST", "/clips", {
      asset_id: assetId,
      source_start_frame: sourceStartFrame,
      source_end_frame: sourceEndFrame,
      timeline_start_frame: timelineStartFrame,
      track_id: trackId,
      why,
    }),
  // GUI-03B: image-first-class media. Frame-native coordinates; the
  // server derives source_range = (0, 1/seq_fps) and speed=1.0.
  addImageClip: (
    assetId: string,
    timelineStartFrame: number,
    timelineDurationFrames: number,
    trackId: string | null,
    why = "",
  ) => mutate<Clip>("POST", "/clips/add_image", {
    asset_id: assetId,
    timeline_start_frame: timelineStartFrame,
    timeline_duration_frames: timelineDurationFrames,
    track_id: trackId, why,
  }),
  trimImageClip: (
    clipId: string,
    timelineStartFrame?: number,
    timelineEndFrame?: number,
    why = "",
  ) => mutate<Clip>("POST", `/clips/${clipId}/trim_image`, {
    timeline_start_frame: timelineStartFrame,
    timeline_end_frame: timelineEndFrame,
    why,
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
      sequence_fps?: { num: number; den: number };
      source_fps?: { num: number; den: number };
      fps: { num: number; den: number };
      duration_frames: number;
    }>(`/clip/${clipId}/timemap`),
  // Raw fetch helpers — used by timemap-cache.ts so the cache layer
  // can build a typed URL with explicit src_fps query params.
  getTimemapRaw: (path: string) =>
    req<{
      source_start_frame: number;
      source_end_frame: number;
      timeline_start_frame: number;
      speed: number;
      sequence_fps?: { num: number; den: number };
      source_fps?: { num: number; den: number };
      fps: { num: number; den: number };
      duration_frames: number;
    }>(path),
  getTimemapAtFrameRaw: (path: string) =>
    req<{
      source_frame: number;
      timeline_frame: number;
      source_fps: { num: number; den: number };
    }>(path),
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

