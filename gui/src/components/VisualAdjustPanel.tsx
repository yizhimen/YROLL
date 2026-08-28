// 画面/位置调整面板（剪映式分区）：全部走非破坏性调整图层，可重置、可单删、可撤销。
// 手动剪辑底座：AI 故障时人能用同一套控制完成全部画面操作。

import { api, Clip } from "../api";

interface Props {
  clip: Clip;
  run: (fn: () => Promise<unknown>, ok: string) => Promise<void>;
}

function Slider({ label, min, max, step, value, defaultValue, fmt, onCommit }: {
  label: string; min: number; max: number; step: number;
  value: number; defaultValue: number; fmt?: (v: number) => string;
  onCommit: (v: number) => void;
}) {
  return (
    <div className="row">
      <label>{label}</label>
      <input
        type="range" min={min} max={max} step={step}
        defaultValue={value ?? defaultValue}
        onMouseUp={(e) => onCommit(Number((e.target as HTMLInputElement).value))}
        onTouchEnd={(e) => onCommit(Number((e.target as HTMLInputElement).value))}
      />
      <span>{fmt ? fmt(value ?? defaultValue) : (value ?? defaultValue)}</span>
    </div>
  );
}

function adj(clip: Clip, kind: string): Record<string, number | boolean> {
  const a = [...clip.adjustments].reverse().find((x) => x.kind === kind);
  return (a?.params ?? {}) as Record<string, number | boolean>;
}

