// GUI-03R4-R3: Shared Timeline Row Geometry.
//
// Both the track header column (`.timeline-headers`) and the timeline
// content column (`.timeline-content`) MUST render with the same
// vertical structure so the same track_id maps to the same vertical
// row position in BOTH columns. Previously the columns hardcoded
// their heights independently — `.timeline-headers` had no ruler
// spacer and no drop-zone tail, causing the header label of the
// last track row to be misaligned with its content row.
//
// These constants are the SINGLE source of truth for vertical
// dimensions. CSS uses them via inline `style` (the column
// itself owns its height values; CSS only provides fallbacks).

export const TRACK_ROW_HEIGHT = 56;       // .track-label-row / .track-row
export const MINIMAP_HEIGHT = 18;         // .minimap (sticky top:0)
export const RULER_HEIGHT = 26;           // .ruler (sticky top:18)
export const DROP_ZONE_HEIGHT = 28;       // .drop-zone-new-track content height
export const DROP_ZONE_VERTICAL_MARGIN = 4; // top + bottom margin (each)

// Per-side vertical offsets that the header column must mirror from
// the content column. These are used to size the spacer / tail
// elements inside `.timeline-headers`.
export const HEADERS_SPACER_HEIGHT = MINIMAP_HEIGHT;        // 18
export const HEADERS_RULER_SPACER_HEIGHT = RULER_HEIGHT;    // 26
export const HEADERS_TAIL_HEIGHT =
    DROP_ZONE_HEIGHT + DROP_ZONE_VERTICAL_MARGIN * 2;       // 28 + 8 = 36

// Total content height (for any vertical-position math that needs it).
// This matches the layout:
//   [minimap 18]
//   [ruler 26]
//   [N × track-row 56]
//   [drop-zone 28 + margin 8]
export function trackContentHeight(trackCount: number): number {
    return MINIMAP_HEIGHT + RULER_HEIGHT
        + trackCount * TRACK_ROW_HEIGHT
        + DROP_ZONE_HEIGHT + DROP_ZONE_VERTICAL_MARGIN * 2;
}