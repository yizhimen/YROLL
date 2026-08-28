// 操作历史面板：Operation Log 可视化 + 一键撤销（工程黑匣子给人看）。

import { useEffect, useState } from "react";
import { api, Operation } from "../api";

interface Props {
  onChanged: () => Promise<void>;
  onStatus: (ok: boolean, text: string) => void;
  refreshKey: number;  // 工程变化时递增，触发重载
}

const WHO_LABEL: Record<string, string> = { human: "人", ai: "AI" };

export default function OpsPanel({ onChanged, onStatus, refreshKey }: Props) {
  const [ops, setOps] = useState<Operation[]>([]);
  const [versions, setVersions] = useState<Awaited<ReturnType<typeof api.versions>>>([]);
  const [costs, setCosts] = useState<Awaited<ReturnType<typeof api.costs>> | null>(null);

  useEffect(() => {
    api.operations().then(setOps).catch(() => setOps([]));
    api.versions().then(setVersions).catch(() => setVersions([]));
    api.costs().then(setCosts).catch(() => setCosts(null));
  }, [refreshKey]);

  const revert = async (op: Operation) => {
    try {
      await api.revert(op.operation_id, "GUI 撤销");
      await onChanged();
      onStatus(true, `已撤销 ${op.type}（${op.operation_id}）`);
    } catch (e) {
      onStatus(false, `撤销失败：${e}`);
    }
  };

  return (
    <div className="ops-list">
      {costs && costs.total > 0 && (
        <div className="version-list">
          <div className="version-title">成本 ¥{costs.total.toFixed(2)}</div>
          {Object.entries(costs.by_tool)
            .filter(([, e]) => e.cost > 0)
            .map(([tool, e]) => (
              <div key={tool} className="version-item">
                <span className="version-note">{tool}</span>
                <span className="version-meta">×{e.count} · ¥{e.cost.toFixed(2)}</span>
              </div>
            ))}
        </div>
      )}
      {versions.length > 0 && (
        <div className="version-list">
          <div className="version-title">版本（{versions.length}）</div>
          {[...versions].reverse().map((v) => (
            <div key={v.version_id} className="version-item">
              <b>{v.version_id}</b>
              <span className="version-note">{v.note || "（无备注）"}</span>
              <span className="version-meta">
                {v.operation_ids.length} ops · {v.created_at.slice(0, 16).replace("T", " ")}
              </span>
            </div>
          ))}
        </div>
      )}
      {ops.length === 0 && <div className="asset-empty">还没有操作记录</div>}
      {[...ops].reverse().map((op) => (
        <div key={op.operation_id} className="ops-item">
          <span className={`ops-who ${op.who}`}>{WHO_LABEL[op.who] || op.who}</span>
          <span className="ops-desc" title={op.operation_id}>
            <b>{op.type}</b> · {op.target}
            {op.why && <><br /><small>{op.why}</small></>}
          </span>
          {!op.type.startsWith("revert:") && op.type !== "report_problem" && (
            <button className="ops-revert" onClick={() => revert(op)}>撤销</button>
          )}
        </div>
      ))}
    </div>
  );
}