export default function VisualAdjustPanel({ clip, run }: Props) {
  const color = adj(clip, "color");
  const t2d = adj(clip, "transform2d");
  const cropP = adj(clip, "crop");
  const flipP = adj(clip, "flip");
  const opacityP = adj(clip, "opacity");
  const hasReverse = clip.adjustments.some((a) => a.kind === "reverse");
  const nVisual = clip.adjustments.filter((a) =>
    ["color", "flip", "opacity", "crop", "transform2d"].includes(String(a.kind))).length;

  const setColor = (k: string, v: number) =>
    run(() => api.setColor(clip.clip_id, { ...color, [k]: v } as Record<string, number>, "GUI 画面调整"), "已调整（重渲染后生效）");
  const setT2d = (k: string, v: number | boolean) =>
    run(() => api.setTransform2d(clip.clip_id, { ...t2d, [k]: v }, "GUI 2D 变换"), "已变换（重渲染后生效）");
  const setCropK = (k: string, v: number) =>
    run(() => {
      const p = { left: 0, top: 0, right: 0, bottom: 0, ...cropP, [k]: v };
      return api.setCrop(clip.clip_id, p.left, p.top, p.right, p.bottom, "GUI 画面裁剪");
    }, "已裁剪画面（重渲染后生效）");

  return (
    <div className="visual-adjust">
      <div className="va-section">
        <div className="va-title">画面</div>
        <Slider label="亮度" min={-0.5} max={0.5} step={0.02}
                value={Number(color.brightness ?? 0)} defaultValue={0}
                fmt={(v) => v.toFixed(2)} onCommit={(v) => setColor("brightness", v)} />
        <Slider label="对比度" min={0.5} max={2} step={0.05}
                value={Number(color.contrast ?? 1)} defaultValue={1}
                fmt={(v) => v.toFixed(2)} onCommit={(v) => setColor("contrast", v)} />
        <Slider label="饱和度" min={0} max={3} step={0.05}
                value={Number(color.saturation ?? 1)} defaultValue={1}
                fmt={(v) => v.toFixed(2)} onCommit={(v) => setColor("saturation", v)} />
        <Slider label="色温" min={2500} max={9000} step={100}
                value={Number(color.temperature ?? 6500)} defaultValue={6500}
                fmt={(v) => `${v}K`} onCommit={(v) => setColor("temperature", v)} />
        <Slider label="锐化" min={0} max={3} step={0.1}
                value={Number(color.sharpen ?? 0)} defaultValue={0}
                fmt={(v) => v.toFixed(1)} onCommit={(v) => setColor("sharpen", v)} />
        <Slider label="不透明" min={0.1} max={1} step={0.02}
                value={Number(opacityP.value ?? 1)} defaultValue={1}
                fmt={(v) => `${Math.round(v * 100)}%`}
                onCommit={(v) => run(() => api.setOpacity(clip.clip_id, v, "GUI 不透明度"), "已调整（重渲染后生效）")} />
        <div className="row">
          <label>镜像</label>
          <button
            style={flipP.h ? { background: "#3a5a8c", color: "#fff" } : undefined}
            onClick={() => run(() => api.setFlip(clip.clip_id, !flipP.h, !!flipP.v, "GUI 镜像"), "已镜像（重渲染后生效）")}>
            水平
          </button>
          <button
            style={flipP.v ? { background: "#3a5a8c", color: "#fff" } : undefined}
            onClick={() => run(() => api.setFlip(clip.clip_id, !!flipP.h, !flipP.v, "GUI 镜像"), "已镜像（重渲染后生效）")}>
            垂直
          </button>
          <button
            style={hasReverse ? { background: "#3a5a8c", color: "#fff" } : undefined}
            disabled={hasReverse}
            title="倒放（重编码，60s 内 clip）"
            onClick={() => run(() => api.setReverse(clip.clip_id, "GUI 倒放"), "已倒放（重渲染后生效）")}>
            {hasReverse ? "已倒放" : "倒放"}
          </button>
        </div>
      </div>

      <div className="va-section">
        <div className="va-title">位置 / 缩放 / 旋转</div>
        <Slider label="缩放" min={0.2} max={2} step={0.02}
                value={Number(t2d.scale ?? 1)} defaultValue={1}
                fmt={(v) => `${Math.round(v * 100)}%`} onCommit={(v) => setT2d("scale", v)} />
        <Slider label="水平" min={-1} max={1} step={0.02}
                value={Number(t2d.x ?? 0)} defaultValue={0}
                fmt={(v) => v.toFixed(2)} onCommit={(v) => setT2d("x", v)} />
        <Slider label="垂直" min={-1} max={1} step={0.02}
                value={Number(t2d.y ?? 0)} defaultValue={0}
                fmt={(v) => v.toFixed(2)} onCommit={(v) => setT2d("y", v)} />
        <Slider label="旋转" min={-180} max={180} step={1}
                value={Number(t2d.rotation ?? 0)} defaultValue={0}
                fmt={(v) => `${v}°`} onCommit={(v) => setT2d("rotation", v)} />
        <div className="row">
          <label>背景</label>
          <button
            style={t2d.bg_blur !== false ? { background: "#3a5a8c", color: "#fff" } : undefined}
            title="缩小时用模糊画面填充背景（剪映同款）"
            onClick={() => setT2d("bg_blur", !(t2d.bg_blur !== false))}>
            {t2d.bg_blur !== false ? "模糊填充" : "黑底"}
          </button>
        </div>
      </div>

      <div className="va-section">
        <div className="va-title">画面裁剪（四边各裁比例）</div>
        {(["left", "top", "right", "bottom"] as const).map((k) => (
          <Slider key={k}
                  label={{ left: "左", top: "上", right: "右", bottom: "下" }[k]}
                  min={0} max={0.45} step={0.01}
                  value={Number(cropP[k] ?? 0)} defaultValue={0}
                  fmt={(v) => `${Math.round(v * 100)}%`}
                  onCommit={(v) => setCropK(k, v)} />
        ))}
      </div>

      {nVisual > 0 && (
        <button
          className="va-reset"
          onClick={() => run(() => api.resetVisual(clip.clip_id, "GUI 重置画面调整"), "已重置画面/位置调整")}
        >
          重置画面/位置（{nVisual} 项）
        </button>
      )}
    </div>
  );
}
