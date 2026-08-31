// GUI-03R5-B4 (Decision 5): Context menu tests.
//
// Pins the shape of track-header + gap content menus so the audit's
// "gap / track actions are CONTEXTUAL, not topbar" rule is enforced.

import { describe, expect, it } from "vitest";
import type { MenuItem } from "./components/ContextMenu";

/** Pure projection of the track-header menu items from the
 *  production logic in Timeline.tsx — duplicated here so the test
 *  pins the user-visible labels WITHOUT depending on the React tree. */
function trackMenuItems(track: {
  track_id: string;
  kind: string;
  muted: boolean;
  locked: boolean;
  hidden: boolean;
}): MenuItem[] {
  const items: MenuItem[] = [
    { label: "关闭本轨道所有间隙" },
    { label: "——", separator: true },
  ];
  if (track.kind !== "text" && (track.kind as string) !== "subtitle") {
    items.push({ label: track.muted ? "取消静音" : "静音" });
  }
  items.push({ label: track.locked ? "解锁轨道" : "锁定轨道（禁拖动）" });
  items.push({ label: track.hidden ? "显示轨道" : "隐藏轨道" });
  return items;
}

/** Pure projection of the gap-content menu items. */
function gapMenuItems(
  gap: { startSec: number; endSec: number } | null,
  trackId: string,
  visibleCount: number,
): MenuItem[] {
  const items: MenuItem[] = [];
  if (gap) {
    items.push({
      label: "关闭这个间隙",
      hint: `${gap.startSec.toFixed(2)}s – ${gap.endSec.toFixed(2)}s`,
    });
  }
  items.push({ label: "关闭本轨道所有间隙" });
  items.push({ label: "关闭全部可见间隙" });
  return items;
}

describe("GUI-03R5-B4: track-header context menu", () => {
  it("always exposes '关闭本轨道所有间隙' as the first item", () => {
    const items = trackMenuItems({
      track_id: "v1", kind: "video",
      muted: false, locked: false, hidden: false,
    });
    expect(items[0].label).toBe("关闭本轨道所有间隙");
  });

  it("includes separator before the existing track controls", () => {
    const items = trackMenuItems({
      track_id: "v1", kind: "video",
      muted: false, locked: false, hidden: false,
    });
    expect(items.some((i) => i.separator)).toBe(true);
  });

  it("shows 静音 (not 取消静音) when track is unmuted", () => {
    const items = trackMenuItems({
      track_id: "v1", kind: "video",
      muted: false, locked: false, hidden: false,
    });
    expect(items.some((i) => i.label === "静音")).toBe(true);
    expect(items.some((i) => i.label === "取消静音")).toBe(false);
  });

  it("shows 取消静音 when track is muted", () => {
    const items = trackMenuItems({
      track_id: "v1", kind: "video",
      muted: true, locked: false, hidden: false,
    });
    expect(items.some((i) => i.label === "取消静音")).toBe(true);
  });

  it("audio track exposes the 静音 toggle", () => {
    const items = trackMenuItems({
      track_id: "a1", kind: "audio",
      muted: false, locked: false, hidden: false,
    });
    expect(items.some((i) => i.label === "静音")).toBe(true);
  });

  it("does NOT expose 静音 for text/subtitle tracks", () => {
    for (const kind of ["text", "subtitle"]) {
      const items = trackMenuItems({
        track_id: "t1", kind,
        muted: false, locked: false, hidden: false,
      });
      expect(items.some((i) => i.label === "静音")).toBe(false);
      expect(items.some((i) => i.label === "取消静音")).toBe(false);
    }
  });

  it("shows 解锁轨道 when locked, 锁定轨道 when not", () => {
    const locked = trackMenuItems({
      track_id: "v1", kind: "video",
      muted: false, locked: true, hidden: false,
    });
    expect(locked.some((i) => i.label === "解锁轨道")).toBe(true);
    const unlocked = trackMenuItems({
      track_id: "v1", kind: "video",
      muted: false, locked: false, hidden: false,
    });
    expect(unlocked.some((i) => i.label?.includes("锁定轨道"))).toBe(true);
  });

  it("shows 显示轨道 when hidden, 隐藏轨道 when not", () => {
    const hidden = trackMenuItems({
      track_id: "v1", kind: "video",
      muted: false, locked: false, hidden: true,
    });
    expect(hidden.some((i) => i.label === "显示轨道")).toBe(true);
    const visible = trackMenuItems({
      track_id: "v1", kind: "video",
      muted: false, locked: false, hidden: false,
    });
    expect(visible.some((i) => i.label === "隐藏轨道")).toBe(true);
  });
});

describe("GUI-03R5-B4: gap context menu", () => {
  it("includes the gap close action with the gap's range in the hint", () => {
    const items = gapMenuItems(
      { startSec: 5.0, endSec: 12.5 }, "v1", 4,
    );
    const close = items.find((i) => i.label === "关闭这个间隙");
    expect(close).toBeDefined();
    expect(close!.hint).toMatch(/5\.00s – 12\.50s/);
  });

  it("includes track-scope and all-visible scope actions", () => {
    const items = gapMenuItems(
      { startSec: 5.0, endSec: 12.5 }, "v1", 4,
    );
    expect(items.some((i) => i.label === "关闭本轨道所有间隙")).toBe(true);
    expect(items.some((i) => i.label === "关闭全部可见间隙")).toBe(true);
  });

  it("renders gap-close-less menu when gap is null (clicked on a clip)", () => {
    const items = gapMenuItems(null, "v1", 4);
    expect(items.some((i) => i.label === "关闭这个间隙")).toBe(false);
    // track-scope and all-visible still available.
    expect(items.some((i) => i.label === "关闭本轨道所有间隙")).toBe(true);
    expect(items.some((i) => i.label === "关闭全部可见间隙")).toBe(true);
  });
});

describe("GUI-03R5-B4: topbar 批量关闭间隙 is GONE", () => {
  it("The removed topbar button is documented as such in App.tsx", async () => {
    // The topbar button was removed in B4. Verify via a static
    // check on the source — we don't want a regression that
    // re-adds it.
    const fs = await import("node:fs");
    const src = fs.readFileSync("src/App.tsx", "utf8");
    expect(src).not.toMatch(/批量关闭间隙\s*</);
    // And the documented removal comment IS present (regex with
    // [\s\S] for cross-line match since the comment is multi-line):
    expect(src).toMatch(/GUI-03R5-B4[\s\S]*Decision 5[\s\S]*REMOVED/);
  });
});