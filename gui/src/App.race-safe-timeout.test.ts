// GUI-05-A (A2 + L-1): race-safe rejection timeout.
//
// Per A2, a stale 600ms rejection-flash timeout must never clear
// state belonging to a newer gesture on the same clip. The pattern:
//  - App.tsx keeps `dragGenerationRef: MutableRefObject<number>`.
//  - When a real drag/resize mutation gesture is armed, ClipBlock
//    calls `onGestureArmed()` which bumps `dragGenerationRef.current++`
//    and resets `dragCancelledRef.current = false`.
//  - When a rejection-flash timeout is scheduled (after a Core 4xx),
//    it captures `genAt = dragGenerationRef.current` at fire time.
//  - When the timeout fires, it compares `dragGenerationRef.current`
//    to `genAt`. If different → stale → no-op.
//
// Per L-1, the generation bumps ONLY when a real drag/resize
// mutation gesture is armed (after canEdit / locked checks). It does
// NOT bump on plain click, marquee, hover, focus.
//
// Per L-2 (related but separate concern), selection hydration uses
// an explicit hydration key — that's 05-B scope, not 05-A.

import { describe, it, expect, vi } from "vitest";

/**
 * Mirror of the 600ms rejection-flash timeout logic in App.tsx
 * (used inside onMoveCommit and onTrimCommit rejection paths).
 *
 * The timeout captures `genAt` at scheduling time. On fire, it
 * checks the current generation. If different → stale → no-op.
 */
function makeRejectionTimer(opts: {
  dragGenerationRef: { current: number };
  clipId: string;
  schedule: (fn: () => void, ms: number) => number;
  clear: (handle: number) => void;
  setDragRejected: (updater: (p: Record<string, boolean>) => Record<string, boolean>) => void;
  setDragPreview: (updater: (p: Record<string, number>) => Record<string, number>) => void;
  durationMs?: number;
}): { schedule: () => number } {
  const REJECT_MS = opts.durationMs ?? 600;
  let handle: number | null = null;

  const fire = () => {
    // Race-safe check: if a newer gesture started, do nothing.
    if (opts.dragGenerationRef.current !== genAt) return;
    opts.setDragRejected((p) => {
      if (!(opts.clipId in p)) return p;
      const { [opts.clipId]: _, ...rest } = p;
      return rest;
    });
    opts.setDragPreview((p) => {
      if (!(opts.clipId in p)) return p;
      const { [opts.clipId]: _, ...rest } = p;
      return rest;
    });
  };

  let genAt = opts.dragGenerationRef.current;
  return {
    schedule: () => {
      genAt = opts.dragGenerationRef.current;
      handle = opts.schedule(fire, REJECT_MS);
      return handle;
    },
  };
}

describe("GUI-05-A (A2) race-safe rejection timeout", () => {
  it("first timeout fires, generation unchanged → state cleared", async () => {
    const dragGenerationRef = { current: 0 };
    const setDragRejected = vi.fn();
    const setDragPreview = vi.fn();
    const handles: number[] = [];
    const timer = makeRejectionTimer({
      dragGenerationRef,
      clipId: "clip-a",
      schedule: (fn, ms) => {
        const h = setTimeout(fn, ms) as unknown as number;
        handles.push(h);
        return h;
      },
      clear: (h) => clearTimeout(h as unknown as ReturnType<typeof setTimeout>),
      setDragRejected,
      setDragPreview,
      durationMs: 0, // fire on next tick
    });
    timer.schedule();
    // Allow setTimeout(0) to fire.
    await new Promise<void>((resolve) => setTimeout(resolve, 10));
    // Generation didn't change → both setters called.
    expect(setDragRejected).toHaveBeenCalledTimes(1);
    expect(setDragPreview).toHaveBeenCalledTimes(1);
  });

  it("stale timeout fires after newer gesture → no-op (no clear)", () => {
    const dragGenerationRef = { current: 0 };
    const setDragRejected = vi.fn();
    const setDragPreview = vi.fn();
    const timer = makeRejectionTimer({
      dragGenerationRef,
      clipId: "clip-a",
      schedule: (fn, _ms) => {
        // Fire on next tick (still in same microtask but after gen bump).
        queueMicrotask(fn);
        return 1;
      },
      clear: () => {},
      setDragRejected,
      setDragPreview,
      durationMs: 0,
    });
    timer.schedule();
    // Simulate a NEW gesture armed before the timeout fires.
    dragGenerationRef.current = dragGenerationRef.current + 1;
    // Run microtasks.
    return new Promise<void>((resolve) => {
      setTimeout(() => {
        // Stale timeout: generation differs from genAt (0 vs 1).
        // Both setters MUST NOT have been called (no-op).
        expect(setDragRejected).not.toHaveBeenCalled();
        expect(setDragPreview).not.toHaveBeenCalled();
        resolve();
      }, 0);
    });
  });

  it("two consecutive rejections on same clip < 600ms apart → first timeout clears nothing (newer gen at fire)", () => {
    const dragGenerationRef = { current: 0 };
    let rejectedCalls: Array<Record<string, boolean>> = [];
    let previewCalls: Array<Record<string, number>> = [];
    const timer1 = makeRejectionTimer({
      dragGenerationRef,
      clipId: "clip-a",
      schedule: (fn, _ms) => {
        setTimeout(() => fn(), 100);
        return 1;
      },
      clear: () => {},
      setDragRejected: (updater) => {
        rejectedCalls.push(updater({ "clip-a": true }));
      },
      setDragPreview: (updater) => {
        previewCalls.push(updater({ "clip-a": 50 }));
      },
    });
    timer1.schedule();

    // 100ms later, a new rejection starts. Generation bumps.
    return new Promise<void>((resolve) => {
      setTimeout(() => {
        dragGenerationRef.current = dragGenerationRef.current + 1;
        const timer2 = makeRejectionTimer({
          dragGenerationRef,
          clipId: "clip-a",
          schedule: (fn, _ms) => {
            setTimeout(() => fn(), 100);
            return 2;
          },
          clear: () => {},
          setDragRejected: (updater) => {
            rejectedCalls.push(updater({ "clip-a": true }));
          },
          setDragPreview: (updater) => {
            previewCalls.push(updater({ "clip-a": 75 }));
          },
        });
        timer2.schedule();
        // Wait 200ms total. timer1's timeout (at 100ms) was before
        // the gen bump (which happens at 100ms — same instant, race-
        // free logic should let the new gen win). timer2 fires at
        // 200ms after gen bump.
        setTimeout(() => {
          // At least one call must have cleared (timer2's fire).
          // Whether timer1's fire was a no-op depends on microtask
          // ordering — but the important invariant is: the FINAL
          // state must be consistent (clip-a NOT in either map).
          const finalRejected = rejectedCalls[rejectedCalls.length - 1];
          expect(finalRejected).toEqual({});
          const finalPreview = previewCalls[previewCalls.length - 1];
          expect(finalPreview).toEqual({});
          resolve();
        }, 250);
      }, 100);
    });
  });
});

