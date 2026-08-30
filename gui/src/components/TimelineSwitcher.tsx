// GUI-03E-3: TimelineSwitcher
//
// Top-level peer-Timeline switcher. The active Timeline id is
// owned by the parent (App) — this component is fully controlled.
// The parent passes:
//   - activeTimelineId:           single source of truth
//   - onSwitch(newId):            called when the user picks a chip;
//                                   parent must optimistically update
//                                   activeTimelineId and refetch
//                                   Timeline-local data
//   - onRequestNewTimeline():     called when the user clicks [+];
//                                   parent opens NewTimelineDialog
//   - onRequestDeleteTimeline(id, fallbackId): called when the user
//                                   clicks a chip's X; parent confirms
//                                   and calls api.deleteTimeline();
//                                   `fallbackId` is the Core-resolved
//                                   replacement (returned by the
//                                   DELETE response). Parent uses it
//                                   to sync activeTimelineId after
//                                   deletion.
//
// Stale-response defense: every server response includes the
// server-resolved active_timeline_id. The parent MUST use that
// value rather than guessing — that's how a deleted-active
// Timeline safely lands the user on the next-surviving Timeline.

import { useEffect, useState } from "react";
import { api, TimelineSummary } from "../api";
import { useTimelines } from "../preview-plan";

export interface TimelineSwitcherProps {
  projectRevision: number;
  activeTimelineId: string;
  onSwitch: (timelineId: string) => void;
  onRequestNewTimeline: () => void;
  onRequestDeleteTimeline: (
    timelineId: string,
    fallbackActiveId: string,
  ) => void;
}

export default function TimelineSwitcher({
  projectRevision,
  activeTimelineId,
  onSwitch,
  onRequestNewTimeline,
  onRequestDeleteTimeline,
}: TimelineSwitcherProps) {
  const { timelines, activeTimelineId: serverActive, loading, error } =
    useTimelines(projectRevision);

  // Per-switch optimistic highlight. Tracks which chip the user
  // just clicked so the UI can show a brief "switching…" state
  // before the server response lands. The single source of truth
  // remains `activeTimelineId` from the parent.
  const [pendingId, setPendingId] = useState<string | null>(null);

  // Clear pending if the parent confirms the switch.
  useEffect(() => {
    if (pendingId && activeTimelineId === pendingId) {
      setPendingId(null);
    }
  }, [activeTimelineId, pendingId]);

  const handleClick = (tl: TimelineSummary) => {
    if (tl.timeline_id === activeTimelineId) return;
    setPendingId(tl.timeline_id);
    // Optimistic UI: parent will update activeTimelineId and the
    // Preview/cache will refetch scoped to the new Timeline. If
    // the server later disagrees (e.g. a deletion raced), the
    // parent's resync from server response will correct it.
    onSwitch(tl.timeline_id);
  };

  const handleDelete = (tl: TimelineSummary, e: React.MouseEvent) => {
    e.stopPropagation();
    if (timelines.length <= 1) return; // last-timeline guard
    if (!window.confirm(
      `删除版本 "${tl.name}"？\n该版本上所有 clip/track/marker/beat 将一并删除。`,
    )) {
      return;
    }
    // We don't know the server-resolved replacement yet — pass an
    // empty string as a sentinel; the parent performs the actual
    // DELETE and reads the response's `active_timeline_id`. We
    // only render the affordance here.
    onRequestDeleteTimeline(tl.timeline_id, "");
  };

  return (
    <div
      className="timeline-switcher"
      data-testid="timeline-switcher"
      style={{
        display: "flex",
        alignItems: "center",
        gap: 6,
        padding: "4px 8px",
        borderBottom: "1px solid #2a2a2a",
        background: "#1a1a1a",
      }}
    >
      <span style={{ fontSize: 11, color: "#888", marginRight: 4 }}>
        版本
      </span>
      {loading && timelines.length === 0 && (
        <span style={{ fontSize: 11, color: "#888" }}>加载…</span>
      )}
      {error && (
        <span style={{ fontSize: 11, color: "#e57373" }}>
          加载失败：{error}
        </span>
      )}
      {timelines.map((tl) => {
        const isActive = tl.timeline_id === activeTimelineId;
        const isPending = tl.timeline_id === pendingId;
        const isServerActive = tl.timeline_id === serverActive;
        const canDelete = timelines.length > 1;
        return (
          <div
            key={tl.timeline_id}
            data-testid={`timeline-chip-${tl.timeline_id}`}
            data-active={isActive ? "true" : "false"}
            data-server-active={isServerActive ? "true" : "false"}
            data-pending={isPending ? "true" : "false"}
            onClick={() => handleClick(tl)}
            style={{
              display: "flex",
              alignItems: "center",
              gap: 4,
              padding: "4px 10px",
              borderRadius: 14,
              cursor: "pointer",
              fontSize: 12,
              userSelect: "none",
              // Active = thick outline ring + slightly different bg.
              boxShadow: isActive
                ? "0 0 0 2px #7ec97e inset"
                : "0 0 0 1px #444 inset",
              background: isActive
                ? "#2a3a2a"
                : isPending
                ? "#2a2a2a"
                : "transparent",
              color: isActive ? "#cfeacf" : "#cfcfcf",
              opacity: isPending && !isActive ? 0.7 : 1,
              transition: "background 80ms, box-shadow 80ms",
            }}
            title={
              tl.derived_from
                ? `派生自 ${tl.derived_from}`
                : undefined
            }
          >
            <span>{tl.name}</span>
            <span style={{ fontSize: 10, color: "#888" }}>
              {tl.clip_count}
            </span>
            {canDelete && (
              <span
                data-testid={`timeline-chip-delete-${tl.timeline_id}`}
                onClick={(e) => handleDelete(tl, e)}
                role="button"
                aria-label={`删除版本 ${tl.name}`}
                style={{
                  marginLeft: 2,
                  padding: "0 4px",
                  borderRadius: 8,
                  fontSize: 11,
                  color: "#aaa",
                }}
                onMouseEnter={(e) => {
                  (e.currentTarget as HTMLElement).style.color = "#e57373";
                }}
                onMouseLeave={(e) => {
                  (e.currentTarget as HTMLElement).style.color = "#aaa";
                }}
              >
                ✕
              </span>
            )}
          </div>
        );
      })}
      <button
        data-testid="timeline-switcher-add"
        onClick={onRequestNewTimeline}
        style={{
          padding: "4px 10px",
          borderRadius: 14,
          border: "1px dashed #555",
          background: "transparent",
          color: "#888",
          cursor: "pointer",
          fontSize: 12,
        }}
        title="新增版本"
      >
        +
      </button>
    </div>
  );
}