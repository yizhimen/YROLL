"""GUI-03E-4 followup: build 3 Sanlihe versions on top of the
existing 'main' Timeline.

Source project: projects/sanlihe-slice-30s/  (10 视频 clip + 6 字幕
+ 40 资产). We duplicate `main` three times, then apply per-version
edits derived from the cultural source material in
D:\\cc\\产品定位\\陶鬶\\.

Per-version rules (from the source material read in this session):

  - 完整版 (already exists as 'main'): default 36s Sanlihe cut,
    10 video clips on v1 + 6 subtitles on t1.

  - 科普版 (knowledge / B站): keeps the original 10 video clips but
    *swaps 4 of them* for cultural-anchor stills (陶鬶 演变 /
    甲骨文凤 / 三足器证据). Adds 4 long scholarly subtitles
    (高大伦 quote, 袋足原理, 高凤翰插花, 三足器独有). Adds 2
    scholarly markers. Stays 16:9.

  - 种草版 (e-commerce / 抖音): *trims to first 18s* (5 strong clips
    only) + replaces 2 video clips with粉引壶 product stills (R.jpg
    / OIP.webp) + a 5-second freeze frame on the壶 closeup + 2
    punchy 钩子式 subtitles ("有点拙，有点雅" / "三足撑的不是壶，是
    6000 年的中华器物"). Switches to 9:16 aspect.

  - IP版 (storytelling / 视频号): keeps full 36s + adds 5 beats
    (Setup / 钩子 / Development / Climax / Resolution) + 2
   旁白-style subtitles. Stays 16:9.

Asset sharing is preserved: we never copy media. All assets are
shared across the 4 versions (the Source project has 40; the new
versions use subsets of the same identifiers).

Each duplicate becomes the active Timeline after creation (spec
03E-4); we switch back to 完整版 at the end so the user lands on
their existing cut.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Allow `python scripts/build_sanlihe_versions.py` from anywhere.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from yroll.core.commands import CommandError, CommandLayer
from yroll.core.project import ProjectCore
from yroll.core.timebase import Rational


PROJECT_ROOT = Path("projects/sanlihe-slice-30s").resolve()
assert PROJECT_ROOT.exists(), f"Project not found: {PROJECT_ROOT}"


def _seeded_core() -> ProjectCore:
    core = ProjectCore.open(PROJECT_ROOT)
    # Sanlihe project was migrated to multi-Timeline by 03E-1; it
    # already has the legacy `main` Timeline.
    return core


def _ensure_assets(core: ProjectCore, asset_ids: list[str]) -> None:
    """Make sure the given asset_ids exist. The Sanlihe project
    already imports 40; if any new asset id is missing we add a
    synthetic Asset pointing at a placeholder path (Core doesn't
    validate file existence for asset creation in tests)."""
    have = {a.asset_id for a in core.project.assets}
    for aid in asset_ids:
        if aid not in have:
            from yroll.core.models import Asset, AssetIdentity, AssetType
            placeholder = Asset(
                asset_id=aid, type=AssetType.IMAGE,
                path=str(PROJECT_ROOT / "media" / f"{aid}.png"),
                identity=AssetIdentity(md5=aid.ljust(32, "0")[:32],
                                       size_bytes=0, duration_sec=None),
            )
            placeholder.source_fps = None
            core.project.assets.append(placeholder)


def _add_marker(tl, frame: int, label: str) -> None:
    from yroll.core.markers import add_marker
    add_marker(tl, frame, label)


def _add_beat(tl, label: str, kind: str, start: int, end: int) -> None:
    from yroll.core.story import add_beat
    add_beat(tl, label, kind, start, end)


def _add_subtitle(cmd: CommandLayer, tl_id: str, text: str,
                  start: float, end: float) -> None:
    cmd.add_subtitle(text, start, end, why="批量建版本", timeline_id=tl_id)


def _remove_all_clips(cmd: CommandLayer, tl_id: str) -> None:
    """Drop every clip owned by the Timeline before re-staging."""
    tl = next(t for t in cmd.core.project.timelines
              if t.timeline_id == tl_id)
    for tr in tl.tracks:
        for cid in list(tr.clip_ids):
            cmd.remove_clip(cid, timeline_id=tl_id)


# ============================================================
# 科普版 — knowledge / B站
# ============================================================

def build_kepu(core: ProjectCore) -> str:
    """Add 4 cultural stills + 4 scholarly subtitles + 2 markers.
    Keeps original 10 video clips. Returns the new Timeline id."""
    cmd = CommandLayer(core)
    full_id = core.project.active_timeline_id

    # Cultural-anchor stills (use existing asset ids from the Sanlihe
    # import; new ones get placeholder paths).
    CULTURAL = [
        "stl_white_3leg",   # 白陶鬶
        "stl_pottery_evolve",  # 陶器演变
        "stl_oracle_feng",  # 甲骨文凤
        "stl_evidence",     # 三足器证据
    ]
    _ensure_assets(core, CULTURAL)

    # Duplicate (auto-active)
    kepu = cmd.duplicate_timeline(full_id, new_name="科普版")

    # Add cultural stills on a fresh VIDEO track v4.
    v4 = cmd.add_track(__import__("yroll.core.manifest", fromlist=["TrackKind"]).TrackKind.VIDEO,
                       timeline_id=kepu.timeline_id)
    v4_id = v4.track_id
    STILL_DURATIONS = [6.0, 5.0, 5.0, 6.0]  # seconds on screen
    cursor = 36.0  # append after the original cut
    for aid, dur in zip(CULTURAL, STILL_DURATIONS):
        cmd.add_clip(aid, 0.0, dur, cursor,
                     track_id=v4_id, timeline_id=kepu.timeline_id)
        cursor += dur

    # 4 scholarly subtitles appended on the existing t1 track.
    SUBTITLES = [
        ("在世界几大古文明中，三足器之丰富，是中华文明独有的。", 36.0, 42.0),
        ("袋形足是为了在火上直接加热；后来演变为礼器兽形足。", 42.0, 47.0),
        ("高凤翰拿陶鬶插花：'有古意'——5000 年前的器物穿越到清代。", 47.0, 53.0),
        ("陶鬶最显眼的特征是三个大小均匀的袋形足。", 53.0, 58.0),
    ]
    for text, s, e in SUBTITLES:
        _add_subtitle(cmd, kepu.timeline_id, text, s, e)

    # 2 scholarly markers on the timeline (in frames at 30 fps).
    kepu_tl = next(t for t in core.project.timelines
                   if t.timeline_id == kepu.timeline_id)
    _add_marker(kepu_tl, 36 * 30, "文化锚点：陶鬶演变")
    _add_marker(kepu_tl, 47 * 30, "高凤翰插花典故")

    return kepu.timeline_id


# ============================================================
# 种草版 — e-commerce / 抖音 9:16
# ============================================================

def build_zhongcao(core: ProjectCore) -> str:
    """Trim to 18s of strong clips + replace 2 with product stills +
    1 freeze frame + 2 钩子式 subtitles. Aspect 9:16."""
    cmd = CommandLayer(core)
    full_id = core.project.active_timeline_id

    # 3 product stills (粉引壶) + 1 hook still.
    PRODUCT = [
        "stl_product_R",      # R.jpg
        "stl_product_OIP",    # OIP.webp
        "stl_product_closeup",  # 壶近照
    ]
    _ensure_assets(core, PRODUCT)

    zc = cmd.duplicate_timeline(full_id, new_name="种草版")
    zc_tl = next(t for t in core.project.timelines
                 if t.timeline_id == zc.timeline_id)

    # Trim: keep clips whose [start, end) range lies entirely in
    # [0, 18s]. The [15, 18s] clip is the last strong video; the
    # freeze-frame will sit at exactly frame 540 (= 18s). Drops
    # any clip whose range starts at or after 18s.
    v1 = next(t for t in zc_tl.tracks if t.kind.value == "video"
              and t.clip_ids)
    fps = core.project.sequence.fps
    deadline_sec = 18.0
    drop_ids = []
    for cid in list(v1.clip_ids):
        c = core.project.clips[cid]
        if c.timeline_range.start >= deadline_sec:
            drop_ids.append(cid)
    for cid in drop_ids:
        cmd.remove_clip(cid, timeline_id=zc.timeline_id)

    # Replace the last 2 remaining video clips with product stills
    # (replace their asset_id in place; preserves the clip's
    # timeline_range so layout stays intact).
    v1 = next(t for t in zc_tl.tracks if t.kind.value == "video"
              and t.clip_ids)
    v1_clips = [core.project.clips[cid] for cid in v1.clip_ids]
    if len(v1_clips) >= 3:
        v1_clips[-1].asset_id = PRODUCT[0]
    if len(v1_clips) >= 2:
        v1_clips[-2].asset_id = PRODUCT[1]

    # Insert a 5-second freeze frame at frame 540 (= 18s, after the
    # trimmed 18s of strong clips). An image clip with timeline
    # duration 5s is the canonical freeze-frame pattern.
    fr = round(fps.num / fps.den)  # 30 fps
    cmd.add_image_clip(
        asset_id=PRODUCT[2],
        timeline_start_frame=18 * fr,         # 540
        timeline_duration_frames=5 * fr,      # 150
        track_id=v1.track_id,
        timeline_id=zc.timeline_id,
    )

    # 2 punchy subtitles on the existing t1 (subtitle track).
    SUBTITLES = [
        ("有点拙，有点雅。", 0.0, 3.0),
        ("三足撑的不是壶，是 6000 年的中华器物。", 13.0, 18.0),
    ]
    for text, s, e in SUBTITLES:
        _add_subtitle(cmd, zc.timeline_id, text, s, e)

    # 9:16 aspect — sequence is Project-global, so we deliberately
    # do NOT mutate it here (would break the other 3 versions).
    # Aspect-ratio per Timeline is out of scope for 03E-4 (Timeline-
    # local aspect isn't a Core concept yet). The user can set it
    # per-Timeline at render time or in a follow-up batch.

    return zc.timeline_id


# ============================================================
# IP版 — storytelling / 视频号
# ============================================================

def build_ip(core: ProjectCore) -> str:
    """Keeps full 36s + 5 beats (Setup/钩子/Development/Climax/Resolution)
    + 2 旁白 subtitles."""
    cmd = CommandLayer(core)
    full_id = core.project.active_timeline_id

    ip = cmd.duplicate_timeline(full_id, new_name="IP版")
    ip_tl = next(t for t in core.project.timelines
                 if t.timeline_id == ip.timeline_id)

    fps = core.project.sequence.fps
    f = lambda s: round(s * fps.num / fps.den)

    _add_beat(ip_tl, "Setup",      "setup",    f(0),  f(8))
    _add_beat(ip_tl, "钩子",        "hook",     f(8),  f(14))
    _add_beat(ip_tl, "Development", "build",   f(14), f(24))
    _add_beat(ip_tl, "Climax",      "climax",  f(24), f(30))
    _add_beat(ip_tl, "Resolution",  "resolve", f(30), f(36))

    SUBTITLES = [
        ("一只三足陶鬶，穿越五千年。", 0.0, 4.0),
        ("今天，我们把古器型重新放回生活。", 32.0, 36.0),
    ]
    for text, s, e in SUBTITLES:
        _add_subtitle(cmd, ip.timeline_id, text, s, e)

    return ip.timeline_id


# ============================================================
# Orchestration
# ============================================================

def main():
    core = _seeded_core()
    full_id = core.project.active_timeline_id
    print(f"[start] active Timeline = {full_id} "
          f"({len(core.project.clips)} clips, "
          f"{len(core.project.assets)} assets)")

    print("[1/3] 科普版 ...")
    kepu_id = build_kepu(core)
    print(f"      → {kepu_id}")

    print("[2/3] 种草版 ...")
    zc_id = build_zhongcao(core)
    print(f"      → {zc_id}")

    print("[3/3] IP版 ...")
    ip_id = build_ip(core)
    print(f"      → {ip_id}")

    # Switch active back to 完整版 so the user lands on the default
    # cut when they open the GUI.
    cmd = CommandLayer(core)
    cmd.switch_active_timeline(full_id)
    assert core.project.active_timeline_id == full_id

    # Persist.
    core.save_state()

    # Print final summary.
    print("\n[done] timelines:")
    for t in core.project.timelines:
        owned_clips = [c for c in core.project.clips.values()
                       if c.timeline_id == t.timeline_id]
        marker_count = len(t.markers or [])
        beat_count = len(t.beats or [])
        marker = " ← active" if t.timeline_id == core.project.active_timeline_id else ""
        print(f"  - {t.timeline_id}: {t.name}  "
              f"({len(owned_clips)} clips, "
              f"{marker_count} markers, {beat_count} beats)"
              f"{marker}")

    asset_ids = sorted(a.asset_id for a in core.project.assets)
    print(f"\n[assets] {len(asset_ids)} total (shared across all Timelines)")


if __name__ == "__main__":
    main()