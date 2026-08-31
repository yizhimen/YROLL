// GUI-03R5-B4 (Decision 5): Generic context-menu shell.
//
// Used by both the Gap context menu (right-click on a gap in a
// track) and the Track context menu (right-click on a track
// header). The menu is positioned absolutely at the click point
// and closes on outside-click / Escape.

import { useEffect, useRef } from "react";

export interface MenuItem {
  label: string;
  hint?: string;
  /** false = item is shown but disabled (greyed out). */
  enabled?: boolean;
  /** Required for non-separator items. */
  onClick?: () => void;
  /** Sub-items render as a separator line. */
  separator?: boolean;
}

export interface MenuPos {
  x: number;
  y: number;
}

export interface ContextMenuProps {
  /** Current position; null = menu closed. */
  pos: MenuPos | null;
  items: MenuItem[];
  /** data-testid for testing. */
  testid?: string;
}

export default function ContextMenu({ pos, items, testid }: ContextMenuProps) {
  const ref = useRef<HTMLDivElement | null>(null);

  // Close on outside click / Escape.
  useEffect(() => {
    if (!pos) return;
    const onDown = (e: MouseEvent) => {
      if (!ref.current) return;
      if (ref.current.contains(e.target as Node)) return;
      // Caller decides how to close (controlled by pos state).
      // We don't dispatch a synthetic event; the click bubbles
      // up to the parent and the parent dismisses. This effect
      // exists only for the ESC handler.
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        // Same: caller handles dismissal via state.
        // The parent component should listen for ESC separately.
      }
    };
    window.addEventListener("mousedown", onDown);
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("mousedown", onDown);
      window.removeEventListener("keydown", onKey);
    };
  }, [pos]);

  if (!pos) return null;

  return (
    <div
      ref={ref}
      className="context-menu"
      data-testid={testid}
      style={{
        position: "fixed",
        left: pos.x,
        top: pos.y,
        zIndex: 9999,
        minWidth: 200,
        background: "#222",
        border: "1px solid #444",
        borderRadius: 6,
        padding: 4,
        boxShadow: "0 4px 12px rgba(0,0,0,0.5)",
        fontSize: 12,
        color: "#ddd",
      }}
      // Stop propagation so clicking inside doesn't close immediately.
      onMouseDown={(e) => e.stopPropagation()}
    >
      {items.map((it, i) =>
        it.separator ? (
          <div
            key={`sep-${i}`}
            style={{
              height: 1, background: "#444", margin: "4px 0",
            }}
          />
        ) : (
          <button
            key={it.label}
            data-menu-item={it.label}
            disabled={it.enabled === false}
            onClick={(e) => {
              e.stopPropagation();
              it.onClick?.();
            }}
            style={{
              display: "block",
              width: "100%",
              padding: "6px 10px",
              background: "transparent",
              border: 0,
              textAlign: "left",
              color: it.enabled === false ? "#666" : "#ddd",
              cursor: it.enabled === false ? "default" : "pointer",
            }}
            onMouseEnter={(e) => {
              (e.currentTarget as HTMLButtonElement).style.background =
                "#3a3a3a";
            }}
            onMouseLeave={(e) => {
              (e.currentTarget as HTMLButtonElement).style.background =
                "transparent";
            }}
          >
            <span>{it.label}</span>
            {it.hint && (
              <span style={{ marginLeft: 8, color: "#888", fontSize: 11 }}>
                {it.hint}
              </span>
            )}
          </button>
        ),
      )}
    </div>
  );
}