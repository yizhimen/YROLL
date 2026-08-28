import { useRef, useState } from "react";
import { Project } from "../api";
import ClipBlock from "./ClipBlock";

interface Props {
  project: Project;
  selectedIds: Set<string>;
  playhead: number;
  pxPerSec: number;
  selRange: [number, number] | null;
  inPoint?: number | null;
  outPoint?: number | null;
  height?: number;  // 可调高度（默认 240）
  snapMode?: "always" | "alt" | "off";  // 磁吸模式
  highlightRel?: boolean;  // 高亮跨轨关联
  onSeek: (t: number) => void;
  onSelect: (clipId: string, viaAiZone: boolean, ctrl?: boolean) => void;
  onDragMove: (clipId: string, newStart: number) => void;
  onZoomPx: (px: number) => void;
  onRangeSelect: (r: [number, number] | null) => void;
  onTrimCommit: (clipId: string, newStart: number | null, newEnd: number | null) => void;
  onDropOnTrack?: (clipId: string, trackId: string) => void;
  onTrackMute?: (trackId: string, muted: boolean) => void;
  onTrackLock?: (trackId: string, locked: boolean) => void;
  onTrackHide?: (trackId: string, hidden: boolean) => void;
  onAssetDrop?: (assetId: string, trackId: string, timelineStart: number) => void;
}

const TRACK_NAME: Record<string, string> = { video: "视频", audio: "音频", text: "字幕" };

