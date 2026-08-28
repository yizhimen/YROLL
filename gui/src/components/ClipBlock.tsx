import { useEffect, useRef, useState } from "react";
import { Clip } from "../api";

// 波形缓存：同一素材全工程共享一份（AI 分析一次长期使用，波形也是）
const waveCache = new Map<string, Promise<{ peaks: number[]; duration: number | null }>>();

function loadWave(assetId: string) {
  if (!waveCache.has(assetId)) {
    waveCache.set(
      assetId,
      fetch(`/assets/${assetId}/waveform?points=300`)
        .then((r) => (r.ok ? r.json() : { peaks: [], duration: null }))
        .catch(() => ({ peaks: [], duration: null }))
    );
  }
  return waveCache.get(assetId)!;
}

interface Props {
  clip: Clip;
  selected: boolean;
  locked?: boolean;
  pxPerSec: number;
  snapMode?: "always" | "alt" | "off";
  highlightRel?: boolean;
  /** 同轨其他 clip（用于拖动时检测重叠边界，不弹回） */
  siblings?: Array<{ id: string; start: number; end: number }>;
  /** 是否被跨轨关联高亮（来自 Timeline 的 highlightRel + semantic link） */
  isRelated?: boolean;
  onSelect: (clipId: string, viaAiZone: boolean, ctrl?: boolean) => void;
  onDragMove: (clipId: string, deltaSec: number) => void;
  onTrimCommit: (clipId: string, newStart: number | null, newEnd: number | null) => void;
  onDropOnTrack?: (clipId: string, trackId: string) => void;
}

/**
 * Clip 上下双层（蓝图 §3.1）：
 * 上 1/3 = AI Context 区（点击 → 打开 Clip Workspace，后续接 Y 轴）
 * 下 2/3 = 普通编辑区（点击选中、拖动移动、左右边缘拖拽 Trim）
 */
