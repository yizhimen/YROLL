// YROLL Manifest v0.1 对应的 TS 类型（与 yroll/core/manifest.py 对齐）

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

export const api = {
  project: () => req<Project>("/project"),
  operations: () => req<Operation[]>("/operations"),
  trim: (clipId: string, newSourceStart?: number, newSourceEnd?: number, why = "") =>
    req(`/clips/${clipId}/trim`, {
      method: "POST",
      body: JSON.stringify({ new_source_start: newSourceStart ?? null, new_source_end: newSourceEnd ?? null, why }),
    }),
  split: (clipId: string, atSourceTime: number, why = "") =>
    req(`/clips/${clipId}/split`, { method: "POST", body: JSON.stringify({ at_source_time: atSourceTime, why }) }),
  move: (clipId: string, newTimelineStart: number, why = "", trackId?: string) =>
    req(`/clips/${clipId}/move`, { method: "POST", body: JSON.stringify({ new_timeline_start: newTimelineStart, new_track_id: trackId ?? null, why }) }),
  speed: (clipId: string, speed: number, why = "") =>
    req(`/clips/${clipId}/speed`, { method: "POST", body: JSON.stringify({ speed, why }) }),
  volume: (clipId: string, volume: number, why = "") =>
    req(`/clips/${clipId}/volume`, { method: "POST", body: JSON.stringify({ volume, why }) }),
  removeClip: (clipId: string, why = "", ripple = false) =>
    req(`/clips/${clipId}?why=${encodeURIComponent(why)}${ripple ? "&ripple=true" : ""}`, { method: "DELETE" }),
  commit: (note: string) => req(`/versions?note=${encodeURIComponent(note)}`, { method: "POST" }),
  render: (burnSubtitles = false, width = 1080, name = "preview.mp4") =>
    req<{ preview: string }>(
      `/render?burn_subtitles=${burnSubtitles}&width=${width}&name=${encodeURIComponent(name)}`,
      { method: "POST" }),
  chat: (message: string, selectedClip: string | null, playhead: number) =>
    req<{
      reply: string;
      applied: string[];
      errors: Array<{ error: string }>;
      problems_reported: Array<{ problem: Problem; solutions: Solution[] }>;
    }>("/chat", {
      method: "POST",
      body: JSON.stringify({ message, selected_clip: selectedClip, playhead }),
    }),
  reportProblem: (description: string, category: string, targetClip: string | null,
                  timeRange?: TimeRange) =>
    req<{ problem: Problem; solutions: Solution[] }>("/problems", {
      method: "POST",
      body: JSON.stringify({ description, category, target_clip: targetClip, time_range: timeRange ?? null }),
    }),
  problems: () => req<{ problems: Problem[]; solutions: Solution[] }>("/problems"),
  executeSolution: (solutionId: string) =>
    req<{ status: string; operation_id?: string; message?: string }>("/solutions/execute", {
      method: "POST",
      body: JSON.stringify({ solution_id: solutionId }),
    }),
  inferLinks: () => req<{ inferred: number; total: number }>("/links/infer", { method: "POST" }),
  impact: (clipId: string, op = "remove") =>
    req<{
      op: string;
      will_sync: Array<{ clip_id: string; kind: string; text: string }>;
      will_prompt: Array<{ clip_id: string; kind: string; text: string }>;
      untouched: Array<{ clip_id: string; kind: string; text: string }>;
    }>(`/clips/${clipId}/impact?op=${op}`),
  delogo: (clipId: string, region: { x: number; y: number; w: number; h: number }, why = "") =>
    req(`/clips/${clipId}/delogo?why=${encodeURIComponent(why)}`, {
      method: "POST",
      body: JSON.stringify(region),
    }),
  denoise: (clipId: string, strength = 12, why = "") =>
    req(`/clips/${clipId}/denoise?strength=${strength}&why=${encodeURIComponent(why)}`, { method: "POST" }),
  loudness: (clipId: string) =>
    req<{ after: { mean_db: number; max_db: number } }>(`/clips/${clipId}/loudness`, { method: "POST" }),
  silenceRemove: (clipId: string, why = "") =>
    req(`/clips/${clipId}/silence-remove?why=${encodeURIComponent(why)}`, { method: "POST" }),
  importAsset: async (file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    const r = await fetch("/assets/import", { method: "POST", body: fd });
    if (!r.ok) throw new Error(`${r.status}: ${await r.text()}`);
    return r.json() as Promise<{ asset: Asset; clip: Clip | null; deduped: boolean }>;
  },
  addClip: (assetId: string, sourceStart: number, sourceEnd: number,
            timelineStart: number, trackId: string, why = "") =>
    req<Clip>("/clips", {
      method: "POST",
      body: JSON.stringify({
        asset_id: assetId, source_start: sourceStart, source_end: sourceEnd,
        timeline_start: timelineStart, track_id: trackId, why,
      }),
    }),
  revert: (operationId: string, why = "") =>
    req("/revert", { method: "POST", body: JSON.stringify({ operation_id: operationId, why }) }),
  volumeRange: (clipId: string, volume: number, start: number, end: number, why = "") =>
    req(`/clips/${clipId}/volume-range?volume=${volume}&start=${start}&end=${end}&why=${encodeURIComponent(why)}`,
      { method: "POST" }),
  removeAdjustment: (clipId: string, adjustmentId: string, why = "") =>
    req(`/clips/${clipId}/adjustments/${adjustmentId}?why=${encodeURIComponent(why)}`,
      { method: "DELETE" }),
  editSubtitle: (clipId: string, text: string, why = "") =>
    req(`/clips/${clipId}/subtitle?text=${encodeURIComponent(text)}&why=${encodeURIComponent(why)}`,
      { method: "POST" }),
  setSubtitleStyle: (clipId: string, style: Record<string, unknown>, why = "") =>
    req(`/clips/${clipId}/subtitle-style?why=${encodeURIComponent(why)}`, {
      method: "POST", body: JSON.stringify(style),
    }),
  addSubtitle: (text: string, start: number, end: number, why = "") =>
    req<Clip>(`/subtitles?text=${encodeURIComponent(text)}&start=${start}&end=${end}&why=${encodeURIComponent(why)}`,
      { method: "POST" }),
  addTrack: (kind: string, trackId?: string) =>
    req<Track>(`/tracks?kind=${kind}${trackId ? `&track_id=${trackId}` : ""}`, { method: "POST" }),
  setTransform: (clipId: string, transform: Record<string, number>, why = "") =>
    req(`/clips/${clipId}/transform?why=${encodeURIComponent(why)}`, {
      method: "POST", body: JSON.stringify(transform),
    }),
  setFade: (clipId: string, fadeIn: number, fadeOut: number, why = "") =>
    req(`/clips/${clipId}/fade?fade_in=${fadeIn}&fade_out=${fadeOut}&why=${encodeURIComponent(why)}`,
      { method: "POST" }),
  setDissolve: (clipId: string, duration: number, kind = "fade", why = "") =>
    req(`/clips/${clipId}/dissolve?duration=${duration}&kind=${kind}&why=${encodeURIComponent(why)}`,
      { method: "POST" }),
  searchTranscripts: (q: string) =>
    req<{ results: Array<{ clip_id: string; timeline: number; text: string; track_id: string }> }>(
      `/search-transcripts?q=${encodeURIComponent(q)}`),
  setMuted: (clipId: string, muted: boolean, why = "") =>
    req(`/clips/${clipId}/mute?muted=${muted}&why=${encodeURIComponent(why)}`, { method: "POST" }),
  renderRange: (start: number, end: number, burnSubtitles: boolean, width: number, name: string) =>
    req<{ preview: string }>(
      `/render?start=${start}&end=${end}&burn_subtitles=${burnSubtitles}&width=${width}&name=${encodeURIComponent(name)}`,
      { method: "POST" }),
  renderStatus: () =>
    req<{ status: string; step: string; done: number; total: number; error: string; preview: string }>(
      "/render/status"),
  setTrackMuted: (trackId: string, muted: boolean, why = "") =>
    req(`/tracks/${trackId}/mute?muted=${muted}&why=${encodeURIComponent(why)}`, { method: "POST" }),
  setTrackLocked: (trackId: string, locked: boolean, why = "") =>
    req(`/tracks/${trackId}/lock?locked=${locked}&why=${encodeURIComponent(why)}`, { method: "POST" }),
  setTrackHidden: (trackId: string, hidden: boolean, why = "") =>
    req(`/tracks/${trackId}/hide?hidden=${hidden}&why=${encodeURIComponent(why)}`, { method: "POST" }),
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
    req(`/clips/${clipId}/voice-replace?text=${encodeURIComponent(text)}&why=${encodeURIComponent(why)}`,
      { method: "POST" }),
  setColor: (clipId: string, params: Record<string, number>, why = "") =>
    req(`/clips/${clipId}/color?why=${encodeURIComponent(why)}`, { method: "POST", body: JSON.stringify(params) }),
  setFlip: (clipId: string, horizontal: boolean, vertical: boolean, why = "") =>
    req(`/clips/${clipId}/flip?horizontal=${horizontal}&vertical=${vertical}&why=${encodeURIComponent(why)}`, { method: "POST" }),
  setOpacity: (clipId: string, opacity: number, why = "") =>
    req(`/clips/${clipId}/opacity?opacity=${opacity}&why=${encodeURIComponent(why)}`, { method: "POST" }),
  setCrop: (clipId: string, left: number, top: number, right: number, bottom: number, why = "") =>
    req(`/clips/${clipId}/crop?left=${left}&top=${top}&right=${right}&bottom=${bottom}&why=${encodeURIComponent(why)}`, { method: "POST" }),
  setReverse: (clipId: string, why = "") =>
    req(`/clips/${clipId}/reverse?why=${encodeURIComponent(why)}`, { method: "POST" }),
  setTransform2d: (clipId: string, params: Record<string, number | boolean>, why = "") =>
    req(`/clips/${clipId}/transform2d?why=${encodeURIComponent(why)}`, { method: "POST", body: JSON.stringify(params) }),
  resetVisual: (clipId: string, why = "") =>
    req(`/clips/${clipId}/reset-visual?why=${encodeURIComponent(why)}`, { method: "POST" }),
  costs: () =>
    req<{ total: number; currency: string; by_tool: Record<string, { count: number; cost: number }>; by_who: Record<string, number> }>("/costs"),
  exportPackage: (cfg: {
    width: number; burn_subtitles: boolean; title: string;
    description: string; tags: string; platform: string;
    cover_offset_sec: number;
  }) =>
    req<{ started: boolean }>(
      `/export/package?width=${cfg.width}&burn_subtitles=${cfg.burn_subtitles}` +
      `&title=${encodeURIComponent(cfg.title)}` +
      `&description=${encodeURIComponent(cfg.description)}` +
      `&tags=${encodeURIComponent(cfg.tags)}` +
      `&platform=${encodeURIComponent(cfg.platform)}` +
      `&cover_offset_sec=${cfg.cover_offset_sec}`,
      { method: "POST" }),
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
    req<{ assets: number; clips: number; tracks: number; skipped: number }>(
      `/import/jianying?draft_dir=${encodeURIComponent(draftDir)}`, { method: "POST" }),
  // === Edit Lease (P0-10) ===
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

