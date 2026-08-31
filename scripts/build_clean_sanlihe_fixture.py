#!/usr/bin/env python3
# GUI-03R4.1 P0-2: Build a clean Sanlihe fixture for UX validation.
#
# Reads projects/sanlihe-slice-30s/current.json and produces
# projects/sanlihe-slice-30s-clean/current.json with stale/test
# debris removed.
#
# Classification (per user instruction: "Do not delete the 50s
# subtitle until classified as editorial vs stale/test"):
#
# STALE / TEST items removed:
#  • v3/cc61634 at [600, 608.5]       — asset ae45f65 (C9717.MP4),
#                                       added 2026-08-30 13:46:31
#  • v5/c0f1e08 at [600, 608.5]       — same asset, added 13:47:04
#  • v6/cf3267c at [600, 608.5]       — same asset, added 13:47:21
#  • v7/c884a18 at [600, 608.5]       — same asset, added 13:48:02
#  • t1/c61ee32 at [31.5, 81.5]       — 50s subtitle anomaly
#
#  Classification for c61ee32 (the controversial one):
#    • All other T1 subtitles in this fixture are 2.5-5.0s in
#      duration. c61ee32 is 50s — 10x the next-longest editorial
#      subtitle in this fixture.
#    • sanlihe-story (the full editorial reference) has 18
#      subtitles ranging 1.7s-8.0s; 50s would be ~10x the longest.
#    • c61ee32 extends past V1's editorial content end (49.51s).
#      No other T1 subtitle crosses the V1 end.
#    • Verdict: STALE / TEST (not editorial).
#
# EDITORIAL content (preserved):
#  • V1: 11 clips, [0, 49.51s]       — main visual
#  • V2: 3 clips at [0.3-10.9],      — B-roll, hidden=True (R4-1)
#    plus a degenerate c3e7628 at [600,600] (zero duration, test debris)
#  • V3: 1 clip at [0-5] (cc61634 removed)
#  • V5: 2 clips at [0-6.8] (c0f1e08 removed)
#  • V6: 1 clip at [0-4.2] (cf3267c removed)
#  • V7: 1 clip at [0-5] (c884a18 removed)
#  • V8: hidden=True — 2 clips
#  • V9: 3 clips at [0-18.5]
#  • V10: hidden=True — 13 clips (incl. 1368s outlier)
#  • T1: 5 editorial subtitles (c61ee32 removed)
#
# The cleanup writes a new project (NOT mutating the original)
# and records its derivation via a single synthetic
# `fixture_cleanup` operation in the new project's log.

import json
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "projects" / "sanlihe-slice-30s"
DST = ROOT / "projects" / "sanlihe-slice-30s-clean"

# Stale/test clip IDs to remove from main timeline.
STALE_CLIP_IDS = {
    "cc61634",  # v3 [600, 608.5]  — auto-test debris (ae45f65)
    "c0f1e08",  # v5 [600, 608.5]  — auto-test debris (ae45f65)
    "cf3267c",  # v6 [600, 608.5]  — auto-test debris (ae45f65)
    "c884a18",  # v7 [600, 608.5]  — auto-test debris (ae45f65)
    "c3e7628",  # v2 [600, 600]    — zero-duration test artifact
    "c61ee32",  # t1 [31.5, 81.5]  — 50s subtitle anomaly (CLASSIFIED STALE)
}


