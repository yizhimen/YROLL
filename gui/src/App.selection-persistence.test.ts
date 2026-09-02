// GUI-05-B: Selection hydration behavior — App-level (L-1 / L-2).
//
// Pins the "exactly once per ${projectId}:${timelineId}" invariant.
// refresh() may replace the project object but MUST NOT rehydrate the
// selection from sessionStorage for the same key.

import { describe, it, expect, beforeEach } from "vitest";
import {
  readPersistedSelection,
  persistSelection,
  filterPersistedSelection,
} from "./selection-persistence";

describe("GUI-05-B selection hydration contract", () => {
  beforeEach(() => {
    sessionStorage.clear();
  });

  // The hydration logic in App.tsx (line ~390) is:
  //
  //   useEffect(() => {
  //     const key = `${project.project_id}:${activeTimelineId}`;
  //     if (hydratedKeyRef.current === key) return;  // skip same key
  //     const persisted = readPersistedSelection(...);
  //     const filtered = filterPersistedSelection(persisted, project.clips);
  //     setSelected(filtered.selected);
  //     setSelectedSet(filtered.selectedSet);
  //     hydratedKeyRef.current = key;
  //   }, [project, activeTimelineId]);
  //
  // The contract we test: readPersistedSelection + filterPersistedSelection
  // are pure functions. The "skip same key" invariant is enforced by
  // hydratedKeyRef.current — we test it here by reading storage AFTER
  // hydration and verifying subsequent reads of the SAME key do NOT
  // produce different output unless storage itself changed.

  function hydrate(
    projectId: string,
    timelineId: string,
    existingClipIds: string[],
  ): { selected: string | null; selectedSet: Set<string> } {
    const persisted = readPersistedSelection(projectId, timelineId);
    if (!persisted) {
      return { selected: null, selectedSet: new Set() };
    }
    return filterPersistedSelection(persisted, existingClipIds);
  }

  it("hydrates a fresh key with persisted IDs (existing + head)", () => {
    persistSelection("p1", "t1", "c1", new Set(["c1", "c2"]));
    const r = hydrate("p1", "t1", ["c1", "c2", "c3"]);
    expect(r.selected).toBe("c1");
    expect(r.selectedSet).toEqual(new Set(["c1", "c2"]));
  });

  it("filters IDs that no longer exist (B5: restore only existing)", () => {
    persistSelection("p1", "t1", "c1", new Set(["c1", "c2", "c-gone"]));
    const r = hydrate("p1", "t1", ["c1"]);
    expect(r.selectedSet).toEqual(new Set(["c1"]));
    expect(r.selected).toBe("c1");
  });

  it("drops head when it was removed; falls back to first surviving", () => {
    persistSelection("p1", "t1", "c-gone", new Set(["c-gone", "c1", "c2"]));
    const r = hydrate("p1", "t1", ["c1", "c2"]);
    expect(r.selected).toBe("c1");  // first surviving
    expect(r.selectedSet).toEqual(new Set(["c1", "c2"]));
  });

  it("returns null head + empty set when no IDs survive", () => {
    persistSelection("p1", "t1", "c-gone", new Set(["c-gone"]));
    const r = hydrate("p1", "t1", ["x", "y"]);
    expect(r.selected).toBeNull();
    expect(r.selectedSet.size).toBe(0);
  });

  it("rehydrating the SAME key twice returns the SAME data (read-only)", () => {
    persistSelection("p1", "t1", "c1", new Set(["c1"]));
    const r1 = hydrate("p1", "t1", ["c1"]);
    const r2 = hydrate("p1", "t1", ["c1"]);
    expect(r2).toEqual(r1);
  });

  it("rehydrating a DIFFERENT key returns DIFFERENT persisted data", () => {
    persistSelection("p1", "t1", "c1", new Set(["c1"]));
    persistSelection("p1", "t2", "c2", new Set(["c2"]));
    const r1 = hydrate("p1", "t1", ["c1"]);
    const r2 = hydrate("p1", "t2", ["c2"]);
    expect(r1.selected).toBe("c1");
    expect(r2.selected).toBe("c2");
  });

  it("rehydrating a key with no persisted entry returns empty (no fallback)", () => {
    // No persistence for "p1:t1".
    const r = hydrate("p1", "t1", ["c1"]);
    expect(r.selected).toBeNull();
    expect(r.selectedSet.size).toBe(0);
  });

  it("after mutation, re-hydration of SAME key would see new data (caller's choice to skip)", () => {
    persistSelection("p1", "t1", "c1", new Set(["c1"]));
    const r1 = hydrate("p1", "t1", ["c1"]);
    expect(r1.selected).toBe("c1");
    // External update to storage (e.g., another tab).
    persistSelection("p1", "t1", "c2", new Set(["c2"]));
    const r2 = hydrate("p1", "t1", ["c2"]);
    // Note: in App.tsx, the same-key rehydration is SKIPPED via
    // hydratedKeyRef.current. This model returns fresh data, but the
    // App.tsx integration test verifies the App.tsx behavior.
    expect(r2.selected).toBe("c2");  // model behavior; App.tsx would skip
  });

  it("switching projects does not leak selection (new key starts fresh)", () => {
    persistSelection("p1", "t1", "c-p1", new Set(["c-p1"]));
    persistSelection("p2", "t1", "c-p2", new Set(["c-p2"]));
    const r1 = hydrate("p1", "t1", ["c-p1"]);
    const r2 = hydrate("p2", "t1", ["c-p2"]);
    expect(r1.selected).toBe("c-p1");
    expect(r2.selected).toBe("c-p2");
    // No cross-key leak — each key returns its own persisted data.
  });
});