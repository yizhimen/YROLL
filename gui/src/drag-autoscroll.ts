// GUI-03R4.1 P0-1: Edge-based Auto-Scroll for Clip Drag.
//
// Drives `.timeline-content.scrollLeft` while the user drags a clip
// past the visible edge of the ContentViewport. The behavior is:
//
//   • Symmetric (left edge ↔ right edge).
//   • Continuous (no "jump to start/end" / no discrete step changes).
//   • Speed scales SMOOTHLY with pointer distance to the edge:
//       0 px from the edge → MAX_SPEED_PX_PER_SEC
//       EDGE_ZONE_PX from the edge → 0
//   • Linear ramp (one break point). A linear ramp is the smoothest
//     possible single-segment mapping; it's also what every desktop
//     OS uses for window-edge scroll during drag (Finder / Explorer /
//     file managers).
//   • Frame math remains canonical: the scroll delta contributes to
//     the total pixel delta in ClipBlock's move handler — pixel
//     delta is the source of truth, both pointer and scroll feed it.
//   • No drag-time snap (this is purely scroll; the snap engine is
//     untouched and remains visual-only on pointerup).
//
// The helper is a small stateful object the ClipBlock instantiates
// at pointerdown and disposes at pointerup. It exposes:
//
//   new DragAutoScroll(contentEl)    — creates + starts the rAF loop
//   .updatePointer(clientX)          — record latest pointer x
//   .dispose()                       — stop rAF + clear listeners
//
// Consumers (ClipBlock) MUST call updatePointer() on every
// pointermove so the loop can compute the correct speed from the
// latest cursor position.

/** Width of the edge zone, in pixels. Within EDGE_ZONE_PX of the
 *  left/right edge of the ContentViewport, auto-scroll engages.
 *  Outside this zone, no scrolling happens. */
export const EDGE_ZONE_PX = 80;

/** Maximum auto-scroll speed at the edge itself (pointer touching
 *  the very edge of ContentViewport). In px/sec. Tuned to feel
 *  like a brisk drag (slightly faster than typical scroll-wheel
 *  inertial scrolling). */
export const MAX_SPEED_PX_PER_SEC = 900;

/** Minimum auto-scroll speed below which the loop considers the
 *  pointer effectively stationary at the zone boundary and stops
 *  scheduling scroll updates. Sub-1px/sec isn't worth the rAF
 *  cost and is below visual perception. */
export const MIN_EFFECTIVE_SPEED_PX_PER_SEC = 4;

export class DragAutoScroll {
  private contentEl: HTMLElement | null;
  private rafId: number | null = null;
  private lastPointerClientX: number = 0;
  private lastTs: number = 0;
  private disposed = false;

  constructor(contentEl: HTMLElement | null) {
    this.contentEl = contentEl;
    if (contentEl) {
      // Start the rAF loop immediately. The loop is a no-op when
      // the cursor isn't in the edge zone (returns speed=0).
      this.lastTs = performance.now();
      this.rafId = requestAnimationFrame(this.tick);
    }
  }

  /** Record the most recent pointer X. Call this on every
   *  pointermove. We deliberately do NOT also call move() from the
   *  rAF tick — the consumer owns the move() invocation so the
   *  consumer's full clamp / ghost-snap logic runs synchronously
   *  with the scroll change. The rAF tick only mutates scrollLeft. */
  updatePointer(clientX: number): void {
    this.lastPointerClientX = clientX;
  }

  /** Compute current auto-scroll speed + direction from the latest
   *  pointer X. Pure helper exposed for testing — the rAF tick
   *  inlines this for performance.
   *
   *   clientX = NaN / outside the viewport → speed=0, dir=0
   *   clientX within EDGE_ZONE_PX of right edge → dir=+1
   *   clientX within EDGE_ZONE_PX of left edge → dir=-1
   *
   *  Speed scales linearly with distance to the edge:
   *    at the edge itself → MAX_SPEED_PX_PER_SEC
   *    at the zone boundary → 0
   */
  computeSpeedAndDir(clientX: number): { dir: 0 | 1 | -1; speed: number } {
    if (!Number.isFinite(clientX)) return { dir: 0, speed: 0 };
    if (!this.contentEl) return { dir: 0, speed: 0 };
    const rect = this.contentEl.getBoundingClientRect();
    // Pointer fully outside horizontally → no scroll (the user is
    // probably over a sibling panel; nothing to drag toward).
    if (clientX < rect.left || clientX > rect.right) {
      return { dir: 0, speed: 0 };
    }
    const distRight = rect.right - clientX;
    if (distRight <= EDGE_ZONE_PX) {
      // distRight in [0, EDGE_ZONE_PX]; t in [0,1].
      const t = Math.max(0, Math.min(1, distRight / EDGE_ZONE_PX));
      // At t=0 (pointer at edge) → speed = MAX; at t=1 (zone boundary) → 0.
      const speed = MAX_SPEED_PX_PER_SEC * (1 - t);
      return { dir: 1, speed };
    }
    const distLeft = clientX - rect.left;
    if (distLeft <= EDGE_ZONE_PX) {
      const t = Math.max(0, Math.min(1, distLeft / EDGE_ZONE_PX));
      const speed = MAX_SPEED_PX_PER_SEC * (1 - t);
      return { dir: -1, speed };
    }
    return { dir: 0, speed: 0 };
  }

  /** rAF tick. Mutates scrollLeft by speed*dt. The consumer's
   *  own pointermove handler reads scrollLeft at the start of each
   *  move() and folds the delta into totalPixelDelta — so the
   *  clip's frame follows the scroll automatically. */
  private tick = (now: number): void => {
    if (this.disposed || !this.contentEl) return;
    const dt = Math.min(0.1, (now - this.lastTs) / 1000);
    this.lastTs = now;
    const { dir, speed } = this.computeSpeedAndDir(this.lastPointerClientX);
    if (dir !== 0 && speed >= MIN_EFFECTIVE_SPEED_PX_PER_SEC) {
      const dx = dir * speed * dt;
      this.contentEl.scrollLeft = Math.max(
        0,
        Math.min(
          this.contentEl.scrollWidth,
          this.contentEl.scrollLeft + dx,
        ),
      );
    }
    this.rafId = requestAnimationFrame(this.tick);
  };

  /** Stop the rAF loop. Idempotent — safe to call multiple times. */
  dispose(): void {
    this.disposed = true;
    if (this.rafId !== null) {
      cancelAnimationFrame(this.rafId);
      this.rafId = null;
    }
    this.contentEl = null;
  }
}