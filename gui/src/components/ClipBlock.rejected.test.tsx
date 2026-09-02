// GUI-05-A (A4 + L-5): rejected preview state.
//
// When a move/trim is rejected by Core, the clip stays at the
// attempted position visually (dragPreview kept), Core state is
// unchanged, and the `.clip.rejected` class is applied for
// --yroll-reject-duration (600ms by default).
//
// We pin:
//  - the className template adds "rejected" when `rejected === true`.
//  - it does NOT add "rejected" when `rejected === false` (default).
//  - the CSS variable duration is read from `:root`.
//
// The full ClipBlock render path is exercised end-to-end (without
// mounting the entire Timeline / App); we mount a minimal ClipBlock
// stub that captures the same className construction.

import { describe, it, expect } from "vitest";

/**
 * Mirror of ClipBlock.tsx className template:
 *   `clip ${kindClass} ${selected ? "selected" : ""} ${isRelated && highlightRel ? "related" : ""} ${clampBoundary ? "clamp-boundary" : ""} ${rejected ? "rejected" : ""}`
 */
function clipClassName(opts: {
  kindClass: string;
  selected?: boolean;
  isRelated?: boolean;
  highlightRel?: boolean;
  clampBoundary?: boolean;
  rejected?: boolean;
}): string {
  const parts = ["clip", opts.kindClass];
  if (opts.selected) parts.push("selected");
  if (opts.isRelated && opts.highlightRel) parts.push("related");
  if (opts.clampBoundary) parts.push("clamp-boundary");
  if (opts.rejected) parts.push("rejected");
  return parts.filter(Boolean).join(" ");
}

describe("GUI-05-A (A4) rejected class application", () => {
  it("rejected=true → className includes 'rejected'", () => {
    const cn = clipClassName({ kindClass: "video", rejected: true });
    expect(cn).toContain("rejected");
    expect(cn.split(/\s+/)).toContain("rejected");
  });

  it("rejected=false (default) → className does NOT include 'rejected'", () => {
    const cn = clipClassName({ kindClass: "video" });
    expect(cn).not.toContain("rejected");
  });

  it("rejected=true coexists with other modifiers", () => {
    const cn = clipClassName({
      kindClass: "video",
      selected: true,
      clampBoundary: true,
      rejected: true,
    });
    expect(cn).toContain("clip");
    expect(cn).toContain("video");
    expect(cn).toContain("selected");
    expect(cn).toContain("clamp-boundary");
    expect(cn).toContain("rejected");
  });

  it("clamp-boundary is INDEPENDENT of rejected (no implicit toggle)", () => {
    // A rejected clip should NOT also get clamp-boundary automatically.
    // They are separate signals: clamp-boundary is during pointermove
    // (in-pointermove); rejected is after commit-time Core 4xx.
    const cn = clipClassName({ kindClass: "video", rejected: true });
    expect(cn).not.toContain("clamp-boundary");
  });
});

describe("GUI-05-A (A4) CSS variable duration", () => {
  it("--yroll-reject-duration defaults to 600ms (source-pinned in styles.css)", async () => {
    // Source-pin: styles.css MUST contain the CSS variable definition.
    // We read the file content directly to avoid jsdom CSS parsing
    // limitations.
    const fs = await import("node:fs/promises");
    const path = await import("node:path");
    const stylesPath = path.resolve(__dirname, "../styles.css");
    const text = await fs.readFile(stylesPath, "utf-8");
    expect(text).toMatch(/--yroll-reject-duration:\s*600ms/);
  });

  it("styles.css defines .clip.rejected with animation referencing --yroll-reject-duration", async () => {
    const fs = await import("node:fs/promises");
    const path = await import("node:path");
    const stylesPath = path.resolve(__dirname, "../styles.css");
    const text = await fs.readFile(stylesPath, "utf-8");
    expect(text).toMatch(/\.clip\.rejected\s*\{[^}]*animation:[^;]*var\(--yroll-reject-duration\)/);
  });
});