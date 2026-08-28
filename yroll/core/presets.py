"""YROLL Presets（精简版，与剪映/CapCut/Premiere 对齐）。

原则（蓝图 §11）：不追求数量，追求可用。
AI 可在运行时生成或推荐；人手剪辑只需要这几样够用。

文件位置：`yroll/core/presets.py`（代码常量，避免冷启动依赖外置 JSON）。
"""

# ───────────────────────────────────────────────────────────
# 字体：5 个 CJK + 2 个英文（系统已有）
# ───────────────────────────────────────────────────────────

FONTS = [
    {"id": "msyh",   "name": "微软雅黑",  "file": "C:/Windows/Fonts/msyh.ttc",   "category": "cjk", "weight": 400},
    {"id": "simhei", "name": "黑体",      "file": "C:/Windows/Fonts/simhei.ttf", "category": "cjk", "weight": 700},
    {"id": "simsun", "name": "宋体",      "file": "C:/Windows/Fonts/simsun.ttc", "category": "cjk", "weight": 400},
    {"id": "kaiti",  "name": "楷体",      "file": "C:/Windows/Fonts/simkai.ttf", "category": "cjk", "weight": 400},
    {"id": "arial",  "name": "Arial",     "file": "C:/Windows/Fonts/arial.ttf",  "category": "latin", "weight": 400},
]

# ───────────────────────────────────────────────────────────
# 字幕样式：5 个（颜色/字号/位置/粗体）
# ───────────────────────────────────────────────────────────

SUBTITLE_STYLES = [
    {
        "id": "white_bottom", "name": "底部白字",
        "font_size": 38, "color": "white", "bold": True,
        "position": "bottom", "align": "center",
        "outline_color": "black", "outline_width": 2,
    },
    {
        "id": "yellow_title", "name": "顶部黄字（标题）",
        "font_size": 56, "color": "#ffd479", "bold": True,
        "position": "top", "align": "center",
        "outline_color": "black", "outline_width": 3,
    },
    {
        "id": "red_subtitle", "name": "中部红字（强调）",
        "font_size": 44, "color": "#ff5555", "bold": True,
        "position": "middle", "align": "center",
        "outline_color": "white", "outline_width": 2,
    },
    {
        "id": "small_caption", "name": "底部小字（注释）",
        "font_size": 24, "color": "#cccccc", "bold": False,
        "position": "bottom", "align": "left",
        "outline_color": "black", "outline_width": 1,
    },
    {
        "id": "white_top_left", "name": "左上白字（标签）",
        "font_size": 28, "color": "white", "bold": False,
        "position": "top", "align": "left",
        "outline_color": "black", "outline_width": 2,
    },
]

# ───────────────────────────────────────────────────────────
# 转场：5 种（xfade 内置）
# ───────────────────────────────────────────────────────────

TRANSITIONS = [
    {"id": "fade",     "name": "淡入淡出", "type": "fade",     "default_duration": 0.5},
    {"id": "wipeleft", "name": "向左擦除", "type": "wipeleft", "default_duration": 0.5},
    {"id": "wiperight","name": "向右擦除", "type": "wiperight","default_duration": 0.5},
    {"id": "slideleft","name": "左滑",     "type": "slideleft","default_duration": 0.5},
    {"id": "circle",   "name": "圆形展开", "type": "circlecrop","default_duration": 0.7},
]

# ───────────────────────────────────────────────────────────
# 滤镜：5 种（亮度/对比度/饱和度/色温/锐化）
# ───────────────────────────────────────────────────────────

FILTERS = [
    {"id": "brighten",  "name": "提亮",      "params": {"brightness": 0.1}},
    {"id": "darken",    "name": "压暗",      "params": {"brightness": -0.1}},
    {"id": "warm",      "name": "暖色",      "params": {"temperature": 6500}},
    {"id": "cool",      "name": "冷色",      "params": {"temperature": 3500}},
    {"id": "sharpen",   "name": "锐化",      "params": {"sharpen": 1.5}},
]

# ───────────────────────────────────────────────────────────
# 音效分类：5 类（每类一个示例实现）
# ───────────────────────────────────────────────────────────

SFX_CATEGORIES = [
    {"id": "silence_remove",  "name": "去停顿",    "tool": "audio.silence_remove", "cost": 0.0,  "tier": "L0"},
    {"id": "loudness_normal", "name": "响度标准化","tool": "audio.loudness_normalize","cost": 0.0,  "tier": "L0"},
    {"id": "denoise",         "name": "降噪",      "tool": "video.denoise",       "cost": 0.0,  "tier": "L1"},
    {"id": "delogo",          "name": "去水印",    "tool": "video.delogo",        "cost": 0.0,  "tier": "L0"},
    {"id": "bgm_duck",        "name": "BGM 自动压低","tool": "audio.bgm_duck",    "cost": 0.0,  "tier": "L0"},
]

# ───────────────────────────────────────────────────────────
# 平台导出预设：6 个常见平台
# ───────────────────────────────────────────────────────────

EXPORT_PRESETS = [
    {"id": "douyin",  "name": "抖音",       "width": 1080, "height": 1920, "fps": 30,
     "platform": "douyin", "burn_subtitles": True},
    {"id": "kuaishou","name": "快手",       "width": 720,  "height": 1280, "fps": 30,
     "platform": "kuaishou", "burn_subtitles": True},
    {"id": "xiaohongshu","name": "小红书", "width": 1080, "height": 1440, "fps": 30,
     "platform": "xiaohongshu", "burn_subtitles": True},
    {"id": "wechat_video","name": "视频号", "width": 720, "height": 1280, "fps": 30,
     "platform": "wechat", "burn_subtitles": True},
    {"id": "bilibili","name": "B站",         "width": 1920, "height": 1080, "fps": 30,
     "platform": "bilibili", "burn_subtitles": False},
    {"id": "youtube", "name": "YouTube",     "width": 1920, "height": 1080, "fps": 30,
     "platform": "youtube", "burn_subtitles": False},
]

# ───────────────────────────────────────────────────────────
# 视频视窗比例（预览窗口候选）
# ───────────────────────────────────────────────────────────

ASPECT_RATIOS = [
    {"id": "16:9",  "name": "横屏 16:9",  "w": 16, "h": 9,   "use": "YouTube/B站"},
    {"id": "9:16",  "name": "竖屏 9:16",  "w": 9,  "h": 16,  "use": "抖音/快手"},
    {"id": "1:1",   "name": "方屏 1:1",   "w": 1,  "h": 1,   "use": "朋友圈/Instagram"},
    {"id": "4:3",   "name": "传统 4:3",   "w": 4,  "h": 3,   "use": "老视频/纪录片"},
    {"id": "3:4",   "name": "竖版 3:4",   "w": 3,  "h": 4,   "use": "小红书图文"},
]


def all_presets() -> dict:
    """一次性返回所有 preset 给前端（一次拉完，避免 N 次 round trip）。"""
    return {
        "fonts": FONTS,
        "subtitle_styles": SUBTITLE_STYLES,
        "transitions": TRANSITIONS,
        "filters": FILTERS,
        "sfx_categories": SFX_CATEGORIES,
        "export_presets": EXPORT_PRESETS,
        "aspect_ratios": ASPECT_RATIOS,
    }
