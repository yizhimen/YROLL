import { useEffect, useRef, useState } from "react";
import { api, Solution } from "../api";

interface Msg {
  who: "user" | "ai";
  text: string;
  solutions?: Solution[];  // AI 登记的方案卡片（可直接执行）
  approval?: { op: string; clip_id?: string };  // 待审批动作
  plan?: Array<Record<string, unknown>>;  // 待确认的计划动作（Plan→Preview→Apply）
  resolved?: "approved" | "rejected" | "applied" | "discarded";
}

interface Props {
  selectedClip: string | null;
  playheadFrame: number;
  onChanged: () => Promise<void>;
  onStatus: (ok: boolean, text: string) => void;
}

/** AI 对话面板：意图 → LLM → Command Layer → Timeline 可见修改。 */
export default function ChatPanel({ selectedClip, playheadFrame, onChanged, onStatus }: Props) {
  const [msgs, setMsgs] = useState<Msg[]>([
    { who: "ai", text: "我是你的 AI 剪辑师。直接说想怎么改，比如：把选中的片段加快到 2 倍 / 把音量调到一半 / 在播放头处切开。" },
  ]);

  // 统一会话历史（蓝图 §3.4）：挂载时从工程目录恢复
  useEffect(() => {
    fetch("/chat/history")
      .then((r) => r.ok ? r.json() : null)
      .then((d) => {
        if (d?.messages?.length) {
          setMsgs((m) => [...m, ...d.messages.map((x: { who: string; text: string }) => ({
            who: x.who === "user" ? "user" as const : "ai" as const,
            text: x.text,
          }))]);
        }
      })
      .catch(() => undefined);
  }, []);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [planMode, setPlanMode] = useState(false);  // 先出计划再执行（Plan→Preview→Apply）
  const wsRef = useRef<WebSocket | null>(null);

  const send = async () => {
    const text = input.trim();
    if (!text || busy) return;
    setInput("");
    setMsgs((m) => [...m, { who: "user", text }]);
    setBusy(true);

    // 优先 WebSocket 流式（实时看 AI 工作过程）；失败回退 HTTP
    try {
      await sendViaWs(text);
    } catch {
      await sendViaHttp(text);
    } finally {
      setBusy(false);
    }
  };

  const sendViaWs = (text: string) =>
    new Promise<void>((resolve, reject) => {
      const proto = location.protocol === "https:" ? "wss" : "ws";
      const ws = new WebSocket(`${proto}://${location.host}/ws/chat`);
      wsRef.current = ws;
      let settled = false;
      ws.onopen = () =>
        ws.send(JSON.stringify({ message: text, selected_clip: selectedClip, playheadFrame, plan: planMode }));
      ws.onmessage = async (ev) => {
        const e = JSON.parse(ev.data);
        if (e.type === "turn_started") {
          setMsgs((m) => [...m, { who: "ai", text: `▸ 第 ${e.turn} 轮思考…` }]);
        } else if (e.type === "action_applied") {
          setMsgs((m) => [...m, { who: "ai", text: `▸ 已执行 ${e.op}（${e.id}）` }]);
          await onChanged();
        } else if (e.type === "action_failed") {
          setMsgs((m) => [...m, { who: "ai", text: `▸ ${e.op} 失败：${e.error}` }]);
        } else if (e.type === "plan_proposed") {
          // Plan→Preview→Apply：AI 的计划先给人看，确认后才执行
          if (e.actions?.length) {
            setMsgs((m) => [...m, { who: "ai", text: `📋 计划（${e.actions.length} 步）：${e.reply || ""}`, plan: e.actions }]);
          } else {
            setMsgs((m) => [...m, { who: "ai", text: e.reply || "（无需操作）" }]);
          }
        } else if (e.type === "approval_request") {
          // 高风险操作：弹审批（批准/拒绝回传服务端）
          setMsgs((m) => [...m, { who: "ai", text: `⚠ AI 请求执行高风险操作：${e.action.op}（${e.action.clip_id || ""}）`, approval: e.action }]);
        } else if (e.type === "done") {
          const r = e.result;
          const sols = r.problems_reported?.flatMap((p: { solutions: Solution[] }) => p.solutions) ?? [];
          setMsgs((m) => [...m, {
            who: "ai",
            text: r.reply || "（完成）",
            solutions: sols.length ? sols : undefined,
          }]);
          await onChanged();
          onStatus(true, r.applied?.length ? "AI 已修改工程" : "AI 未做修改");
          ws.close();
          wsRef.current = null;
          if (!settled) { settled = true; resolve(); }
        }
      };
      ws.onerror = () => { if (!settled) { settled = true; reject(new Error("ws error")); } };
    });

  const sendViaHttp = async (text: string) => {
    try {
      const r = await api.chat(text, selectedClip, playheadFrame);
      const note =
        r.applied.length > 0
          ? `（已执行 ${r.applied.length} 个操作）`
          : r.errors.length > 0
            ? `（${r.errors.length} 个操作失败）`
            : "";
      const sols = r.problems_reported?.flatMap((p) => p.solutions) ?? [];
      setMsgs((m) => [...m, { who: "ai", text: r.reply + note, solutions: sols.length ? sols : undefined }]);
      if (r.applied.length > 0) await onChanged();
      onStatus(true, r.applied.length > 0 ? "AI 已修改工程" : "AI 未做修改");
    } catch (e) {
      setMsgs((m) => [...m, { who: "ai", text: `出错了：${e}` }]);
      onStatus(false, String(e));
    }
  };

  const executeSolution = async (s: Solution) => {
    if (busy) return;
    setBusy(true);
    try {
      const r = await api.executeSolution(s.solution_id);
      setMsgs((m) => [...m, {
        who: "ai",
        text: r.status === "applied"
          ? `✓ 已执行「${s.tool}」（操作 ${r.operation_id}）`
          : `⏸ ${r.message || "该方案能力将在后续版本接入"}`,
      }]);
      await onChanged();
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="chat-panel">
      <div className="chat-log">
        {msgs.map((m, i) => (
          <div key={i} className={`chat-msg ${m.who}`}>
            {m.text}
            {m.approval && !m.resolved && (
              <div style={{ display: "flex", gap: 6, marginTop: 6 }}>
                <button
                  style={{ background: "#7ec97e", color: "#141414", border: "none", borderRadius: 4, padding: "3px 12px", cursor: "pointer" }}
                  onClick={() => {
                    wsRef.current?.send(JSON.stringify({ type: "approval_response", approved: true }));
                    setMsgs((prev) => prev.map((x, j) => j === i ? { ...x, resolved: "approved" } : x));
                  }}
                >
                  批准
                </button>
                <button
                  style={{ background: "#a33", color: "#fff", border: "none", borderRadius: 4, padding: "3px 12px", cursor: "pointer" }}
                  onClick={() => {
                    wsRef.current?.send(JSON.stringify({ type: "approval_response", approved: false }));
                    setMsgs((prev) => prev.map((x, j) => j === i ? { ...x, resolved: "rejected" } : x));
                  }}
                >
                  拒绝
                </button>
              </div>
            )}
            {m.resolved && (m.resolved === "approved" || m.resolved === "rejected") && (
              <div style={{ marginTop: 4, fontSize: 11, color: "#888" }}>
                {m.resolved === "approved" ? "已批准" : "已拒绝"}
              </div>
            )}
            {m.plan && !m.resolved && (
              <div style={{ marginTop: 6 }}>
                {m.plan.map((a, k) => (
                  <div key={k} style={{ fontSize: 12, color: "#9c9", padding: "2px 0" }}>
                    {k + 1}. {String(a.op)}（{String(a.clip_id ?? "")}）
                  </div>
                ))}
                <div style={{ display: "flex", gap: 6, marginTop: 6 }}>
                  <button
                    style={{ background: "#7ec97e", color: "#141414", border: "none", borderRadius: 4, padding: "3px 12px", cursor: "pointer" }}
                    onClick={() => {
                      wsRef.current?.send(JSON.stringify({ type: "plan_response", apply: true }));
                      setMsgs((prev) => prev.map((x, j) => j === i ? { ...x, resolved: "applied" } : x));
                    }}
                  >
                    应用全部
                  </button>
                  <button
                    style={{ background: "#555", color: "#fff", border: "none", borderRadius: 4, padding: "3px 12px", cursor: "pointer" }}
                    onClick={() => {
                      wsRef.current?.send(JSON.stringify({ type: "plan_response", apply: false }));
                      setMsgs((prev) => prev.map((x, j) => j === i ? { ...x, resolved: "discarded" } : x));
                    }}
                  >
                    放弃
                  </button>
                </div>
              </div>
            )}
            {m.plan && m.resolved && (
              <div style={{ marginTop: 4, fontSize: 11, color: "#888" }}>
                {m.resolved === "applied" ? "已应用" : "已放弃"}
              </div>
            )}
            {m.solutions?.map((s, j) => (
              <div key={j} className="ws-solution" style={{ marginTop: 4 }}>
                <span className="ws-route">{s.route.replace("_", " ")}</span>
                <span className="ws-sol-label">{s.tool}</span>
                <span className="ws-cost">{s.cost === 0 ? "免费" : `¥${s.cost}`}</span>
                <button disabled={busy} onClick={() => executeSolution(s)}>执行</button>
              </div>
            ))}
          </div>
        ))}
        {busy && <div className="chat-msg ai">思考中…</div>}
      </div>
      <div className="chat-input">
        <label style={{ display: "flex", alignItems: "center", gap: 3, fontSize: 11, color: planMode ? "#7ec97e" : "#888", cursor: "pointer", whiteSpace: "nowrap" }}
               title="开启后：AI 先出动作计划，你确认后才执行（Plan→Preview→Apply）">
          <input type="checkbox" checked={planMode}
                 onChange={(e) => setPlanMode(e.target.checked)} />
          计划
        </label>
        <input
          value={input}
          placeholder="对 AI 说：这里哪里不对、想怎么改…"
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && send()}
          disabled={busy}
        />
        <button onClick={send} disabled={busy}>发送</button>
      </div>
    </div>
  );
}
