// 素材库面板：导入 / 列表 / 一键加到时间轴（追加到对应轨道末尾）。

import { useState } from "react";
import { api, Project } from "../api";

interface Props {
  project: Project;
  activeTimelineId: string;
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

export default function AssetPanel({ project, activeTimelineId, onChanged, onStatus, onPreview }: Props) {
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
    try {
      // GUI-03R-Micro: the "+" / ⧉ buttons do NOT pick a track on
      // the GUI side. They pass no track_id (server translates
      // empty → None) so Core's Track Allocation Policy picks the
      // minimum suitable non-overlapping track. Image and video
      // sharing V1 when their time ranges don't overlap is a Core
      // guarantee, not a GUI side computation.
      //
      // Explicit-track behavior (drop-on-track → App.tsx
      // onAssetDrop) is unchanged: the drop target's track_id is
      // forwarded to Core, and Core rejects overlap there.
      let explicitTrackId: string | null = null;
      if (mode === "overlay") {
        // Overlay = "create a new dedicated PiP/B-roll video
        // track". The user is explicit about wanting a new track.
        const tl = project.timelines?.find(
          (tl) => tl.timeline_id === activeTimelineId)
          ?? project.timelines?.[0];
        const tlTracks = tl?.tracks ?? project.timeline.tracks;
        const vTracks = tlTracks.filter((t) => t.kind === "video");
        const newTrack = await api.addTrack("video",
          `v${vTracks.length + 1}`);
        explicitTrackId = newTrack.track_id;
      }
      const tlStart = 0;  // Core allocator picks the start frame
      if (asset.type === "image") {
        // GUI-03R: image goes through the frame-native
        // /clips/add_image endpoint. No set_speed, no seconds-as-
        // duration hack. Default 5 seconds @ the project's sequence
        // fps.
        const fps = project.sequence?.fps ?? { num: 30, den: 1 };
        const DEFAULT_IMG_DUR_SEC = 5;
        const durFrames = Math.round(
          DEFAULT_IMG_DUR_SEC * fps.num / fps.den);
        await api.addImageClip(assetId, tlStart, durFrames, explicitTrackId,
          mode === "overlay" ? "素材库加入（叠加轨）" : "素材库加入");
      } else {
        const dur = asset.identity.duration_sec;
        if (!dur) {
          onStatus(false, "该素材无时长，不能上时间轴");
          return;
        }
        await api.addClip(assetId, 0, dur, tlStart, explicitTrackId,
          mode === "overlay" ? "素材库加入（叠加轨）" : "素材库加入");
      }
      await onChanged();
      onStatus(true,
        `${baseName(asset.path)} 已加入（Core allocator 选轨）`);
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
