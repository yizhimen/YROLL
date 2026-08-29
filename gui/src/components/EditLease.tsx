// EditLease — 编辑权 / Revision / Gate 状态条（v0.2 P0-10 + GUI-01）
//
// GUI-01: this component no longer owns any session state. sessionId,
// polling and localStorage all live in session.ts; here we only render
// what the store says and offer the recovery actions.
import { useState } from "react";
import { sessionStore, useProjectSession } from "../session";

export default function EditLease() {
  const s = useProjectSession();
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

  const text = !s.loaded
    ? "连接中…"
    : conflict
      ? "🔴 工程已被其他会话修改"
      : needsLease
        ? "🟡 无编辑权，写操作已被拒绝"
        : s.mine
          ? "🟢 编辑权：我"
          : s.owner === "agent"
            ? `🟡 编辑权：${s.agentLabel || "Claude"}`
            : s.owner === "observe"
              ? "⚪ 只读观察"
              : "⭕ 编辑权：空闲";

  return (
    <div
      className="edit-lease"
      style={{
        display: "flex", alignItems: "center", gap: 8, padding: "2px 8px",
        background: "#1a1a1a", borderRadius: 4, fontSize: 12,
        border: `1px solid ${color}`,
      }}
    >
      <span
        style={{
          width: 8, height: 8, borderRadius: "50%",
          background: color, boxShadow: `0 0 6px ${color}`,
        }}
      />
      <span style={{ color: "#ddd" }}>{text}</span>

      {/* Revision is first-class per §三: you should always be able to see
          which version you are editing. */}
      <span style={{ color: "#888", fontVariantNumeric: "tabular-nums" }}>
        r{s.revision}
      </span>

      {conflict && (
        <button className="lease-btn primary" onClick={onRefresh} disabled={busy}
          style={{ fontSize: 11, padding: "2px 8px" }}>
          刷新
        </button>
      )}

      {!conflict && !s.mine && (
        <button className="lease-btn primary" onClick={onAcquire} disabled={busy}
          style={{ fontSize: 11, padding: "2px 8px" }}>
          {s.owner === "agent" ? "收回" : "获取编辑权"}
        </button>
      )}

      {!conflict && s.mine && (
        <>
          <button className="lease-btn" onClick={onHandoff} disabled={busy}
            style={{ fontSize: 11, padding: "2px 8px" }}>
            交给 Claude
          </button>
          <button className="lease-btn" onClick={onRelease} disabled={busy}
            style={{ fontSize: 11, padding: "2px 8px" }}>
            释放
          </button>
        </>
      )}

      {/* The raw server detail, so a refused write is never silent. */}
      {gate && (
        <span style={{ color: "#f88", fontSize: 11, maxWidth: 320,
                       overflow: "hidden", textOverflow: "ellipsis",
                       whiteSpace: "nowrap" }}
              title={s.gateMessage}>
          {s.gateMessage}
        </span>
      )}
      {error && <span style={{ color: "#f88", fontSize: 11 }}>{error}</span>}
    </div>
  );
}
