// EditLease - 显示当前编辑权归属（v0.2 P0-10）
import { useEffect, useState, useRef } from "react";
import { api } from "../api";

interface LeaseState {
  heldBy: string | null;
  sessionId: string | null;
  mode: string | null;
  baseRevision: number;
  isAlive: boolean;
  humanLabel: string;
}

const STORAGE_KEY = "yroll.sessionId";

export default function EditLease() {
  const [lease, setLease] = useState<LeaseState | null>(null);
  const [localSessionId] = useState(() => {
    let s = localStorage.getItem(STORAGE_KEY);
    if (!s) {
      s = crypto.randomUUID();
      localStorage.setItem(STORAGE_KEY, s);
    }
    return s;
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>("");
  const pollRef = useRef<number | null>(null);

  const refresh = async () => {
    try {
      const data = await api.getLease();
      setLease(data);
    } catch (e: any) {
      console.warn("getLease failed", e);
    }
  };

  useEffect(() => {
    refresh();
    pollRef.current = window.setInterval(() => {
      api.getLease().then(setLease).catch(() => {});
      if (lease?.sessionId && lease.sessionId === localSessionId) {
        api.releaseLease(lease.sessionId).catch(() => {});
      }
      if (!lease || !lease.sessionId || lease.sessionId !== localSessionId) {
        api.acquireLease("human", "edit", undefined, "User")
          .then(() => api.getLease().then(setLease))
          .catch(() => {});
      }
    }, 5000);
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, [lease?.sessionId, localSessionId]);

  const onHandoff = async () => {
    if (!lease?.sessionId) return;
    setBusy(true); setError("");
    try {
      await api.handoffLease(lease.sessionId, "agent", "edit", "Claude");
      await refresh();
    } catch (e: any) { setError(e.message || "handoff failed"); }
    finally { setBusy(false); }
  };

  const onRelease = async () => {
    if (!lease?.sessionId) return;
    setBusy(true); setError("");
    try {
      await api.releaseLease(lease.sessionId);
      await refresh();
    } catch (e: any) { setError(e.message || "release failed"); }
    finally { setBusy(false); }
  };

  const onTakeBack = async () => {
    setBusy(true); setError("");
    try {
      await api.acquireLease("human", "edit", undefined, "User");
      await refresh();
    } catch (e: any) { setError(e.message || "acquire failed"); }
    finally { setBusy(false); }
  };

  const mine = lease?.sessionId === localSessionId;
  const other = lease?.isAlive && !mine;

  return (
    <div className="edit-lease" style={{
      display: "flex", alignItems: "center", gap: 8, padding: "2px 8px",
      background: "#1a1a1a", borderRadius: 4, fontSize: 12,
      border: mine ? "1px solid #7ec97e" : (other ? "1px solid #ffd479" : "1px solid #555"),
    }}>
      <span style={{
        width: 8, height: 8, borderRadius: "50%",
        background: mine ? "#7ec97e" : (other ? "#ffd479" : "#888"),
        boxShadow: mine ? "0 0 6px #7ec97e" : (other ? "0 0 6px #ffd479" : "none"),
      }} />
      <span style={{ color: "#ddd" }}>
        {other
          ? `编辑权：${lease?.humanLabel || lease?.heldBy}（${lease?.mode === "edit" ? "可改" : "只读"}）`
          : mine
          ? "编辑权：我（可改）"
          : "无编辑权"}
      </span>
      {other && (
        <button className="lease-btn primary" onClick={onTakeBack} disabled={busy}
          style={{ fontSize: 11, padding: "2px 8px" }}>
          收回
        </button>
      )}
      {mine && (
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
      {error && <span style={{ color: "#f88", fontSize: 11 }}>{error}</span>}
    </div>
  );
}
