// GUI-02: FrameInspector — development-only panel (visible with ?dev=1).
//
// Shows the canonical frame-domain state of the playhead and the
// selected clip: timecode via framesToTimecode (Core conformance), FPS,
// duration in frames, and the current zoom in both perceived-pxPerSec
// and derived pxPerFrame. The point: the dev can verify "is what I
// see on screen actually what Core has?".

import { useProjectSequence } from "../sequence";
import { framesToTimecode, pxPerFrame, type Rational } from "../frames";

interface Props {
  playheadFrame: number;
  selectedClip?: {
    source_start_frame: number;
    source_end_frame: number;
    timeline_start_frame: number;
    duration_frames: number;
    speed: number;
  } | null;
  pxPerSec: number;
}

export function FrameInspector({ playheadFrame, selectedClip, pxPerSec }: Props) {
  const seq = useProjectSequence();
  const pxPerF = pxPerFrame(pxPerSec, seq.fps);
  return (
    <div className="frame-inspector" style={{
      padding: 8, background: "#181818", color: "#ddd", fontSize: 11,
      borderTop: "1px solid #333", fontFamily: "monospace",
    }}>
      <div><b>Frame Inspector</b> (GUI-02 dev panel, ?dev=1)</div>
      <hr style={{ borderColor: "#333" }} />
      <Row label="playhead (frame)">{playheadFrame}</Row>
      <Row label="playhead (timecode)">{framesToTimecode(playheadFrame, seq.fps, seq.dropFrame)}</Row>
      <Row label="fps">{`${seq.fps.num}/${seq.fps.den}`}</Row>
      <Row label="timecode_format">{seq.timecodeFormat}{seq.dropFrame ? " (DF)" : ""}</Row>
      <Row label="pxPerSec (perceived)">{pxPerSec.toFixed(2)}</Row>
      <Row label="pxPerFrame (derived)">{pxPerF.toFixed(4)}</Row>
      {selectedClip && (
        <>
          <hr style={{ borderColor: "#333" }} />
          <Row label="clip.timeline_start_frame">{selectedClip.timeline_start_frame}</Row>
          <Row label="clip.source_start_frame">{selectedClip.source_start_frame}</Row>
          <Row label="clip.source_end_frame">{selectedClip.source_end_frame}</Row>
          <Row label="clip.duration_frames">{selectedClip.duration_frames}</Row>
          <Row label="clip.speed">{selectedClip.speed}</Row>
          <Row label="clip.timeline (timecode)">
            {framesToTimecode(selectedClip.timeline_start_frame, seq.fps, seq.dropFrame)}
            {" → "}
            {framesToTimecode(
              selectedClip.timeline_start_frame + selectedClip.duration_frames,
              seq.fps, seq.dropFrame)}
          </Row>
        </>
      )}
    </div>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div style={{ display: "flex", gap: 8 }}>
      <span style={{ color: "#888", minWidth: 220 }}>{label}</span>
      <span>{children}</span>
    </div>
  );
}
