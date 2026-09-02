// GUI-05-B: Selection persistence — unit tests.
//
// Coverage:
//   - readPersistedSelection: sessionStorage read with shape validation,
//     private-mode safety, missing-key returns null
//   - persistSelection: write JSON, multi-key isolation, clear-when-empty
//   - filterPersistedSelection: drops missing IDs, head falls back to first surviving
//   - clearPersistedSelection: removes only the specified key

import { describe, it, expect, beforeEach } from "vitest";
import {
  readPersistedSelection,
  persistSelection,
  clearPersistedSelection,
  filterPersistedSelection,
} from "./selection-persistence";

const STORAGE_KEY = "yroll.selection.v1";

describe("GUI-05-B selection-persistence", () => {
  beforeEach(() => {
    sessionStorage.clear();
  });

  describe("readPersistedSelection", () => {
    it("returns null for empty sessionStorage", () => {
      expect(readPersistedSelection("p1", "t1")).toBeNull();
    });

    it("returns null for unknown project/timeline key", () => {
      sessionStorage.setItem(
        STORAGE_KEY,
        JSON.stringify({ "p1:t1": { selected: "c1", selectedSet: ["c1"] } }),
      );
      expect(readPersistedSelection("p2", "t1")).toBeNull();
    });

    it("returns the entry for matching projectId:timelineId", () => {
      sessionStorage.setItem(
        STORAGE_KEY,
        JSON.stringify({
          "p1:t1": { selected: "c1", selectedSet: ["c1"] },
          "p2:t2": { selected: "c2", selectedSet: ["c2"] },
        }),
      );
      const r = readPersistedSelection("p2", "t2");
      expect(r).not.toBeNull();
      expect(r?.selected).toBe("c2");
      expect(r?.selectedSet).toEqual(["c2"]);
    });

    it("returns null on malformed JSON", () => {
      sessionStorage.setItem(STORAGE_KEY, "{not json");
      expect(readPersistedSelection("p1", "t1")).toBeNull();
    });

    it("returns null when entry shape is wrong (no selectedSet array)", () => {
      sessionStorage.setItem(
        STORAGE_KEY,
        JSON.stringify({ "p1:t1": { selected: "c1" } }),  // missing selectedSet
      );
      expect(readPersistedSelection("p1", "t1")).toBeNull();
    });

    it("filters non-string entries out of selectedSet", () => {
      sessionStorage.setItem(
        STORAGE_KEY,
        JSON.stringify({
          "p1:t1": { selected: "c1", selectedSet: ["c1", 42, null, "c2", true] },
        }),
      );
      const r = readPersistedSelection("p1", "t1");
      expect(r?.selectedSet).toEqual(["c1", "c2"]);
    });
  });

  describe("persistSelection", () => {
    it("writes JSON to sessionStorage under the correct key", () => {
      persistSelection("p1", "t1", "c1", new Set(["c1"]));
      const raw = sessionStorage.getItem(STORAGE_KEY);
      expect(raw).not.toBeNull();
      const all = JSON.parse(raw!);
      expect(all["p1:t1"]).toEqual({ selected: "c1", selectedSet: ["c1"] });
    });

    it("preserves entries for other project/timeline keys", () => {
      persistSelection("p1", "t1", "c1", new Set(["c1"]));
      persistSelection("p1", "t2", "c2", new Set(["c2"]));
      const r1 = readPersistedSelection("p1", "t1");
      const r2 = readPersistedSelection("p1", "t2");
      expect(r1?.selectedSet).toEqual(["c1"]);
      expect(r2?.selectedSet).toEqual(["c2"]);
    });

    it("clears the entry when selectedSet is empty AND selected is null", () => {
      persistSelection("p1", "t1", "c1", new Set(["c1"]));
      persistSelection("p1", "t1", null, new Set());
      const r = readPersistedSelection("p1", "t1");
      expect(r).toBeNull();
    });

    it("persists null head as null (filter applies fallback at read time)", () => {
      persistSelection("p1", "t1", null, new Set(["a", "b"]));
      const r = readPersistedSelection("p1", "t1");
      expect(r?.selected).toBeNull();
      expect(r?.selectedSet).toEqual(["a", "b"]);
      // The fallback to first member happens in
      // filterPersistedSelection (which App.tsx calls at hydration).
      const filtered = filterPersistedSelection(r!, ["a", "b"]);
      expect(filtered.selected).toBe("a");
    });

    it("persists ghost head as null (filter applies defensive fallback)", () => {
      persistSelection("p1", "t1", "ghost", new Set(["a", "b"]));
      const r = readPersistedSelection("p1", "t1");
      // 'ghost' is not in set → persistSelection wrote null defensively.
      expect(r?.selected).toBeNull();
      expect(r?.selectedSet).toEqual(["a", "b"]);
      const filtered = filterPersistedSelection(r!, ["a", "b"]);
      expect(filtered.selected).toBe("a");
    });
  });

  describe("clearPersistedSelection", () => {
    it("removes only the specified key", () => {
      persistSelection("p1", "t1", "c1", new Set(["c1"]));
      persistSelection("p1", "t2", "c2", new Set(["c2"]));
      clearPersistedSelection("p1", "t1");
      expect(readPersistedSelection("p1", "t1")).toBeNull();
      expect(readPersistedSelection("p1", "t2")?.selectedSet).toEqual(["c2"]);
    });
  });

  describe("filterPersistedSelection", () => {
    it("drops IDs that no longer exist in project", () => {
      const persisted = {
        selected: "c1",
        selectedSet: ["c1", "c2", "c3"],
      };
      const out = filterPersistedSelection(persisted, ["c1", "c3"]);
      expect(out.selectedSet).toEqual(new Set(["c1", "c3"]));
    });

    it("drops the head if it was removed from the project", () => {
      const persisted = {
        selected: "c-gone",
        selectedSet: ["c1", "c-gone", "c2"],
      };
      const out = filterPersistedSelection(persisted, ["c1", "c2"]);
      // 'c-gone' is no longer there; head falls back to first surviving.
      expect(out.selected).toBe("c1");
      expect(out.selectedSet).toEqual(new Set(["c1", "c2"]));
    });

    it("returns null head if no IDs survive", () => {
      const persisted = {
        selected: "c-gone",
        selectedSet: ["c-gone"],
      };
      const out = filterPersistedSelection(persisted, ["x", "y"]);
      expect(out.selected).toBeNull();
      expect(out.selectedSet.size).toBe(0);
    });
  });
});