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
//
// GUI-03R4.1 P1-6: the SAME track_id must resolve to the SAME
// {top, height} across header column, content column, clip, marquee
// hit-test, and drop zone. The `trackRowGeometry(idx)` helper
// below is the ONLY place that computes row positions. Do not
// re-derive these in Timeline.tsx / ClipBlock.tsx — call this
// helper instead.

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

export interface TrackRowGeometry {
  /** Top of the row, in `.timeline-content` coord-space pixels. */
  top: number;
  /** Height of the row, in pixels (= TRACK_ROW_HEIGHT). */
  height: number;
  /** Bottom of the row (= top + height), in pixels. */
  bottom: number;
}

/** Single source of truth for a track row's vertical position.
 *
 *  Layout (every pixel accounted for, no magic offsets):
 *    [minimap   18px]      ← MINIMAP_HEIGHT
 *    [ruler     26px]      ← RULER_HEIGHT
 *    [track 0   56px]      ← top = MINIMAP + RULER + 0 × 56
 *    [track 1   56px]      ← top = MINIMAP + RULER + 1 × 56
 *    [track N-1 56px]
 *    [drop-zone 28+8px]    ← HEADERS_TAIL_HEIGHT
 *
 *  Every consumer of track-row geometry MUST call this helper:
 *   - Timeline.tsx marquee hit-test (computeMarqueeSelection)
 *   - Timeline.tsx marquee rect rendering (top offset)
 *   - ClipBlock.tsx (no y-coord needed; clip is inside its row)
 *   - Anything that paints inside a specific row
 *
 *  Header column rows render in the same DOM order — they don't
 *  need this helper because CSS flex order handles the alignment
 *  for them. But if any future code computes a header row's y
 *  position, it must use the same formula. */
export function trackRowGeometry(index: number): TrackRowGeometry {
  const top = MINIMAP_HEIGHT + RULER_HEIGHT + index * TRACK_ROW_HEIGHT;
  return {
    top,
    height: TRACK_ROW_HEIGHT,
    bottom: top + TRACK_ROW_HEIGHT,
  };
}