// ResizeHandle：可拖拽分界线（剪映/Premiere 风格）。
//
// 用法：放在两个面板之间，onDelta 实时上报像素偏移。
// 受 min/max 限制，松开保存最终宽度（可选）。

import { useEffect, useRef, useState } from "react";

interface Props {
  /** "vertical" = 左右拖（改变左右两个面板宽度），"horizontal" = 上下拖 */
  direction: "vertical" | "horizontal";
  onDelta: (deltaPx: number) => void;
  onCommit?: () => void;
}

export default function ResizeHandle({ direction, onDelta, onCommit }: Props) {
  const [hover, setHover] = useState(false);
  const dragging = useRef(false);
  const lastX = useRef(0);
  const lastY = useRef(0);

  useEffect(() => {
    const onMove = (e: PointerEvent) => {
      if (!dragging.current) return;
      if (direction === "vertical") {
        onDelta(e.clientX - lastX.current);
        lastX.current = e.clientX;
      } else {
        onDelta(e.clientY - lastY.current);
        lastY.current = e.clientY;
      }
      e.preventDefault();
    };
    const onUp = () => {
      if (!dragging.current) return;
      dragging.current = false;
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
      onCommit?.();
    };
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
    return () => {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
    };
  }, [direction, onDelta, onCommit]);

  const onDown = (e: React.PointerEvent) => {
    dragging.current = true;
    lastX.current = e.clientX;
    lastY.current = e.clientY;
    document.body.style.cursor = direction === "vertical" ? "col-resize" : "row-resize";
    document.body.style.userSelect = "none";
    e.preventDefault();
  };

  return (
    <div
      className={`resize-handle ${direction} ${hover ? "hover" : ""}`}
      onPointerDown={onDown}
      onPointerEnter={() => setHover(true)}
      onPointerLeave={() => setHover(false)}
      title={direction === "vertical" ? "拖动调整左右面板宽度" : "拖动调整上下面板高度"}
    />
  );
}
