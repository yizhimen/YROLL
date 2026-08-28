// 素材库面板：导入 / 列表 / 一键加到时间轴（追加到对应轨道末尾）。

import { useState } from "react";
import { api, Project } from "../api";

interface Props {
  project: Project;
  onChanged: () => Promise<void>;
  onStatus: (ok: boolean, text: string) => void;
  onPreview: (assetId: string) => void;
}

const TYPE_ICON: Record<string, string> = {
  video: "🎬", audio: "🎵", image: "🖼", subtitle: "💬", document: "📄",
};

function baseName(p: string) {
  return p.split(/[\\/]/).pop() || p;
}

export default function AssetPanel({ project, onChanged, onStatus, onPreview }: Props) {
  const [filter, setFilter] = useState("");
  const importFiles = async (files: FileList) => {
    try {
      let added = 0;
      for (const f of Array.from(files)) {
        const r = await api.importAsset(f);
        if (!r.deduped) added++;
      }
      await onChanged();
      onStatus(true, `导入完成：新增 ${added} 个（重复自动跳过）`);
    } catch (e) {
      onStatus(false, `导入失败：${e}`);
    }
  };

  const addToTimeline = async (assetId: string, mode: "matched" | "overlay") => {
    const asset = project.assets.find((a) => a.asset_id === assetId);
    if (!asset) return;
    const dur = asset.identity.duration_sec;
    if (!dur) {
      onStatus(false, "该素材无时长的（暂不支持图片/文档上时间轴）");
      return;
    }
    try {
      let track;
      if (mode === "overlay") {
        // 新建叠加轨（v2/v3…）：PiP/B-roll 专用
        const vTracks = project.timeline.tracks.filter((t) => t.kind === "video");
        track = await api.addTrack("video", `v${vTracks.length + 1}`);
      } else {
        const kind = asset.type === "audio" ? "audio" : "video";
        track = project.timeline.tracks.find((t) => t.kind === kind);
        if (!track) {
          // 同类轨不存在就建（修：音频不再错落到视频轨）
          track = await api.addTrack(kind, kind === "audio" ? "a1" : "v1");
        }
      }
      const tlStart = Math.max(
        0,
        ...track.clip_ids.map((id) => project.clips[id]?.timeline_range.end ?? 0)
      );
      await api.addClip(assetId, 0, dur, tlStart, track.track_id,
        mode === "overlay" ? "素材库加入（叠加轨）" : "素材库加入");
      await onChanged();
      onStatus(true, `${baseName(asset.path)} 已加到 ${track.track_id}`);
    } catch (e) {
      onStatus(false, `添加失败：${e}`);
    }
  };

  return (
    <div className="asset-panel">
      <div className="asset-header">
        <span>素材库（{project.assets.length}）</span>
        <button
          onClick={() => {
            const input = document.createElement("input");
            input.type = "file";
            input.multiple = true;
            input.accept = "video/*,audio/*,image/*";
            input.onchange = () => input.files?.length && importFiles(input.files);
            input.click();
          }}
        >
          导入…
        </button>
      </div>
      <div className="asset-list">
        {project.assets.length > 5 && (
          <input
            className="asset-filter"
            placeholder="过滤素材…"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
          />
        )}
        {project.assets.length === 0 && (
          <div className="asset-empty">还没有素材，点「导入…」开始</div>
        )}
        {project.assets
          .filter((a) => !filter || baseName(a.path).toLowerCase().includes(filter.toLowerCase()))
          .map((a) => (
          <div key={a.asset_id} className="asset-item" title={`${a.path}
点击预览 · 拖到时间轴`}
               draggable
               onDragStart={(e) => {
                 e.dataTransfer.setData("text/yroll-asset", a.asset_id);
                 e.dataTransfer.effectAllowed = "copy";
               }}>
            <span className="asset-icon">{TYPE_ICON[a.type] || "📦"}</span>
            <span className="asset-name" style={{ cursor: "pointer" }}
                  onClick={() => onPreview(a.asset_id)}>{baseName(a.path)}</span>
            <span className="asset-meta">
              {a.identity.duration_sec ? `${a.identity.duration_sec.toFixed(1)}s` : ""}
              {a.identity.width ? ` ${a.identity.width}×${a.identity.height}` : ""}
            </span>
            <button className="asset-add" title="加到时间轴末尾"
                    onClick={() => addToTimeline(a.asset_id, "matched")}>
              ＋
            </button>
            {(a.type === "video" || a.type === "image") && (
              <button className="asset-add" title="新建叠加轨（PiP/B-roll）"
                      onClick={() => addToTimeline(a.asset_id, "overlay")}>
                ⧉
              </button>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
