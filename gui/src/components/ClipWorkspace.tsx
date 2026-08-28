import { useEffect, useState } from "react";
import { api, Clip, Operation, Problem, Solution } from "../api";

interface Props {
  clip: Clip;
  assetPath?: string;
  assetOrigin?: string;
  assetGen?: Record<string, unknown> | null;
  onClose: () => void;
  onChanged: () => Promise<void>;
}

const CATEGORIES: Array<[string, string]> = [
  ["temporal", "时间问题（太长/节奏/停顿）"],
  ["audio", "音频问题（音量/噪音/音质）"],
  ["text", "文字问题（错字/同步/水印）"],
  ["visual", "画面问题（暗/抖/糊/色彩）"],
  ["spatial_object", "空间对象（太大/位置/删除/替换）"],
  ["semantic", "语义问题（不贴主题/信息密度）"],
  ["consistency", "一致性（跨片段不统一）"],
];

const ROUTE_NAME: Record<string, string> = {
  L0_transform: "L0 参数调整",
  L1_local_ai: "L1 本地 AI",
  L2_cloud_ai: "L2 云端 AI",
  L3_regenerate: "L3 重新生成",
};

/**
 * Clip Workspace（Y 轴，蓝图 §3.2）：
 * Current State / Origin / Intent / Operations / Problems → Solutions。
 * 半透明黑色浮层，不破坏布局。
 */
