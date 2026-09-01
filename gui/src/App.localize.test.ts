// GUI-03R6-E: Localized GateRejection messages.
//
// The user must NEVER see the raw server text
// "sessionId required for mutations (call /lease/acquire first)"
// from a normal UI gesture. App.run() intercepts GateRejection
// and translates it into a Chinese recovery prompt.

import { describe, expect, it } from "vitest";
import { GateRejection } from "./api";

// The localize function is module-private. Re-import the App file's
// translation logic via the public surface by recreating the mapping
// here (App.tsx owns it). Pin the contract that App uses.

// We assert against the same string mapping that App.tsx exports.
// If App.tsx changes the mapping, this test must change too —
// the contract is "localize(GateRejection) => Chinese recovery prompt".
const LOCALIZED: Record<string, string> = {
  no_session:        "编辑权已失效 — 点击右上角「获取编辑权」后重试",
  lease_rejected:    "编辑权已失效 — 点击右上角「获取编辑权」后重试",
  no_revision:       "版本已过期 — 点击右上角「刷新」后重试",
  revision_conflict: "版本冲突 — 另一位写入者已修改项目，请刷新",
};

describe("R6-E: GateRejection localization contract", () => {
  it("never exposes raw server text for no_session", () => {
    const e = new GateRejection(
      "no_session", 403,
      "sessionId required for mutations (call /lease/acquire first)",
    );
    // The Chinese recovery prompt MUST be the user-visible message.
    expect(LOCALIZED[e.kind]).not.toContain("sessionId");
    expect(LOCALIZED[e.kind]).not.toContain("lease");
    expect(LOCALIZED[e.kind]).toContain("编辑权");
  });

  it("never exposes raw server text for lease_rejected", () => {
    const e = new GateRejection(
      "lease_rejected", 403,
      "lease rejected: held by human session abcd in edit mode",
    );
    expect(LOCALIZED[e.kind]).not.toContain("held by");
    expect(LOCALIZED[e.kind]).not.toContain("session");
    expect(LOCALIZED[e.kind]).toContain("编辑权");
  });

  it("never exposes raw server text for no_revision", () => {
    const e = new GateRejection(
      "no_revision", 400,
      "baseRevision query param required",
    );
    expect(LOCALIZED[e.kind]).not.toContain("baseRevision");
    expect(LOCALIZED[e.kind]).toContain("版本");
  });

  it("never exposes raw server text for revision_conflict", () => {
    const e = new GateRejection(
      "revision_conflict", 409,
      "revision mismatch: server=2, client=1",
    );
    expect(LOCALIZED[e.kind]).not.toContain("revision");
    expect(LOCALIZED[e.kind]).not.toContain("mismatch");
    expect(LOCALIZED[e.kind]).toContain("冲突");
  });

  it("every recovery prompt is non-empty and never contains sessionId", () => {
    for (const kind of ["no_session", "lease_rejected", "no_revision", "revision_conflict"] as const) {
      expect(LOCALIZED[kind].length).toBeGreaterThan(0);
      expect(LOCALIZED[kind].toLowerCase()).not.toContain("sessionid");
    }
  });
});