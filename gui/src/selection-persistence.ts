// GUI-05-B: Selection persistence (GUI-only, sessionStorage).
//
// Per L-1 / L-2 implementation lock:
//   - Exactly-once hydration per `${projectId}:${timelineId}`.
//   - Refresh() may replace the project object but MUST NOT rehydrate
//     selection from sessionStorage again for the same key.
//   - Restore only clip IDs that still exist in project.clips.
//   - Switching projects/timelines (key change) triggers fresh
//     hydration; switching back does NOT re-hydrate (already done).
//
// SessionStorage (NOT localStorage) — lives only for the browser
// session, not across user-restored tabs. This matches the GUI's
// session-scoped lifecycle.

const STORAGE_KEY = "yroll.selection.v1";

/** Shape stored in sessionStorage. We store just IDs — the head is
 *  reconstructed from the set on read (or kept as null if empty). */
interface PersistedSelection {
  selected: string | null;
  selectedSet: string[];
}

/**
 * Read the persisted selection for a given `{projectId, timelineId}`
 * from sessionStorage. Returns null if:
 *   - sessionStorage is unavailable (private mode, disabled),
 *   - the JSON is malformed,
 *   - the shape doesn't match.
 *
 * IMPORTANT: This function does NOT filter against existing clips.
 * Filtering happens at the App.tsx call site so this helper stays a
 * pure read.
 */
export function readPersistedSelection(
  projectId: string,
  timelineId: string,
): PersistedSelection | null {
  if (typeof sessionStorage === "undefined") return null;
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const all = JSON.parse(raw) as Record<string, PersistedSelection>;
    const key = `${projectId}:${timelineId}`;
    const entry = all?.[key];
    if (
      !entry ||
      typeof entry !== "object" ||
      !Array.isArray(entry.selectedSet)
    ) {
      return null;
    }
    return {
      selected: typeof entry.selected === "string" ? entry.selected : null,
      selectedSet: entry.selectedSet.filter((s): s is string => typeof s === "string"),
    };
  } catch {
    return null;
  }
}

/**
 * Persist the current selection for `{projectId, timelineId}`.
 * No-op if sessionStorage is unavailable. Existing entries for other
 * projects/timelines are preserved.
 */
export function persistSelection(
  projectId: string,
  timelineId: string,
  selected: string | null,
  selectedSet: Set<string>,
): void {
  if (typeof sessionStorage === "undefined") return;
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    const all: Record<string, PersistedSelection> = raw
      ? (JSON.parse(raw) as Record<string, PersistedSelection>)
      : {};
    const key = `${projectId}:${timelineId}`;
    if (selectedSet.size === 0 && selected == null) {
      // Clear the entry if nothing to persist.
      delete all[key];
    } else {
      all[key] = {
        selected: selectedSet.has(selected ?? "") ? selected : null,
        selectedSet: Array.from(selectedSet),
      };
    }
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(all));
  } catch {
    // Private mode / quota exceeded — silently fail (GUI state is
    // still in memory; persistence is best-effort).
  }
}

/**
 * Clear the persisted selection for `{projectId, timelineId}`.
 * Used on Escape and clear-selection UX so we don't restore stale
 * state on next page load.
 */
export function clearPersistedSelection(
  projectId: string,
  timelineId: string,
): void {
  if (typeof sessionStorage === "undefined") return;
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    if (!raw) return;
    const all = JSON.parse(raw) as Record<string, PersistedSelection>;
    const key = `${projectId}:${timelineId}`;
    delete all[key];
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(all));
  } catch {
    // ignore
  }
}

/**
 * Filter a persisted selection's IDs against the current project's
 * clip IDs. Missing IDs are silently dropped. The `selected` head is
 * dropped if it's not in the surviving set.
 */
export function filterPersistedSelection(
  persisted: PersistedSelection,
  existingClipIds: Iterable<string>,
): { selected: string | null; selectedSet: Set<string> } {
  const existing = new Set(existingClipIds);
  const filteredSet = new Set<string>();
  for (const id of persisted.selectedSet) {
    if (existing.has(id)) filteredSet.add(id);
  }
  const filteredSelected =
    persisted.selected != null && filteredSet.has(persisted.selected)
      ? persisted.selected
      : filteredSet.values().next().value ?? null;
  return { selected: filteredSelected, selectedSet: filteredSet };
}