export default function ClipWorkspace({ clip, assetPath, assetOrigin, assetGen, onClose, onChanged }: Props) {
  const [ops, setOps] = useState<Operation[]>([]);
  const [problems, setProblems] = useState<Problem[]>([]);
  const [solutions, setSolutions] = useState<Record<string, Solution[]>>({});
  const [category, setCategory] = useState("temporal");
  const [desc, setDesc] = useState("");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const [impact, setImpact] = useState<Awaited<ReturnType<typeof api.impact>> | null>(null);

  const load = async () => {
    const [allOps, ps, imp] = await Promise.all([
      api.operations(),
      api.problems(),
      api.impact(clip.clip_id),
    ]);
    setOps(allOps.filter((o) => o.target === clip.clip_id));
    setProblems(ps.problems.filter((p) => p.target_clip === clip.clip_id));
    const map: Record<string, Solution[]> = {};
    for (const s of ps.solutions) {
      (map[s.problem_id] ||= []).push(s);
    }
    setSolutions(map);
    setImpact(imp);
  };

  useEffect(() => {
    load();
  }, [clip.clip_id]);

  const report = async () => {
    if (!desc.trim() || busy) return;
    setBusy(true);
    try {
      const r = await api.reportProblem(desc.trim(), category, clip.clip_id, {
        start: clip.timeline_range.start,
        end: clip.timeline_range.end,
      });
      setDesc("");
      setNotice(`已登记问题，AI 给出 ${r.solutions.length} 个方案（默认推荐最低成本）`);
      await load();
    } finally {
      setBusy(false);
    }
  };

  const execute = async (s: Solution) => {
    if (busy) return;
    setBusy(true);
    try {
      const r = await api.executeSolution(s.solution_id);
      setNotice(
        r.status === "applied"
          ? `✓ 已执行（操作 ${r.operation_id}）`
          : `⏸ ${r.message || "该方案的能力将在后续版本接入"}`
      );
      await onChanged();
      await load();
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="workspace-overlay" onClick={onClose}>
      <div className="workspace" onClick={(e) => e.stopPropagation()}>
        <div className="ws-header">
          <span className="ws-title">Clip Workspace · {clip.clip_id}</span>
          <button onClick={onClose}>✕</button>
        </div>

        <div className="ws-body">
          <section>
            <h4>当前状态</h4>
            <div className="ws-meta">
              时间轴 {clip.timeline_range.start.toFixed(1)}–{clip.timeline_range.end.toFixed(1)}s ·
              速度 {clip.speed}x · 音量 {clip.volume}
              {clip.adjustments.length > 0 && ` · ${clip.adjustments.length} 个调整图层`}
            </div>
          </section>

          <section>
            <h4>来源（Origin）</h4>
            <div className="ws-meta">
              素材 {clip.asset_id}
              {assetPath && <><br />{assetPath}</>}
              <br />源区间 {clip.source_range.start.toFixed(1)}–{clip.source_range.end.toFixed(1)}s
            </div>
          </section>

          <section>
            <h4>意图（Intent）</h4>
            <div className="ws-meta">
              {clip.context?.why && <>为何在此：{clip.context.why}<br /></>}
              {clip.context?.scene && <>场景：{clip.context.scene} </>}
              {clip.context?.emotion && <>情绪：{clip.context.emotion} </>}
              {clip.context?.story_role && <>叙事角色：{clip.context.story_role}</>}
              {!clip.context?.why && !clip.context?.scene && !clip.context?.story_role
                && "无记录（人手放置，未标注意图）"}
            </div>
          </section>

          <section>
            <h4>生成链（Generation Chain）</h4>
            <div className="ws-meta">
              {assetOrigin === "generated" ? (
                <>
                  ✦ AI 生成素材
                  {assetGen?.prompt != null && <div>Prompt：{String(assetGen.prompt)}</div>}
                  {assetGen?.model != null && <div>模型：{String(assetGen.model)}
                    {assetGen?.seed != null && ` · seed ${String(assetGen.seed)}`}</div>}
                  {assetGen?.source_tool != null && <div>来源工具：{String(assetGen.source_tool)}</div>}
                  {ops.filter((o) => o.type === "add_clip").map((o) => (
                    <div key={o.operation_id}>生成背景：{o.why}</div>
                  ))}
                </>
              ) : "实拍/导入素材，无生成链"}
            </div>
          </section>

          <section>
            <h4>操作历史（前世今生）</h4>
            {ops.length === 0 && <div className="ws-meta">还没有修改记录</div>}
            {ops.map((o) => (
              <div key={o.operation_id} className="ws-op">
                <span className={`ws-who ${o.who}`}>{o.who === "ai" ? "AI" : "人"}</span>
                {" "}{o.type}
                {o.why && <span className="ws-why"> · {o.why}</span>}
              </div>
            ))}
          </section>

          <section>
            <h4>语义关系（Semantic Link）</h4>
            {impact && impact.will_sync.length + impact.will_prompt.length + impact.untouched.length === 0 && (
              <div className="ws-meta">暂无关系</div>
            )}
            {impact && impact.will_sync.length > 0 && (
              <div className="ws-meta">🔗 强关联（随它动）：{impact.will_sync.map((d) => d.text).join("、")}</div>
            )}
            {impact && impact.will_prompt.length > 0 && (
              <div className="ws-meta">◇ 中关联（会提示）：{impact.will_prompt.map((d) => d.text).join("、")}</div>
            )}
            {impact && impact.untouched.length > 0 && (
              <div className="ws-meta">○ 不受影响：{impact.untouched.map((d) => d.text).join("、")}</div>
            )}
            <button
              className="ws-link-btn"
              disabled={busy}
              onClick={async () => {
                setBusy(true);
                try {
                  const r = await api.inferLinks();
                  setNotice(`已自动推断关系：新增 ${r.inferred} 条，共 ${r.total} 条`);
                  await load();
                } finally {
                  setBusy(false);
                }
              }}
            >
              自动推断关系
            </button>
          </section>

          <section>
            <h4>问题 → 方案</h4>
            {problems.map((p) => (
              <div key={p.problem_id} className="ws-problem">
                <div className="ws-problem-desc">⚠ {p.description}</div>
                {(solutions[p.problem_id] || []).map((s, i) => (
                  <div key={s.solution_id} className={`ws-solution ${s.selected ? "selected" : ""}`}>
                    <span className="ws-route">{ROUTE_NAME[s.route]}</span>
                    <span className="ws-sol-label">{s.tool}</span>
                    <span className="ws-cost">
                      {s.cost === 0 ? "免费" : `¥${s.cost}`} · {(s.duration_ms / 1000).toFixed(0)}s · {s.risk}
                    </span>
                    <button disabled={busy || s.selected} onClick={() => execute(s)}>
                      {s.selected ? "已执行" : i === 0 ? "执行（推荐）" : "执行"}
                    </button>
                  </div>
                ))}
              </div>
            ))}

            <div className="ws-report">
              <select value={category} onChange={(e) => setCategory(e.target.value)}>
                {CATEGORIES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
              </select>
              <input
                value={desc}
                placeholder="这里哪里不对？（如：这个壶太大挡住字幕）"
                onChange={(e) => setDesc(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && report()}
              />
              <button onClick={report} disabled={busy}>提方案</button>
            </div>
            {notice && <div className="ws-notice">{notice}</div>}
          </section>
        </div>
      </div>
    </div>
  );
}