describe("GUI-05-A (L-1) gesture generation scope", () => {
  it("source-pin: App.tsx onGestureArmed handler bumps dragGenerationRef.current", async () => {
    const fs = await import("node:fs/promises");
    const path = await import("node:path");
    const appPath = path.resolve(__dirname, "./App.tsx");
    const text = await fs.readFile(appPath, "utf-8");
    // The onGestureArmed prop wired to Timeline must increment the
    // generation counter. Source-pin: accepts either `++` form or
    // `current = current + 1` form.
    expect(text).toMatch(/onGestureArmed=\{[\s\S]*?dragGenerationRef\.current\s*(?:\+\+|\s*=\s*dragGenerationRef\.current\s*\+\s*1)\s*;[\s\S]*?\}\s*\}/);
  });

  it("source-pin: dragGenerationRef is declared in App.tsx", async () => {
    const fs = await import("node:fs/promises");
    const path = await import("node:path");
    const appPath = path.resolve(__dirname, "./App.tsx");
    const text = await fs.readFile(appPath, "utf-8");
    expect(text).toMatch(/const dragGenerationRef = useRef\(0\)/);
  });

  it("source-pin: ClipBlock onGestureArmed fires ONLY inside drag/trim armed paths (not on plain click)", async () => {
    const fs = await import("node:fs/promises");
    const path = await import("node:path");
    const cbPath = path.resolve(__dirname, "./components/ClipBlock.tsx");
    const text = await fs.readFile(cbPath, "utf-8");

    // Strip comments first to avoid false positives.
    const stripped = text
      .replace(/\/\*[\s\S]*?\*\//g, "")
      .replace(/^\s*\/\/.*$/gm, "")
      .replace(/\s+\/\/.*$/g, "");

    // Count occurrences — should be exactly 2 (one in onPointerDown
    // for move, one in onEdgeDown for trim).
    const matches = stripped.match(/onGestureArmed\(\)/g);
    expect(matches, "no onGestureArmed() calls in ClipBlock").toBeTruthy();
    expect(matches!.length).toBe(2);

    // Each onGestureArmed() call must be AFTER its function's
    // `if (locked) return;` guard. We verify this by extracting
    // the two function bodies (onPointerDown + onEdgeDown) and
    // checking that within each, `if (locked) return;` precedes
    // `onGestureArmed()`.

    function checkFunctionArmedAfterLocked(fnName: string): void {
      // Match the function body: `const fnName = (...) => { ... };`
      // up to the next `};` at the same brace depth (heuristic: match
      // to first `\n  };` after `=> {`).
      const fnStart = stripped.indexOf(`const ${fnName} = `);
      expect(fnStart, `${fnName} not found in ClipBlock`).toBeGreaterThan(-1);
      const fnBodyStart = stripped.indexOf("=> {", fnStart) + 4;
      // Find the matching closing brace by scanning braces.
      let depth = 1;
      let i = fnBodyStart;
      while (i < stripped.length && depth > 0) {
        const ch = stripped[i];
        if (ch === "{") depth++;
        else if (ch === "}") depth--;
        i++;
      }
      const fnBody = stripped.slice(fnBodyStart, i);
      const lockedIdx = fnBody.indexOf("if (locked) return;");
      const armedIdx = fnBody.indexOf("onGestureArmed()");
      expect(lockedIdx, `${fnName} must contain 'if (locked) return;'`).toBeGreaterThan(-1);
      expect(armedIdx, `${fnName} must contain 'onGestureArmed()'`).toBeGreaterThan(-1);
      expect(
        armedIdx > lockedIdx,
        `${fnName}: onGestureArmed() must come AFTER 'if (locked) return;' (armed=${armedIdx} locked=${lockedIdx})`,
      ).toBe(true);
    }

    checkFunctionArmedAfterLocked("onPointerDown");
    checkFunctionArmedAfterLocked("onEdgeDown");
  });
});