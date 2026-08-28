// 导出面板：选平台 preset → 自动填宽度/高度/烧字幕 → 设置标题/描述/标签。

import { useEffect, useState } from "react";

interface ExportPreset {
  id: string;
  name: string;
  width: number;
  height: number;
  fps: number;
  platform: string;
  burn_subtitles: boolean;
}

interface Props {
  presets: ExportPreset[];
  initial?: {
    width?: number; height?: number; fps?: number;
    title?: string; description?: string; tags?: string;
    burn_subtitles?: boolean;
    platform?: string;
    cover_offset_sec?: number;
  };
  onCancel: () => void;
  onExport: (cfg: {
    width: number; height: number; fps: number;
    title: string; description: string; tags: string;
    burn_subtitles: boolean;
    platform: string;
    cover_offset_sec: number;
  }) => void;
}

export default function ExportPanel({ presets, initial, onCancel, onExport }: Props) {
  const [presetId, setPresetId] = useState(initial?.platform ?? "douyin");
  const [width, setWidth] = useState(initial?.width ?? 1080);
  const [height, setHeight] = useState(initial?.height ?? 1920);
  const [fps, setFps] = useState(initial?.fps ?? 30);
  const [burn, setBurn] = useState(initial?.burn_subtitles ?? true);
  const [title, setTitle] = useState(initial?.title ?? "");
  const [desc, setDesc] = useState(initial?.description ?? "");
  const [tags, setTags] = useState(initial?.tags ?? "");
  const [coverOffset, setCoverOffset] = useState(initial?.cover_offset_sec ?? 0.5);

  // 选 preset 自动填宽度/高度/烧录
  useEffect(() => {
    const p = presets.find((x) => x.id === presetId);
    if (p) {
      setWidth(p.width);
      setHeight(p.height);
      setFps(p.fps);
      setBurn(p.burn_subtitles);
    }
  }, [presetId, presets]);

  const handleExport = () => onExport({
    width, height, fps, burn_subtitles: burn,
    title: title.trim(),
    description: desc.trim(),
    tags: tags.trim(),
    platform: presetId,
    cover_offset_sec: coverOffset,
  });

  return (
    <div className="export-panel">
      <div className="export-header">
        <span>📤 导出发布包</span>
        <button onClick={onCancel}>取消</button>
        <button className="primary" onClick={handleExport}>开始导出</button>
      </div>

      <div className="export-section">
        <label>平台：</label>
        {presets.map((p) => (
          <button key={p.id}
            className={`platform-btn ${presetId === p.id ? "active" : ""}`}
            onClick={() => setPresetId(p.id)}>
            {p.name} <small style={{ color: "#888" }}>{p.width}×{p.height}</small>
          </button>
        ))}
      </div>

      <div className="export-section">
        <label>分辨率：</label>
        <input type="number" value={width}
          onChange={(e) => setWidth(Number(e.target.value))} />
        <span>×</span>
        <input type="number" value={height}
          onChange={(e) => setHeight(Number(e.target.value))} />
        <label>FPS：</label>
        <select value={fps} onChange={(e) => setFps(Number(e.target.value))}>
          <option value={24}>24</option>
          <option value={30}>30</option>
          <option value={60}>60</option>
        </select>
      </div>

      <div className="export-section">
        <label>封面偏移：</label>
        <input type="number" step={0.1} min={0} value={coverOffset}
          onChange={(e) => setCoverOffset(Number(e.target.value))} />
        <small style={{ color: "#888" }}>秒（取视频第 N 秒做封面）</small>
      </div>

      <div className="export-section">
        <label>字幕烧录：</label>
        <input type="checkbox" checked={burn}
          onChange={(e) => setBurn(e.target.checked)} />
        <small style={{ color: "#888" }}>
          烧录后字幕不可编辑；不烧录则导出独立 .srt 文件供平台上传
        </small>
      </div>

      <div className="export-section">
        <label>标题：</label>
        <input value={title} onChange={(e) => setTitle(e.target.value)}
          placeholder="例如：30 秒看完柴烧茶器之美" />
      </div>

      <div className="export-section">
        <label>描述：</label>
        <textarea value={desc} onChange={(e) => setDesc(e.target.value)}
          placeholder="视频简介…" rows={3} />
      </div>

      <div className="export-section">
        <label>标签：</label>
        <input value={tags} onChange={(e) => setTags(e.target.value)}
          placeholder="逗号分隔：柴烧, 茶器, 手作" />
      </div>

      <div className="export-files">
        <small>导出文件：</small>
        <ul>
          <li>video.mp4 - 成片视频</li>
          <li>cover.jpg - 封面（取自偏移秒）</li>
          <li>subtitles.srt - 字幕轨（始终输出）</li>
          <li>metadata.json - 标题/描述/标签/平台</li>
          <li>report.json - 工程快照 + 成本</li>
        </ul>
      </div>
    </div>
  );
}
