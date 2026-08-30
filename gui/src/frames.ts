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
 * we anchor in frames: `pxPerFrame = pxPerSec * fps.den / fps.num`. */
export function pxPerFrame(pxPerSec: number, fps: Rational): number {
  return pxPerSec * fps.den / fps.num;
}

/** Inverse: how many perceived-seconds per pixel at the current zoom
 * (used for tooltips and the "pxPerSec" display in the inspector). */
export function pxPerSecFromFrame(pxFrame: number, fps: Rational): number {
  return pxFrame * fps.num / fps.den;
}

/** Width of the track-name header column (OUTSIDE the coord space).
 *  This constant sizes the sticky left column; the ContentViewport
 *  itself starts at x=0 from frame 0 (no offset). */
export const LABEL_GUTTER_PX = 80;

/** Convert an integer playhead frame to a pixel x position from the
 * timeline ContentViewport origin. Default originPx=0 so frame 0
 * sits exactly at x=0 inside the ContentViewport — the header column
 * is OUTSIDE this coord space. */
export function playheadFrameToPixel(
  frame: number,
  zoom: number,
  fps: Rational,
  originPx: number = 0,
): number {
  return originPx + Math.round(frame * pxPerFrame(zoom, fps));
}

/** Inverse: which frame is at this pixel x? Uses
 * roundHalfAwayFromZero so the boundary semantics match the editor
 * spec. Default originPx=0 to match playheadFrameToPixel. */
