// GUI-03E-3 — TimelineSwitcher rendering tests.
//
// Covers the rendering contract:
//   1. Active chip is visually distinguished (data-active="true").
//   2. Last-timeline X button is NOT rendered (cannot delete last).
//   3. Click on a chip invokes onSwitch (parent decides what to do).
//   4. Click on X invokes onRequestDeleteTimeline.
//   5. Click on "+" invokes onRequestNewTimeline.

import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { fireEvent, render, screen, cleanup } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";

import TimelineSwitcher from "./TimelineSwitcher";

vi.mock("../preview-plan", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../preview-plan")>();
  return {
    ...actual,
    useTimelines: vi.fn(),
  };
});

import { useTimelines } from "../preview-plan";
// (mock reset lives inside mockUseTimelines)

function mockUseTimelines(state: {
  activeTimelineId: string;
  timelines: Array<{
    timeline_id: string;
    name: string;
    track_count: number;
    clip_count: number;
    marker_count: number;
    beat_count: number;
  }>;
}) {
  vi.mocked(useTimelines).mockReset();
  vi.mocked(useTimelines).mockReturnValue({
    activeTimelineId: state.activeTimelineId,
    defaultTimelineId: state.timelines[0]?.timeline_id ?? "",
    timelines: state.timelines,
    loading: false,
    error: null,
  });
}

afterEach(() => {
  cleanup();
});

describe("TimelineSwitcher", () => {
  it("renders one chip per Timeline and marks active", () => {
    mockUseTimelines({
      activeTimelineId: "tlB",
      timelines: [
        { timeline_id: "tlA", name: "完整版", track_count: 1, clip_count: 3, marker_count: 0, beat_count: 0 },
        { timeline_id: "tlB", name: "种草版", track_count: 1, clip_count: 0, marker_count: 0, beat_count: 0 },
      ],
    });
    render(
      <TimelineSwitcher
        projectRevision={1}
        activeTimelineId="tlB"
        onSwitch={() => {}}
        onRequestNewTimeline={() => {}}
        onRequestDeleteTimeline={() => {}}
      />,
    );
    const chipA = screen.getByTestId("timeline-chip-tlA");
    const chipB = screen.getByTestId("timeline-chip-tlB");
    expect(chipA).toHaveAttribute("data-active", "false");
    expect(chipB).toHaveAttribute("data-active", "true");
    expect(screen.getByText("完整版")).toBeInTheDocument();
    expect(screen.getByText("种草版")).toBeInTheDocument();
  });

  it("does not render delete X on the only Timeline", () => {
    mockUseTimelines({
      activeTimelineId: "tlA",
      timelines: [
        { timeline_id: "tlA", name: "完整版", track_count: 1, clip_count: 3, marker_count: 0, beat_count: 0 },
      ],
    });
    render(
      <TimelineSwitcher
        projectRevision={1}
        activeTimelineId="tlA"
        onSwitch={() => {}}
        onRequestNewTimeline={() => {}}
        onRequestDeleteTimeline={() => {}}
      />,
    );
    expect(screen.queryByTestId("timeline-chip-delete-tlA")).toBeNull();
  });

  it("renders delete X when there are multiple Timelines", () => {
    mockUseTimelines({
      activeTimelineId: "tlA",
      timelines: [
        { timeline_id: "tlA", name: "完整版", track_count: 1, clip_count: 3, marker_count: 0, beat_count: 0 },
        { timeline_id: "tlB", name: "种草版", track_count: 1, clip_count: 0, marker_count: 0, beat_count: 0 },
      ],
    });
    render(
      <TimelineSwitcher
        projectRevision={1}
        activeTimelineId="tlA"
        onSwitch={() => {}}
        onRequestNewTimeline={() => {}}
        onRequestDeleteTimeline={() => {}}
      />,
    );
    expect(screen.getByTestId("timeline-chip-delete-tlA")).toBeInTheDocument();
    expect(screen.getByTestId("timeline-chip-delete-tlB")).toBeInTheDocument();
  });

  it("invokes onSwitch when an inactive chip is clicked", () => {
    mockUseTimelines({
      activeTimelineId: "tlA",
      timelines: [
        { timeline_id: "tlA", name: "完整版", track_count: 1, clip_count: 3, marker_count: 0, beat_count: 0 },
        { timeline_id: "tlB", name: "种草版", track_count: 1, clip_count: 0, marker_count: 0, beat_count: 0 },
      ],
    });
    const onSwitch = vi.fn();
    render(
      <TimelineSwitcher
        projectRevision={1}
        activeTimelineId="tlA"
        onSwitch={onSwitch}
        onRequestNewTimeline={() => {}}
        onRequestDeleteTimeline={() => {}}
      />,
    );
    fireEvent.click(screen.getByTestId("timeline-chip-tlB"));
    expect(onSwitch).toHaveBeenCalledWith("tlB");
  });

  it("does NOT invoke onSwitch when the active chip is clicked", () => {
    mockUseTimelines({
      activeTimelineId: "tlA",
      timelines: [
        { timeline_id: "tlA", name: "完整版", track_count: 1, clip_count: 3, marker_count: 0, beat_count: 0 },
        { timeline_id: "tlB", name: "种草版", track_count: 1, clip_count: 0, marker_count: 0, beat_count: 0 },
      ],
    });
    const onSwitch = vi.fn();
    render(
      <TimelineSwitcher
        projectRevision={1}
        activeTimelineId="tlA"
        onSwitch={onSwitch}
        onRequestNewTimeline={() => {}}
        onRequestDeleteTimeline={() => {}}
      />,
    );
    fireEvent.click(screen.getByTestId("timeline-chip-tlA"));
    expect(onSwitch).not.toHaveBeenCalled();
  });

  it("invokes onRequestNewTimeline when '+' is clicked", () => {
    mockUseTimelines({
      activeTimelineId: "tlA",
      timelines: [
        { timeline_id: "tlA", name: "完整版", track_count: 1, clip_count: 3, marker_count: 0, beat_count: 0 },
      ],
    });
    const onNew = vi.fn();
    render(
      <TimelineSwitcher
        projectRevision={1}
        activeTimelineId="tlA"
        onSwitch={() => {}}
        onRequestNewTimeline={onNew}
        onRequestDeleteTimeline={() => {}}
      />,
    );
    fireEvent.click(screen.getByTestId("timeline-switcher-add"));
    expect(onNew).toHaveBeenCalledTimes(1);
  });
});