export default function ClipBlock({
  clip, selected, locked, pxPerSec, siblings = [],
  snapMode = "always", highlightRel = false, isRelated = false,
  onSelect, onDragMove, onTrimCommit, onDropOnTrack,
}: Props) {
  // 边缘 Trim 的本地预览（松手才提交 API）
  const [trimDelta, setTrimDelta] = useState<{ dStart: number; dEnd: number } | null>(null);

  const dStart = trimDelta?.dStart ?? 0;
  const dEnd = trimDelta?.dEnd ?? 0;
  // trim 头：源起点 +dStart，时间轴起点同步 +dStart/speed；trim 尾：时间轴终点 -dEnd/speed
  const tlStart = clip.timeline_range.start + dStart / clip.speed;
  const tlEnd = clip.timeline_range.end + dEnd / clip.speed;
  const left = tlStart * pxPerSec;
  const width = Math.max(8, (tlEnd - tlStart) * pxPerSec);

  const kindClass = clip.track_id.startsWith("t")
    ? "kind-text"
    : clip.track_id.startsWith("a")
      ? "kind-audio"
      : "";

  const label =
    clip.context?.text ||
    clip.context?.scene ||
    `${clip.source_range.start.toFixed(1)}-${clip.source_range.end.toFixed(1)}s`;

  // 波形背景（视频/音频 clip）：按源区间从全素材波形里切片
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const isMedia = clip.asset_id !== "";
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !isMedia) return;
    let dead = false;
    loadWave(clip.asset_id).then(({ peaks, duration }) => {
      if (dead || !peaks.length) return;
      const ctx = canvas.getContext("2d");
      if (!ctx) return;
      const w = (canvas.width = canvas.clientWidth || 100);
      const h = (canvas.height = canvas.clientHeight || 20);
      ctx.clearRect(0, 0, w, h);
      ctx.fillStyle = "rgba(126, 201, 126, 0.55)";
      const dur = duration || clip.source_range.end;
      const i0 = Math.floor((clip.source_range.start / dur) * peaks.length);
      const i1 = Math.max(i0 + 1, Math.ceil((clip.source_range.end / dur) * peaks.length));
      const slice = peaks.slice(i0, i1);
      const barW = w / slice.length;
      slice.forEach((p, i) => {
        const bh = Math.max(1, p * h);
        ctx.fillRect(i * barW, (h - bh) / 2, Math.max(1, barW - 0.5), bh);
      });
    });
    return () => { dead = true; };
  }, [clip.asset_id, clip.source_range.start, clip.source_range.end,
      pxPerSec, isMedia, width]);

  const onPointerDown = (e: React.PointerEvent) => {
    if ((e.target as HTMLElement).classList.contains("ai-zone")) return;
    if ((e.target as HTMLElement).classList.contains("trim-handle")) return;
    onSelect(clip.clip_id, false, e.ctrlKey || e.metaKey);
    if (locked) return;  // 轨道锁定：禁拖动
    const startX = e.clientX;
    const origStart = clip.timeline_range.start;
    const origEnd = clip.timeline_range.end;
    const len = origEnd - origStart;
    // 计算同轨其他 clip 的位置（用于碰撞边界检测）
    const otherRanges = siblings
      .filter((s) => s.id !== clip.clip_id)
      .map((s) => ({ start: s.start, end: s.end }))
      .sort((a, b) => a.start - b.start);

    /** 把尝试的 newStart 限制到不重叠的范围（剪映/Premiere 行为：拖到边界即停）。

        方向感知：向右拖撞到右边 clip → snap before；向左拖撞到左边 clip → snap after。 */
    const clamp = (tryStart: number) => {
      const tryEnd = tryStart + len;
      const conflicts = otherRanges.filter(
        (r) => tryStart < r.end && r.start < tryEnd
      );
      if (conflicts.length === 0) return Math.max(0, tryStart);

      if (tryStart >= origStart) {
        // 向右拖：snap 到第一个冲突 clip 的左侧（r.start - len）
        const first = conflicts.reduce((a, b) => a.start < b.start ? a : b);
        return Math.max(0, first.start - len);
      } else {
        // 向左拖：snap 到最后一个冲突 clip 的右侧（r.end）
        const last = conflicts.reduce((a, b) => a.end > b.end ? a : b);
        return Math.max(0, last.end);
      }
    };

    /** 按住 Alt 时：磁吸到邻居边界 / 播放头 / 0 点（剪映/Premiere 行为）。 */
    const SNAP_RADIUS_SEC = 0.3;
    const snap = (tryStart: number) => {
      // 候选磁吸点：自己两端的左右 + 所有邻居两端的左右 + 0
      const candidates: number[] = [0];
      candidates.push(origStart);  // 保留原位（拖回去时吸附）
      for (const r of otherRanges) {
        candidates.push(r.start, r.end);
      }
      const tryEnd = tryStart + len;
      // 检查起点的吸附
      for (const cand of candidates) {
        if (Math.abs(tryStart - cand) < SNAP_RADIUS_SEC) return cand;
      }
      // 检查终点的吸附（让右边缘也能磁吸到邻居左边缘）
      for (const cand of candidates) {
        if (Math.abs(tryEnd - cand) < SNAP_RADIUS_SEC) return cand - len;
      }
      return null;
    };

    const move = (ev: PointerEvent) => {
      const delta = (ev.clientX - startX) / pxPerSec;
      const want = origStart + delta;
      let next: number;
      const allowSnap = snapMode === "always" || (snapMode === "alt" && ev.altKey);
      if (allowSnap) {
        const snapTarget = snap(want);
        if (snapTarget !== null) {
          next = snapTarget;
        } else {
          next = Math.max(0, want);
        }
      } else {
        next = clamp(want);
      }
      onDragMove(clip.clip_id, next);
    };
    const up = (ev: PointerEvent) => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
      // 竖向拖轨：松手位置落在别的轨道行 → 换轨
      const row = document.elementsFromPoint(ev.clientX, ev.clientY)
        .find((el) => (el as HTMLElement).dataset?.trackId) as HTMLElement | undefined;
      const tid = row?.dataset.trackId;
      if (tid && tid !== clip.track_id && onDropOnTrack) {
        onDropOnTrack(clip.clip_id, tid);
      }
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
  };

  const onEdgeDown = (e: React.PointerEvent, edge: "left" | "right") => {
    e.stopPropagation();
    onSelect(clip.clip_id, false, e.ctrlKey || e.metaKey);
    if (locked) return;  // 轨道锁定：禁裁剪
    const startX = e.clientX;
    let cur = { dStart: 0, dEnd: 0 };
    const move = (ev: PointerEvent) => {
      const delta = ((ev.clientX - startX) / pxPerSec) * clip.speed; // 时间轴秒 → 源秒
      if (edge === "left") {
        // 源区间 [start, end)：头最多拖到尾 -0.1s，且不小于 0
        const maxD = clip.source_range.end - clip.source_range.start - 0.1;
        const d = Math.min(maxD, Math.max(-clip.source_range.start, delta));
        cur = { dStart: d, dEnd: 0 };
      } else {
        const maxD = clip.source_range.end - clip.source_range.start - 0.1;
        const d = Math.max(-maxD, delta);
        cur = { dStart: 0, dEnd: d };
      }
      setTrimDelta({ ...cur });
    };
    const up = () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
      setTrimDelta(null);
      const minChange = 0.05;
      if (edge === "left" && Math.abs(cur.dStart) > minChange) {
        onTrimCommit(clip.clip_id, clip.source_range.start + cur.dStart, null);
      } else if (edge === "right" && Math.abs(cur.dEnd) > minChange) {
        onTrimCommit(clip.clip_id, null, clip.source_range.end + cur.dEnd);
      }
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
  };

  return (
    <div
      className={`clip ${kindClass} ${selected ? "selected" : ""} ${isRelated && highlightRel ? "related" : ""}`}
      style={{ left, width, boxShadow: isRelated && highlightRel ? "0 0 0 2px #ffd479" : undefined }}
      onPointerDown={onPointerDown}
      title={isRelated ? "跨轨关联 clip（Semantic Link）" : undefined}
    >
      <div
        className="trim-handle left"
        title="拖动裁剪头部"
        onPointerDown={(e) => onEdgeDown(e, "left")}
      />
      <div
        className="ai-zone"
        title="AI Context 区：点击打开 Clip Workspace（Y 轴）"
        onClick={(e) => {
          e.stopPropagation();
          onSelect(clip.clip_id, true);
        }}
      >
        Y · {clip.context?.why || "AI"}
      </div>
      <div className="edit-zone" title={`源 ${(clip.source_range.start + dStart).toFixed(1)}-${(clip.source_range.end + dEnd).toFixed(1)}s · 速度 ${clip.speed}x · 音量 ${clip.volume}`}>
        {isMedia && <canvas ref={canvasRef} className="wave-canvas" />}
        {isMedia && !kindClass && width > 60 && (
          <img
            className="clip-thumb"
            src={`/assets/${clip.asset_id}/thumbnail?t=${(clip.source_range.start + 0.1).toFixed(1)}`}
            alt=""
            draggable={false}
            onError={(e) => { (e.target as HTMLImageElement).style.display = "none"; }}
          />
        )}
        <span className="clip-label">
          {clip.context?.muted ? "🔇 " : ""}{label}（{(tlEnd - tlStart).toFixed(1)}s）
        </span>
      </div>
      <div
        className="trim-handle right"
        title="拖动裁剪尾部"
        onPointerDown={(e) => onEdgeDown(e, "right")}
      />
    </div>
  );
}
