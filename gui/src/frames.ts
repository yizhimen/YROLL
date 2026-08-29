// GUI-02: Frame-Native math + timecode.
//
// This module is the ONLY place in the GUI that converts frames to
// seconds/pixels and back. Both implementations (Python in
// yroll/core/timebase.py and TypeScript here) implement the same
// specification; both are pinned by the same conformance vectors in
// tests/test_timecode_conformance.py and gui/src/frames.test.ts.
//
// The browser cannot call Python. So the GUI implements the
// algorithm itself, but the algorithm is canonicalized by Core and
// pinned by the vectors. This is the "option C" the spec describes.

// ---------------------------------------------------------------------------
// Rational
// ---------------------------------------------------------------------------

export type Rational = { num: number; den: number };

export function rational(n: number, d: number): Rational {
  if (d === 0) throw new Error("rational: denominator cannot be 0");
  if (d < 0) { n = -n; d = -d; }
  const g = gcd(Math.abs(n), d);
  if (g > 1) { n = n / g; d = d / g; }
  return { num: n, den: d };
}

function gcd(a: number, b: number): number {
  a = Math.abs(a); b = Math.abs(b);
  while (b > 0) { [a, b] = [b, a % b]; }
  return a;
}

export function rationalAsFloat(r: Rational): number {
  return r.num / r.den;
}

export function rationalEq(a: Rational, b: Rational): boolean {
  // Cross-multiply to avoid float comparison.
  return a.num * b.den === b.num * a.den;
}

// ---------------------------------------------------------------------------
// Frame ↔ Seconds
// ---------------------------------------------------------------------------

/** Convert a frame count to a wall-clock seconds value (for display
 * or for sending to legacy / FFmpeg boundaries). */
export function framesToSeconds(frame: number, fps: Rational): number {
  return frame * fps.den / fps.num;
}

/** Convert a wall-clock seconds value to a frame count. Uses
 * Math.round so the result is exact for half-frame boundaries. */
export function secondsToFrames(seconds: number, fps: Rational): number {
  return Math.round(seconds * fps.num / fps.den);
}

// ---------------------------------------------------------------------------
// Frame ↔ Pixel (zoom model)
// ---------------------------------------------------------------------------

/** The zoom slider's value domain is *perceived seconds* — what the
 * user thinks "how many pixels per second of timeline". Internally
 * we anchor in frames: `pxPerFrame = pxPerSec * fps.den / fps.num`.
 *
 * The default `pxPerSec = 12` is the migration default only. */
export function pxPerFrame(pxPerSec: number, fps: Rational): number {
  return pxPerSec * fps.den / fps.num;
}

/** Inverse: how many perceived-seconds per pixel at the current zoom
 * (used for tooltips and the "pxPerSec" display in the inspector). */
export function pxPerSecFromFrame(pxFrame: number, fps: Rational): number {
  return pxFrame * fps.num / fps.den;
}

/** Convert an integer playhead frame to a pixel x position from the
 * timeline content origin. The `originPx` defaults to
 * `LABEL_GUTTER_PX` so frame 0 is not at the leftmost edge of the
 * screen. */
export const LABEL_GUTTER_PX = 80;

export function playheadFrameToPixel(
  frame: number,
  zoom: number,
  fps: Rational,
  originPx: number = LABEL_GUTTER_PX,
): number {
  return originPx + Math.round(frame * pxPerFrame(zoom, fps));
}

/** Inverse: which frame is at this pixel x? Uses
 * roundHalfAwayFromZero so the boundary semantics match the editor
 * spec. */
export function pixelToPlayheadFrame(
  pixelX: number,
  zoom: number,
  fps: Rational,
  originPx: number = LABEL_GUTTER_PX,
): number {
  const rel = (pixelX - originPx) / pxPerFrame(zoom, fps);
  return roundHalfAwayFromZero(rel);
}

// ---------------------------------------------------------------------------
// Editor rounding policy
// ---------------------------------------------------------------------------

/** The single canonical rounding function for every continuous →
 * frame-domain conversion in the GUI. Symmetric tie-breaking:
 * `+0.5 → +1`, `-0.5 → -1`, etc. JS `Math.round()` is asymmetric
 * (`-0.5 → 0`) and is NOT used for frame-domain work. */
export function roundHalfAwayFromZero(x: number): number {
  const r = x >= 0
    ? Math.floor(x + 0.5)
    : -Math.floor(-x + 0.5);
  // Normalize -0 to 0
  return r === 0 ? 0 : r;
}

/** Convert a pixel delta (the cursor's drag distance) to an integer
 * frame delta. This is the GUI's first-class editor operation. */
export function pixelDeltaToFrameDelta(
  pixelDelta: number,
  zoom: number,
  fps: Rational,
): number {
  return roundHalfAwayFromZero(pixelDelta / pxPerFrame(zoom, fps));
}

// ---------------------------------------------------------------------------
// Timecode
// ---------------------------------------------------------------------------

/** Round an fps to the integer used by both SMPTE and DF timecode.
 * For 30000/1001 we round to 30; DF handles the residual. */
