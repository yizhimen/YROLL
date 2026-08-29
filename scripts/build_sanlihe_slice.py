"""三里河陶鬶垂直切片：30-36s 戏剧高潮段。

GUI-03B: this version uses `add_image_clip(...)` directly — no
`set_speed(5/duration)` kludge. Image clips are first-class
Timeline media with a fixed 1-frame source range and a user-
controlled timeline duration.

Storyboard:
  0-5s   高凤翰/田野       oracle_feng_01.jpg
  5-10s  画/落款            painting_gaofenghan_hd.jpg
  10-12s 刘敦愿（彩色）     scholars_1959_color.jpg
  12-15s 刘敦愿（黑白照片） scholars_1959_photo.jpg
  15-18s 古地图全景        R.jpg
  18-22s 地图推近          R (1).jpg
  22-25s 墓葬陶片          evidence_pig_burial.jpg
  25-28s 考古报告          page_14.jpg
  28-32s 龙山白陶鬶        pottery_white_3leg.jpg
  32-36s 龙山红陶          pottery_longshan_red.jpg
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding='utf-8')

from yroll.core.commands import CommandLayer
from yroll.core.manifest import Actor, TrackKind
from yroll.core.models import Asset, AssetIdentity, AssetType
from yroll.core.project import ProjectCore
from yroll.core.timebase import Rational

# 源工程：复用 asset（直接指路径，不复制文件）
SRC = ROOT / 'projects' / 'sanlihe-story'
DST_NAME = 'sanlihe-slice-30s'
DST = ROOT / 'projects' / DST_NAME

# 源 asset 的 image file 列表（直接复用）
SRC_ASSETS = [a for a in ProjectCore.open(SRC).project.assets]

# ---------- 创建目标工程 ----------
if DST.exists():
    shutil.rmtree(DST)
core = ProjectCore.create(ROOT / 'projects', DST_NAME, intent={
    'goal': '三里河陶鬶垂直切片测试',
    'slice_duration_sec': '36',
    'storyboard': '高凤翰→画→刘敦愿→按图索骥→三里河→龙山陶鬶',
})

# 复用源 asset —— 直接指同一文件，不复制
for a in SRC_ASSETS:
    new_id = Asset(
        asset_id=a.asset_id,
        type=a.type,
        path=a.path,
        identity=a.identity,
        source_fps=a.source_fps,
        source_is_cfr=a.source_is_cfr,
        source_frame_count=a.source_frame_count,
    )
    core.project.assets.append(new_id)

# 仅保留 V1 + T1 两个轨
core.project.timeline.tracks = [
    t for t in core.project.timeline.tracks
    if t.track_id in ('v1', 't1')
]

core.save_state()
print(f'[init] DST={DST}')
print(f'[init] assets reused: {len(core.project.assets)}')

# ---------- 加 clip + 字幕 ----------
layer = CommandLayer(core, who=Actor.HUMAN)

# Project FPS: 30 (default for sanlihe-story)
fps = core.project.sequence.fps
SEQ_NUM, SEQ_DEN = fps.num, fps.den


def sec_to_frame(sec: float) -> int:
    return round(sec * SEQ_NUM / SEQ_DEN)


def add_image(filename, tl_start_frame, duration_frames, transform=None, why=''):
    """GUI-03B: add_image_clip — no set_speed hack needed.
    Image's source range is fixed at (0, 1/seq_fps); the timeline
    duration is user-controlled via timeline_duration_frames."""
    asset_id = next(
        (a.asset_id for a in core.project.assets
         if Path(a.path).name == filename),
        None,
    )
    if not asset_id:
        raise RuntimeError(f'asset not found: {filename}')
    clip = layer.add_image_clip(
        asset_id=asset_id,
        timeline_start_frame=tl_start_frame,
        timeline_duration_frames=duration_frames,
        track_id='v1',
        why=why or filename,
    )
    if transform:
        layer.set_transform2d(
            clip.clip_id,
            x=transform.get('x'), y=transform.get('y'),
            scale=transform.get('scale'),
            bg_blur=transform.get('bg_blur', True),
            why='Ken Burns',
        )
    return clip


def add_subtitle(text, start_frame, end_frame):
    """Add subtitle at frame-native boundaries."""
    return layer.add_subtitle(
        text,
        start_frame * SEQ_DEN / SEQ_NUM,
        end_frame * SEQ_DEN / SEQ_NUM,
        why='旁白',
    )


def add_fade(clip_id, fade_in, fade_out):
    layer.set_fade(clip_id, fade_in=fade_in, fade_out=fade_out, why='转场')


# ---------- Segment 1: 0-5s  高凤翰 / 田野 ----------
print('\n[seg1 0-5s] 高凤翰 田野')
c1 = add_image('oracle_feng_01.jpg', tl_start_frame=0, duration_frames=5 * SEQ_NUM,
               transform={'x': 0.0, 'y': 0.05, 'scale': 1.08, 'bg_blur': True},
               why='seg1 高凤翰 田野')
add_fade(c1.clip_id, 0.4, 0.3)
add_subtitle('两百多年前，一个农人在地里干活。', sec_to_frame(0.5), sec_to_frame(4.5))

# ---------- Segment 2: 5-10s  画 / 落款 ----------
print('[seg2 5-10s] 画 落款')
c2 = add_image('painting_gaofenghan_hd.jpg', tl_start_frame=5 * SEQ_NUM, duration_frames=5 * SEQ_NUM,
               transform={'x': -0.05, 'scale': 1.10, 'bg_blur': True},
               why='seg2 画 落款')
add_fade(c2.clip_id, 0.3, 0.3)
add_subtitle('他不知道它有多古，只是觉得，拿来插莲花挺好。', sec_to_frame(0.5) + 5 * SEQ_NUM, sec_to_frame(4.5) + 5 * SEQ_NUM)

# ---------- Segment 3: 10-15s  刘敦愿 ----------
print('[seg3 10-15s] 刘敦愿')
c3a = add_image('scholars_1959_color.jpg', tl_start_frame=10 * SEQ_NUM, duration_frames=2 * SEQ_NUM,
                transform={'scale': 1.05, 'bg_blur': True},
                why='seg3a 刘敦愿 彩色')
add_fade(c3a.clip_id, 0.3, 0.2)
c3b = add_image('scholars_1959_photo.jpg', tl_start_frame=12 * SEQ_NUM, duration_frames=3 * SEQ_NUM,
                transform={'scale': 1.10, 'x': 0.05, 'bg_blur': True},
                why='seg3b 刘敦愿 黑白照片')
add_fade(c3b.clip_id, 0.2, 0.3)
add_subtitle('200多年后，有人看到了这段题记。', sec_to_frame(0.5) + 10 * SEQ_NUM, sec_to_frame(4.5) + 10 * SEQ_NUM)

# ---------- Segment 4: 15-22s  按图索骥 ----------
print('[seg4 15-22s] 按图索骥')
c4a = add_image('R.jpg', tl_start_frame=15 * SEQ_NUM, duration_frames=3 * SEQ_NUM,
                transform={'scale': 1.0, 'bg_blur': True},
                why='seg4a 古地图 全景')
add_fade(c4a.clip_id, 0.3, 0.3)
c4b = add_image('R (1).jpg', tl_start_frame=18 * SEQ_NUM, duration_frames=4 * SEQ_NUM,
                transform={'scale': 1.15, 'x': 0.1, 'bg_blur': True},
                why='seg4b 地图推近')
add_fade(c4b.clip_id, 0.3, 0.3)
add_subtitle('余家介子城下。', sec_to_frame(0.5) + 15 * SEQ_NUM, sec_to_frame(4.5) + 15 * SEQ_NUM)
add_subtitle('他们真的去找了。', sec_to_frame(4.5) + 15 * SEQ_NUM, sec_to_frame(7.0) + 15 * SEQ_NUM)

# ---------- Segment 5: 22-28s  三里河 ----------
print('[seg5 22-28s] 三里河 发现')
c5a = add_image('evidence_pig_burial.jpg', tl_start_frame=22 * SEQ_NUM, duration_frames=3 * SEQ_NUM,
                transform={'scale': 1.10, 'bg_blur': True},
                why='seg5a 墓葬陶片')
add_fade(c5a.clip_id, 0.3, 0.3)
c5b = add_image('page_14.jpg', tl_start_frame=25 * SEQ_NUM, duration_frames=3 * SEQ_NUM,
                transform={'scale': 1.08, 'bg_blur': True},
                why='seg5b 考古报告')
add_fade(c5b.clip_id, 0.3, 0.3)
add_subtitle('这一次，他们找到了。三里河遗址。', sec_to_frame(0.5) + 22 * SEQ_NUM, sec_to_frame(5.5) + 22 * SEQ_NUM)

# ---------- Segment 6: 28-36s  龙山陶鬶（无言高潮）----------
print('[seg6 28-36s] 龙山陶鬶（高潮无言）')
c6a = add_image('pottery_white_3leg.jpg', tl_start_frame=28 * SEQ_NUM, duration_frames=4 * SEQ_NUM,
                transform={'scale': 1.15, 'x': 0.0, 'y': 0.0, 'bg_blur': True},
                why='seg6a 龙山白陶鬶')
add_fade(c6a.clip_id, 0.3, 0.5)
c6b = add_image('pottery_longshan_red.jpg', tl_start_frame=32 * SEQ_NUM, duration_frames=4 * SEQ_NUM,
                transform={'scale': 1.10, 'bg_blur': True},
                why='seg6b 龙山红陶')
add_fade(c6b.clip_id, 0.5, 0.0)

core.save_state()
print(f'\n[done] v1 clips: {len([t for t in core.project.timeline.tracks if t.track_id=="v1"][0].clip_ids)}')
print(f'[done] t1 clips: {len([t for t in core.project.timeline.tracks if t.track_id=="t1"][0].clip_ids)}')
print(f'[done] total clips: {len(core.project.clips)}')
print(f'[done] duration: 36.0s')