export function pixelToPlayheadFrame(
  pixelX: number,
  zoom: number,
  fps: Rational,
  originPx: number = 0,
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

/** Standard NTSC DF: number of NDF frame numbers skipped before
 * real frame F (SMPTE 12M / Wikipedia closed-form). Mirrors
 * `yroll.core.timebase._df_drops_so_far` exactly:
 *     drops(F) = 2 * (F // fpm) - 2 * (F // fpm_10)
 * counts minutes 1..8 within every 10-min group (each contributing
 * 2 drops) and subtracts the 2 drops per 10-min boundary that
 * the minute-counting would otherwise over-count. */
function dfDropsSoFar(F: number, drop = 2, fpm = 1798, fpm_10 = 17982): number {
  if (F < 0) throw new Error(`frame must be non-negative, got ${F}`);
  return 2 * Math.floor(F / fpm) - 2 * Math.floor(F / fpm_10);
}

/** True iff `ndf` is a dropped frame number at 30000/1001 DF.
 * The standard NTSC DF drops 2 NDF frame numbers at the start of
 * every minute except every tenth: 1800*m and 1800*m+1 for minute
 * m in 1..9 within each 10-min group. So the dropped range within
 * a 10-min group is [1800, 16202). */
function isDroppedNdfAt29_97(ndf: number): boolean {
  if (ndf < 0) return false;
  const ndfD = ((ndf % 18000) + 18000) % 18000;  // NDF within the 10-min group
  return ndfD >= 1800 && ndfD < 16202;
}

/** Convert a frame count to a timecode string. SMPTE non-drop uses
 * `HH:MM:SS:FF`. SMPTE drop-frame (at 30000/1001) uses `HH:MM:SS;FF`
 * with the standard NTSC drop rule (closed-form SMPTE 12M).
 *
 * Mirrors `yroll.core.timebase.to_timecode` exactly. The 6 user-pinned
 * vectors (F=0/29/30/1798/17982/107892) are the boundary results of
 * the standard algorithm — no PINNED lookup table. */
export function framesToTimecode(
  frame: number,
  fps: Rational,
  dropFrame: boolean = false,
): string {
  if (frame < 0) throw new Error(`frame must be non-negative, got ${frame}`);
  const is30000over1001 = fps.num === 30000 && fps.den === 1001;
  let ndf: number;
  let sep: string;
  if (dropFrame && is30000over1001) {
    ndf = frame + dfDropsSoFar(frame);
    sep = ";";
  } else {
    ndf = frame;
    sep = ":";
  }
  const fpsInt = roundFps(fps);
  const ff = ndf % fpsInt;
  const totalSeconds = Math.floor(ndf / fpsInt);
  const ss = totalSeconds % 60;
  const totalMinutes = Math.floor(totalSeconds / 60);
  const mm = totalMinutes % 60;
  const hh = Math.floor(totalMinutes / 60);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${pad(hh)}:${pad(mm)}:${pad(ss)}${sep}${pad(ff)}`;
}

/** GUI-03R: ruler-friendly seconds display. Returns `MM:SS.mmm`
 *  where `.mmm` is the sub-second fraction in milliseconds (3-digit
 *  precision). Drops the HH field because editor content rarely
 *  exceeds an hour; for very long projects, the caller can prefix
 *  with an hours component.
 *
 *  The trailing field is **milliseconds**, not a frame field — even
 *  though both share the same display width. The companion
 *  `frameRulerLabel` returns the frame number for precise zoom. */
export function frameToRulerSeconds(
  frame: number,
  fps: Rational,
): string {
  if (frame < 0) throw new Error(`frame must be non-negative, got ${frame}`);
  const totalSeconds = frame * fps.den / fps.num;
  const mm = Math.floor(totalSeconds / 60);
  const ss = Math.floor(totalSeconds) % 60;
  const mmm = Math.round((totalSeconds - Math.floor(totalSeconds)) * 1000);
  const pad2 = (n: number) => String(n).padStart(2, "0");
  const pad3 = (n: number) => String(n).padStart(3, "0");
  return `${pad2(mm)}:${pad2(ss)}.${pad3(mmm)}`;
}

/** GUI-03R: precise-zoom companion label, e.g. `F372`. Pure frame
 *  integer; consumers concat after the seconds label. */
export function frameRulerLabel(frame: number): string {
  return `F${Math.round(frame)}`;
}

/** Inverse of `framesToTimecode`. Mirrors `yroll.core.timebase.from_timecode`.
 *
 * Round-trip is exact for both NDF and DF (bijective). For DF at
 * 30000/1001: illegal dropped labels (00:01:00;00, 00:01:00;01, etc.)
 * raise `Error`. Out-of-range fields (FF ≥ fps, SS/MM/HH ≥ 60/24)
 * also raise. */
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
  if (Number.isNaN(hh) || Number.isNaN(mm) || Number.isNaN(ss) || Number.isNaN(ff))
    throw new Error(`bad timecode ${JSON.stringify(s)}`);
  const fpsInt = roundFps(fps);
  if (hh < 0 || mm < 0 || ss < 0 || ff < 0)
    throw new Error(`negative timecode field in ${JSON.stringify(s)}`);
  if (hh > 23)
    throw new Error(`hour > 23 in ${JSON.stringify(s)}`);
  if (mm > 59 || ss > 59 || ff >= fpsInt)
    throw new Error(`out-of-range timecode field in ${JSON.stringify(s)}`);

  const ndfFrames = ((hh * 60 + mm) * 60 + ss) * fpsInt + ff;
  if (!isDf) return ndfFrames;

  const is30000over1001 = fps.num === 30000 && fps.den === 1001;
  if (!is30000over1001) return ndfFrames;

  // DF inverse at 30000/1001: reject illegal dropped labels, then
  // invert the standard NDF → F mapping (closed-form).
  if (isDroppedNdfAt29_97(ndfFrames))
    throw new Error(
      `${JSON.stringify(s)} is a dropped NDF label at 29.97 DF; ` +
      `the standard algorithm does not display it. ` +
      `Use the next non-dropped label.`,
    );

  const fpm = 1800;
  const fpm_10 = 17982;
  const drop = 2;
  const d = Math.floor(ndfFrames / (10 * fpm));
  const mIn = ndfFrames % (10 * fpm);

  let f: number;
  if (mIn < fpm) {
    // Minute 0 of the 10-min group: no drops.
    f = mIn;
  } else if (mIn >= 9 * fpm) {
    // 10th minute: no drop (10-min boundary resumes "real" frame count).
    f = 9 * (fpm - drop) + (mIn - 9 * fpm);
  } else {
    // Minutes 1..8: each carries 2 drops at the start.
    // minute_in_10 is in 0..7 (mIn in [1800, 9*1800) so minute_in_10 < 9).
    const minuteIn10 = Math.floor((mIn - fpm) / fpm);
    const ndfInMinute = mIn - fpm - minuteIn10 * fpm;  // 0..1797
    f = (minuteIn10 + 1) * (fpm - drop) + ndfInMinute;
  }
  return d * fpm_10 + f;
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

/** The 6 user-pinned DF vectors for 30000/1001 drop_frame=true —
 * the boundary results of the standard NTSC DF algorithm (no PINNED
 * dict hack). Mirrors `tests/test_timecode_conformance.py` exactly.
 *
 * Exposed for tests; the production algorithm derives these from
 * `dfDropsSoFar` directly. */
export const USER_PINNED_DF: Array<[number, string]> = [
  [0,      "00:00:00;00"],   // 0 sec, frame 0
  [29,     "00:00:00;29"],   // 0.97 sec, last frame of second 0
  [30,     "00:00:01;00"],   // 1.00 sec, first frame of second 1 (standard)
  [1798,   "00:01:00;00"],   // 60.03 sec, first frame of minute 1 (dropped label!)
  [17982,  "00:10:00;00"],   // 600.6 sec, 10-min boundary (no skip)
  [107892, "01:00:00;00"],   // 3599.4 sec, full hour
];
