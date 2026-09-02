// GUI-05-A (A3): user-facing mutation errors must NEVER expose
// technical error class names (HTTPError / ValueError / etc).
//
// We test `localizeMutationError` end-to-end:
//  - GateRejection → existing localizeGateRejection path
//  - Overlap 400 → Chinese text, no class names, no stack
//  - Default fallback → never raw detail
//
// Per L-7, `run()` returns `Promise<boolean>` (true=accepted+Core
// changed; false=rejected+Core unchanged). Per A3, the catch branch
// emits `console.warn("[YROLL-MUTATION-ERROR]", e)` for developer
// diagnostics and uses `localizeMutationError` for the user-facing
// status text.

import { describe, it, expect, vi } from "vitest";
import {
  localizeMutationError,
  localizeGateRejection,
} from "./error-localize";
import { GateRejection } from "./api";

describe("GUI-05-A (A3) localizeMutationError", () => {
  it("GateRejection → delegates to localizeGateRejection (existing path)", () => {
    const e = new GateRejection("lease_rejected", 409, "lease lost");
    const out = localizeMutationError(e);
    expect(out).toBe(localizeGateRejection(e));
    // UI text does NOT contain class names.
    expect(out).not.toMatch(/GateRejection/);
    expect(out).not.toMatch(/Error/);
  });

  it("overlap 400 (Chinese detail) → Chinese human message", () => {
    const e = new Error("与其他片段时间重叠：clip-a 与 clip-b 在 [0, 10) 重叠");
    const out = localizeMutationError(e);
    expect(out).toBe("与其他片段时间重叠，请换一个位置");
  });

  it("overlap 400 (English detail) → still Chinese human message", () => {
    const e = new Error("overlap with sibling clip-b in track t1");
    const out = localizeMutationError(e);
    expect(out).toBe("与其他片段时间重叠，请换一个位置");
  });

  it("target track missing → Chinese human message", () => {
    const e = new Error("目标轨道不存在: v99");
    const out = localizeMutationError(e);
    expect(out).toBe("目标轨道不存在");
  });

  it("default fallback — never raw detail, never class name", () => {
    const e = new Error("Some weird HTTP 500 stack trace with /api/foo");
    const out = localizeMutationError(e);
    expect(out).toBe("编辑未生效，请重试");
    // MUST NOT contain raw server detail or class names.
    expect(out).not.toMatch(/Some weird/);
    expect(out).not.toMatch(/HTTPError/);
    expect(out).not.toMatch(/ValueError/);
    expect(out).not.toMatch(/TypeError/);
    expect(out).not.toMatch(/Error/);
    expect(out).not.toMatch(/stack/);
    expect(out).not.toMatch(/api\/foo/);
  });

  it("non-Error thrown value (string) → fallback", () => {
    const out = localizeMutationError("totally not an error object");
    // "not an error" doesn't match any pattern → default fallback.
    expect(out).toBe("编辑未生效，请重试");
  });

  it("null/undefined → fallback", () => {
    expect(localizeMutationError(null)).toBe("编辑未生效，请重试");
    expect(localizeMutationError(undefined)).toBe("编辑未生效，请重试");
  });

  it("never exposes HTTPError / ValueError / TypeError class names", () => {
    const errors = [
      new Error("HTTPError: 500"),
      new Error("ValueError: invalid"),
      new TypeError("TypeError: bad type"),
      { name: "HTTPError", message: "500" },
      { name: "ValueError", message: "bad" },
      { name: "TypeError", message: "bad" },
    ];
    for (const e of errors) {
      const out = localizeMutationError(e);
      expect(out).not.toMatch(/HTTPError|ValueError|TypeError/);
    }
  });

  it("never includes raw JSON detail (no 'detail': pattern in output)", () => {
    const e = new Error(`{"detail":"overlap with sibling"}`);
    const out = localizeMutationError(e);
    // The output is a Chinese string; it MUST NOT contain the JSON
    // object or the 'detail' key.
    expect(out).not.toMatch(/"detail"/);
    expect(out).not.toMatch(/\{/);
  });
});

describe("GUI-05-A (A3) run() boolean semantics", () => {
  // Helper: read App.tsx, strip JS line + block comments, then locate
  // the run() function body. Comment-stripping is required because
  // App.tsx has a comment that mentions `String(e)` as a banned
  // pattern — we don't want the source-pin to falsely match.
  async function readRunFnBody(): Promise<string | null> {
    const fs = await import("node:fs/promises");
    const path = await import("node:path");
    const appPath = path.resolve(__dirname, "./App.tsx");
    const raw = await fs.readFile(appPath, "utf-8");
    // Strip // line comments and /* block comments */. Naive but
    // sufficient for our use case (no // or /* inside string
    // literals here).
    const stripped = raw
      .replace(/\/\*[\s\S]*?\*\//g, "")
      .replace(/^\s*\/\/.*$/gm, "")
      .replace(/\s+\/\/.*$/g, "");
    const m = stripped.match(/const run = async[\s\S]*?\n  \}\s*;/);
    return m ? m[0] : null;
  }

  // L-7 contract: `run()` returns Promise<boolean>. We can verify
  // the source-pin: error-localize.ts does NOT return raw `String(e)`
  // or class names. The run() function (in App.tsx) is harder to
  // unit-test without mounting App; we source-pin the catch branch.
  it("run() catch branch uses localizeMutationError, NOT String(e)", async () => {
    const body = await readRunFnBody();
    expect(body, "could not locate run() function in App.tsx").toBeTruthy();
    if (!body) return;
    // The catch branch must use localizeMutationError AND must NOT
    // use String(e).
    expect(body).toMatch(/localizeMutationError\(e\)/);
    expect(body).not.toMatch(/String\s*\(\s*e\s*\)/);
  });

  it("run() catch branch emits console.warn for developer diagnostics (A3d)", async () => {
    const body = await readRunFnBody();
    expect(body).toBeTruthy();
    if (!body) return;
    // Source-pin the developer diagnostics.
    expect(body).toMatch(/console\.warn\("\[YROLL-MUTATION-ERROR\]"/);
  });

  it("run() returns Promise<boolean> — source-pin", async () => {
    const body = await readRunFnBody();
    expect(body).toBeTruthy();
    if (!body) return;
    // L-7: signature must be Promise<boolean>.
    expect(body).toMatch(/Promise<boolean>/);
    // return true on success path.
    expect(body).toMatch(/return true/);
    // return false on catch path.
    expect(body).toMatch(/return false/);
  });
});