export default function Timeline({
  project, selectedIds, playhead, pxPerSec, selRange, inPoint, outPoint,
  height = 240,
  snapMode = "always",
  highlightRel = false,
  onSeek, onSelect, onDragMove, onZoomPx, onRangeSelect, onTrimCommit, onDropOnTrack, onTrackMute, onTrackLock, onTrackHide, onAssetDrop,
}: Props) {
  const paneRef = useRef<HTMLDivElement | null>(null);
  const [viewport, setViewport] = useState({ left: 0, width: 1 });
  const syncViewport = () => {
    const pane = paneRef.current;
    if (!pane) return;
    const total = Math.max(1, duration * pxPerSec + 40);
    setViewport({
      left: pane.scrollLeft / total,
      width: Math.min(1, pane.clientWidth / total),
    });
  };
  const duration = Math.max(
    10,
    ...Object.values(project.clips).map((c) => c.timeline_range.end)
  );
  const width = duration * pxPerSec + 40;
  const ticks: number[] = [];
  const step = duration > 120 ? 30 : duration > 60 ? 10 : 5;
  for (let t = 0; t <= duration; t += step) ticks.push(t);

  // 滚轮以鼠标位置为锚点缩放（蓝图 §2.6）
  const onWheel = (e: React.WheelEvent) => {
    if (!e.ctrlKey && Math.abs(e.deltaY) < Math.abs(e.deltaX)) return; // 横向滚动不抢
    const pane = paneRef.current;
    if (!pane) return;
    e.preventDefault();
    const rect = pane.getBoundingClientRect();
    const mouseX = e.clientX - rect.left + pane.scrollLeft;
    const anchorTime = mouseX / pxPerSec;
    const factor = e.deltaY < 0 ? 1.25 : 0.8;
    const next = Math.min(60, Math.max(4, pxPerSec * factor));
    onZoomPx(next);
    // 状态更新后把锚点时间放回鼠标下
    requestAnimationFrame(() => {
      pane.scrollLeft = anchorTime * next - (e.clientX - rect.left);
    });
  };

  // 标尺：点按 = seek，拖拽 = 时间范围选择（蓝图 §2.4 不必先 Split）
  const dragT = useRef<number | null>(null);
  const onRulerDown = (e: React.PointerEvent) => {
    const rect = (e.currentTarget as HTMLElement).getBoundingClientRect();
    dragT.current = (e.clientX - rect.left) / pxPerSec;
    const move = (ev: PointerEvent) => {
      if (dragT.current === null) return;
      const t = Math.max(0, (ev.clientX - rect.left) / pxPerSec);
      if (Math.abs(t - dragT.current) * pxPerSec > 4) {
        onRangeSelect([Math.min(dragT.current, t), Math.max(dragT.current, t)]);
      }
    };
    const up = (ev: PointerEvent) => {
      if (dragT.current !== null) {
        const t = Math.max(0, (ev.clientX - rect.left) / pxPerSec);
        if (Math.abs(t - dragT.current) * pxPerSec <= 4) {
          onSeek(t);           // 没拖成范围 = 点击 seek
          onRangeSelect(null);
        }
      }
      dragT.current = null;
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
  };

  return (
    <div className="timeline-pane" ref={paneRef} onWheel={onWheel} onScroll={syncViewport}
      style={{ height, flexShrink: 0 }}>
      {/* 双刻度导航：全局迷你地图（蓝图 §2.6），点击/拖拽跳转 + 视口指示 */}
      <div
        className="minimap"
        onPointerDown={(e) => {
          const pane = paneRef.current;
          const rect = (e.currentTarget as HTMLElement).getBoundingClientRect();
          const jump = (clientX: number) => {
            const ratio = Math.min(1, Math.max(0, (clientX - rect.left) / rect.width));
            const t = ratio * duration;
            onSeek(t);
            if (pane) {
              pane.scrollLeft = t * pxPerSec - pane.clientWidth / 2;
            }
          };
          jump(e.clientX);
          const move = (ev: PointerEvent) => jump(ev.clientX);
          const up = () => {
            window.removeEventListener("pointermove", move);
            window.removeEventListener("pointerup", up);
          };
          window.addEventListener("pointermove", move);
          window.addEventListener("pointerup", up);
        }}
      >
        {project.timeline.tracks.flatMap((track) =>
          track.clip_ids.map((cid) => {
            const c = project.clips[cid];
            if (!c) return null;
            return (
              <div
                key={cid}
                className={`minimap-clip ${track.kind}`}
                style={{
                  left: `${(c.timeline_range.start / duration) * 100}%`,
                  width: `${((c.timeline_range.end - c.timeline_range.start) / duration) * 100}%`,
                }}
              />
            );
          })
        )}
        <div
          className="minimap-viewport"
          style={{ left: `${viewport.left * 100}%`, width: `${viewport.width * 100}%` }}
        />
        <div className="minimap-playhead" style={{ left: `${(playhead / duration) * 100}%` }} />
      </div>
      <div className="timeline-body">
        {/* Playhead 贯穿 ruler + 所有轨道（剪映/Premiere 风格） */}
        <div className="playhead-full"
          style={{ left: 110 + playhead * pxPerSec }} />
        <div className="ruler" style={{ width, paddingLeft: 110 }} onPointerDown={onRulerDown}>
          {ticks.map((t) => (
            <div key={t} className="tick" style={{ left: t * pxPerSec }}>
              {t}s
            </div>
          ))}
          {selRange && (
            <div
              className="range-sel"
              style={{
                left: selRange[0] * pxPerSec,
                width: (selRange[1] - selRange[0]) * pxPerSec,
              }}
            />
          )}
          {inPoint != null && (
            <div className="io-marker" style={{ left: inPoint * pxPerSec }}>I</div>
          )}
          {outPoint != null && (
            <div className="io-marker out" style={{ left: outPoint * pxPerSec }}>O</div>
          )}
        </div>
        <div className="tracks">
        {/* 倒序：T1/T2 字幕轨显示在最上（视觉上盖住 V1/V2/V3） */}
        {[...project.timeline.tracks].reverse().map((track) => (
          <div
            key={track.track_id}
            className={`track-row ${track.hidden ? "track-hidden" : ""}`}
            style={{ width, display: track.hidden ? "none" : "flex" }}
            data-track-id={track.track_id}
          >
            <div className="track-label-gutter"
                 onDragOver={(e) => { e.preventDefault(); e.dataTransfer.dropEffect = "none"; }}>
              <span className="track-label-title">{TRACK_NAME[track.kind] || track.kind} · {track.track_id}</span>
              <div className="track-label-buttons">
              {track.kind !== "text" && (
                <button
                  className={track.muted ? "muted" : ""}
                  title={track.muted ? "取消轨道静音" : "轨道静音"}
                  onClick={(e) => {
                    e.stopPropagation();
                    onTrackMute?.(track.track_id, !track.muted);
                  }}
                >
                  {track.muted ? "取消静音" : "静音"}
                </button>
              )}
              <button
                className={track.locked ? "locked" : ""}
                title={track.locked ? "解锁轨道" : "锁定轨道（禁拖动）"}
                onClick={(e) => {
                  e.stopPropagation();
                  onTrackLock?.(track.track_id, !track.locked);
                }}
              >
                {track.locked ? "解锁" : "锁定"}
              </button>
              <button
                className={track.hidden ? "hidden-active" : ""}
                title={track.hidden ? "显示轨道（点击恢复）" : "隐藏轨道（仅 GUI 不显示，渲染仍参与）"}
                onClick={(e) => {
                  e.stopPropagation();
                  onTrackHide?.(track.track_id, !track.hidden);
                }}
              >
                {track.hidden ? "显示" : "隐藏"}
              </button>
              </div>
            </div>
            <div
              className="track-content"
              onDragOver={(e) => {
                if (e.dataTransfer.types.includes("text/yroll-asset")) {
                  e.preventDefault();
                  e.dataTransfer.dropEffect = "copy";
                }
              }}
              onDrop={(e) => {
                const assetId = e.dataTransfer.getData("text/yroll-asset");
                if (!assetId) return;
                e.preventDefault();
                const rect = (e.currentTarget as HTMLElement).getBoundingClientRect();
                const t = Math.max(0, (e.clientX - rect.left) / pxPerSec);
                onAssetDrop?.(assetId, track.track_id, Math.round(t * 10) / 10);
              }}
              data-track-content={track.track_id}
            >
            {track.clip_ids.map((cid) => {
              const clip = project.clips[cid];
              if (!clip) return null;
              const siblings = track.clip_ids
                .filter((sid) => sid !== cid)
                .map((sid) => {
                  const s = project.clips[sid];
                  return s && {
                    id: sid,
                    start: s.timeline_range.start,
                    end: s.timeline_range.end,
                  };
                })
                .filter(Boolean) as Array<{ id: string; start: number; end: number }>;
              return (
                <ClipBlock
                  key={cid}
                  clip={clip}
                  locked={track.locked}
                  selected={selectedIds.has(cid)}
                  pxPerSec={pxPerSec}
                  snapMode={snapMode}
                  highlightRel={highlightRel}
                  isRelated={highlightRel && selectedIds.size > 0 && Array.from(selectedIds).some((selId) => {
                    const sel = project.clips[selId];
                    if (!sel || sel.track_id === clip.track_id) return false;
                    return clip.timeline_range.start < sel.timeline_range.end &&
                           sel.timeline_range.start < clip.timeline_range.end;
                  })}
                  siblings={siblings}
                  onSelect={onSelect}
                  onDragMove={onDragMove}
                  onTrimCommit={onTrimCommit}
                  onDropOnTrack={onDropOnTrack}
                />
              );
            })}
            </div>
          </div>
        ))}
        </div>
      </div>
    </div>
  );
}
