// GUI-02.4: jsdom does not ship PointerEvent or document.elementsFromPoint.
// Minimal polyfills for the drag tests in ClipBlock.test.tsx — only
// the fields ClipBlock reads are implemented.
if (typeof globalThis.PointerEvent === "undefined") {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  (globalThis as any).PointerEvent = class PointerEvent extends MouseEvent {
    public readonly pointerId: number;
    constructor(type: string, init: PointerEventInit = {}) {
      super(type, init);
      this.pointerId = init.pointerId ?? 0;
    }
  };
}

// jsdom doesn't implement elementsFromPoint — ClipBlock uses it on
// pointerup to detect track drops. Stub to an empty array so the
// drag-end logic doesn't throw in tests.
if (typeof document.elementsFromPoint !== "function") {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  (document as any).elementsFromPoint = () => [];
}

// GUI-03R4.1: jsdom doesn't implement requestAnimationFrame —
// DragAutoScroll's rAF loop would throw on construction. Stub to
// a no-op + clear-handle pair so DragAutoScroll.dispose() works
// in tests without burning real frames.
if (typeof globalThis.requestAnimationFrame === "undefined") {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  (globalThis as any).requestAnimationFrame = (_cb: FrameRequestCallback): number => 0;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  (globalThis as any).cancelAnimationFrame = (_id: number): void => {};
}