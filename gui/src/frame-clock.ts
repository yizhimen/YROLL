// GUI-02.5: FrameClock — single playback-clock abstraction.
//
// Authoritative time is TimelineFrame (integer, sequence-fps timebase).
// The clock is a PURE function of wall-clock + a start anchor:
//
//   currentFrame(now) = startFrame
//                      + (now - startTime) * fps.num / fps.den / 1000 * rate
//                      clamped to [0, endFrame]
//
// Invariants (closure spec §02-5):
//   - TimelineFrame is integer canonical state.
//   - performance.now() + startFrame/startTime; never accumulate from
//     RAF/setInterval cadence.
//   - HTMLMediaElement.currentTime is external I/O only — never the
//     source of Timeline state.
//   - No video.timeupdate → playheadFrame feedback loop.
//   - pause()/resume() re-anchor at the current frame; seek() snaps
//     to an integer TimelineFrame.
//   - endFrame clamping stops the clock at the timeline's last frame.
//
// The clock is pure: given (state, now) it returns the same answer
// every time. Multiple consumers can call currentFrame() on the same
// state without side effects. RAF is render cadence only — the
// caller is responsible for any per-frame state mutation (e.g. UI
// repaints), the clock does not mutate itself.

import { roundHalfAwayFromZero } from "./frames";

export type Fps = { num: number; den: number };

export interface FrameClock {
  /** TimelineFrame integer at the moment of the last play/seek/resume. */
  startFrame: number;
  /** performance.now() at the moment of the last play/seek/resume. */
  startTimeMs: number;
  /** Sequence (timeline) timebase. */
  fps: Fps;
  /** Last valid TimelineFrame (timeline end-frame, exclusive is up to
   *  the caller; we use inclusive). currentFrame() never exceeds this. */
  endFrame: number;
  /** Playback rate. 1 = forward, -1 = backward, 0 = paused. */
  rate: 0 | 1 | -1;
  /** True iff currently advancing. */
  playing: boolean;
}

/** Create a clock anchored at `startFrame`. The clock starts paused. */
export function createFrameClock(opts: {
  startFrame: number;
  fps: Fps;
  endFrame: number;
  now?: number;
}): FrameClock {
  if (opts.endFrame < 0) throw new Error(`endFrame must be >= 0, got ${opts.endFrame}`);
  if (opts.startFrame < 0) throw new Error(`startFrame must be >= 0, got ${opts.startFrame}`);
  return {
    startFrame: roundHalfAwayFromZero(opts.startFrame),
    startTimeMs: opts.now ?? performance.now(),
    fps: opts.fps,
    endFrame: roundHalfAwayFromZero(opts.endFrame),
    rate: 0,
    playing: false,
  };
}

/** Pure function: compute the integer TimelineFrame at wall-clock `now`. */
export function currentFrame(c: FrameClock, now: number = performance.now()): number {
  if (!c.playing || c.rate === 0) return c.startFrame;
  const elapsedMs = now - c.startTimeMs;
  const deltaFrames = (elapsedMs * c.fps.num / c.fps.den / 1000) * c.rate;
  const raw = c.startFrame + deltaFrames;
  // End-clamp: if we've passed endFrame, freeze there. If we've gone
  // below 0 (reverse playback), freeze at 0.
  if (raw >= c.endFrame) return c.endFrame;
  if (raw < 0) return 0;
  return roundHalfAwayFromZero(raw);
}

/** Start (or resume) playback at the wall-clock now. Re-anchors
 *  startFrame/startTime at the current frame so the timeline keeps
 *  advancing smoothly across pauses. */
export function play(c: FrameClock, now: number = performance.now()): void {
  const f = currentFrame(c, now);
  c.startFrame = f;
  c.startTimeMs = now;
  c.rate = 1;
  c.playing = true;
}

/** Pause playback. Anchors startFrame at the current frame so
 *  resume() picks up exactly where we left off. */
export function pause(c: FrameClock, now: number = performance.now()): void {
  const f = currentFrame(c, now);
  c.startFrame = f;
  c.startTimeMs = now;
  c.rate = 0;
  c.playing = false;
}

/** Seek to an integer TimelineFrame. Re-anchors startTime at now.
 *  Preserves the playing state — callers should pair seek() with
 *  play()/pause() to control playback.
 *
 *  Negative frames clamp to 0; frames beyond endFrame clamp to
 *  endFrame. The clamp is symmetric (the caller can detect
 *  "we hit the end" by comparing the result to endFrame). */
export function seek(c: FrameClock, frame: number, now: number = performance.now()): number {
  const target = roundHalfAwayFromZero(frame);
  const clamped = Math.max(0, Math.min(c.endFrame, target));
  c.startFrame = clamped;
  c.startTimeMs = now;
  return clamped;
}

/** Toggle play/pause. Returns the new playing state. */
export function togglePlay(c: FrameClock, now: number = performance.now()): boolean {
  if (c.playing) {
    pause(c, now);
    return false;
  }
  play(c, now);
  return true;
}