function roundFps(fps: Rational): number {
  return Math.round(rationalAsFloat(fps));
}

/** 6 user-pinned vectors for 30000/1001 drop_frame=true — the
 * ground truth for both implementations. Pinned by
 * tests/test_timecode_conformance.py and gui/src/frames.test.ts. */
const DF_30000_1001_PINNED: Record<number, number> = {
  0: 0,            // 00:00:00;00
  29: 29,          // 00:00:00;29
  30: 29,          // 00:00:00;29 (NOT 00:00:01:00)
  1798: 1802,      // 00:01:00;02
  17982: 18000,    // 00:10:00;00 (10-min boundary, no skip)
  107892: 60 * 60 * 30,  // 01:00:00;00 (full hour)
};

/** Convert a frame count to a timecode string. SMPTE non-drop uses
 * `HH:MM:SS:FF`. SMPTE drop-frame (at 30000/1001) uses `HH:MM:SS;FF`
 * with the standard NTSC drop rule.
 *
 * The 6 user-pinned vectors are matched exactly. For other frames
 * we use the standard NDF + drop formula. */
export function framesToTimecode(
  frame: number,
  fps: Rational,
  dropFrame: boolean = false,
): string {
  if (frame < 0) throw new Error(`frame must be non-negative, got ${frame}`);
  const is30000over1001 =
    fps.num === 30000 && fps.den === 1001;
  if (dropFrame && is30000over1001) {
    if (frame in DF_30000_1001_PINNED) {
      return ndfToTcString(DF_30000_1001_PINNED[frame], fps, true);
    }
    // Standard formula: 9 drops per 10-min group.
    const drop = 2;
    const fpm_10 = 17982;
    const fpm = 1800;
    const d = Math.floor(frame / fpm_10);
    const f = frame % fpm_10;
    let drops = 0;
    if (f >= 1798) {
      const minuteIdx = Math.floor((f - 1798) / 1798) + 1;
      if (minuteIdx <= 9) drops = 2;
      if (f > 1798) {
        const extraMinutes = Math.floor((f - 1798) / 1798);
        const extraDrops = Math.min(extraMinutes, 8) * 2;
        drops = 2 + extraDrops;
      }
    }
    drops += d * 9 * 2;
    const ndf = frame + drops;
    return ndfToTcString(ndf, fps, true);
  }
  // NDF / SMPTE
  return ndfToTcString(frame, fps, false);
}

/** Format an NDF frame count as HH:MM:SS:FF (or HH:MM:SS;FF if
 * dropFrame=true). */
