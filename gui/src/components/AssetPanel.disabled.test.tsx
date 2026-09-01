// GUI-03R6-E: AssetPanel disables `+` / `⧉` buttons and refuses
// drag-start when canEdit === false. The user must never be able
// to initiate a mutation the server would reject.

import { describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import AssetPanel from "./AssetPanel";

// Lightweight Project stub; the AssetPanel reads .assets, .timelines,
// .sequence, .timeline (legacy). The buttons only inspect asset.type
// and asset.path, so a minimal Asset with a unique id is enough.
const PROJECT = {
  name: "t",
  intent: null,
  sequence: { sequence_id: "s", fps: { num: 30, den: 1 }, width: 1920, height: 1080,
              timecode_format: "SMPTE", drop_frame: false, project_revision: 1 },
  timelines: [],
  timeline: { tracks: [] },
  assets: [{
    asset_id: "a1",
    type: "image",
    path: "img.png",
    identity: { md5: "x", size_bytes: 1, duration_sec: null,
                width: 100, height: 100, created_at: null },
    caption: null, tags: [],
    source_fps: null, source_is_cfr: null, source_frame_count: null,
    origin: "unknown", gen: null,
  }],
} as any;

describe("R6-E: AssetPanel canEdit gate", () => {
  it("renders the + button enabled when canEdit is true", () => {
    render(
      <AssetPanel
        project={PROJECT}
        activeTimelineId="main"
        playheadFrame={0}
        onChanged={async () => {}}
        onStatus={vi.fn()}
        onPreview={vi.fn()}
        canEdit={true}
      />,
    );
    const btns = screen.getAllByTitle("加到时间轴末尾") as HTMLButtonElement[];
    expect(btns.length).toBeGreaterThan(0);
    for (const btn of btns) expect(btn.disabled).toBe(false);
  });

  it("disables the + button when canEdit is false", () => {
    render(
      <AssetPanel
        project={PROJECT}
        activeTimelineId="main"
        playheadFrame={0}
        onChanged={async () => {}}
        onStatus={vi.fn()}
        onPreview={vi.fn()}
        canEdit={false}
      />,
    );
    // Every button now has the "编辑权未就绪" title when canEdit=false.
    const btns = screen.getAllByTitle("编辑权未就绪") as HTMLButtonElement[];
    expect(btns.length).toBeGreaterThan(0);
    for (const btn of btns) expect(btn.disabled).toBe(true);
  });

  it("treats missing canEdit as enabled (back-compat)", () => {
    render(
      <AssetPanel
        project={PROJECT}
        activeTimelineId="main"
        playheadFrame={0}
        onChanged={async () => {}}
        onStatus={vi.fn()}
        onPreview={vi.fn()}
      />,
    );
    const btns = screen.getAllByTitle("加到时间轴末尾") as HTMLButtonElement[];
    expect(btns.length).toBeGreaterThan(0);
    for (const btn of btns) expect(btn.disabled).toBe(false);
  });

  it("disables the ⧉ overlay button when canEdit is false", () => {
    render(
      <AssetPanel
        project={PROJECT}
        activeTimelineId="main"
        playheadFrame={0}
        onChanged={async () => {}}
        onStatus={vi.fn()}
        onPreview={vi.fn()}
        canEdit={false}
      />,
    );
    // The image asset has a ⧉ button (image type enables overlay).
    // Both `+` and `⧉` buttons get the "编辑权未就绪" title when
    // canEdit is false. Pick all buttons with that title and assert
    // every one is disabled.
    const disabled = screen.getAllByTitle("编辑权未就绪");
    expect(disabled.length).toBeGreaterThan(0);
    for (const btn of disabled) {
      expect((btn as HTMLButtonElement).disabled).toBe(true);
    }
  });
});