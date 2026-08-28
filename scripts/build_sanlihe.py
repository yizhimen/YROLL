"""Sanlihe Story 真实剪辑：按 brief 11 段排时间线。

每个 segment:
- 1-2 个图片 clip（每张 3-6s）
- Ken Burns 动画（缩放/平移）
- segment 间淡入淡出
- 字幕（每段一句旁白）
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

sys.stdout.reconfigure(encoding='utf-8')

from yroll.core.commands import CommandLayer
from yroll.core.manifest import Actor
from yroll.core.project import ProjectCore
from yroll.core.manifest import TrackKind

# 加载工程
core = ProjectCore.open(ROOT / 'projects' / 'sanlihe-story')
layer = CommandLayer(core, who=Actor.HUMAN)

# 资产 → 短 id 映射
assets = {a.path.split(chr(92))[-1]: a.asset_id for a in core.project.assets}
A = lambda fn: assets.get(fn)  # noqa: E731

# 找第一个 video 轨
v1 = next(t for t in core.project.timeline.tracks if t.kind == TrackKind.VIDEO and t.track_id == 'v1')
t1 = next(t for t in core.project.timeline.tracks if t.kind == TrackKind.TEXT and t.track_id == 't1')

print(f'[init] v1 clips: {len(v1.clip_ids)}, t1 clips: {len(t1.clip_ids)}')
print(f'[init] assets: {len(assets)}')


def add_clip(asset_id, tl_start, duration, transform=None, why=''):
    """加图片 clip 到 v1。"""
    if asset_id not in [a.asset_id for a in core.project.assets]:
        return None
    c = layer.add_clip(
        asset_id, 0.0, 5.0,  # 图片 source 区间 0-5s
        timeline_start=tl_start, track_id='v1', why=why or f'add {asset_id}',
    )
    # 调整时长
    if duration != 5.0:
        # 调速到目标时长（source 5s → target duration）
        speed = 5.0 / duration
        layer.set_speed(c.clip_id, speed, why=f'节奏 {duration}s')
    # Ken Burns: 缩放 1 → 1.08（轻微推近）
    if transform:
        _d = transform or {}
        layer.set_transform2d(c.clip_id, x=_d.get("x"), y=_d.get("y"), scale=_d.get("scale"), bg_blur=_d.get("bg_blur", True), why='Ken Burns')
    return c


def add_subtitle(text, start, end):
    """加字幕到 t1。"""
    return layer.add_subtitle(text, start, end, why='旁白')


def add_fade(clip_id, fade_in, fade_out):
    layer.set_fade(clip_id, fade_in=fade_in, fade_out=fade_out, why='转场淡入淡出')


# ─────────────────────────────────────
# 11 段时间线（按 brief）
# ─────────────────────────────────────

# 0-5s：黑屏 + 1959 假画 + 手指划过
print('\n[seg 1] 0-5s 假画')
c1 = add_clip(A('painting_gaofenghan_hd.jpg'), 0.0, 5.0,
              transform={'x': 0.05, 'y': 0.0, 'scale': 1.0, 'bg_blur': True},
              why='0-5s 假画入场')
add_fade(c1.clip_id, 0.5, 0.5)
add_subtitle('1959年，有几个人拿着一幅假画，去找4000年前的人。', 1.5, 4.5)

# 5-15s：1745 高凤翰得陶器
print('[seg 2] 5-15s 1745 高凤翰')
# 5-10s 田野
c2 = add_clip(A('oracle_feng_01.jpg'), 5.0, 5.0,
              transform={'x': 0.0, 'y': 0.05, 'scale': 1.05, 'bg_blur': True},
              why='5-10s 1745 田野')
add_fade(c2.clip_id, 0.5, 0.5)
add_subtitle('两百多年前，一个农人在地里干活。', 5.5, 8.0)
# 10-15s 农人挖出陶器
c3 = add_clip(A('pottery_white_3leg.jpg'), 10.0, 5.0,
              transform={'scale': 1.15, 'x': 0.0, 'y': -0.1, 'bg_blur': True},
              why='10-15s 挖出陶器')
add_fade(c3.clip_id, 0.5, 0.5)
add_subtitle('不知道从哪里，挖出了一件奇怪的陶器。', 11.0, 14.0)

# 15-25s：插莲 / 作画 / 留题
print('[seg 3] 15-25s 插莲作画')
c4 = add_clip(A('pottery_white_3leg.jpg'), 15.0, 4.0,
              transform={'scale': 1.1, 'x': 0.0, 'y': 0.0, 'bg_blur': True},
              why='15-19s 陶鬶近景')
add_fade(c4.clip_id, 0.5, 0.3)
c5 = add_clip(A('painting_gaofenghan_hd.jpg'), 19.0, 6.0,
              transform={'x': -0.05, 'scale': 1.08, 'bg_blur': True},
              why='19-25s 落款作画')
add_fade(c5.clip_id, 0.3, 0.5)
add_subtitle('「介子城边老瓦窑，田夫掘出说前朝」', 17.0, 21.0)
add_subtitle('他根本不知道它有多古，只是觉得，拿来插莲花挺好。', 21.0, 24.5)

# 25-35s：1958 韩连琪
print('[seg 4] 25-35s 1958 韩连琪')
c6 = add_clip(A('scholars_1959_photo.jpg'), 25.0, 4.0,
              transform={'scale': 1.0, 'bg_blur': True},
              why='25-29s 1958 山东大学')
add_fade(c6.clip_id, 0.5, 0.3)
c7 = add_clip(A('oracle_feng_02.jpg'), 29.0, 6.0,
              transform={'scale': 1.2, 'x': 0.0, 'y': -0.05, 'bg_blur': True},
              why='29-35s 题记特写')
add_fade(c7.clip_id, 0.3, 0.5)
add_subtitle('200多年过去，有人在文物收藏中，又看到了这段文字。', 27.0, 30.0)
add_subtitle('介子城。这是第一条真正的线索。', 32.0, 34.5)

# 35-48s：按图索骥（地图）
print('[seg 5] 35-48s 按图索骥')
c8 = add_clip(A('R.jpg'), 35.0, 4.5,
              transform={'scale': 1.0, 'bg_blur': True},
              why='35-39.5s 古地图')
add_fade(c8.clip_id, 0.5, 0.3)
c9 = add_clip(A('R (1).jpg'), 39.5, 4.5,
              transform={'scale': 1.1, 'x': 0.1, 'y': 0.0, 'bg_blur': True},
              why='39.5-44s 地图推近')
add_fade(c9.clip_id, 0.3, 0.3)
c10 = add_clip(A('R (2).jpg'), 44.0, 4.0,
               transform={'scale': 1.15, 'x': -0.1, 'y': 0.0, 'bg_blur': True},
               why='44-48s 地图聚焦')
add_fade(c10.clip_id, 0.3, 0.5)
add_subtitle('「余家介子城下。」', 36.5, 39.0)
add_subtitle('1959年，刘敦愿他们顺着这条线索，去找了。', 40.0, 45.0)

# 48-58s：介子城找错
print('[seg 6] 48-58s 介子城找错')
c11 = add_clip(A('evidence_cave_section.jpg'), 48.0, 5.0,
               transform={'scale': 1.1, 'x': 0.0, 'y': 0.0, 'bg_blur': True},
               why='48-53s 介子城田野')
add_fade(c11.clip_id, 0.5, 0.3)
c12 = add_clip(A('art5156870796.jpg'), 53.0, 5.0,
               transform={'scale': 1.05, 'x': 0.0, 'y': -0.05, 'bg_blur': True},
               why='53-58s 找错的田野')
add_fade(c12.clip_id, 0.3, 0.5)
add_subtitle('他们真的去了，但第一站——错了。', 50.0, 53.0)
add_subtitle('没有找到龙山文化遗物。', 55.0, 57.5)

# 58-68s：三里河找到龙山遗址
print('[seg 7] 58-68s 三里河找到')
c13 = add_clip(A('evidence_pig_burial.jpg'), 58.0, 5.0,
               transform={'scale': 1.15, 'x': 0.0, 'y': 0.0, 'bg_blur': True},
               why='58-63s 墓葬陶片')
add_fade(c13.clip_id, 0.5, 0.3)
c14 = add_clip(A('page_14.jpg'), 63.0, 5.0,
               transform={'scale': 1.1, 'x': 0.0, 'y': 0.0, 'bg_blur': True},
               why='63-68s 考古报告')
add_fade(c14.clip_id, 0.3, 0.5)
add_subtitle('这一次，他们找到了。', 60.0, 62.0)
add_subtitle('这里真的有龙山文化遗存。三里河遗址。', 64.0, 67.5)

# 68-78s：4000年前的生活世界
print('[seg 8] 68-78s 4000年前生活')
c15 = add_clip(A('evidence_bones_shells.jpg'), 68.0, 4.0,
               transform={'scale': 1.1, 'bg_blur': True},
               why='68-72s 家畜/贝壳')
add_fade(c15.clip_id, 0.5, 0.3)
c16 = add_clip(A('pottery_longshan_red.jpg'), 72.0, 3.0,
               transform={'scale': 1.08, 'bg_blur': True},
               why='72-75s 龙山陶')
add_fade(c16.clip_id, 0.3, 0.3)
c17 = add_clip(A('pottery_dawenkou_brown.jpg'), 75.0, 3.0,
               transform={'scale': 1.08, 'bg_blur': True},
               why='75-78s 大汶口陶')
add_fade(c17.clip_id, 0.3, 0.5)
add_subtitle('4000多年前，这里有人生活。', 69.0, 71.5)
add_subtitle('种粮、养猪、做陶器、吃饭、长大、老去。', 73.0, 77.5)

# 78-88s：陶鬶 → 当代三袋足茶壶
print('[seg 9] 78-88s 当代茶壶')
c18 = add_clip(A('pottery_white_3leg.jpg'), 78.0, 4.0,
               transform={'scale': 1.1, 'x': 0.0, 'y': 0.0, 'bg_blur': True},
               why='78-82s 陶鬶回归')
add_fade(c18.clip_id, 0.5, 0.3)
c19 = add_clip(A('pottery_black_stemcup_short.jpg'), 82.0, 6.0,
               transform={'scale': 1.15, 'x': 0.0, 'y': -0.05, 'bg_blur': True},
               why='82-88s 当代粉引壶')
add_fade(c19.clip_id, 0.3, 0.5)
add_subtitle('我们把这个古老的器形，重新做成了茶壶。', 80.0, 83.0)
add_subtitle('它已经不是原来的东西，但我们觉得——', 84.0, 87.5)

# 88-90s：收尾
print('[seg 10] 88-90s 收尾')
c20 = add_clip(A('pottery_birdshaped.jpg'), 88.0, 2.0,
               transform={'scale': 1.1, 'bg_blur': True},
               why='88-90s 收尾陶鬶')
add_fade(c20.clip_id, 0.3, 0.0)
add_subtitle('他们看到的是自己的日子。', 88.5, 89.8)

core.save_state()
print(f'\n[done] v1 clips: {len(v1.clip_ids)}, t1 clips: {len(t1.clip_ids)}')
print(f'[done] total clips: {len(core.project.clips)}')
