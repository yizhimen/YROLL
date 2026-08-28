"""YROLL Manifest v0.1 — Phase 0 数据模型子集。

只包含 Phase 0（理解 Spike）需要的对象：
Project / Asset / Shot / Transcript / Understanding。
完整 Manifest（Clip/Timeline/Relationship/Problem/Solution/...）在 Phase 1 扩展。

设计原则（来自蓝图）：
- Asset 是素材的唯一身份，Origin 只是属性（素材平权）
- Shot 是 AI 理解的基本单位
- 一切分析结果进 Project Memory，"AI 分析一次，长期使用"
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class AssetOrigin(str, Enum):
    """素材来源。YROLL 不关心来源，只记录。"""

    CAMERA = "camera"  # 拍摄
    GENERATED = "generated"  # AI 生成
    SCREEN_RECORD = "screen_record"
    UNKNOWN = "unknown"


class AssetType(str, Enum):
    VIDEO = "video"
    IMAGE = "image"
    AUDIO = "audio"
    SUBTITLE = "subtitle"
    DOCUMENT = "document"


class AssetIdentity(BaseModel):
    """Asset Identity：素材移动后靠指纹找回（纯代码，不需要 LLM）。"""

    md5: str
    size_bytes: int
    duration_sec: Optional[float] = None
    width: Optional[int] = None
    height: Optional[int] = None
    created_at: Optional[datetime] = None  # 拍摄时间（EXIF/文件时间）


class Asset(BaseModel):
    asset_id: str
    type: AssetType
    origin: AssetOrigin = AssetOrigin.UNKNOWN
    path: str  # 当前已知路径（可能失效，靠 identity 找回）
    identity: AssetIdentity
    # Stage 3 本地视觉初筛结果（图像/关键帧描述）
    caption: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    # 外部 AI 产物生成链（§4 Adapter：prompt/model/seed/source_tool）
    gen: Optional[dict] = None


class TranscriptSegment(BaseModel):
    start: float
    end: float
    text: str
    words: list[dict] = Field(default_factory=list)  # 词级时间戳


class Shot(BaseModel):
    """镜头：AI 理解/修改的主要操作单位。"""

    shot_id: str
    asset_id: str
    start: float  # 源素材内时间（Source Time）
    end: float
    keyframes: list[str] = Field(default_factory=list)  # 关键帧文件路径
    caption: Optional[str] = None
    tags: list[str] = Field(default_factory=list)


class SceneSuggestion(BaseModel):
    """Stage 4 LLM 导演分析的输出：场景/故事线建议。"""

    title: str
    shot_ids: list[str]
    narrative: str = ""  # 这一段在讲什么
    role: str = ""  # hook / body / climax / ending ...


class ProjectMemory(BaseModel):
    """Project Memory：一次理解，长期使用。"""

    project_id: str
    name: str
    root: str
    created_at: datetime = Field(default_factory=datetime.now)
    assets: list[Asset] = Field(default_factory=list)
    shots: list[Shot] = Field(default_factory=list)
    transcripts: dict[str, list[TranscriptSegment]] = Field(default_factory=dict)  # asset_id -> segments
    story: list[SceneSuggestion] = Field(default_factory=list)
    # 成本记录（Cost-aware：每次操作记录 model/token/耗时）
    costs: list[dict] = Field(default_factory=list)
