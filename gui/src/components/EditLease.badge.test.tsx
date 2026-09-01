// GUI-03R6-E: EditLease badge text agrees with canEdit.
//
// The badge text per state:
//   !loaded       → "⏳ 连接中"
//   conflict      → "🔴 冲突 · r<N>"
//   needsLease    → "🟡 编辑权失效 · r<N>"
//   s.mine        → "🟢 我 · r<N>"
//   s.owner agent → "🟡 <agentLabel> · r<N>"
//   observe       → "⚪ 只读 · r<N>"
//   free (canEdit) → "🟢 可编辑 · r<N>"
//   free (!canEdit) → "⭕ 空闲 · r<N>"

import { afterEach, describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import EditLease from "./EditLease";
import { sessionStore } from "../session";

function reset() {
  sessionStore._reset();
}

afterEach(() => reset());

describe("R6-E: EditLease badge text", () => {
  it("shows 连接中 before first /ui/status lands", () => {
    reset();
    render(<EditLease />);
    expect(screen.getByText(/连接中/)).toBeTruthy();
  });

  it("shows 我 · r<N> when mine & alive", () => {
    sessionStore.set({
      sessionId: "sess-1",
      owner: "human",
      mode: "edit",
      mine: true,
      alive: true,
      revision: 7,
      loaded: true,
    });
    render(<EditLease />);
    expect(screen.getByText(/🟢 我 · r7/)).toBeTruthy();
  });

  it("shows 编辑权失效 when gateError is no_session", () => {
    sessionStore.set({
      sessionId: "sess-1",
      owner: "human",
      mode: "edit",
      mine: true,
      alive: true,
      revision: 7,
      loaded: true,
      gateError: "no_session",
      gateMessage: "session not ready",
    });
    render(<EditLease />);
    expect(screen.getByText(/🟡 编辑权失效 · r7/)).toBeTruthy();
  });

  it("shows 只读 when in observe mode", () => {
    sessionStore.set({
      sessionId: "sess-1",
      owner: "observe",
      mode: "observe",
      mine: false,
      alive: true,
      revision: 4,
      loaded: true,
    });
    render(<EditLease />);
    expect(screen.getByText(/⚪ 只读 · r4/)).toBeTruthy();
  });

  it("honors the App's canEdit prop when owner is free", () => {
    sessionStore.set({
      sessionId: null,
      owner: "free",
      mode: null,
      mine: false,
      alive: false,
      revision: 0,
      loaded: true,
    });
    const { rerender } = render(<EditLease canEdit={false} />);
    expect(screen.getByText(/⭕ 空闲 · r0/)).toBeTruthy();
    rerender(<EditLease canEdit={true} />);
    expect(screen.getByText(/🟢 可编辑 · r0/)).toBeTruthy();
  });
});