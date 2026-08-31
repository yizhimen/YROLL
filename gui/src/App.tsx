import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, Clip, Project } from "./api";
import { sessionStore } from "./session";
import { useProjectSequence } from "./sequence";
import { useCoreKeymap } from "./keymap";
import {
  frameToRulerSeconds,
  framesToTimecode,
  pxPerFrame,
  roundHalfAwayFromZero,
  type Rational,
} from "./frames";
import { fitContentEndSec, playbackDurationSec }
  from "./fit-content";
import Timeline from "./components/Timeline";
import TimelineSwitcher from "./components/TimelineSwitcher";
import NewTimelineDialog from "./components/NewTimelineDialog";
import ChatPanel from "./components/ChatPanel";
import ClipWorkspace from "./components/ClipWorkspace";
import MenuBar from "./components/MenuBar";
import EditLease from "./components/EditLease";
import AssetPanel from "./components/AssetPanel";
import OpsPanel from "./components/OpsPanel";
import PreviewPlayer, { AspectRatio } from "./components/PreviewPlayer";
import VisualAdjustPanel from "./components/VisualAdjustPanel";
import SubtitleEditor from "./components/SubtitleEditor";
import ExportPanel from "./components/ExportPanel";
import ResizeHandle from "./components/ResizeHandle";

interface Region { x: number; y: number; w: number; h: number }

/** Convert a KeyboardEvent into the exact combo string Core uses in
 *  its keymap table. Examples:
 *    e.key="J",  e.shiftKey=false  → "J"
 *    e.key="j",  e.shiftKey=true   → "Shift+J"
 *    e.key="L",  e.shiftKey=false  → "L"
 *    e.key="ArrowLeft", shift=true → "Shift+ArrowLeft"
 *    e.key=" " (Space)            → "Space"
 *
 *  The Core keymap canonicalizes letter keys to UPPERCASE. The
 *  browser reports `e.key` case-aware ("j" lower, "J" upper when
 *  shift held) — we uppercase single-character keys here so the
 *  lookup matches. */
function eventToKeyCombo(e: KeyboardEvent): string {
  let key = e.key;
  if (key.length === 1) key = key.toUpperCase();
  // Special keys (Space, ArrowLeft, etc.) stay as-is — they're
  // already in Core's canonical form.
  if (key === " ") return "Space";
  return e.shiftKey && key !== "Shift" ? `Shift+${key}` : key;
}

// GUI-03R3-W-D: Help dialog label helpers.
//
// Each helper pulls the relevant entries from the loaded Core
// keymap and renders a short Chinese label. The label format is
// `Key 显示名` (e.g. "J/L ±1 frame"). If the binding is missing
// from the keymap, we fall back to a plain Chinese description
// (no fake numbers / no fake step sizes). This guarantees the
// Help dialog never invents shortcut semantics.
type KMAction = {
  name: string;
  key: string;
  description: string;
  deltaFrames: number;
  params: Record<string, unknown>;
};

const fmtFrames = (n: number): string => {
  // Match Core keymap's description vocabulary: "1 frame" / "10 frames"
  const abs = Math.abs(n);
  return `${abs} frame${abs === 1 ? "" : "s"}`;
};

const helpBindingLabel = (
  keymap: KMAction[], combo: string, fallback: string,
): string => {
  const b = keymap.find((a) => a.key === combo);
  if (!b) return `${combo} ${fallback}`;
  return `${combo} ${b.description}`;
};

// J/L (and Shift+J/Shift+L) — frame step from keymap params.
const helpNudgeLabel = (keymap: KMAction[], base: string, fwd: string): string => {
  const b = keymap.find((a) => a.key === base);
  const f = keymap.find((a) => a.key === fwd);
  if (!b || !f) return `${base}/${fwd} ${fmtFrames(1)}（Shift ±${fmtFrames(10)}）`;
  const small = Math.abs(b.deltaFrames);
  const sb = keymap.find((a) => a.key === `Shift+${base}`);
  const sf = keymap.find((a) => a.key === `Shift+${fwd}`);
  const large = sb && sf ? Math.abs(sb.deltaFrames) : 10;
  return `${base}/${fwd} ±${fmtFrames(small)}（Shift ±${fmtFrames(large)}）`;
};

// ArrowLeft / ArrowRight (and Shift variants).
const helpArrowNudgeLabel = (keymap: KMAction[]): string => {
  const l = keymap.find((a) => a.key === "ArrowLeft");
  const r = keymap.find((a) => a.key === "ArrowRight");
  if (!l || !r) return "←/→ ±1 frame（Shift ±10 frames）";
  const small = Math.abs(l.deltaFrames);
  const sl = keymap.find((a) => a.key === "Shift+ArrowLeft");
  const sr = keymap.find((a) => a.key === "Shift+ArrowRight");
  const large = sl && sr ? Math.abs(sl.deltaFrames) : 10;
  return `←/→ ±${fmtFrames(small)}（Shift ±${fmtFrames(large)}）`;
};

// ArrowUp / ArrowDown — boundary jump.
const helpBoundaryLabel = (keymap: KMAction[]): string => {
  const u = keymap.find((a) => a.key === "ArrowUp");
  const d = keymap.find((a) => a.key === "ArrowDown");
  if (!u || !d) return "↑/↓ 跳剪辑点";
  return "↑/↓ 跳剪辑点";
};

// Home — center playhead in viewport.
const helpCenterLabel = (keymap: KMAction[]): string => {
  const h = keymap.find((a) => a.key === "Home");
  if (!h) return "Home 播放头居中";
  return `Home ${h.description}`;
};

// Combined Space/K toggle label.
const helpKeyLabel = (
  keymap: KMAction[], combos: string[], fallback: string,
): string => {
  const names = combos.filter((c) => keymap.some((a) => a.key === c));
  if (names.length === 0) return `${combos.join("/")} ${fallback}`;
  return `${names.join("/")} ${fallback}`;
};

