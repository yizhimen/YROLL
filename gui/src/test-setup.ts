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