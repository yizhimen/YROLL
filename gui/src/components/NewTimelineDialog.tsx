// GUI-03E-4: NewTimelineDialog — "复制为新版本" workflow.
//
// Modal for creating a new peer Timeline. Two modes:
//   - "empty":    brand-new Timeline, no derived_from.
//   - "duplicate": copy the source Timeline (default = current
//                  active Timeline) into a new Timeline with fresh
//                  ids. The new duplicate becomes the active
//                  Timeline (server-authoritative) so the user can
//                  immediately edit the new version. Assets are
//                  SHARED — media files are never copied (Core
//                  guarantees this; the GUI does not need to warn
//                  about disk usage).
//
// The dialog is fully controlled by the parent:
//   isOpen / onClose:                open state
//   currentTimelineName:             used to pre-fill the default
//                                    name when duplicating
//   onSubmit(name, mode):            the parent performs the actual
//                                    API call (addTimeline or
//                                    duplicateTimeline). The dialog
//                                    never invokes the API directly
//                                    so the Mutation Gate + Project
//                                    Revision stay in one place.

import { useEffect, useRef, useState } from "react";

export type NewTimelineMode = "empty" | "duplicate";

export interface NewTimelineDialogProps {
  isOpen: boolean;
  /** Name of the source Timeline for the "duplicate" mode. The
   *  default source for duplication is the current active Timeline;
   *  pass `currentTimelineName` (the active one) so the dialog can
   *  show "复制自 <name>" and pre-fill the new name. */
  currentTimelineName: string;
  /** Name to pre-fill when duplicating. */
  defaultDuplicateName: string;
  onClose: () => void;
  onSubmit: (name: string, mode: NewTimelineMode) => void;
}

export default function NewTimelineDialog({
  isOpen,
  currentTimelineName,
  defaultDuplicateName,
  onClose,
  onSubmit,
}: NewTimelineDialogProps) {
  const [mode, setMode] = useState<NewTimelineMode>("empty");
  const [name, setName] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  // Reset state every time the dialog opens.
  useEffect(() => {
    if (isOpen) {
      setMode("empty");
      setName("");
      // focus the input on next tick after mount
      setTimeout(() => inputRef.current?.focus(), 0);
    }
  }, [isOpen]);

  // Esc cancels, Enter submits.
  useEffect(() => {
    if (!isOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        onClose();
      } else if (e.key === "Enter" && name.trim()) {
        e.preventDefault();
        onSubmit(name.trim(), mode);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [isOpen, name, mode, onClose, onSubmit]);

  if (!isOpen) return null;

  const trimmed = name.trim();
  const canSubmit = trimmed.length > 0;
  // The default duplicate name is computed by the parent (so the
  // caller can name it after its semantic role, e.g. "种草版"). If
  // the parent didn't supply one, fall back to "<source> 副本".
  const fallbackDupName = currentTimelineName
    ? `${currentTimelineName} 副本`
    : "副本";

  return (
    <div
      data-testid="new-timeline-dialog"
      role="dialog"
      aria-modal="true"
      aria-label="新增时间线"
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(0,0,0,0.5)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 1000,
      }}
      onClick={(e) => {
        // backdrop click closes
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        style={{
          background: "#222",
          border: "1px solid #444",
          borderRadius: 8,
          padding: 20,
          minWidth: 360,
          maxWidth: 480,
          color: "#eee",
          fontSize: 13,
        }}
      >
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            marginBottom: 12,
          }}
        >
          <h3 style={{ margin: 0, fontSize: 15 }}>新增时间线</h3>
          <button
            onClick={onClose}
            aria-label="关闭"
            style={{
              background: "transparent",
              border: "none",
              color: "#888",
              fontSize: 16,
              cursor: "pointer",
            }}
          >
            ✕
          </button>
        </div>

        <label
          style={{
            display: "block",
            marginBottom: 4,
            fontSize: 12,
            color: "#bbb",
          }}
        >
          名称
        </label>
        <input
          ref={inputRef}
          data-testid="new-timeline-dialog-name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder={
            mode === "duplicate"
              ? defaultDuplicateName || fallbackDupName
              : "如：种草版 / 收割版"
          }
          style={{
            width: "100%",
            padding: "6px 8px",
            background: "#111",
            border: "1px solid #444",
            borderRadius: 4,
            color: "#eee",
            fontSize: 13,
            boxSizing: "border-box",
          }}
        />

        <div
          style={{
            display: "flex",
            gap: 8,
            marginTop: 14,
            fontSize: 12,
            color: "#bbb",
          }}
        >
          <label
            style={{ display: "flex", alignItems: "center", gap: 4, cursor: "pointer" }}
          >
            <input
              type="radio"
              name="new-timeline-mode"
              data-testid="new-timeline-mode-empty"
              checked={mode === "empty"}
              onChange={() => setMode("empty")}
            />
            空时间线
          </label>
          <label
            style={{ display: "flex", alignItems: "center", gap: 4, cursor: "pointer" }}
          >
            <input
              type="radio"
              name="new-timeline-mode"
              data-testid="new-timeline-mode-duplicate"
              checked={mode === "duplicate"}
              onChange={() => {
                setMode("duplicate");
                if (!name.trim()) {
                  setName(defaultDuplicateName || fallbackDupName);
                }
              }}
            />
            复制为新版本
            <span style={{ color: "#888" }}>
              （Tracks/Clips/Markers/Beats 复制；素材共享不复制媒体）
            </span>
          </label>
        </div>

        <div
          style={{
            display: "flex",
            justifyContent: "flex-end",
            gap: 8,
            marginTop: 18,
          }}
        >
          <button
            onClick={onClose}
            style={{
              padding: "6px 14px",
              background: "transparent",
              border: "1px solid #555",
              borderRadius: 4,
              color: "#bbb",
              cursor: "pointer",
              fontSize: 13,
            }}
          >
            取消
          </button>
          <button
            data-testid="new-timeline-dialog-submit"
            onClick={() => canSubmit && onSubmit(trimmed, mode)}
            disabled={!canSubmit}
            style={{
              padding: "6px 14px",
              background: canSubmit ? "#7ec97e" : "#3a3a3a",
              border: "none",
              borderRadius: 4,
              color: canSubmit ? "#141414" : "#666",
              cursor: canSubmit ? "pointer" : "not-allowed",
              fontSize: 13,
              fontWeight: 600,
            }}
          >
            {mode === "duplicate" ? "复制为新版本" : "创建"}
          </button>
        </div>
      </div>
    </div>
  );
}