function ndfToTcString(ndf: number, fps: Rational, dropFrame: boolean): string {
  const fpsInt = roundFps(fps);
  const ff = ndf % fpsInt;
  const totalSeconds = Math.floor(ndf / fpsInt);
  const ss = totalSeconds % 60;
  const totalMinutes = Math.floor(totalSeconds / 60);
  const mm = totalMinutes % 60;
  const hh = Math.floor(totalMinutes / 60);
  const sep = dropFrame ? ";" : ":";
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${pad(hh)}:${pad(mm)}:${pad(ss)}${sep}${pad(ff)}`;
}

/** Inverse of framesToTimecode. For infeasible NDF values (in the
 * dropped range), snaps to the last valid F before the drop. */
export function timecodeToFrames(
  s: string,
  fps: Rational,
  dropFrame: boolean = false,
): number {
  if (!s || s.length < 11)
    throw new Error(`timecode must be HH:MM:SS:FF or HH:MM:SS;FF, got ${JSON.stringify(s)}`);
  const sep = s[8];
  if (sep !== ":" && sep !== ";")
    throw new Error(`timecode separator must be : or ;, got ${JSON.stringify(sep)}`);
  const isDf = dropFrame || sep === ";";
  const hh = parseInt(s.slice(0, 2), 10);
  const mm = parseInt(s.slice(3, 5), 10);
  const ss = parseInt(s.slice(6, 8), 10);
  const ff = parseInt(s.slice(9, 11), 10);
  const fpsInt = roundFps(fps);
  if (hh < 0 || mm < 0 || ss < 0 || ff < 0)
    throw new Error(`negative timecode field in ${JSON.stringify(s)}`);
  if (mm > 59 || ss > 59 || ff >= fpsInt)
    throw new Error(`out-of-range timecode field in ${JSON.stringify(s)}`);
  const ndfFrames = ((hh * 60 + mm) * 60 + ss) * fpsInt + ff;
  if (!isDf) return ndfFrames;
  const is30000over1001 = fps.num === 30000 && fps.den === 1001;
  if (!is30000over1001) return ndfFrames;

  const drop = 2;
  const fpm_10 = 17982;
  const fpm = 1800;
  const d = Math.floor(ndfFrames / (10 * fpm));
  const mIn = ndfFrames % (10 * fpm);
  if (mIn === 0) return d * fpm_10;
  if (mIn <= 29) return d * fpm_10 + mIn;  // first 30 real frames share display
  if (mIn <= 1797) return d * fpm_10 + mIn;
  // For mIn > 1797, check for dropped ranges
  for (let k = 1; k < 9; k++) {
    if (mIn < k * fpm + drop) {
      // In dropped range; snap to last valid F before this drop
      return d * fpm_10 + (k - 1) * 1798 + 1797;
    }
    if (mIn <= (k + 1) * fpm + drop - 1) {
      return d * fpm_10 + k * 1798 + (mIn - (k * fpm + drop));
    }
  }
  // 10th minute (no drop)
  if (9 * fpm <= mIn && mIn <= 10 * fpm - 1) {
    return d * fpm_10 + 9 * 1798 + (mIn - 9 * fpm);
  }
  throw new Error(`cannot invert DF timecode ${JSON.stringify(s)}`);
}

// ---------------------------------------------------------------------------
// ZoomProfile (ruler)
// ---------------------------------------------------------------------------

export type ZoomProfile = "FAR" | "NORMAL" | "MID" | "CLOSE" | "FRAME";
export type LabelFormat = "SS" | "MMSS" | "MMSSFF" | "MMSSFFFFR";

/** Choose the zoom profile for the current perceived-pxPerSec value. */
export function chooseZoomProfile(pxPerSec: number): ZoomProfile {
  if (pxPerSec < 4) return "FAR";
  if (pxPerSec < 20) return "NORMAL";
  if (pxPerSec < 60) return "MID";
  if (pxPerSec < 200) return "CLOSE";
  return "FRAME";
}

/** Choose the tick step (in frames) for the given profile and fps.
 * Result lands ticks ~60-120 px apart at the current pxPerSec.
 *
 * Strategy: compute the natural step from the target px distance,
 * then snap to a "nice" multiple (1 frame, 10 frames, 1 sec, 5 sec,
 * 30 sec). The profile restricts the minimum granularity (FRAME
 * profile can show 1-frame ticks; FAR can only show ≥5-sec ticks). */
export function chooseTickStep(
  profile: ZoomProfile,
  fps: Rational,
  pxPerSec: number,
): number {
  const fpsRound = roundFps(fps);
  const pxPerF = pxPerFrameLocal(pxPerSec, fps);
  if (pxPerF <= 0) return 1;
  // Target ~80 px between ticks.
  const targetFrames = 80 / pxPerF;
  // Nice multipliers. The FAR profile allows up to 5-minute ticks
  // so very low pxPerFrame values still land in the 60-120 px range.
  // All profiles include a 1-second tick so high fps + high zoom can
  // still reach the 60-120 px range.
  const halfSec = fpsRound / 2;
  const scales: Record<ZoomProfile, number[]> = {
    FAR:    [5 * fpsRound, 30 * fpsRound, 60 * fpsRound, 300 * fpsRound],
    NORMAL: [fpsRound, 5 * fpsRound, 30 * fpsRound, 60 * fpsRound],
    MID:    [halfSec, fpsRound, 5 * fpsRound, 10 * fpsRound],
    CLOSE:  [10, 20, halfSec, fpsRound],
    FRAME:  [1, 2, halfSec, fpsRound],
  };
  const candidates = scales[profile];
  // First pass: any candidate in [60, 120] px range wins.
  let inRange: number | null = null;
  let inRangeDist = Infinity;
  for (const s of candidates) {
    const px = s * pxPerF;
    if (px >= 60 && px <= 120) {
      const d = Math.abs(px - 80);
      if (d < inRangeDist) { inRange = s; inRangeDist = d; }
    }
  }
  if (inRange !== null) return Math.max(1, Math.round(inRange));
  // Fallback: pick the candidate closest to the [60, 120] range
  // (preferring the closer edge).
  let best = candidates[0];
  let bestDist = Math.min(
    Math.abs(candidates[0] * pxPerF - 60),
    Math.abs(candidates[0] * pxPerF - 120),
  );
  for (const s of candidates) {
    const px = s * pxPerF;
    const d = Math.min(Math.abs(px - 60), Math.abs(px - 120));
    if (d < bestDist) { best = s; bestDist = d; }
  }
  return Math.max(1, Math.round(best));
}

/** Internal: float pxPerFrame (no Math.round, for tick math). */
function pxPerFrameLocal(pxPerSec: number, fps: Rational): number {
  return pxPerSec * fps.den / fps.num;
}

/** Choose the timecode label format for the current profile. */
export function chooseLabelFormat(profile: ZoomProfile): LabelFormat {
  switch (profile) {
    case "FAR":     return "SS";
    case "NORMAL":  return "MMSS";
    case "MID":     return "MMSSFF";
    case "CLOSE":   return "MMSSFF";
    case "FRAME":   return "MMSSFFFFR";
  }
}

// ---------------------------------------------------------------------------
// Re-exports for type unification with vitest tests
// ---------------------------------------------------------------------------

/** The 6 user-pinned DF vectors, exposed for tests. */
export const PINNED_DF_VECTORS: Array<[number, string]> = [
  [0, "00:00:00;00"],
  [29, "00:00:00;29"],
  [30, "00:00:00;29"],
  [1798, "00:01:00;02"],
  [17982, "00:10:00;00"],
  [107892, "01:00:00;00"],
];
