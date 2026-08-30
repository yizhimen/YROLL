// EditLease — 编辑权 / Revision / Gate 状态条（v0.2 P0-10 + GUI-01）
//
// GUI-03R: Lease is PROJECT-level, not Timeline-level. The compact
// badge `🟢 我 · r<N>` lives in the main Project header. Clicking
// the badge reveals the recovery controls (acquire/release/handoff/
// refresh + the raw server gate detail) so the header stays tidy
// but the controls remain one click away.
//
// GUI-01: this component owns no session state. sessionId, polling
// and localStorage all live in session.ts; here we only render
// what the store says and offer the recovery actions.
import { useState } from "react";
import { sessionStore, useProjectSession } from "../session";

export default function EditLease() {
  const s = useProjectSession();
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const act = (fn: () => Promise<unknown>) => async () => {
    setBusy(true);
    setError("");
    try {
      await fn();
    } catch (e: any) {
      setError(e?.message || "操作失败");
    } finally {
      setBusy(false);
    }
  };

  const onHandoff = act(() => sessionStore.handoffToAgent("Claude"));
  const onRelease = act(() => sessionStore.release());
  const onAcquire = act(() => sessionStore.acquire("User"));
  const onRefresh = act(() => sessionStore.refresh());

  // Gate rejections are the loudest thing on the bar: a write was refused,
  // and the user needs to know which recovery applies.
  const gate = s.gateError;
  const conflict = s.conflict || gate === "revision_conflict";
  const needsLease = gate === "no_session" || gate === "lease_rejected";

  const color = conflict
    ? "#ff6b6b"
    : needsLease
      ? "#ffd479"
      : s.mine
        ? "#7ec97e"
        : s.owner === "agent"
          ? "#ffd479"
          : "#888";

  // Compact form: emoji + actor short + revision. Full detail in the
  // popover. The badge is one click; long-form is opt-in.
  const badgeText = !s.loaded
    ? "⏳ 连接中"
    : conflict
      ? `🔴 冲突 · r${s.revision}`
      : needsLease
        ? `🟡 无权 · r${s.revision}`
        : s.mine
          ? `🟢 我 · r${s.revision}`
          : s.owner === "agent"
            ? `🟡 ${s.agentLabel || "Claude"} · r${s.revision}`
            : s.owner === "observe"
              ? `⚪ 只读 · r${s.revision}`
              : `⭕ 空闲 · r${s.revision}`;

  return (
    <span
      className="edit-lease"
      style={{
        position: "relative",
        display: "inline-flex",
        alignItems: "center",
        gap: 6,
        padding: "2px 8px",
        background: "#1a1a1a",
        borderRadius: 4,
        fontSize: 12,
        border: `1px solid ${color}`,
        cursor: "pointer",
        userSelect: "none",
      }}
      onClick={() => setOpen((o) => !o)}
      title={gate ? s.gateMessage : "点击展开编辑权操作"}
      data-testid="edit-lease-badge"
    >
      <span
        style={{
          width: 8, height: 8, borderRadius: "50%",
          background: color, boxShadow: `0 0 6px ${color}`,
        }}
      />
      <span style={{ color: "#ddd", fontVariantNumeric: "tabular-nums" }}>
        {badgeText}
      </span>

      {open && (
        <span
          onClick={(e) => e.stopPropagation()}
          style={{
            position: "absolute",
            top: "calc(100% + 4px)",
            right: 0,
            zIndex: 50,
            display: "flex",
            flexDirection: "column",
            gap: 6,
            padding: 10,
            background: "#222",
            border: "1px solid #444",
            borderRadius: 6,
            boxShadow: "0 4px 12px rgba(0,0,0,0.5)",
            minWidth: 260,
            fontSize: 12,
          }}
          data-testid="edit-lease-popover"
        >
          <span style={{ color: "#888" }}>
            Project-level Lease（与版本/轨道无关）
          </span>

          {conflict && (
            <button className="lease-btn primary" onClick={onRefresh}
              disabled={busy}
              style={{ fontSize: 11, padding: "4px 10px" }}>
              刷新
            </button>
          )}

          {!conflict && !s.mine && (
            <button className="lease-btn primary" onClick={onAcquire}
              disabled={busy}
              style={{ fontSize: 11, padding: "4px 10px" }}>
              {s.owner === "agent" ? "收回" : "获取编辑权"}
            </button>
          )}

          {!conflict && s.mine && (
            <>
              <button className="lease-btn" onClick={onHandoff} disabled={busy}
                style={{ fontSize: 11, padding: "4px 10px" }}>
                交给 Claude
              </button>
              <button className="lease-btn" onClick={onRelease} disabled={busy}
                style={{ fontSize: 11, padding: "4px 10px" }}>
                释放
              </button>
            </>
          )}

          {/* The raw server detail, so a refused write is never silent. */}
          {gate && (
            <span style={{ color: "#f88", fontSize: 11,
                           maxWidth: 320, overflowWrap: "anywhere" }}
                  title={s.gateMessage}>
              {s.gateMessage}
            </span>
          )}
          {error && (
            <span style={{ color: "#f88", fontSize: 11 }}>{error}</span>
          )}
        </span>
      )}
    </span>
  );
}