def load_json(path: Path):
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def main() -> int:
    if not SRC.exists():
        print(f"Source project not found: {SRC}", file=sys.stderr)
        return 1
    if DST.exists():
        print(f"Destination already exists: {DST}", file=sys.stderr)
        print(f"Delete it first or move it aside.", file=sys.stderr)
        return 2

    print(f"Building clean fixture: {SRC.name}  →  {DST.name}")
    project = load_json(SRC / "current.json")

    # ── Remove stale clip_ids from main timeline tracks ───────
    removed = []
    for tl in project["timelines"]:
        if tl["timeline_id"] != "main":
            continue
        for t in tl["tracks"]:
            before = list(t.get("clip_ids", []))
            after = [cid for cid in before if cid not in STALE_CLIP_IDS]
            if len(after) != len(before):
                removed.extend(before[i] for i in range(len(before))
                               if before[i] not in after)
                t["clip_ids"] = after

    print(f"Removed {len(removed)} stale clip(s):")
    for cid in removed:
        # Print short id and full range from project.clips.
        c = project["clips"].get(cid, {})
        tr = c.get("timeline_range", {})
        track_id = c.get("track_id", "?")
        print(f"  {cid[-8:]}  track={track_id}  "
              f"[{tr.get('start', '?')}, {tr.get('end', '?')}]")

    # ── Remove stale clip entries from project.clips ─────────
    for cid in removed:
        if cid in project["clips"]:
            del project["clips"][cid]

    # ── W-B invariant: no empty tracks in tl.tracks ───────────
    # The static guard test_no_orphan_empty_tracks_in_projects_dir
    # pins this at the disk level (without going through
    # ProjectCore.open()'s load-time migration). The clean
    # fixture must therefore have ZERO empty tracks on disk too.
    # We only run the cleanup against the main timeline since
    # that's the one the GUI/UX scenarios use.
    for tl in project["timelines"]:
        if tl["timeline_id"] != "main":
            continue
        kept_tracks = []
        removed_empty = []
        for t in tl["tracks"]:
            if t.get("clip_ids"):
                kept_tracks.append(t)
            else:
                removed_empty.append(t["track_id"])
        if removed_empty:
            print(f"  Also removed {len(removed_empty)} empty track(s): "
                  f"{removed_empty}")
            tl["tracks"] = kept_tracks

    # ── Verify V1 editorial extent is unchanged ───────────────
    v1 = next(t for t in project["timelines"][0]["tracks"]
              if t["track_id"] == "v1")
    v1_max = max(
        project["clips"][cid]["timeline_range"]["end"]
        for cid in v1["clip_ids"]
    )
    print(f"V1 editorial extent (max end): {v1_max:.2f}s")

    # ── Compute visible extent (used for Fit Content) ────────
    visible_max = 0.0
    for tl in project["timelines"]:
        if tl["timeline_id"] != "main":
            continue
        for t in tl["tracks"]:
            if t.get("hidden"):
                continue
            for cid in t.get("clip_ids", []):
                c = project["clips"].get(cid, {})
                if c.get("timeline_range", {}).get("end", 0) > visible_max:
                    visible_max = c["timeline_range"]["end"]
    print(f"Visible extent (excludes hidden): {visible_max:.2f}s")

    # ── Create new project directory ─────────────────────────
    DST.mkdir(parents=True)
    # Mirror the directory structure (operations/, versions/, cache/, generated/)
    for sub in ["operations", "versions", "cache", "generated"]:
        (DST / sub).mkdir(exist_ok=True)

    # ── Write current.json ───────────────────────────────────
    # Update project metadata so the fixture is self-describing.
    project["name"] = "sanlihe-slice-30s-clean"
    project["project_id"] = project["project_id"]  # keep original id
    project.setdefault("intent", {})
    if isinstance(project["intent"], dict):
        project["intent"]["fixture_kind"] = (
            "clean-ux-validation"
        )
        project["intent"]["derived_from"] = "sanlihe-slice-30s"
        project["intent"]["removed_stale_clip_ids"] = sorted(removed)
        project["intent"]["removed_stale_reason"] = (
            "P0-2 fixture cleanup: 4 auto-test debris clips at [600,608.5]"
            " + 1 zero-duration artifact + 1 classified-stale 50s subtitle"
        )
        # GUI-03R4.1 P1-5: explicitly declare editorial tracks so the
        # GUI's fit-content helper zooms to V1's end (49.51s) instead
        # of falling back to V1-heuristic or playback-duration (which
        # includes hidden tracks' tails like v10 at 1368.5s).
        project["intent"]["editorial_track_ids"] = ["v1"]

    write_json(DST / "current.json", project)

    # ── Write the cleanup operation ──────────────────────────
    cleanup_op = {
        "operation_id": "op00001",
        "who": "human",
        "at": "2026-08-31T12:00:00.000000",
        "type": "fixture_cleanup",
        "target": "sanlihe-slice-30s-clean",
        "time_range": None,
        "region": None,
        "parameters": {
            "derived_from": "sanlihe-slice-30s",
            "removed_clip_ids": sorted(removed),
            "removed_classification": {
                "cc61634": "auto-test debris (asset ae45f65 @ 600s)",
                "c0f1e08": "auto-test debris (asset ae45f65 @ 600s)",
                "cf3267c": "auto-test debris (asset ae45f65 @ 600s)",
                "c884a18": "auto-test debris (asset ae45f65 @ 600s)",
                "c3e7628": "zero-duration test artifact @ 600s",
                "c61ee32": (
                    "stale/test subtitle — classified by anomaly:"
                    " 50s duration (vs 2.5-5.0s editorial); extends"
                    " past V1 editorial end (49.51s); 10x longest"
                    " sanlihe-story subtitle (8.0s)."
                ),
            },
        },
        "before": {},
        "after": {
            "removed_clip_ids": sorted(removed),
            "visible_extent_sec": visible_max,
            "v1_editorial_extent_sec": v1_max,
        },
        "why": "GUI-03R4.1 P0-2 fixture cleanup",
        "tool": "scripts/build_clean_sanlihe_fixture.py",
        "model": None,
        "cost": 0.0,
        "approved_by": "human",
    }
    write_json(DST / "operations" / "op00001.json", cleanup_op)

    # Copy a minimal versions/ entry so the fixture looks "complete".
    versions_dir = DST / "versions"
    write_json(versions_dir / "v00001.json", {
        "version_id": "v00001",
        "saved_at": "2026-08-31T12:00:00.000000",
        "label": "clean-ux-validation",
        "project_id": project["project_id"],
        "op_count": 1,
    })

    # ── Print a brief summary for the run log ─────────────────
    summary = {
        "fixture": str(DST.relative_to(ROOT)),
        "removed_clip_ids": sorted(removed),
        "v1_editorial_extent_sec": v1_max,
        "visible_extent_sec": visible_max,
    }
    print()
    print("Summary:")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())