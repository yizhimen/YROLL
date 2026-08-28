// 字幕编辑器：文字 + 样式（字号/颜色/粗体/位置/对齐/预设）。
//
// 替代简陋的 window.prompt("字幕内容：")。
// 字段参考剪映/Premiere 字幕面板，但只保留 YROLL preset 里的 5 个样式。

import { useEffect, useState } from "react";

export interface SubtitleStyle {
  font_size?: number;
  color?: string;
  bold?: boolean;
  position?: "top" | "middle" | "bottom";
  align?: "left" | "center" | "right";
  outline_color?: string;
  outline_width?: number;
  font_id?: string;
}

interface SubtitlePreset {
  id: string;
  name: string;
  font_size: number;
  color: string;
  bold: boolean;
  position: "top" | "middle" | "bottom";
  align: "left" | "center" | "right";
  outline_color: string;
  outline_width: number;
}

interface FontPreset {
  id: string;
  name: string;
}

interface Props {
  initialText: string;
  initialStyle: SubtitleStyle;
  start: number;
  end: number;
  presets?: { fonts: FontPreset[]; subtitle_styles: SubtitlePreset[] };
  onCancel: () => void;
  onSave: (text: string, style: SubtitleStyle) => void;
}

const DEFAULT_STYLE: SubtitleStyle = {
  font_size: 38, color: "white", bold: true,
  position: "bottom", align: "center",
  outline_color: "black", outline_width: 2,
};

// presets 为空时的兜底（避免 API 失败阻塞 UI）
const FALLBACK_FONTS: FontPreset[] = [
  { id: "msyh", name: "微软雅黑" },
  { id: "simhei", name: "黑体" },
];
const FALLBACK_STYLES: SubtitlePreset[] = [
  { id: "white_bottom", name: "底部白字",
    font_size: 38, color: "white", bold: true,
    position: "bottom", align: "center",
    outline_color: "black", outline_width: 2 },
  { id: "yellow_title", name: "顶部黄字",
    font_size: 56, color: "#ffd479", bold: true,
    position: "top", align: "center",
    outline_color: "black", outline_width: 3 },
  { id: "small_caption", name: "底部小字",
    font_size: 24, color: "#cccccc", bold: false,
    position: "bottom", align: "left",
    outline_color: "black", outline_width: 1 },
];

export default function SubtitleEditor({
  initialText, initialStyle, start, end,
  presets,
  onCancel, onSave,
}: Props) {
  // 用 props 或 fallback，确保即使 presets 加载失败也能用
  const safePresets: { fonts: FontPreset[]; subtitle_styles: SubtitlePreset[] } =
    presets ?? { fonts: [], subtitle_styles: [] };
  const fonts = safePresets.fonts?.length ? safePresets.fonts : FALLBACK_FONTS;
  const styles = safePresets.subtitle_styles?.length ? safePresets.subtitle_styles : FALLBACK_STYLES;

  const [text, setText] = useState(initialText);
  const [style, setStyle] = useState<SubtitleStyle>({ ...DEFAULT_STYLE, ...initialStyle });

  // 文本同步：从 props 更新（覆盖）
  useEffect(() => setText(initialText), [initialText]);

  const applyPreset = (id: string) => {
    const p = safePresets.subtitle_styles.find((x) => x.id === id);
    if (p) setStyle({ ...p });
  };

  const fmt = (s: number) => {
    const m = Math.floor(s / 60), sec = Math.floor(s % 60);
    const ms = Math.floor((s % 1) * 100);
    return `${m}:${sec.toString().padStart(2, "0")}.${ms.toString().padStart(2, "0")}`;
  };

  return (
    <div className="subtitle-editor">
      <div className="subtitle-editor-header">
        <span>✏️ 字幕编辑</span>
        <span className="subtitle-time">{fmt(start)} → {fmt(end)}</span>
        <button onClick={onCancel}>取消</button>
        <button className="primary" onClick={() => onSave(text, style)}>保存</button>
      </div>
      <textarea
        className="subtitle-text"
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder="字幕文字…"
        autoFocus
        rows={3}
      />
      <div className="subtitle-preview" style={{
        fontSize: `${(style.font_size ?? 38) / 2}px`,
        color: style.color ?? "white",
        fontWeight: style.bold ? "bold" : "normal",
        textAlign: style.align ?? "center",
        WebkitTextStroke: `${(style.outline_width ?? 2) / 2}px ${style.outline_color ?? "black"}`,
      }}>
        {text || "预览"}
      </div>
      <div className="subtitle-section">
        <label>预设样式：</label>
        {styles.map((p) => (
          <button key={p.id} className="preset-btn"
            onClick={() => applyPreset(p.id)}
            style={{
              fontSize: 11, padding: "4px 10px",
              background: style === (style as any) ? "#3a3a3a" : "transparent",
            }}>
            {p.name}
          </button>
        ))}
      </div>
      <div className="subtitle-section">
        <label>字体：</label>
        <select value={style.font_id ?? "msyh"}
          onChange={(e) => setStyle({ ...style, font_id: e.target.value })}>
          {fonts.map((f) => (
            <option key={f.id} value={f.id}>{f.name}</option>
          ))}
        </select>
        <label>字号：</label>
        <input type="number" min={16} max={120} value={style.font_size ?? 38}
          onChange={(e) => setStyle({ ...style, font_size: Number(e.target.value) })} />
        <label>颜色：</label>
        <input type="color" value={style.color ?? "#ffffff"}
          onChange={(e) => setStyle({ ...style, color: e.target.value })} />
        <label>粗体：</label>
        <input type="checkbox" checked={style.bold ?? false}
          onChange={(e) => setStyle({ ...style, bold: e.target.checked })} />
      </div>
      <div className="subtitle-section">
        <label>位置：</label>
        {(["top", "middle", "bottom"] as const).map((p) => (
          <button key={p} className={`pos-btn ${style.position === p ? "active" : ""}`}
            onClick={() => setStyle({ ...style, position: p })}>
            {p === "top" ? "顶部" : p === "middle" ? "中部" : "底部"}
          </button>
        ))}
        <label>对齐：</label>
        {(["left", "center", "right"] as const).map((a) => (
          <button key={a} className={`align-btn ${style.align === a ? "active" : ""}`}
            onClick={() => setStyle({ ...style, align: a })}>
            {a === "left" ? "左" : a === "center" ? "中" : "右"}
          </button>
        ))}
      </div>
      <div className="subtitle-section">
        <label>描边色：</label>
        <input type="color" value={style.outline_color ?? "#000000"}
          onChange={(e) => setStyle({ ...style, outline_color: e.target.value })} />
        <label>描边宽：</label>
        <input type="number" min={0} max={8} value={style.outline_width ?? 2}
          onChange={(e) => setStyle({ ...style, outline_width: Number(e.target.value) })} />
      </div>
    </div>
  );
}
