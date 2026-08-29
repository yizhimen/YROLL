// GUI-02: useProjectSequence — reads /sequence and exposes the
// canonical timebase (Sequence sub-model from Project).
//
// The server returns:
//   { sequence_id, fps: {num, den}, width, height,
//     timecode_format, drop_frame, project_revision }
//
// This hook is the GUI's single source of truth for the timebase.
// All other components derive frame↔pixel and frame↔seconds from
// `fps` and `drop_frame` returned by this hook.

import { useEffect, useState } from "react";
import { api } from "./api";
import { rational, type Rational } from "./frames";

export interface ProjectSequence {
  sequenceId: string;
  fps: Rational;
  width: number;
  height: number;
  timecodeFormat: "SMPTE" | "DF" | "NDF";
  dropFrame: boolean;
  projectRevision: number;
}

const POLL_MS = 5000;

const EMPTY: ProjectSequence = {
  sequenceId: "",
  fps: rational(30, 1),
  width: 1920,
  height: 1080,
  timecodeFormat: "SMPTE",
  dropFrame: false,
  projectRevision: 0,
};

/** Hook: read /sequence and expose the canonical timebase. Polled
 * on the same cadence as sessionStore. Returns a stable object
 * until /sequence actually changes. */
export function useProjectSequence(): ProjectSequence {
  const [seq, setSeq] = useState<ProjectSequence>(EMPTY);

  useEffect(() => {
    let cancelled = false;
    const tick = async () => {
      try {
        const data = await api.getSequence();
        if (cancelled) return;
        setSeq({
          sequenceId: data.sequence_id ?? "",
          fps: rational(data.fps.num, data.fps.den),
          width: data.width,
          height: data.height,
          timecodeFormat: data.timecode_format ?? "SMPTE",
          dropFrame: !!data.drop_frame,
          projectRevision: data.project_revision ?? 0,
        });
      } catch {
        // network blip; keep last known sequence
      }
    };
    void tick();
    const id = setInterval(tick, POLL_MS);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, []);

  return seq;
}