export default function App() {
  const [project, setProject] = useState<Project | null>(null);
  // GUI-03E-3: activeTimelineId is the GUI's single source of truth
  // for Timeline context. Switcher is fully controlled by this
  // state. We initialize from the project's `active_timeline_id`
  // when the project first loads; subsequent switches are driven by
  // user clicks. The server response's `active_timeline_id` is
  // authoritative for delete-active — we use it instead of guessing.
  const [activeTimelineId, setActiveTimelineId] = useState<string>("");
  const [selected, setSelected] = useState<string | null>(null);
  const [selectedSet, setSelectedSet] = useState<Set<string>>(new Set());
  // Selected clip (used by keyboard handlers in the useEffect below).
  const clip = project && selected ? project.clips[selected] : null;
  const [workspaceClip, setWorkspaceClip] = useState<string | null>(null);
  const [pendingDelete, setPendingDelete] = useState<{
    clipId: string;
    impact: Awaited<ReturnType<typeof api.impact>>;
  } | null>(null);
  // GUI-02: playheadFrame is canonical in integer frames. The float
  // seconds interface is gone. Display via framesToTimecode.
  const [playheadFrame, setPlayheadFrame] = useState(0);
  // pxPerSec is the *perceived* px-per-second (stable across FPS).
  // Internally we anchor in frames: pxPerFrame = pxPerSec * fps.den/fps.num.
  // GUI-03R: default 30 px/sec — at 30 fps that's ~1 px/frame, the
  // frame-native feel. User can still zoom via the slider (4-60).
  // GUI-03R3-2 P1-1: default view = Fit Content for newly opened
  // projects (no persisted viewport state). We set a sane initial
  // value (30 px/sec) and immediately run the Fit Content effect
  // when the project loads.
  const [pxPerSec, setPxPerSec] = useState(30);
  // Sequence (canonical timebase) from /sequence
  const seq = useProjectSequence();
  // Core keymap (semantic binding) from /keyboard/keymap
  const keymap = useCoreKeymap();
  const pxPerFrameVal = useMemo(
    () => pxPerFrame(pxPerSec, seq.fps),
    [pxPerSec, seq.fps],
  );
  const [status, setStatus] = useState<{ ok: boolean; text: string }>({ ok: true, text: "加载中…" });
  const [previewVersion, setPreviewVersion] = useState(0);
  // Preview 框选（去水印）：框选模式 + 归一化坐标草稿
  const [regionMode, setRegionMode] = useState(false);
  const [regionDraft, setRegionDraft] = useState<Region | null>(null);
  const dragStart = useRef<{ x: number; y: number } | null>(null);
  const previewRef = useRef<HTMLDivElement | null>(null);
  // GUI-03R3-W-D: Timeline exposes its .timeline-content element so
  // the keyboard dispatcher (Home = _center_playhead) can scroll the
  // playhead into the middle of the visible viewport. The Content
  // Origin (frame 0 = x=0 inside ContentViewport) is NOT touched.
  const timelineContentRef = useRef<HTMLDivElement | null>(null);
  // 时间范围选择（蓝图 §2.4）+ 操作历史刷新 + Inspector 页签
  const [selRange, setSelRange] = useState<[number, number] | null>(null);
  const [rangeVolume, setRangeVolume] = useState(0.3);
  const [opsKey, setOpsKey] = useState(0);
  const [inspectorTab, setInspectorTab] = useState<"props" | "history">("props");
  const [burnSubs, setBurnSubs] = useState(false);  // 渲染时烧录字幕（分发成片用）
  // 视窗比例 / 字幕编辑器 / 导出面板 / Presets
  const [aspect, setAspect] = useState<AspectRatio>("16:9");
  const [subtitleEdit, setSubtitleEdit] = useState<{
    clipId: string; text: string;
    style: Record<string, unknown>; start: number; end: number;
    track_id?: string;
  } | null>(null);
  const [exportOpen, setExportOpen] = useState(false);
  const [presets, setPresets] = useState<Awaited<ReturnType<typeof api.presets>> | null>(null);
  // GUI-03R3-W-C: track the asset currently being dragged. The
  // Timeline reads this to label the "below-tracks" drop zone
  // (V/A/T). Set by AssetPanel's onDragStart; cleared on dragend.
  const [draggingAssetKind, setDraggingAssetKind] = useState<
    "video" | "image" | "audio" | "subtitle" | "text" | null>(null);
  // 面板宽度（可拖动分界线）
  const [assetW, setAssetW] = useState(260);
  // GUI-03R3-W-D: track header column width. Range 80–300px,
  // default 160. Persisted in localStorage. Resizing the column
  // does NOT shift the Timeline Content Origin (frame 0 stays at
  // x=0 inside .timeline-content); it only widens the OUTSIDE-
  // coord-space label column.
  const HEADER_W_MIN = 80;
  const HEADER_W_MAX = 300;
  const HEADER_W_DEFAULT = 160;
  const HEADER_W_STORAGE = "yroll.timelineHeaderWidth.v1";
  const [headerW, setHeaderW] = useState<number>(() => {
    try {
      const raw = localStorage.getItem(HEADER_W_STORAGE);
      if (!raw) return HEADER_W_DEFAULT;
      const n = parseInt(raw, 10);
      if (!Number.isFinite(n)) return HEADER_W_DEFAULT;
      return Math.min(HEADER_W_MAX, Math.max(HEADER_W_MIN, n));
    } catch { return HEADER_W_DEFAULT; }
  });
  const clampHeaderW = (n: number): number => {
    // Math.max/min(NaN, x) === NaN — guard against non-finite input
    // so the resize handle can never store a NaN width.
    if (!Number.isFinite(n)) return HEADER_W_DEFAULT;
    return Math.min(HEADER_W_MAX, Math.max(HEADER_W_MIN, n));
  };
  const setHeaderWPersisted = (n: number) => {
    const clamped = clampHeaderW(n);
    setHeaderW(clamped);
    try { localStorage.setItem(HEADER_W_STORAGE, String(clamped)); } catch {}
  };
  // GUI-03R3-W-D: stable ref for the resize-handle callback. The
  // pointermove closure inside the Timeline runs every frame and
  // would otherwise capture a stale `headerW` from the first
  // render — making subsequent moves reset the width back to the
  // starting value. Read the latest value via a ref instead.
  const headerWRef = useRef(headerW);
  useEffect(() => { headerWRef.current = headerW; }, [headerW]);
  const onHeaderWidthDelta = useCallback((d: number) => {
    setHeaderWPersisted(headerWRef.current + d);
  }, []);
  const [snapMode, setSnapMode] = useState<"always" | "alt" | "off">("always");
  const [highlightRel, setHighlightRel] = useState(false);
  // GUI-03C: when false (default), the Timeline hides tracks with
  // no clips. Toggle to inspect / debug the allocation policy.
  const [showEmptyTracks, setShowEmptyTracks] = useState(false);
  const [inspectorW, setInspectorW] = useState(260);
  // GUI-03R5-B2 (Decision 3): Timeline height with viewport-aware
  // bounds. Defaults to 240px (was 280), clamp to [160, 60% of
  // viewport height] (was [150, 700]). The 60% cap ensures the
  // Viewer always has at least 40% of the screen on small monitors.
  const [timelineH, setTimelineH] = useState(240);  // 时间线高度
  const TIMELINE_H_DEFAULT = 240;
  const TIMELINE_H_MIN = 160;
  const TIMELINE_H_MAX_PCT = 0.6;  // ≤60% of viewport height
  // 台词搜索定位
  const [searchQ, setSearchQ] = useState("");
  const [searchHits, setSearchHits] = useState<Array<{ clip_id: string; timeline: number; text: string }>>([]);
  // 渲染进度（后台任务轮询）
  const [renderJob, setRenderJob] = useState<{ status: string; step: string; done: number; total: number; error: string; preview: string } | null>(null);
  const pollRender = (onDone: (preview: string) => void) => {
    const timer = setInterval(async () => {
      try {
        const job = await api.renderStatus();
        setRenderJob(job);
        if (job.status === "done") {
          clearInterval(timer);
          setRenderJob(null);
          onDone(job.preview);
        } else if (job.status === "error") {
          clearInterval(timer);
          setRenderJob(null);
          setStatus({ ok: false, text: `渲染失败：${job.error}` });
        }
      } catch { /* 网络抖动忽略，下轮再试 */ }
    }, 500);
  };
  const startRender = () =>
    run(async () => {
      await api.render(burnSubs);
      pollRender(() => {
        setPreviewVersion((v) => v + 1);
        setStatus({ ok: true, text: "渲染完成" });
      });
    }, "渲染已开始");

  // 加载 Presets（字体/字幕样式/转场/滤镜/音效/导出/视窗比例）
  useEffect(() => {
    api.presets().then(setPresets).catch((e) =>
      console.warn("加载 presets 失败", e));
  }, []);

  const [showHelp, setShowHelp] = useState(false);
  // 素材点击预览（覆盖预览窗，看完返回时间轴）
  const [previewAsset, setPreviewAsset] = useState<{ url: string; isImage: boolean; label: string } | null>(null);
  // I/O 点（选区导出）
  const [inPoint, setInPoint] = useState<number | null>(null);
  const [outPoint, setOutPoint] = useState<number | null>(null);

  useEffect(() => {
    if (!searchQ.trim()) { setSearchHits([]); return; }
    const timer = setTimeout(() => {
      api.searchTranscripts(searchQ.trim())
        .then((r) => setSearchHits(r.results))
        .catch(() => setSearchHits([]));
    }, 300);
    return () => clearTimeout(timer);
  }, [searchQ]);

  const refresh = async () => {
    try {
      const fresh = await api.project();
      setProject(fresh);
      // Authoritative sync from server (handles delete-active where
      // the Core selected the Open-Order replacement).
      const serverActive =
        fresh.active_timeline_id || (fresh.timelines?.[0]?.timeline_id ?? "");
      if (serverActive) setActiveTimelineId(serverActive);
      setOpsKey((k) => k + 1);  // 操作历史跟着工程状态走
      setStatus({ ok: true, text: "已连接 YROLL Server" });
    } catch (e) {
      setStatus({ ok: false, text: `连接失败：${e}` });
    }
  };

  useEffect(() => {
    refresh();
  }, []);

  // GUI-03E-3: New Timeline dialog state.
  const [newTimelineOpen, setNewTimelineOpen] = useState(false);

  // Switch active Timeline. Optimistic update of local state so the
  // Preview/cache refetches scoped to the new Timeline immediately;
  // if the server response disagrees (rare — only if a deletion
  // raced), the response's `active_timeline_id` wins.
  const switchTimeline = async (timelineId: string) => {
    const previous = activeTimelineId;
    setActiveTimelineId(timelineId);  // optimistic
    // Reset Timeline-local editor state — switching context does
    // NOT belong to the content Undo stack; it is navigation. We
    // also clear playhead to 0 (Timeline A's playhead is meaningless
    // in Timeline B).
    setSelected(null);
    setSelectedSet(new Set());
    setPlayheadFrame(0);
    try {
      const r = await api.switchActiveTimeline(timelineId);
      // Server is authoritative: if it disagrees with our optimistic
      // pick, use its value (Open-Order races).
      if (r.active_timeline_id !== timelineId) {
        setActiveTimelineId(r.active_timeline_id);
      }
      // Re-sync the whole project (Timeline-local data may have
      // shifted) without bumping the local opsKey (this is a
      // navigation, not an edit).
      await refresh();
    } catch (e) {
      // Roll back on failure.
      setActiveTimelineId(previous);
      setStatus({ ok: false, text: `切版本失败：${e}` });
    }
  };

  // Delete a Timeline. Server returns the Open-Order-resolved
  // replacement; we use it as the authoritative next-active.
  const deleteTimeline = async (timelineId: string) => {
    try {
      const r = await api.deleteTimeline(timelineId);
      // Server-resolved replacement.
      setActiveTimelineId(r.active_timeline_id);
      setSelected(null);
      setSelectedSet(new Set());
      setPlayheadFrame(0);
      await refresh();
    } catch (e) {
      setStatus({ ok: false, text: `删除版本失败：${e}` });
    }
  };

  // Create a new Timeline (empty or duplicate). Parent owns the
  // mutation so the Mutation Gate stays in one place.
  const createTimeline = async (
    name: string,
    mode: "empty" | "duplicate",
  ) => {
    try {
      if (mode === "duplicate") {
        const r = await api.duplicateTimeline(activeTimelineId, name);
        // GUI-03E-4: server has already made the duplicate active.
        // Server is authoritative (Open Order race-safe).
        setActiveTimelineId(r.active_timeline_id);
      } else {
        // Empty Timeline: do NOT switch to it; user explicitly
        // creates a side-Timeline and stays on the current one
        // for editing. The new Timeline appears as a chip in the
        // switcher for later use.
        await api.addTimeline(name);
      }
      // Switcher refresh; selected/playhead reset (timeline-local
      // editor context may have shifted). This is navigation, NOT
      // content Undo.
      setSelected(null);
      setSelectedSet(new Set());
      setPlayheadFrame(0);
      setNewTimelineOpen(false);
      await refresh();
    } catch (e) {
      setStatus({ ok: false, text: `新增版本失败：${e}` });
    }
  };

  // GUI-03E-3: when the project loads, sync activeTimelineId from
  // the server's source of truth. This handles legacy single-
  // Timeline projects (which lack active_timeline_id but the Core
  // synthesizes "main") and any reload that arrived after a
  // delete-active cycle where we missed the response.
  useEffect(() => {
    if (!project) return;
    const fromProject = project.active_timeline_id || "main";
    if (fromProject !== activeTimelineId) {
      setActiveTimelineId(fromProject);
    }
    // Intentionally only re-run when the project object changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [project]);

  // GUI-03R: helper for the active path. The deprecated
  // `project.timeline` (singular) alias is still served by Core for
  // legacy compatibility but reads of it from the active editing path
  // are forbidden (03E-3 spec + 03R). All new call sites must go
  // through this helper.
  const activeTimeline = project?.timelines?.find(
    (tl) => tl.timeline_id === activeTimelineId,
  ) ?? project?.timelines?.[0];
  const activeTimelineTracks = activeTimeline?.tracks ?? [];

  // GUI-01: session lifecycle. initLocal() restores our sessionId from
  // localStorage; startPolling() reconciles owner/revision/conflict against
  // /ui/status and heartbeats the lease. api.mutate() reads the same store,
  // so every write carries the Gate.
  useEffect(() => {
    sessionStore.initLocal();
    sessionStore.startPolling();
    return () => sessionStore.stopPolling();
  }, []);

  // GUI-03R3-2 P1-1: Fit Content on first project load. Runs once
  // when the project is available — computes pxPerSec so the longest
  // VISIBLE clip's end fits into the visible timeline-content area.
  // The default zoom (30 px/sec) is a placeholder until the effect
  // runs. We also early-return if the user has already set zoom in
  // this session (via slider or "适配内容" button).
  //
  // GUI-03R4-R2: hidden tracks (track.hidden === true) are excluded
  // from the extent — a hidden track is invisible to the Viewer, so
  // its tail must not drag the fit-content zoom out. We walk the
  // active Timeline's tracks, skip hidden ones, and take the max of
  // visible-track clip ends. If no visible track has any content, we
  // fall back to the original (all-tracks) extent.
  const fitContentRanRef = useRef(false);
  useEffect(() => {
    if (fitContentRanRef.current) return;
    if (!project || !project.clips) return;
    // Defer to next tick so .timeline-content has its real clientWidth.
    const t = setTimeout(() => {
      const cEl = document.querySelector('.timeline-content');
      if (!cEl) return;
      // GUI-03R4.1 P1-5: Fit Content uses EDITORIAL content bounds
      // (V1 by default; project.intent.editorial_track_ids wins).
      // Stale/test debris on visible tracks (e.g., Sanlihe's
      // 600-608s clips) MUST NOT drag the zoom out — only the
      // canonical story end should. Falls back to playback
      // duration if no editorial content is found.
      const maxEnd = fitContentEndSec(project as Project);
      if (maxEnd <= 0) { fitContentRanRef.current = true; return; }
      const target = Math.max(0.5, Math.min(120,
        cEl.clientWidth / Math.max(0.001, maxEnd)));
      setPxPerSec(Math.round(target * 10) / 10);
      fitContentRanRef.current = true;
    }, 200);
    return () => clearTimeout(t);
  }, [project, activeTimelineId]);

  // GUI-03R4-R4: marquee selection — Timeline computes the hit set
  // and passes it here; we either replace or extend selectedSet
  // based on the additive flag (Ctrl/Cmd held during drag).
  const onMarqueeSelect = (
    newSelectedSet: Set<string>,
    additive: boolean,
  ) => {
    if (additive) {
      setSelectedSet((prev) => {
        const next = new Set(prev);
        for (const id of newSelectedSet) next.add(id);
        return next;
      });
    } else {
      setSelectedSet(new Set(newSelectedSet));
    }
    // Keep `selected` (the single-selection head) pointing at one
    // member of the new set if non-empty.
    const first = newSelectedSet.values().next().value as string | undefined;
    setSelected(first ?? null);
  };
  const onMarqueeCancel = () => {
    // Currently no-op (the marquee rect is owned by Timeline).
    // Hook reserved for future "press Esc to clear selection" UX.
  };

  // GUI-03R4-R5: Close Gap (single track) + Batch Close Gaps (visible
  // tracks). Both go through Core commands so each user intent =
  // one Core Operation. The GUI never loops Core mutations for
  // multi-track actions.
  const onCloseGap = async (trackId: string, startFrame: number,
                              endFrame: number) => {
    await run(() => api.closeGap(trackId, startFrame, endFrame,
                                  "GUI 右键关闭间隙"),
      `已关闭 ${trackId} 上的间隙 (${(endFrame - startFrame).toFixed(2)}s)`);
  };
  const onCloseGapsBatch = async (trackIds: string[]) => {
    if (trackIds.length === 0) return;
    if (!window.confirm(
      `Batch close gaps on ${trackIds.length} tracks? Each gap becomes ONE Operation per track.`)) {
      return;
    }
    await run(() => api.closeGapsBatch(trackIds, "GUI 批量关闭间隙"),
      `已批量关闭 ${trackIds.length} 个轨道的间隙`);
  };

  // GUI-03R3-1A: drag payload log sink. The smoke script reads it
  // back via page.evaluate(...). Reset on each mount so tests
  // start with an empty log.
  useEffect(() => {
    (window as unknown as { __yrollDragLog?: unknown[] }).__yrollDragLog = [];
  }, []);

  // 时间轴 seek → 预览跟随（PreviewPlayer 按模式映射源时间/成片时间）
  const seek = (t: number) => {
    setPlayheadFrame(Math.max(0, t));
  };

  // 走带控制（PreviewPlayer 注入）+ 剪贴板
  const transportRef = useRef<{ toggle?: () => void } | null>(null);
  const clipboard = useRef<Clip | null>(null);

  // 撤销/重做（语义撤销：revert 的 revert = redo）
  const undoLast = async () => {
    const ops = await api.operations();
    const last = [...ops].reverse().find(
      (o) => !o.type.startsWith("revert:") && o.type !== "analyze_loudness");
    if (last) {
      await run(() => api.revert(last.operation_id, "GUI Ctrl+Z"), `已撤销 ${last.type}`);
    } else {
      setStatus({ ok: false, text: "没有可撤销的操作" });
    }
  };
  const redoLast = async () => {
    const ops = await api.operations();
    const lastRevert = [...ops].reverse().find((o) => o.type.startsWith("revert:"));
    if (lastRevert) {
      await run(() => api.revert(lastRevert.operation_id, "GUI Redo"), `已重做 ${lastRevert.type}`);
    } else {
      setStatus({ ok: false, text: "没有可重做的操作" });
    }
  };

  // 剪辑点导航（↑/↓ 跳上一个/下一个边界）
  //
  // GUI-02.6.1 invariant: boundary navigation operates in
  // TimelineFrame space (integer). The clip's timeline_range.start
  // / .end are legacy SECONDS storage; we convert to frames via
  // the project's sequence fps before comparing with playheadFrame.
  // No seconds-based comparison, no 0.05-second epsilon magic.
  const jumpBoundary = (dir: 1 | -1) => {
    if (!project) return;
    const seqFps = project.sequence?.fps ?? {
      num: project.fps_num ?? 30, den: project.fps_den ?? 1,
    };
    const toFrame = (sec: number) =>
      Math.round(sec * seqFps.num / seqFps.den);
    const pts = new Set<number>([0]);
    for (const c of Object.values(project.clips)) {
      pts.add(toFrame(c.timeline_range.start));
      pts.add(toFrame(c.timeline_range.end));
    }
    const sorted = [...pts].sort((a, b) => a - b);
    // Strict integer comparison in TimelineFrame space; no epsilon.
    const t = dir === 1
      ? sorted.find((p) => p > playheadFrame)
      : [...sorted].reverse().find((p) => p < playheadFrame);
    if (t !== undefined) seek(t);
  };

  // 键盘快捷键（NLE 标准手感）
  //
  // GUI-02.6: ALL key handling routes through useCoreKeymap() — the
  // Core keymap is the sole source of key semantics. Local navigation
  // (J/K/L/arrows) reads `delta_frames` from the keymap; there are
  // NO hardcoded fallback values. If a key is absent from the keymap
  // (e.g. the keymap hasn't loaded yet, or Core removed a binding),
  // the handler is a no-op — we never invent step sizes locally.
  //
  // Mutation bindings (Ctrl+Z/Y/C/V/D/A) are shortcuts to existing
  // gated APIs (undo/redo/clipboard/select-all). They are not in the
  // Core keymap's `delta_frames` taxonomy but they DO have stable
  // key combos that we honor unconditionally.
  //
  // The handler never derives step sizes from seconds thresholds —
  // that would be a hidden variable renaming trick (a "1" or "10" is
  // a step size, not a delta_frames from Core).
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement).tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
      const ctrl = e.ctrlKey || e.metaKey;
      if (ctrl && (e.key === "z" || e.key === "Z")) {
        e.preventDefault();
        if (e.shiftKey) redoLast(); else undoLast();
      } else if (ctrl && (e.key === "y" || e.key === "Y")) {
        e.preventDefault();
        redoLast();
      } else if (ctrl && (e.key === "c" || e.key === "C")) {
        if (clip) clipboard.current = clip;
      } else if (ctrl && (e.key === "v" || e.key === "V")) {
        const c = clipboard.current;
        if (!c) return;
        e.preventDefault();
        if (c.asset_id === "") {
          const dur = c.timeline_range.end - c.timeline_range.start;
          run(() => api.addSubtitle(c.context?.text ?? "", playheadFrame, playheadFrame + dur, "GUI 粘贴字幕"), "已粘贴");
        } else {
          run(() => api.addClip(c.asset_id, c.source_range.start, c.source_range.end,
            playheadFrame, c.track_id, "GUI 粘贴"), "已粘贴到播放头");
        }
      } else if (ctrl && (e.key === "d" || e.key === "D")) {
        if (!clip) return;
        e.preventDefault();
        if (clip.asset_id === "") {
          const dur = clip.timeline_range.end - clip.timeline_range.start;
          run(() => api.addSubtitle(clip.context?.text ?? "", clip.timeline_range.end,
            clip.timeline_range.end + dur, "GUI 复制字幕"), "已复制");
        } else {
          run(() => api.addClip(clip.asset_id, clip.source_range.start, clip.source_range.end,
            clip.timeline_range.end, clip.track_id, "GUI 复制"), "已复制到原 clip 之后");
        }
      } else if (ctrl && (e.key === "a" || e.key === "A")) {
        e.preventDefault();
        if (project) setSelectedSet(new Set(Object.keys(project.clips)));
      } else if (e.key === " ") {
        // Spacebar toggles play/pause. The Core keymap binds "Space"
        // with delta_frames=0 (it's a transport toggle, not a nudge).
        // We honor it unconditionally even though no seek occurs.
        const binding = keymap.find((a) => a.key === "Space");
        if (binding) {
          e.preventDefault();
          transportRef.current?.toggle?.();
        }
        // else: no-op — Core hasn't told us Space is a transport key.
      } else {
        // Non-Ctrl keys: dispatch via Core keymap. Build the exact
        // combo (e.g. "J", "Shift+J", "ArrowLeft", "Shift+ArrowLeft")
        // and look up delta_frames from the binding. NO magic numbers.
        const combo = eventToKeyCombo(e);
        const binding = keymap.find((a) => a.key === combo);
        if (binding) {
          e.preventDefault();
          if (binding.deltaFrames !== 0) {
            // Local nav: seek by delta_frames (signed).
            seek(playheadFrame + binding.deltaFrames);
          } else if (binding.name === "_toggle_play") {
            // Space / K binding — toggle transport.
            transportRef.current?.toggle?.();
          } else if (binding.name === "_set_in_out") {
            const which = (binding.params as { which?: "in" | "out" })?.which;
            if (which === "in") {
              setInPoint(playheadFrame);
              setStatus({ ok: true, text: `入点 ${playheadFrame} frames` });
            } else if (which === "out") {
              setOutPoint(playheadFrame);
              setStatus({ ok: true, text: `出点 ${playheadFrame} frames` });
            }
          } else if (binding.name === "split_clip_at_frame") {
            if (clip) splitAtPlayhead();
          } else if (binding.name === "delete_selection") {
            // GUI-03R3-W-A.2: Delete / Shift+Delete keyboard path.
            // Dispatch rules (locked in plan §2.1.1):
            //   selectedSet.size === 0 + no `clip` → no-op
            //   selectedSet.size === 1 (or single `selected`) →
            //     ripple=false → existing pendingDelete impact-preview flow (one Core op)
            //     ripple=true  → api.deleteSelection([id], true)
            //   selectedSet.size > 1 →
            //     window.confirm then api.deleteSelection(set, ripple)
            //
            // We use the selection-level path (deleteSelection) so the
            // Multi-Ripple case emits ONE Core Operation, not N.
            // Note: the keydown handler is synchronous (not async);
            // we use .then() chains so the handler stays sync.
            const ripple = Boolean(
              (binding.params as { ripple?: boolean })?.ripple ?? false,
            );
            const ids = Array.from(selectedSet);
            if (ids.length === 0 && !clip) return;
            if (ids.length <= 1 && clip && !ripple) {
              // Single-clip Delete → existing impact-preview UX.
              const target = clip.clip_id;
              void api.impact(target, "remove").then((imp) => {
                if (imp.will_sync.length === 0 && imp.will_prompt.length === 0) {
                  run(() => api.removeClip(target, "GUI Delete").then(() => setSelected(null)),
                    "已删除");
                } else {
                  setPendingDelete({ clipId: target, impact: imp });
                }
              });
              return;
            }
            if (ids.length <= 1 && clip && ripple) {
              // Single-clip Shift+Delete → direct ripple via
              // selection path (one Core op).
              run(() => api.deleteSelection([clip.clip_id], true, "GUI Shift+Delete")
                        .then(() => setSelected(null)),
                "已删除并收拢");
              return;
            }
            // Multi-clip: confirm then one Core op.
            const n = ids.length;
            const msg = ripple
              ? `Ripple-delete ${n} clip${n === 1 ? "" : "s"}?`
              : `Delete ${n} clip${n === 1 ? "" : "s"}?`;
            if (!window.confirm(msg)) return;
            run(() => api.deleteSelection(ids, ripple, "GUI multi-delete")
                  .then(() => { setSelectedSet(new Set()); setSelected(null); }),
              ripple ? `已 ripple 删除 ${n} 个 clip` : `已删除 ${n} 个 clip`);
          } else if (binding.name === "_nudge_playhead_boundary") {
            // ArrowUp / ArrowDown: jump to clip boundary.
            // The Core keymap signals this via the binding name; the
            // magnitude/direction is in binding.params.
            const dir = ((binding.params as { direction?: number })?.direction) ?? 1;
            jumpBoundary(dir as 1 | -1);
          } else if (binding.name === "_center_playhead") {
            // GUI-03R3-W-D: Home — scroll the .timeline-content so
            // the playhead sits in the middle of the visible
            // viewport. Pure GUI-local scroll; frame 0 stays at
            // x=0 inside ContentViewport (Content Origin invariant
            // is preserved — we only adjust scrollLeft).
            const el = timelineContentRef.current;
            if (el) {
              const target = playheadFrame * pxPerFrameVal - el.clientWidth / 2;
              el.scrollLeft = Math.max(0, target);
            }
          } else {
            // Unknown binding name — silent no-op (do not crash).
          }
        }
        // No binding found → silent no-op (per GUI-02.6: missing binding
        // produces no-op, never fallback magic numbers).
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [keymap, clip, project, selectedSet, playheadFrame, pxPerFrameVal]);

  // GUI-02.4: pointermove only emits integer frame preview; the
  // authoritative /snap call + commit happens in ClipBlock's pointerup
  // handler via onMoveCommit. App.tsx tracks the preview for any
  // overlay rendering that depends on the in-flight position.
  const run = async (fn: () => Promise<unknown>, ok: string) => {
    try {
      await fn();
      await refresh();
      setStatus({ ok: true, text: ok });
    } catch (e) {
      setStatus({ ok: false, text: String(e) });
    }
  };

  // GUI-02.4: pointermove only emits integer frame preview; the
  // authoritative /snap call + commit happens in ClipBlock's pointerup
  // handler via onMoveCommit. App.tsx tracks the preview for any
  // overlay rendering that depends on the in-flight position.
  // GUI-03R3-1E: optional second arg is the visual ghost-snap
  // target (TimelineFrame). It is used to render a thin snap line
  // in the track-content row during drag — it NEVER modifies the
  // dragged clip's preview position.
  const [dragPreview, setDragPreview] = useState<Record<string, number>>({});
  const [dragGhost, setDragGhost] = useState<Record<string, number | null>>({});
  const onDragMove = (
    clipId: string,
    newStartFrame: number,
    ghostSnapFrame: number | null = null,
  ) => {
    // newStartFrame is an INTEGER TimelineFrame (post clamp; snap
    // is NEVER applied during drag — ghost is visual only).
    setDragPreview((p) => ({ ...p, [clipId]: newStartFrame }));
    setDragGhost((p) => ({ ...p, [clipId]: ghostSnapFrame }));
  };
  // commitDrag is no longer needed — ClipBlock calls onMoveCommit
  // directly on pointerup. Kept as a no-op for backward compatibility
  // with the old global pointerup listener (now removed).

  if (!project) {
    return <div className="app"><div className="statusbar err">{status.text}</div></div>;
  }

  const displayProject: Project = {
    ...project,
    clips: Object.fromEntries(
      Object.entries(project.clips).map(([id, c]) => {
        const s = dragPreview[id];
        if (s === undefined) return [id, c];
        const len = c.timeline_range.end - c.timeline_range.start;
        return [id, { ...c, timeline_range: { start: s, end: s + len } }];
      })
    ),
  };

  const splitAtPlayhead = () => {
    if (!clip) return;
    // 播放头（timeline 时间）→ 源时间换算
    const tr = clip.timeline_range;
    if (playheadFrame <= tr.start || playheadFrame >= tr.end) {
      setStatus({ ok: false, text: "播放头不在选中 clip 范围内" });
      return;
    }
    const ratio = (playheadFrame - tr.start) / (tr.end - tr.start);
    const atSource =
      clip.source_range.start + (clip.source_range.end - clip.source_range.start) * ratio;
    run(() => api.split(clip.clip_id, atSource, "GUI 在播放头处切分"), "已切分");
  };

  return (
    <div className="app">
      <div className="topbar">
        <span className="title">YROLL AI</span>
        <span>{project.name}</span>
        {/* GUI-03R: EditLease (Project-level) lives in the header as
            a compact badge; controls revealed on click. */}
        <EditLease />
        {project.intent?.goal && <span className="goal">目标：{project.intent.goal}</span>}
        <span style={{ flex: 1 }} />
        <span style={{ position: "relative" }}>
          <input
            value={searchQ}
            placeholder="🔍 台词搜索…"
            onChange={(e) => setSearchQ(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Escape") { setSearchQ(""); setSearchHits([]); }
            }}
            style={{ width: 160, background: "#222", border: "1px solid #3a3a3a", borderRadius: 4, color: "#ddd", padding: "3px 8px", fontSize: 12 }}
          />
          {searchHits.length > 0 && (
            <div className="search-drop">
              {searchHits.map((h, i) => (
                <div
                  key={i}
                  className="search-hit"
                  onClick={() => {
                    seek(h.timeline);
                    setSelected(h.clip_id);
                    setSelectedSet(new Set([h.clip_id]));
                    setSearchHits([]);
                    setSearchQ("");
                  }}
                >
                  <span className="search-time">{h.timeline.toFixed(1)}s</span>
                  {h.text}
                </div>
              ))}
            </div>
          )}
        </span>
        <label style={{ color: "#888" }}>缩放</label>
        <input
          type="range" min={1} max={120} step={1} value={pxPerSec}
          onChange={(e) => setPxPerSec(Number(e.target.value))}
          style={{ width: 100 }}
        />
        <button
          title="批量关闭当前可见轨道的所有间隙（每条轨道一个 Operation）"
          onClick={() => {
            const activeTl = project?.timelines?.find(
              (tl) => tl.timeline_id === activeTimelineId) ?? project?.timelines?.[0];
            const ids = (activeTl?.tracks ?? []).filter((t) => !t.hidden).map((t) => t.track_id);
            onCloseGapsBatch(ids);
          }}
        >
          批量关闭间隙
        </button>
        <button
          title="缩放到全部内容可见"
          onClick={() => {
            const cEl = document.querySelector('.timeline-content');
            if (!cEl) return;
            // GUI-03R4.1 P1-5: same editor as the auto-fit effect —
            // EDITORIAL bounds, not stale/test extent.
            const maxEnd = fitContentEndSec(project as Project);
            if (maxEnd <= 0) return;
            const target = Math.max(0.5, Math.min(120,
              cEl.clientWidth / Math.max(0.001, maxEnd)));
            setPxPerSec(Math.round(target * 10) / 10);
          }}
        >
          适配内容
        </button>
        <button onClick={startRender} disabled={!!renderJob}>
          {renderJob ? "渲染中…" : "渲染预览"}
        </button>
        <label style={{ color: "#888", fontSize: 12, display: "flex", alignItems: "center", gap: 3 }}
               title="勾选后字幕烧进画面（分发成片）；不勾是软字幕（可开关）">
          <input type="checkbox" checked={burnSubs} onChange={(e) => setBurnSubs(e.target.checked)} />
          烧录字幕
        </label>
        <label style={{ color: "#888", fontSize: 12, display: "flex", alignItems: "center", gap: 3 }}
               title="磁吸模式：总是 = 拖动时自动磁吸；Alt = 按住 Alt 才磁吸；关 = 不磁吸">
          磁吸：
          <select value={snapMode} onChange={(e) => setSnapMode(e.target.value as any)}
                  style={{ background: "#222", border: "1px solid #444", color: "#ccc", padding: "2px 4px", borderRadius: 3 }}>
            <option value="always">总是</option>
            <option value="alt">Alt+拖动</option>
            <option value="off">关</option>
          </select>
        </label>
        <label style={{ color: "#888", fontSize: 12, display: "flex", alignItems: "center", gap: 3 }}
               title="GUI-03C：显示空轨道（默认隐藏，Core 仍持有空轨道数据）">
          <input type="checkbox" checked={showEmptyTracks}
                 onChange={(e) => setShowEmptyTracks(e.target.checked)} />
          空轨道
        </label>
        <label style={{ color: "#888", fontSize: 12, display: "flex", alignItems: "center", gap: 3 }}
               title="高亮所有跨轨关联的 clip（Semantic Link）">
          <input type="checkbox" checked={highlightRel} onChange={(e) => setHighlightRel(e.target.checked)} />
          高亮关联
        </label>
        <button
          disabled={previewVersion === 0}
          style={regionMode ? { background: "#7ec97e", color: "#141414" } : undefined}
          onClick={() => { setRegionMode((m) => !m); setRegionDraft(null); }}
        >
          {regionMode ? "框选中…" : "框选去水印"}
        </button>
        <button onClick={() => run(() => api.commit("GUI 手动存档"), "已存版本")}>存版本</button>
      </div>

      <TimelineSwitcher
        projectRevision={project?.sequence?.project_revision ?? 0}
        activeTimelineId={activeTimelineId}
        onSwitch={switchTimeline}
        onRequestNewTimeline={() => setNewTimelineOpen(true)}
        onRequestDeleteTimeline={(id) => deleteTimeline(id)}
      />
      <NewTimelineDialog
        isOpen={newTimelineOpen}
        currentTimelineName={
          project?.timelines?.find((t) => t.timeline_id === activeTimelineId)
            ?.name ?? ""
        }
        defaultDuplicateName={
          // GUI-03E-4: default to "复制自 <current>"; the user can
          // override to a semantic name (种草版 / 收割版 / ...).
          (project?.timelines?.find((t) => t.timeline_id === activeTimelineId)
            ?.name ?? "")
            ? `${project?.timelines?.find((t) => t.timeline_id === activeTimelineId)?.name} 副本`
            : "副本"
        }
        onClose={() => setNewTimelineOpen(false)}
        onSubmit={createTimeline}
      />
        <MenuBar
        hasClip={!!clip}
        onOpenProject={() => {
          const path = window.prompt("工程目录路径（含 current.json）：");
          if (!path) return;
          run(async () => {
            const r = await api.openProject(path);
            setPreviewVersion(0);
            setSelected(null);
            setSelectedSet(new Set());
            setStatus({ ok: true, text: `已打开工程：${r.project}` });
          }, "工程已切换");
        }}
        onNewProject={() => {
          const root = window.prompt("工程存放目录（会在其下建 <名字>/ 工程目录）：", "projects");
          if (!root) return;
          const name = window.prompt("工程名字：");
          if (!name) return;
          const goal = window.prompt("目标（可空）：") || "";
          run(async () => {
            const r = await api.newProject(root, name, goal);
            setPreviewVersion(0);
            setSelected(null);
            setSelectedSet(new Set());
            setStatus({ ok: true, text: `已创建并打开工程：${r.project}` });
          }, "工程已创建");
        }}
        onShowHelp={() => setShowHelp(true)}
        regionMode={regionMode}
        onImportJianying={() => {
          const dir = window.prompt("剪映草稿目录（含 draft_content.json）：");
          if (!dir) return;
          run(async () => {
            const r = await api.importJianying(dir);
            setStatus({ ok: true, text: `剪映导入：${r.tracks} 轨 ${r.clips} clip ${r.assets} 素材（跳过 ${r.skipped}）` });
          }, "剪映工程已导入");
        }}
        onImport={(files) =>
          run(async () => {
            let n = 0;
            for (const f of Array.from(files)) {
              const r = await api.importAsset(f);
              if (!r.deduped) n++;
            }
          }, `已导入 ${files.length} 个素材（去重自动跳过）`)
        }
        onRender={startRender}
        onExportPackage={() => setExportOpen(true)}
        onExportRange={() => {
          if (inPoint === null || outPoint === null || outPoint <= inPoint) {
            setStatus({ ok: false, text: "先用 I/O 键标记入点和出点" });
            return;
          }
          const name = window.prompt("选区导出文件名", "clip-range.mp4") || "clip-range.mp4";
          const [i, o] = [inPoint, outPoint];
          run(async () => {
            await api.renderRange(i, o, burnSubs, 1080, name);
            pollRender((preview) =>
              setStatus({ ok: true, text: `已导出选区 ${i.toFixed(1)}-${o.toFixed(1)}s：${preview}` }));
          }, "选区导出已开始");
        }}
        onExport={() => {
          const w = window.prompt("导出宽度（像素，如 720 / 1080 / 1920 / 3840）", "1080");
          if (!w) return;
          const name = window.prompt("文件名", "export.mp4") || "export.mp4";
          run(async () => {
            await api.render(burnSubs, Number(w) || 1080, name);
            pollRender((preview) => setStatus({ ok: true, text: `已导出：${preview}` }));
          }, "导出已开始");
        }}
        onCommit={() => run(() => api.commit("GUI 手动存档"), "已存版本")}
        onSplit={splitAtPlayhead}
        onTrimHead={() => clip && run(() => api.trim(clip.clip_id, clip.source_range.start + 0.5), "头部裁掉 0.5s")}
        onTrimTail={() => clip && run(() => api.trim(clip.clip_id, undefined, clip.source_range.end - 0.5), "尾部裁掉 0.5s")}
        onSilenceRemove={() => clip && run(() => api.silenceRemove(clip.clip_id, "GUI 去停顿"), "已去停顿")}
        onDenoise={() => clip && run(() => api.denoise(clip.clip_id, 12, "GUI 降噪"), "已加降噪（重渲染后生效）")}
        onLoudness={() => clip && run(
          async () => {
            const r = await api.loudness(clip.clip_id);
            setStatus({ ok: true, text: `响度：mean ${r.after.mean_db}dB / max ${r.after.max_db}dB` });
          }, "响度分析完成")}
        onAddSubtitle={() => {
          // 优先编辑已有字幕（如果 playheadFrame 在某字幕 clip 上），否则新建
          const selClip = project.clips[selected ?? ""];
          if (selClip && activeTimelineTracks.find((t) => t.track_id === selClip.track_id)?.kind === "text"
              && playheadFrame >= selClip.timeline_range.start && playheadFrame < selClip.timeline_range.end) {
            setSubtitleEdit({
              clipId: selClip.clip_id,
              text: selClip.context?.text ?? "",
              style: (selClip.context?.style ?? {}) as unknown as Record<string, unknown>,
              start: selClip.timeline_range.start,
              end: selClip.timeline_range.end,
              track_id: selClip.track_id,
            });
          } else {
            // 新建空白字幕
            const [s, e] = selRange ?? [playheadFrame, playheadFrame + 2];
            setSubtitleEdit({
              clipId: "",
              text: "",
              style: {} as unknown as Record<string, unknown>,
              start: s,
              end: e,
              track_id: (activeTimelineTracks.find((t) => t.kind === "text") ?? { track_id: "t1" }).track_id,
            });
          }
          setSelRange(null);
        }}
        onGenerateSubtitles={() =>
          run(async () => {
            const op = await api.generateSubtitles();
            setStatus({ ok: true, text: `已生成 ${op.after?.count ?? 0} 条字幕（重渲染后可见）` });
          }, "自动字幕完成")}
        onRegionMode={() => { setRegionMode((m) => !m); setRegionDraft(null); }}
      />

      <div className="main">
        <div className="asset-pane" style={{ width: assetW }}>
          <AssetPanel project={project} activeTimelineId={activeTimelineId}
            playheadFrame={playheadFrame} onChanged={refresh}
            onStatus={(ok, text) => setStatus({ ok, text })}
            onAssetDragStart={(_assetId, kind) => {
              // Timeline's drop-zone label needs the asset kind.
              // The Timeline never reads from a global drag state
              // directly — App passes the kind explicitly here.
              setDraggingAssetKind(
                kind === "video" || kind === "image" || kind === "audio"
                || kind === "subtitle" || kind === "text"
                  ? kind : null,
              );
            }}
            onAssetDragEnd={() => setDraggingAssetKind(null)}
            onPreview={(assetId) => {
              const a = project.assets.find((x) => x.asset_id === assetId);
              if (!a) return;
              setPreviewAsset({
                url: `/assets/${assetId}/file`,
                isImage: a.type === "image",
                label: a.path.split(/[\/]/).pop() || assetId,
              });
            }} />
        </div>
        <ResizeHandle direction="vertical"
          onDelta={(d) => setAssetW((w) => Math.max(180, Math.min(500, w + d)))} />

        <div className="preview-pane" ref={previewRef} style={{ position: "relative" }}>
          <PreviewPlayer
            project={project}
            playheadFrame={playheadFrame}
            durationHint={Math.max(90, ...Object.values(project.clips).map((c) => c.timeline_range.end))}
            renderedUrl={previewVersion > 0 ? `/preview.mp4?v=${previewVersion}` : null}
            onPlayhead={setPlayheadFrame}
            onStatus={(ok, text) => setStatus({ ok, text })}
            overrideSrc={previewAsset}
            onClearOverride={() => setPreviewAsset(null)}
            aspect={aspect}
            onAspect={setAspect}
            timelineId={activeTimelineId}
            // GUI-03R3-W-A.4: Space/K (keymap's local-action
            // `_toggle_play` binding) calls into the PreviewPlayer's
            // FrameClock toggle through this ref. FrameClock stays
            // internal to PreviewPlayer; the parent never sees it
            // directly. No `/keyboard/execute` endpoint — this is
            // purely a GUI-local transport action.
            onTransportReady={(api) => { transportRef.current = api; }}
          />
          {previewVersion > 0 && clip && activeTimelineTracks
            .filter((t) => t.kind === "video").slice(1)
            .some((t) => t.clip_ids.includes(clip.clip_id)) && (
            <div
              className="pip-drag-box"
              style={{
                left: `${Number(clip.transform?.x ?? 0.68) * 100}%`,
                top: `${Number(clip.transform?.y ?? 0.68) * 100}%`,
                width: `${Number(clip.transform?.scale ?? 0.3) * 100}%`,
                aspectRatio: "16/9",
              }}
              title="拖动调整 PiP 位置"
              onPointerDown={(e) => {
                e.preventDefault();
                const pane = previewRef.current;
                if (!pane) return;
                const rect = pane.getBoundingClientRect();
                const startX = e.clientX;
                const startY = e.clientY;
                const origX = Number(clip.transform?.x ?? 0.68);
                const origY = Number(clip.transform?.y ?? 0.68);
                const box = e.currentTarget as HTMLElement;
                const move = (ev: PointerEvent) => {
                  const nx = Math.min(0.95, Math.max(0, origX + (ev.clientX - startX) / rect.width));
                  const ny = Math.min(0.95, Math.max(0, origY + (ev.clientY - startY) / rect.height));
                  box.style.left = `${nx * 100}%`;
                  box.style.top = `${ny * 100}%`;
                  box.dataset.nx = String(nx);
                  box.dataset.ny = String(ny);
                };
                const up = () => {
                  window.removeEventListener("pointermove", move);
                  window.removeEventListener("pointerup", up);
                  const nx = Number(box.dataset.nx ?? origX);
                  const ny = Number(box.dataset.ny ?? origY);
                  if (Math.abs(nx - origX) > 0.005 || Math.abs(ny - origY) > 0.005) {
                    run(() => api.setTransform(clip.clip_id,
                      { x: nx, y: ny, scale: Number(clip.transform?.scale ?? 0.3) },
                      "GUI 拖 PiP"), "PiP 位置已改（重渲染后生效）");
                  }
                };
                window.addEventListener("pointermove", move);
                window.addEventListener("pointerup", up);
              }}
            />
          )}
          {renderJob && (
            <div className="render-progress">
              渲染中：{renderJob.step}（{renderJob.done}/{renderJob.total}）
              <div className="bar">
                <div style={{ width: `${Math.min(100, (renderJob.done / Math.max(1, renderJob.total)) * 100)}%` }} />
              </div>
            </div>
          )}
          {regionMode && previewVersion > 0 && (
            <div
              style={{
                position: "absolute", inset: 0, cursor: "crosshair", zIndex: 5,
                background: "rgba(0,0,0,0.05)",
              }}
              onPointerDown={(e) => {
                const r = e.currentTarget.getBoundingClientRect();
                dragStart.current = {
                  x: (e.clientX - r.left) / r.width,
                  y: (e.clientY - r.top) / r.height,
                };
                setRegionDraft(null);
              }}
              onPointerMove={(e) => {
                if (!dragStart.current) return;
                const r = e.currentTarget.getBoundingClientRect();
                const cx = (e.clientX - r.left) / r.width;
                const cy = (e.clientY - r.top) / r.height;
                const s = dragStart.current;
                setRegionDraft({
                  x: Math.max(0, Math.min(s.x, cx)),
                  y: Math.max(0, Math.min(s.y, cy)),
                  w: Math.min(1, Math.abs(cx - s.x)),
                  h: Math.min(1, Math.abs(cy - s.y)),
                });
              }}
              onPointerUp={() => { dragStart.current = null; }}
            >
              {regionDraft && (
                <div style={{
                  position: "absolute",
                  left: `${regionDraft.x * 100}%`, top: `${regionDraft.y * 100}%`,
                  width: `${regionDraft.w * 100}%`, height: `${regionDraft.h * 100}%`,
                  border: "2px dashed #7ec97e", background: "rgba(126,201,126,0.15)",
                }} />
              )}
            </div>
          )}
          {regionDraft && (
            <div style={{
              position: "absolute", bottom: 12, left: "50%", transform: "translateX(-50%)",
              zIndex: 6, display: "flex", gap: 8, background: "#222", padding: "6px 10px",
              borderRadius: 6, border: "1px solid #444",
            }}>
              <button
                onClick={() => {
                  // 目标 = 播放头所在的主视频轨 clip（框的就是眼前这段）
                  const vtrack = activeTimelineTracks.find((t) => t.kind === "video");
                  const target = vtrack?.clip_ids
                    .map((id) => project.clips[id])
                    .find((c) => c && playheadFrame >= c.timeline_range.start && playheadFrame <= c.timeline_range.end);
                  if (!target) {
                    setStatus({ ok: false, text: "播放头下没有视频 clip" });
                    return;
                  }
                  const region = regionDraft;
                  setRegionDraft(null);
                  setRegionMode(false);
                  run(() => api.delogo(target.clip_id, region, "GUI 框选去水印"), "已加去水印（重渲染后生效）");
                }}
              >
                对此区域去水印
              </button>
              <button onClick={() => { setRegionDraft(null); }}>重选</button>
              <button onClick={() => { setRegionDraft(null); setRegionMode(false); }}>取消</button>
            </div>
          )}
        </div>

        <ResizeHandle direction="vertical"
          onDelta={(d) => setInspectorW((w) => Math.max(200, Math.min(500, w - d)))} />
        <div className="inspector" style={{ width: inspectorW }}>
          <div className="inspector-tabs">
            <button
              className={inspectorTab === "props" ? "tab active" : "tab"}
              onClick={() => setInspectorTab("props")}
            >
              属性
            </button>
            <button
              className={inspectorTab === "history" ? "tab active" : "tab"}
              onClick={() => setInspectorTab("history")}
            >
              历史
            </button>
          </div>
          {inspectorTab === "history" ? (
            <OpsPanel refreshKey={opsKey} onChanged={refresh}
                      onStatus={(ok, text) => setStatus({ ok, text })} />
          ) : (
          <>
          {selectedSet.size > 1 && (
            <div className="batch-panel">
              <h3>已选 {selectedSet.size} 个 clip</h3>
              <div className="row">
                <label>统一音量</label>
                {[0.5, 1, 1.5].map((v) => (
                  <button key={v} onClick={() =>
                    run(async () => {
                      for (const id of selectedSet) {
                        await api.volume(id, v, "GUI 批量音量");
                      }
                    }, `已对 ${selectedSet.size} 个 clip 设音量 ${v}`)}>
                    {v}
                  </button>
                ))}
              </div>
              <div className="row">
                <label>统一速度</label>
                {[1, 1.5, 2].map((v) => (
                  <button key={v} onClick={() =>
                    run(async () => {
                      for (const id of selectedSet) {
                        await api.speed(id, v, "GUI 批量速度");
                      }
                    }, `已对 ${selectedSet.size} 个 clip 设速度 ${v}x`)}>
                    {v}x
                  </button>
                ))}
              </div>
              <div className="row">
                <button
                  className="danger"
                  // GUI-03R3-W-A.3: multi-clip delete uses
                  // api.deleteSelection so the GUI does NOT loop
                  // removeClip. ONE Core Operation per user intent.
                  onClick={() => {
                    const ids = Array.from(selectedSet);
                    if (!window.confirm(`删除选中的 ${ids.length} 个 clip？`)) return;
                    run(() => api.deleteSelection(ids, false, "GUI 批量删除")
                          .then(() => { setSelectedSet(new Set()); setSelected(null); }),
                      `已删除 ${ids.length} 个 clip`);
                  }}
                >
                  全部删除
                </button>
                <button
                  // GUI-03R3-W-A.3: ripple-delete is also one Core
                  // Operation via the selection path (NOT a loop).
                  onClick={() => {
                    const ids = Array.from(selectedSet);
                    if (!window.confirm(`Ripple 删除选中的 ${ids.length} 个 clip？`)) return;
                    run(() => api.deleteSelection(ids, true, "GUI 批量 Ripple")
                          .then(() => { setSelectedSet(new Set()); setSelected(null); }),
                      `已 ripple 删除 ${ids.length} 个 clip`);
                  }}
                >
                  Ripple
                </button>
                <button onClick={() => setSelectedSet(selected ? new Set([selected]) : new Set())}>
                  取消多选
                </button>
              </div>
            </div>
          )}
          {selectedSet.size <= 1 && (
          <>
          <h3>{clip ? `Clip ${clip.clip_id}` : "未选中 Clip"}</h3>{clip && (
            <>
              <div className="meta">
                素材：{clip.asset_id}
                <br />
                源：{clip.source_range.start.toFixed(1)}–{clip.source_range.end.toFixed(1)}s
                <br />
                时间轴：{clip.timeline_range.start.toFixed(1)}–{clip.timeline_range.end.toFixed(1)}s
              </div>
              <div className="row">
                <label>音量</label>
                <input
                  type="range" min={0} max={2} step={0.05} value={clip.volume}
                  onChange={(e) =>
                    run(() => api.volume(clip.clip_id, Number(e.target.value), "GUI 调音量"), "音量已改")
                  }
                />
                <span>{clip.volume.toFixed(2)}</span>
              </div>
              <div className="row">
                <label>速度</label>
                <input
                  type="range" min={0.5} max={3} step={0.25} value={clip.speed}
                  onChange={(e) =>
                    run(() => api.speed(clip.clip_id, Number(e.target.value), "GUI 调速"), "速度已改")
                  }
                />
                <span>{clip.speed}x</span>
              </div>
              {activeTimelineTracks
                .filter((t) => t.kind === "video").slice(1)
                .some((t) => t.clip_ids.includes(clip.clip_id)) && (
                <>
                  <div className="meta">叠加轨（PiP）位置/尺寸：</div>
                  {(["x", "y", "scale"] as const).map((key) => {
                    const def = key === "scale" ? 0.3 : 0.68;
                    const val = Number(clip.transform?.[key] ?? def);
                    return (
                      <div className="row" key={key}>
                        <label>{{ x: "水平", y: "垂直", scale: "尺寸" }[key]}</label>
                        <input
                          type="range" min={0} max={1} step={0.02} value={val}
                          onChange={(e) =>
                            run(() => api.setTransform(
                              clip.clip_id,
                              { x: 0.68, y: 0.68, scale: 0.3, ...clip.transform, [key]: Number(e.target.value) },
                              "GUI 调 PiP"), "位置已改（重渲染后生效）")
                          }
                        />
                        <span>{val.toFixed(2)}</span>
                      </div>
                    );
                  })}
                </>
              )}
              <div className="row">
                <button onClick={() => run(() => api.trim(clip.clip_id, clip.source_range.start + 0.5), "头部裁掉 0.5s")}>
                  头裁 0.5s
                </button>
                <button onClick={() => run(() => api.trim(clip.clip_id, undefined, clip.source_range.end - 0.5), "尾部裁掉 0.5s")}>
                  尾裁 0.5s
                </button>
              </div>
              <div className="row">
                <label>淡入/淡出</label>
                {[0.5, 1].map((s) => (
                  <button
                    key={s}
                    onClick={() =>
                      run(() => api.setFade(clip.clip_id, s, s, "GUI 淡入淡出"),
                        `淡入淡出 ${s}s（重渲染后生效）`)}
                  >
                    {s}s
                  </button>
                ))}
                <label style={{ marginLeft: 8 }}>叠化</label>
                {([["fade", "溶解"], ["wipeleft", "左擦"], ["slideleft", "左滑"]] as const).map(([kind, label2]) => (
                  <button
                    key={kind}
                    title={`与前一个 clip ${label2}（成片比重叠部分短）`}
                    onClick={() =>
                      run(() => api.setDissolve(clip.clip_id, 0.5, kind, "GUI 叠化"),
                        `与前段${label2} 0.5s（重渲染后生效）`)}
                  >
                    {label2}
                  </button>
                ))}
              </div>
              {clip.asset_id !== "" && (
                <div className="row">
                  <button
                    title="这句说错了不用重拍：输入正确台词，AI 合成语音替换（原声静音，可撤销）"
                    onClick={() => {
                      const text = window.prompt("正确的台词（将合成语音替换原声）：");
                      if (!text) return;
                      run(() => api.voiceReplace(clip.clip_id, text, "GUI 语音重配"),
                        "已合成重配（原声已静音，重渲染后生效）");
                    }}
                  >
                    🎙 重配这句
                  </button>
                </div>
              )}
              <div className="row">
                <button onClick={splitAtPlayhead}>在播放头切分</button>
                <button
                  id="btn-delete-clip"
                  className="danger"
                  onClick={async () => {
                    // Impact Preview：删除前先看影响（蓝图 §43.2）
                    const imp = await api.impact(clip.clip_id, "remove");
                    if (imp.will_sync.length === 0 && imp.will_prompt.length === 0) {
                      await run(() => api.removeClip(clip.clip_id, "GUI 删除").then(() => setSelected(null)), "已删除");
                    } else {
                      setPendingDelete({ clipId: clip.clip_id, impact: imp });
                    }
                  }}
                >
                  删除
                </button>
                <button
                  title="删除并把后面的 clip 前移收拢（Shift+Delete）"
                  onClick={() =>
                    run(() => api.removeClip(clip.clip_id, "GUI Ripple 删除", true).then(() => setSelected(null)),
                      "已删除并收拢")}
                >
                  Ripple
                </button>
              </div>
              {clip.asset_id !== "" && (
                <VisualAdjustPanel clip={clip} run={run} />
              )}
              {clip.asset_id === "" && (
                <div className="subtitle-editor">
                  <label>字幕文字</label>
                  <textarea
                    key={clip.clip_id}
                    defaultValue={clip.context?.text ?? ""}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
                        run(() => api.editSubtitle(
                          clip.clip_id,
                          (e.target as HTMLTextAreaElement).value,
                          "GUI 改字幕"), `字幕已更新 → ${clip.track_id} ${clip.timeline_range.start.toFixed(1)}-${clip.timeline_range.end.toFixed(1)}s（重渲染后可见）`);
                      }
                    }}
                  />
                  <button
                    onClick={(e) => {
                      const ta = (e.currentTarget.previousSibling as HTMLTextAreaElement);
                      run(() => api.editSubtitle(clip.clip_id, ta.value, "GUI 改字幕"),
                        `字幕已更新 → ${clip.track_id} ${clip.timeline_range.start.toFixed(1)}-${clip.timeline_range.end.toFixed(1)}s（重渲染后可见）`);
                    }}
                  >
                    保存字幕（Ctrl+Enter）
                  </button>
                  <div className="row" style={{ marginTop: 6 }}>
                    <label>字号</label>
                    <select
                      value={Number((clip.context?.style as unknown as Record<string, unknown> | undefined)?.size ?? 38)}
                      onChange={(e) =>
                        run(() => api.setSubtitleStyle(clip.clip_id, { size: Number(e.target.value) }, "GUI 字幕字号"), "样式已改（烧录生效）")}
                    >
                      {[24, 38, 56].map((s) => <option key={s} value={s}>{s}</option>)}
                    </select>
                    <label>位置</label>
                    <select
                      value={String((clip.context?.style as unknown as Record<string, unknown> | undefined)?.position ?? "bottom")}
                      onChange={(e) =>
                        run(() => api.setSubtitleStyle(clip.clip_id, { position: e.target.value }, "GUI 字幕位置"), "样式已改（烧录生效）")}
                    >
                      <option value="bottom">底部</option>
                      <option value="top">顶部</option>
                    </select>
                    <label>颜色</label>
                    <select
                      value={String((clip.context?.style as unknown as Record<string, unknown> | undefined)?.color ?? "white")}
                      onChange={(e) =>
                        run(() => api.setSubtitleStyle(clip.clip_id, { color: e.target.value }, "GUI 字幕颜色"), "样式已改（烧录生效）")}
                    >
                      <option value="white">白</option>
                      <option value="yellow">黄</option>
                    </select>
                  </div>
                </div>
              )}
              {clip.adjustments.length > 0 && (
                <div className="adj-list">
                  <label>调整图层（{clip.adjustments.length}）</label>
                  {clip.adjustments.map((a) => (
                    <div key={String(a.id)} className="adj-item">
                      <span>
                        {String(a.kind)}
                        {a.kind === "delogo" && "（去水印）"}
                        {a.kind === "denoise" && `（降噪 nr=${(a.params as { nr?: number })?.nr ?? 12}）`}
                        {a.kind === "volume_range" && `（范围音量 ×${(a.params as { volume?: number })?.volume}）`}
                      </span>
                      <button
                        className="adj-remove"
                        onClick={() =>
                          run(() => api.removeAdjustment(clip.clip_id, String(a.id), "GUI 移除调整图层"), "已移除")}
                      >
                        ×
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </>
          )}
          </>
          )}
          <hr style={{ borderColor: "#333" }} />
          <ChatPanel
            selectedClip={selected}
            playheadFrame={playheadFrame}
            onChanged={refresh}
            onStatus={(ok, text) => setStatus({ ok, text })}
          />
          </>
          )}
        </div>
      </div>

      {selRange && (
        <div className="range-bar">
          <span>
            已选 {selRange[0].toFixed(1)}–{selRange[1].toFixed(1)}s
          </span>
          <label>范围内音量</label>
          <input
            type="range" min={0} max={2} step={0.05} value={rangeVolume}
            onChange={(e) => setRangeVolume(Number(e.target.value))}
            style={{ width: 80 }}
          />
          <span>{rangeVolume.toFixed(2)}</span>
          <button
            onClick={() => {
              // 范围音量作用于播放头下/选中的 clip（不必先 Split，蓝图 §2.4）
              const target = clip ?? activeTimelineTracks
                .find((t) => t.kind === "video")?.clip_ids
                .map((id) => project.clips[id])
                .find((c) => c && selRange[0] < c.timeline_range.end && selRange[1] > c.timeline_range.start);
              if (!target) {
                setStatus({ ok: false, text: "范围内没有 clip" });
                return;
              }
              const [s, e] = selRange;
              setSelRange(null);
              run(() => api.volumeRange(target.clip_id, rangeVolume, s, e, "GUI 范围音量"),
                "已加范围音量（重渲染后生效）");
            }}
          >
            应用
          </button>
          <button
            onClick={() => {
              const desc = window.prompt("这段有什么问题？（登记后 AI 给候选方案）");
              if (!desc) return;
              const [s, e] = selRange;
              setSelRange(null);
              run(() => api.reportProblem(desc, "temporal", selected,
                { start: s, end: e }), "问题已登记，见 Clip Workspace 方案");
            }}
          >
            登记问题
          </button>
          <button onClick={() => setSelRange(null)}>取消</button>
        </div>
      )}

      <ResizeHandle direction="horizontal"
        onDelta={(d) => setTimelineH((h) => {
          // GUI-03R5-B2 (Decision 3): 60% viewport cap + 160px floor.
          const maxH = Math.max(TIMELINE_H_MIN,
            Math.floor(window.innerHeight * TIMELINE_H_MAX_PCT));
          return Math.max(TIMELINE_H_MIN, Math.min(maxH, h - d));
        })} />
      <Timeline
        project={displayProject}
        height={timelineH}
        headerWidth={headerW}
        onContentRef={(el) => { timelineContentRef.current = el; }}
        onHeaderWidthDelta={onHeaderWidthDelta}
        snapMode={snapMode}
        highlightRel={highlightRel}
        showEmptyTracks={showEmptyTracks}
        selectedIds={selectedSet}
        playheadFrame={playheadFrame}
        pxPerSec={pxPerSec}
        selRange={selRange}
        inPoint={inPoint}
        outPoint={outPoint}
        // GUI-03R3-W-C: pass the dragging asset kind so the
        // Timeline can label the "below-tracks" drop zone correctly
        // (V/A/T). The Timeline never reads from a global drag state.
        draggingAssetKind={draggingAssetKind}
        // GUI-03R4-R4: marquee selection callbacks.
        onMarqueeSelect={onMarqueeSelect}
        onMarqueeCancel={onMarqueeCancel}
        // GUI-03R4-R5: gap operations callbacks.
        onCloseGap={onCloseGap}
        onCloseGapsBatch={onCloseGapsBatch}
        onSeek={seek}
        onSelect={(id, viaAi, ctrl) => {
          if (viaAi) {
            setSelected(id);
            setSelectedSet(new Set([id]));
            setWorkspaceClip(id);  // 上 1/3 AI 区 → 打开 Clip Workspace（Y 轴）
            return;
          }
          if (ctrl) {
            // Ctrl+点击：多选切换
            setSelectedSet((prev) => {
              const next = new Set(prev);
              if (next.has(id)) next.delete(id); else next.add(id);
              return next;
            });
          } else {
            setSelectedSet(new Set([id]));
          }
          setSelected(id);
        }}
        onDragMove={onDragMove}
        dragGhost={dragGhost}
        onMoveCommit={(clipId, newStartFrame, newTrackId) => {
          // GUI-03R: if a vertical-track-drop target was resolved by
          // the drag, perform ONE transactional move (new timeline
          // start frame + target track in a single API). Previously
          // the parent would commit the frame first and then
          // dispatch a separate track move, leaving a brief window
          // where the clip lived on the wrong track.
          if (newTrackId) {
            run(() => api.move(clipId, newStartFrame, "GUI 跨轨拖动",
                  newTrackId), "已跨轨移动");
            return;
          }
          run(() => api.move(clipId, newStartFrame, "GUI 拖动"),
              "已移动");
        }}
        onZoomPx={setPxPerSec}
        onRangeSelect={setSelRange}
        // Trim receives integer SOURCE FRAMES from ClipBlock; api.trim
        // forwards them as-is to the server (which requires frames).
        onTrimCommit={(clipId, newStartFrame, newEndFrame) =>
          run(() => api.trim(clipId, newStartFrame ?? undefined, newEndFrame ?? undefined, "GUI 边缘拖拽裁剪"), "已裁剪")}
        onAssetDrop={(assetId, trackId, t) => {
          const a = project.assets.find((x) => x.asset_id === assetId);
          if (!a) return;
          // 类型校验：图片只能上 V 轨，音频只能上 A 轨，字幕只能上 T 轨
          const track = project.timelines
            ?.find((tl) => tl.timeline_id === activeTimelineId)
            ?.tracks.find((x) => x.track_id === trackId);
          if (track) {
            if (a.type === "image" && track.kind !== "video") {
              setStatus({ ok: false, text: "图片只能放到视频轨（V1/V2/V3）" });
              return;
            }
            if ((a.type === "audio") && track.kind !== "audio") {
              setStatus({ ok: false, text: "音频只能放到音频轨（A1/A2/A3）" });
              return;
            }
          }
          // GUI-03R-Micro: explicit drops pass the drop-target
          // track_id through to Core. Core itself rejects overlap
          // and enforces same-track policy; the GUI no longer
          // pre-computes a "free" frame via local findFree (that
          // duplicated Core's overlap-check logic and could
          // disagree with it under heterogeneous fps).
          if (a.type === "image") {
            const fps = seq.fps;
            const DEFAULT_IMG_DUR_SEC = 5;
            const durFrames = Math.round(
              DEFAULT_IMG_DUR_SEC * fps.num / fps.den);
            run(() => api.addImageClip(assetId, t, durFrames,
                trackId, "GUI 拖入图片"),
              `${a.path.split(/[\/]/).pop()} 已放到 F${t}（${durFrames}f）`);
            return;
          }
          // video / audio → /clips (seconds-based)
          const dur = a.identity.duration_sec;
          if (!dur) {
            setStatus({ ok: false, text: "该素材无时长，不能上时间轴" });
            return;
          }
          run(() => api.addClip(assetId, 0, dur, t, trackId,
              "GUI 拖入时间轴"),
            `${a.path.split(/[\/]/).pop()} 已放到 ${t.toFixed(1)}s（${dur.toFixed(1)}s）`);
        }}
        // GUI-03R3-W-C: drop onto the "新建轨道" zone below all
        // visible tracks. The Timeline resolved pointer geometry
        // into a structural intent: `insertAfterTrackId` is the
        // last visible track. We call ensure_track_for_drop (Core
        // decides the new track's id; existing tracks never rename)
        // and then place the clip on the returned track. The asset
        // type drives the new track's kind; the CLI responds with
        // the resolved Track object.
        onAssetDropNewTrack={async (assetId, insertAfterTrackId, t) => {
          const a = project.assets.find((x) => x.asset_id === assetId);
          if (!a) return;
          try {
            const created = await api.ensureTrackForDrop(
              a.type, undefined, insertAfterTrackId,
            );
            const newTrackId = created.track_id;
            // Now place the clip on the new track.
            if (a.type === "image") {
              const fps = seq.fps;
              const DEFAULT_IMG_DUR_SEC = 5;
              const durFrames = Math.round(
                DEFAULT_IMG_DUR_SEC * fps.num / fps.den);
              await api.addImageClip(assetId, t, durFrames, newTrackId,
                "GUI 新建轨道+拖入");
            } else if (a.type === "audio" || a.type === "video") {
              const dur = a.identity.duration_sec;
              if (!dur) {
                setStatus({ ok: false, text: "该素材无时长，不能上时间轴" });
                return;
              }
              await api.addClip(assetId, 0, dur, t, newTrackId,
                "GUI 新建轨道+拖入");
            } else {
              // subtitle / text drop-below-tracks is out of v0.1 scope.
              // The AssetPanel's "+" button handles subtitle insertion
              // via addSubtitle (the Core allocator picks the track).
              // Drag-drop a subtitle below tracks would need an
              // ensure_track_for_drop + add_subtitle-with-track-id
              // pair; deferring to a follow-up.
              setStatus({ ok: false,
                text: "字幕请用素材库的 + 按钮（v0.1 拖拽字幕仅支持现有轨）" });
              return;
            }
            await refresh();
            setStatus({ ok: true,
              text: `${a.path.split(/[\/]/).pop()} 已放到新建轨道 ${newTrackId}` });
          } catch (e) {
            setStatus({ ok: false, text: `新建轨道失败：${e}` });
          }
        }}
        onTrackLock={(trackId, locked) =>
          run(() => api.setTrackLocked(trackId, locked, "GUI 轨道锁"),
            locked ? `轨道 ${trackId} 已锁定` : `轨道 ${trackId} 已解锁`)}
        onTrackHide={(trackId, hidden) =>
          run(() => api.setTrackHidden(trackId, hidden, "GUI 轨道隐藏"),
            hidden ? `轨道 ${trackId} 已隐藏` : `轨道 ${trackId} 已显示`)}
        onTrackMute={(trackId, muted) =>
          run(() => api.setTrackMuted(trackId, muted, "GUI 轨道静音"),
            muted ? `轨道 ${trackId} 已静音` : `轨道 ${trackId} 已取消静音`)}
      />

      {workspaceClip && project.clips[workspaceClip] && (
        <ClipWorkspace
          clip={project.clips[workspaceClip]}
          assetPath={project.assets.find((a) => a.asset_id === project.clips[workspaceClip].asset_id)?.path}
          assetOrigin={project.assets.find((a) => a.asset_id === project.clips[workspaceClip].asset_id)?.origin}
          assetGen={(project.assets.find((a) => a.asset_id === project.clips[workspaceClip].asset_id) as { gen?: Record<string, unknown> } | undefined)?.gen}
          onClose={() => setWorkspaceClip(null)}
          onChanged={refresh}
        />
      )}

      {pendingDelete && (
        <div className="workspace-overlay" onClick={() => setPendingDelete(null)}>
          <div className="workspace" style={{ width: 460 }} onClick={(e) => e.stopPropagation()}>
            <div className="ws-header">
              <span className="ws-title">即将删除 {pendingDelete.clipId}，影响范围：</span>
            </div>
            <div className="ws-body">
              {pendingDelete.impact.will_sync.length > 0 && (
                <div className="ws-meta">
                  ✓ 强关联将同步删除：{pendingDelete.impact.will_sync.map((d) => `${d.text}（${d.kind}）`).join("、")}
                </div>
              )}
              {pendingDelete.impact.will_prompt.length > 0 && (
                <div className="ws-meta">
                  ◇ 建议检查：{pendingDelete.impact.will_prompt.map((d) => d.text).join("、")}
                </div>
              )}
              {pendingDelete.impact.untouched.length > 0 && (
                <div className="ws-meta">
                  × 不受影响：{pendingDelete.impact.untouched.map((d) => d.text).join("、")}
                </div>
              )}
              <div className="row" style={{ display: "flex", gap: 8, marginTop: 14 }}>
                <button
                  onClick={async () => {
                    const { clipId, impact } = pendingDelete;
                    setPendingDelete(null);
                    await run(async () => {
                      for (const d of impact.will_sync) {
                        await api.removeClip(d.clip_id, `随 ${clipId} 强关联同步删除`);
                      }
                      await api.removeClip(clipId, "GUI 删除（含强关联）");
                      setSelected(null);
                    }, "已删除（含强关联项）");
                  }}
                >
                  全部删除（含强关联）
                </button>
                <button
                  onClick={async () => {
                    const { clipId } = pendingDelete;
                    setPendingDelete(null);
                    await run(() => api.removeClip(clipId, "GUI 删除（仅本片段）").then(() => setSelected(null)), "已删除（仅本片段）");
                  }}
                >
                  只删本片段
                </button>
                <button onClick={() => setPendingDelete(null)}>取消</button>
              </div>
            </div>
          </div>
        </div>
      )}

      {showHelp && (
        <div className="workspace-overlay" onClick={() => setShowHelp(false)}>
          <div className="workspace" style={{ width: 560 }} onClick={(e) => e.stopPropagation()}>
            <div className="ws-header">
              <span className="ws-title">快捷键清单</span>
              <button onClick={() => setShowHelp(false)}>✕</button>
            </div>
            {/* GUI-03R3-W-D: labels are derived from the Core keymap
                (the same /keyboard/keymap the dispatcher consumes),
                not from a separate hardcoded string. There is no
                second shortcut definition. Mutation bindings that
                live outside the Core keymap (clipboard / history /
                zoom / multi-select) are listed under "其他" with
                an explicit "（非 Core 键位）" annotation so the
                reader knows those are not pinned by Core.
                No stale entries (M / Shift+Z / Esc are gone). */}
            <div className="ws-body" style={{ fontSize: 13, lineHeight: 1.9, color: "#ccc" }}>
              <b>走带</b>：{helpKeyLabel(keymap, ["Space", "K"], "播放/暂停")} ·{" "}
              {helpNudgeLabel(keymap, "J", "L")} ·{" "}
              {helpArrowNudgeLabel(keymap)} ·{" "}
              {helpBoundaryLabel(keymap)} ·{" "}
              {helpCenterLabel(keymap)}<br />
              <b>编辑</b>：{helpBindingLabel(keymap, "S", "切分（播放头）")} ·{" "}
              {helpBindingLabel(keymap, "Delete", "删除选区")} ·{" "}
              {helpBindingLabel(keymap, "Shift+Delete", "Ripple 删除")}<br />
              <b>标记</b>：{helpBindingLabel(keymap, "I", "入点 = 播放头")} ·{" "}
              {helpBindingLabel(keymap, "O", "出点 = 播放头")}<br />
              <b>多选</b>：Ctrl+点击 切换 · 批量删除/收拢（与 Delete 共用同一 Core 操作）<br />
              <b>剪贴板</b>（非 Core 键位）：Ctrl+C/V 复制粘贴 · Ctrl+D 复制到原片段之后 · Ctrl+A 全选<br />
              <b>历史</b>（非 Core 键位）：Ctrl+Z 撤销 · Ctrl+Shift+Z / Ctrl+Y 重做<br />
              <b>视图</b>（非 Core 键位）：滚轮 缩放（鼠标锚点） · 标尺拖拽=范围选择 · 顶栏「适配内容」按钮<br />
              <b>其他</b>：顶栏台词搜索 · 迷你地图点击跳转 · 拖到别的轨道=换轨
            </div>
          </div>
        </div>
      )}

      <div className="statusbar">
        <span className={status.ok ? "ok" : "err"}>{status.text}</span>
        {/* GUI-03R-Micro: explicit separator. Without the space
            inside the previous <span>, `·F0` and `86 clips` were
            visually concatenated (the leading bullet of the
            playhead label ran into the next span when the playhead
            was 0). The bullet now lives in its own span so flex
            gap is consistent across all status rows. */}
        <span aria-hidden="true" style={{ color: "#555" }}>·</span>
        <span data-testid="playhead-status">
          播放头 {frameToRulerSeconds(playheadFrame, seq.fps)} · F{playheadFrame}
        </span>
        <span aria-hidden="true" style={{ color: "#555" }}>·</span>
        <span>{Object.keys(project.clips).length} clips</span>
      </div>

      {subtitleEdit && (
        <div className="modal-overlay" onClick={() => setSubtitleEdit(null)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <SubtitleEditor
              initialText={subtitleEdit.text}
              initialStyle={subtitleEdit.style}
              start={subtitleEdit.start}
              end={subtitleEdit.end}
              presets={presets ?? undefined}
              onCancel={() => setSubtitleEdit(null)}
              onSave={async (text, style) => {
                const edit = subtitleEdit!;
                if (edit.clipId) {
                  // 编辑现有字幕
                  await api.editSubtitle(edit.clipId, text, "GUI 改字幕");
                  await api.setSubtitleStyle(edit.clipId, style as Record<string, unknown>, "GUI 改字幕样式");
                  setStatus({ ok: true, text: `字幕已更新 → ${edit.track_id ?? edit.clipId} ${edit.start.toFixed(1)}-${edit.end.toFixed(1)}s（重渲染后可见）` });
                } else {
                  // 新建字幕
                  await api.addSubtitle(text, edit.start, edit.end, "GUI 加字幕");
                  // 找到刚加的字幕（最新创建的 text 轨 clip）并应用样式
                  const proj = await api.project();
                  const textClips = proj.timeline.tracks
                    .filter((t) => t.kind === "text")
                    .flatMap((t) => t.clip_ids.map((id) => proj.clips[id]))
                    .filter(Boolean)
                    .filter((c) => Math.abs(c.timeline_range.start - edit.start) < 0.1);
                  const newest = textClips[textClips.length - 1];
                  if (newest) {
                    await api.setSubtitleStyle(newest.clip_id, style as Record<string, unknown>, "GUI 字幕样式");
                  }
                  setStatus({ ok: true, text: `字幕已加 → ${newest ? newest.track_id : "t1"} ${edit.start.toFixed(1)}-${edit.end.toFixed(1)}s（重渲染后可见）` });
                }
                setSubtitleEdit(null);
                refresh();
              }}
            />
          </div>
        </div>
      )}

      {exportOpen && (
        <div className="modal-overlay" onClick={() => setExportOpen(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <ExportPanel
              presets={presets?.export_presets ?? []}
              initial={{
                title: (project as any).publishing?.title ?? "",
                description: (project as any).publishing?.description ?? "",
                tags: ((project as any).publishing?.tags ?? []).join(","),
                burn_subtitles: burnSubs,
              }}
              onCancel={() => setExportOpen(false)}
              onExport={(cfg) => {
                run(async () => {
                  await api.exportPackage(cfg);
                  pollRender((preview) =>
                    setStatus({ ok: true,
                      text: `发布包已导出（mp4+cover+srt+metadata+report）：${preview}` }));
                  setExportOpen(false);
                }, "导出已开始");
              }}
            />
          </div>
        </div>
      )}
    </div>
  );
}
