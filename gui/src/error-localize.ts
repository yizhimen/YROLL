// GUI-05-A (A3): user-facing mutation error localization.
//
// Rule: UI never shows technical class names (HTTPError, ValueError, etc).
//       Developer console may keep raw error for debug.
//
// This helper returns a Chinese human-readable string. It NEVER returns
// `String(e)` raw. It NEVER includes `e.message` directly. It NEVER
// includes a stack trace or class name.
//
// The matching `run()` catch branch in App.tsx emits the raw error to
// `console.warn("[YROLL-MUTATION-ERROR]", e)` for developer diagnostics
// before calling this helper.

import { GateRejection } from "./api";

/**
 * Localize a `GateRejection` (gate / lease / revision failure) to a
 * user-facing Chinese message. Previously a private function in App.tsx;
 * moved here in GUI-05-A so it can be reused by `localizeMutationError`.
 *
 * The recovery prompt is one consistent phrase regardless of which
 * specific server-side condition triggered it (no session, expired
 * lease, lost race during pointerdown). The badge in the top bar
 * flips to the appropriate recovery affordance ("获取编辑权" /
 * "刷新") based on the same GateRejection.kind.
 */
export function localizeGateRejection(e: GateRejection): string {
  switch (e.kind) {
    case "no_session":
    case "lease_rejected":
      // The lease was free / lost / expired while the gesture was
      // in flight. The badge flips to the "获取编辑权" affordance.
      return "编辑权已失效 — 点击右上角「获取编辑权」后重试";
    case "no_revision":
      // baseRevision wasn't injected (very rare — only if a mutation
      // skipped mutate()/gated()). The badge flips to "刷新".
      return "版本已过期 — 点击右上角「刷新」后重试";
    case "revision_conflict":
      // Another writer beat us between our last /ui/status poll
      // and this mutation. The badge flips to "刷新".
      return "版本冲突 — 另一位写入者已修改项目，请刷新";
    default:
      return "操作被服务器拒绝 — 刷新或重新获取编辑权";
  }
}

/**
 * Localize a Core mutation error to a user-facing Chinese message.
 *
 * Behavior map (verified against today's Core raise sites):
 *   - `e instanceof GateRejection` → delegate to `localizeGateRejection`
 *   - `_check_no_overlap` raise → "与其他片段时间重叠，请换一个位置"
 *   - `move_clip` target-track-not-found → "目标轨道不存在"
 *   - invalid `track_id` → "目标轨道无效"
 *   - HTTP 422 with frame-shape error → "帧号必须为整数" (defensive)
 *   - default fallback → "编辑未生效，请重试"
 *
 * @param e any error thrown by a mutation call
 * @returns a Chinese human-readable string suitable for the status bar
 */
export function localizeMutationError(e: unknown): string {
  // 1. GateRejection — existing localization path.
  if (e instanceof GateRejection) {
    return localizeGateRejection(e);
  }

  // Pull a message string if available. We ONLY inspect the message text
  // to choose a Chinese string — we never return the message itself.
  const raw = errorMessage(e);

  // 2. Overlap 400 (`_check_no_overlap` in `commands.py`).
  // Core raise sites use one of these Chinese fragments.
  if (raw.includes("时间重叠") || raw.includes("overlap") || raw.includes("重叠")) {
    return "与其他片段时间重叠，请换一个位置";
  }

  // 3. Target track missing (`move_clip` post-04-05 target-track pre-flight).
  if (raw.includes("目标轨道不存在") || (raw.includes("track_id") && raw.includes("不存在"))) {
    return "目标轨道不存在";
  }

  // 4. Invalid track id.
  if (raw.includes("目标轨道无效") || raw.includes("无效的轨道")) {
    return "目标轨道无效";
  }

  // 5. Frame shape error (HTTP 422 with int_from_float detail).
  if (raw.includes("int_from_float") || (raw.includes("frame") && raw.includes("integer"))) {
    return "帧号必须为整数";
  }

  // 6. Default fallback — NEVER raw detail.
  return "编辑未生效，请重试";
}

/**
 * Extract a message string from an unknown value. Returns "" if no
 * message can be extracted. This is purely for pattern matching; the
 * returned string is NEVER surfaced to the user.
 */
function errorMessage(e: unknown): string {
  if (e == null) return "";
  if (typeof e === "string") return e;
  if (typeof e === "object") {
    const m = (e as { message?: unknown }).message;
    if (typeof m === "string") return m;
    const d = (e as { detail?: unknown }).detail;
    if (typeof d === "string") return d;
  }
  return "";
}