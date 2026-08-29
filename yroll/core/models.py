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

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, Field

from yroll.core.timebase import Rational


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

    # ----------------------------------------------------------------
    # GUI-02.3: Explicit source timebase.
    #
    # Frame-native editing requires the asset's SOURCE timebase to be
    # explicit. The asset's source timebase is independent of the
    # project's sequence timebase — they may match (conformant) or
    # differ (heterogeneous).
    #
    # These fields are the unified accessors; legacy fps_num/fps_den
    # on AssetIdentity (already there for some assets) are migrated
    # here when the project is opened. None means "unknown" — the
    # asset's container did not declare a frame rate (VFR detection
    # in progress, missing metadata, etc.).
    # ----------------------------------------------------------------
    source_fps: Optional[Rational] = None        # asset's source FPS, None = unknown
    source_is_cfr: Optional[bool] = None         # True = CFR, False = VFR, None = unknown
    source_frame_count: Optional[int] = None     # total source frames (when known)

    @property
    def source_fps_rational(self) -> Rational:
        """Strict accessor for the asset's source timebase.

        Raises ValueError if the source FPS is unknown. Per the
        GUI-02.3 invariant, frame-native editing NEVER silently falls
        back to the project sequence FPS — that would relabel a
        SourceFrame as a TimelineFrame and lose the conversion that
        TimeMap is supposed to perform.

        Use `Project.validate_media_conformance()` to discover which
        assets need their source FPS supplied (e.g. via
        ffprobe/mediainfo) before relying on this accessor.
        """
        if self.source_fps is None:
            raise ValueError(
                f"asset {self.asset_id!r} has no source FPS set; "
                f"frame-native editing requires an explicit source "
                f"timebase (run ffprobe / set Asset.source_fps)"
            )
        return self.source_fps

    @property
    def is_vfr(self) -> bool:
        """True iff the asset has been positively identified as VFR.
        Returns False for CFR or unknown — use Project.validate_media_
        conformance() to disambiguate unknown."""
        return self.source_is_cfr is False

    @property
    def source_timebase_known(self) -> bool:
        """True iff the asset's source timebase is fully known:
        source_fps set AND source_is_cfr known."""
        return self.source_fps is not None and self.source_is_cfr is not None


# ---------------------------------------------------------------------------
# GUI-02.3: Media conformance result.
#
# validate_media_conformance() returns one AssetConformanceResult per
# asset. The status taxonomy is deliberately open — it covers FPS
# mismatch, VFR, and missing source timebase under the SAME result
# type, so future checks (resolution, codec, color space, …) can be
# added without renaming this check.
# ---------------------------------------------------------------------------

# The set of possible status values. Kept narrow on purpose; new
# statuses (e.g. "needs_color_convert") can be added without
# breaking old callers because callers should always inspect the
# `reason` and `recommended_action` fields rather than switch on
# status strings. We do NOT name this "FPS-only" because VFR
# detection, codec mismatch, resolution mismatch, etc. all fall
# under "needs_conform" / "unsupported".
AssetConformanceStatus = Literal[
    "frame_editable",     # source FPS matches sequence FPS AND source is CFR
    "needs_conform",      # source FPS mismatch OR VFR — transcode recommended
    "unsupported",        # source timebase unknown — resolve via ffprobe first
]


@dataclass(frozen=True)
class AssetConformanceResult:
    """Result of conformance check for a single asset.

    Produced by `Project.validate_media_conformance()`. Each asset in
    the project gets exactly one result.

    Fields:
      asset_id:            the asset's identity
      status:              one of frame_editable / needs_conform / unsupported
      reason:              human-readable explanation (English)
      sequence_fps:        the project sequence FPS used for the check
      source_fps:          the asset's source FPS, None iff unknown
      source_is_cfr:       True = CFR, False = VFR, None = unknown
      recommended_action:  remediation hint (e.g. "transcode to sequence FPS
                           then reload", "run ffprobe to extract source FPS")

    `frame_editable` means the asset can be used in frame-native
    editing as-is. `needs_conform` means the asset's source timebase
    differs from the sequence; YROLL will still allow the clip via
    TimeMap speed mapping, but the recommendation is to transcode to
    the sequence FPS first to avoid fractional-frame boundaries.
    `unsupported` means the source timebase is unknown; resolve before
    editing. Full VFR editing is OUT OF SCOPE per the GUI-02.3
    invariant — VFR assets return `needs_conform` with a transcode
    recommendation.
    """
    asset_id: str
    status: AssetConformanceStatus
    reason: str
    sequence_fps: Rational
    source_fps: Optional[Rational]
    source_is_cfr: Optional[bool]
    recommended_action: Optional[str]

    @property
    def is_frame_editable(self) -> bool:
        return self.status == "frame_editable"

    @property
    def needs_conform(self) -> bool:
        return self.status == "needs_conform"

    @property
    def is_unsupported(self) -> bool:
        return self.status == "unsupported"


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
