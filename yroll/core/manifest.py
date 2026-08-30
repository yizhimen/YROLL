"""YROLL Manifest v0.1 — 完整数据模型（规范见 docs/manifest-v0.1.md）。

原则：
- Timeline 只记录最终作品结构（X 轴）；Relationship Graph 与 Timeline 并列
- Problem/Solution 是一级数据对象
- Version 只存 Operation 引用（diff），不复制素材
- extensions 隔离来源特定数据，Core 不被旧软件绑架
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal, Optional
import uuid

from pydantic import BaseModel, Field

from yroll.core.models import Asset, AssetConformanceResult
from yroll.core.timebase import Rational


# ---------- 枚举 ----------

class TrackKind(str, Enum):
    VIDEO = "video"
    AUDIO = "audio"
    TEXT = "text"
    SUBTITLE = "subtitle"


class TrackRole(str, Enum):
    """GUI-03C: optional semantic role for a track. Not required —
    most tracks leave role=None and rely on kind-based policy.
    Roles hint at the intended use (V1=primary, A1=voice, etc.)
    and may be displayed in the track label.
    """
    PRIMARY = "primary"     # main visual
    OVERLAY = "overlay"     # PiP, B-roll, picture-in-picture
    VOICE = "voice"         # voiceover
    MUSIC = "music"         # background music
    SFX = "sfx"             # sound effects
    CAPTION = "caption"     # subtitle / karaoke text


# Map asset.type.value → allowed TrackKind(s).
# Image and video share VIDEO tracks. Audio and subtitle are
# exclusive to their own kinds. TrackKind.TEXT and TrackKind.SUBTITLE
# are aliases (subtitle clips are text-only assets).
ASSET_TYPE_TO_TRACK_KINDS: dict[str, set[str]] = {
    "video":    {"video"},
    "image":    {"video"},
    "audio":    {"audio"},
    "subtitle": {"subtitle", "text"},   # accept both for legacy
    "text":     {"subtitle", "text"},
    "document": set(),                  # documents aren't a Timeline media
}


class RelationStrength(str, Enum):
    """Semantic Link 四级：强=自动同步 / 中=提示 / 弱=默认不动 / 独立=绝不动。"""

    STRONG = "strong"
    MEDIUM = "medium"
    WEAK = "weak"
    INDEPENDENT = "independent"


class ProblemCategory(str, Enum):
    TEMPORAL = "temporal"
    AUDIO = "audio"
    TEXT = "text"
    VISUAL = "visual"
    SPATIAL_OBJECT = "spatial_object"
    SEMANTIC = "semantic"
    CONSISTENCY = "consistency"


class SolutionRoute(str, Enum):
    """Intelligence Routing：默认推荐最低成本。"""

    L0_TRANSFORM = "L0_transform"  # 纯算法/参数调整，成本 0
    L1_LOCAL_AI = "L1_local_ai"  # 本地模型
    L2_CLOUD_AI = "L2_cloud_ai"  # 云端 AI
    L3_REGENERATE = "L3_regenerate"  # 重新生成


class ProblemSource(str, Enum):
    HUMAN = "human"  # 最高价值
    AI_REVIEW = "ai_review"
    DATA_FEEDBACK = "data_feedback"


class Actor(str, Enum):
    HUMAN = "human"
    AI = "ai"


class Sequence(BaseModel):
    """GUI-02: canonical timebase accessor for a project.

    Project.sequence is the single source of truth for the GUI's
    time/frame concerns. The flat fps_num / fps_den / width /
    height fields on Project are synchronized denormalized storage
    for on-disk back-compat with v0.1 project files.

    `timecode_format` and `drop_frame` are explicit — DF vs NDF is
    never inferred from the 30000/1001 fraction alone. NDF is a
    valid choice for 30000/1001 workflows.
    """
    sequence_id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    fps: Rational = Field(default_factory=lambda: Rational(30, 1))
    width: int = 1920
    height: int = 1080
    timecode_format: Literal["SMPTE", "DF", "NDF"] = "SMPTE"
    drop_frame: bool = False

    def sync_to_project(self, project: "Project") -> None:
        """Write canonical values into the flat denormalized fields."""
        project.fps_num = self.fps.num
        project.fps_den = self.fps.den
        project.width = self.width
        project.height = self.height

    @classmethod
    def from_project(cls, project: "Project") -> "Sequence":
        """Build a Sequence from a project. Used when opening v0.1 files
        that lack `sequence`."""
        return cls(
            fps=Rational(project.fps_num, project.fps_den or 1),
            width=project.width,
            height=project.height,
        )


# ---------- 基础值对象 ----------

class TimeRange(BaseModel):
    start: float
    end: float


class Region(BaseModel):
    """空间区域 + 羽化（所有局部修改默认带羽化）。"""

    x: float
    y: float
    w: float
    h: float
    feather: float = 20.0


class Selection(BaseModel):
    """统一选择对象：人画框、AI 画框、选时间，本质都是 Selection。"""

    timeline_range: Optional[TimeRange] = None
    spatial_region: Optional[Region] = None
    semantic_target: Optional[str] = None
    track_ids: list[str] = Field(default_factory=list)
    asset_ids: list[str] = Field(default_factory=list)


# ---------- 核心对象 ----------

class Clip(BaseModel):
    """时间轴上的使用实例。同一 Asset 可被多个 Clip 复用。

    GUI-03E-2A: every Clip carries an explicit `timeline_id`. Clip IDs
    remain globally unique across all Timelines (so
    `Project.clips[clip_id]` keeps working as a flat dict), but
    `timeline_id` is the source of truth for ownership. A mutation
    targeting Clip X with mismatched timeline_id is rejected.
    """

    clip_id: str
    asset_id: str
    timeline_id: str = "main"
    source_range: TimeRange
    timeline_range: TimeRange
    track_id: str = "v1"
    speed: float = 1.0
    volume: float = 1.0
    transform: dict[str, Any] = Field(default_factory=dict)
    adjustments: list[dict[str, Any]] = Field(default_factory=list)  # 调整图层（带羽化）
    context: dict[str, Any] = Field(default_factory=dict)  # story_role/scene/emotion/intent
    version_ids: list[str] = Field(default_factory=list)


class Track(BaseModel):
    track_id: str
    timeline_id: str = "main"  # GUI-03E-2A: explicit Timeline ownership
    kind: TrackKind
    clip_ids: list[str] = Field(default_factory=list)
    muted: bool = False   # 轨道静音（音频轨不出声 / PiP 轨不叠画）
    locked: bool = False  # 轨道锁定（GUI 禁止拖动/编辑该轨 clip）
    hidden: bool = False  # 轨道隐藏（GUI 不显示该轨 clip，渲染时仍参与）
    role: Optional[TrackRole] = None  # GUI-03C optional semantic role
    label: Optional[str] = None       # human label, e.g. "V1 主画面"


class Timeline(BaseModel):
    """X 轴：只记录最终作品结构。

    GUI-03E: a Project owns multiple peer Timelines. Each Timeline is
    an independent editing answer/version (完整版/种草版/收割版/...),
    NOT a child/nested timeline. Timeline identity is the stable
    `timeline_id`; `name` is a user-visible label and is NOT a
    canonical unique key. `derived_from` stores the source Timeline's
    stable ID (never its name) when this Timeline was duplicated from
    another via "Duplicate Timeline".
    """

    timeline_id: str = "main"
    name: str = "main"
    derived_from: Optional[str] = None  # stable source timeline_id, never name
    created_at: datetime = Field(default_factory=datetime.now)
    tracks: list[Track] = Field(default_factory=list)
    # GUI-03E-2A: per-Timeline markers / beats (list of Marker/StoryBeat
    # .to_dict() shape). Each entry carries a `timeline_id` key.
    markers: list[dict[str, Any]] = Field(default_factory=list)
    beats: list[dict[str, Any]] = Field(default_factory=list)

    def find_clip(self, clip_id: str) -> Optional["ClipRef"]:
        for t in self.tracks:
            if clip_id in t.clip_ids:
                return ClipRef(track_id=t.track_id, clip_id=clip_id)
        return None


class ClipRef(BaseModel):
    track_id: str
    clip_id: str


class Relationship(BaseModel):
    """语义关系图：与 Timeline 并列存放。"""

    relation_id: str
    source: str  # clip_id
    target: str  # clip_id
    relation: RelationStrength
    kind: str  # voice_of / caption_of / bgm_of / sfx_of ...
    confidence: float = 1.0
    scope: Optional[dict[str, TimeRange]] = None
    reason: str = ""


class Operation(BaseModel):
    """一切有意义修改（不可变日志）。Every mutation must have provenance。"""

    operation_id: str
    who: Actor
    at: datetime = Field(default_factory=datetime.now)
    type: str  # trim / split / move / transform / adjust / generate ...
    target: str  # clip_id 或对象 id
    time_range: Optional[TimeRange] = None
    region: Optional[Region] = None
    parameters: dict[str, Any] = Field(default_factory=dict)
    before: dict[str, Any] = Field(default_factory=dict)
    after: dict[str, Any] = Field(default_factory=dict)
    why: str = ""
    tool: Optional[str] = None
    model: Optional[str] = None
    cost: float = 0.0
    approved_by: Actor = Actor.HUMAN


class Version(BaseModel):
    """Git 式版本：只引用 Operation，不复制素材。"""

    version_id: str
    parent: Optional[str] = None
    operation_ids: list[str] = Field(default_factory=list)
    note: str = ""
    created_at: datetime = Field(default_factory=datetime.now)


class Problem(BaseModel):
    problem_id: str
    target_clip: Optional[str] = None
    time_range: Optional[TimeRange] = None
    region: Optional[Region] = None
    category: ProblemCategory
    description: str
    source: ProblemSource = ProblemSource.HUMAN
    severity: int = 1
    confidence: float = 1.0


class Solution(BaseModel):
    solution_id: str
    problem_id: str
    route: SolutionRoute
    tool: str
    params: dict[str, Any] = Field(default_factory=dict)
    cost: float = 0.0
    duration_ms: int = 0
    risk: str = "low"
    reversible: bool = True
    selected: bool = False


class Generation(BaseModel):
    """生成谱系：谁生成/什么模型/参数/参考/成本。"""

    generation_id: str
    clip_id: Optional[str] = None
    provider: str
    model: str
    prompt: str = ""
    references: list[str] = Field(default_factory=list)
    workflow: dict[str, Any] = Field(default_factory=dict)
    cost: float = 0.0
    duration_ms: int = 0
    review_status: str = "pending"  # pending / accepted / rejected


class Publishing(BaseModel):
    """Final Production Package：不只是 MP4。"""

    video_versions: list[dict[str, Any]] = Field(default_factory=list)
    cover: dict[str, Any] = Field(default_factory=dict)
    title: str = ""
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    platform_copy: dict[str, str] = Field(default_factory=dict)
    cost_report: dict[str, Any] = Field(default_factory=dict)


class Project(BaseModel):
    """YROLL Manifest v0.1 顶层对象。

    GUI-03E: a Project owns multiple peer Timelines. Each Timeline
    is an independent editing answer/version, NOT a child/nested
    timeline. Identity is `timeline_id`; `name` is a user label and
    is NOT a canonical key. Assets are SHARED across Timelines —
    duplication of a Timeline does NOT copy media files, only the
    editing state (tracks/clips/markers/beats).

    Fields:
      timelines:           the Project's peer Timelines. Must contain
                           at least one Timeline at all times.
      active_timeline_id:  the last/current editing context. Mutable
                           via `switch_active_timeline` (03E-2).
      default_timeline_id: the Project-designated default Timeline.
      schema_version:      monotonically increasing. GUI-03E bumps to
                           "0.2" (timeline_id-based multi-Timeline).
    """

    manifest_version: str = "0.1"
    schema_version: str = "0.2"  # GUI-03E: timeline_id-based multi-Timeline
    project_id: str
    name: str
    created_at: datetime = Field(default_factory=datetime.now)
    intent: dict[str, str] = Field(default_factory=dict)  # goal/audience/style
    # GUI-02: Sequence is the canonical accessor; the flat fields
    # below are denormalized storage kept in sync with Sequence.
    sequence: Sequence = Field(default_factory=Sequence)
    fps_num: int = 30
    fps_den: int = 1
    width: int = 1920
    height: int = 1080
    assets: list[Asset] = Field(default_factory=list)
    # GUI-03E: multiple peer Timelines. `timeline` (singular) below
    # is a deprecated property that returns the active Timeline —
    # kept for backward compatibility with pre-03E command/server
    # code, but new code MUST go through `timelines[]` +
    # `active_timeline_id`.
    timelines: list[Timeline] = Field(default_factory=list)
    active_timeline_id: str = "main"
    default_timeline_id: str = "main"
    clips: dict[str, Clip] = Field(default_factory=dict)
    relationships: list[Relationship] = Field(default_factory=list)
    problems: list[Problem] = Field(default_factory=list)
    solutions: list[Solution] = Field(default_factory=list)
    generations: list[Generation] = Field(default_factory=list)
    publishing: Publishing = Field(default_factory=Publishing)
    extensions: dict[str, Any] = Field(default_factory=dict)

    # ----------------------------------------------------------------
    # GUI-03E-1: canonical Timeline accessors.
    #
    # Open order (used by ProjectCore.open() and any UI fallback):
    #   active_timeline_id → default_timeline_id → timelines[0]
    # ----------------------------------------------------------------

    def get_timeline(self, timeline_id: str) -> Optional[Timeline]:
        """Return the Timeline with the given stable id, or None."""
        return next((t for t in self.timelines if t.timeline_id == timeline_id), None)

    def require_timeline(self, timeline_id: str) -> Timeline:
        """Strict variant: raise KeyError if the id is unknown. Used
        by command layer after schema validation."""
        t = self.get_timeline(timeline_id)
        if t is None:
            raise KeyError(
                f"project {self.project_id!r} has no timeline {timeline_id!r}; "
                f"known ids: {[t.timeline_id for t in self.timelines]}")
        return t

    @property
    def active_timeline(self) -> Optional[Timeline]:
        """Return the currently active Timeline. Falls back through
        open order if `active_timeline_id` is missing or stale. The
        caller should treat the returned Timeline as mutable — it is
        a reference to the actual entry in `self.timelines`, so
        mutations propagate (verified by tests).

        Returns None iff the Project has zero Timelines. After
        ProjectCore.open()/create() the Project is guaranteed to
        contain at least one Timeline, so this is only None for
        bare-constructed Project objects used in tests.
        """
        if not self.timelines:
            return None
        t = self.get_timeline(self.active_timeline_id)
        if t is not None:
            return t
        t = self.get_timeline(self.default_timeline_id)
        if t is not None:
            return t
        return self.timelines[0]

    @property
    def default_timeline(self) -> Optional[Timeline]:
        """Return the Project-designated default Timeline. Same
        fallback order as `active_timeline`."""
        if not self.timelines:
            return None
        t = self.get_timeline(self.default_timeline_id)
        if t is not None:
            return t
        return self.timelines[0]

    @property
    def timeline(self) -> Optional[Timeline]:
        """DEPRECATED GUI-03E-1: returns the active Timeline.

        This property exists only so pre-03E commands/server code can
        keep reading `project.timeline.tracks` without churn. New code
        MUST go through `project.timelines[]` + `active_timeline_id`.

        Important: the returned Timeline is the same reference as
        `timelines[active_idx]`; mutations propagate. We do NOT cache
        or copy here — that would break the shared-reference contract.

        Returns None iff the Project has zero Timelines (bare
        construction only).
        """
        return self.active_timeline

    # ----------------------------------------------------------------
    # GUI-02.3: Media conformance
    # ----------------------------------------------------------------

    def validate_media_conformance(
        self, sequence_fps: Optional[Rational] = None,
    ) -> list[AssetConformanceResult]:
        """Classify every asset against the project sequence timebase.

        Returns one `AssetConformanceResult` per asset. The taxonomy is:
          - "frame_editable":   source FPS matches sequence FPS AND CFR
          - "needs_conform":    FPS mismatch OR VFR — transcode recommended
          - "unsupported":      source timebase unknown — ffprobe first

        The default `sequence_fps` is `self.sequence.fps`. Callers may
        override to preview what would change under a new sequence
        frame rate without mutating the project.

        This method does NOT mutate project state. It does NOT convert
        any SourceFrame to a TimelineFrame — it only reports status.
        Per the GUI-02.3 invariant, the GUI's frame-native edit path
        MUST inspect these results before any clip referencing an
        asset that is not "frame_editable" is touched.
        """
        seq_fps = sequence_fps if sequence_fps is not None else self.sequence.fps
        return [_classify_asset(a, seq_fps) for a in self.assets]

    def frame_editable_asset_ids(
        self, sequence_fps: Optional[Rational] = None,
    ) -> list[str]:
        """Convenience: asset_ids of all assets currently frame-editable
        against the sequence. Use this to filter Clip.asset_id lookups
        before invoking frame-native operations."""
        return [
            r.asset_id for r in self.validate_media_conformance(sequence_fps)
            if r.is_frame_editable
        ]

    def unsupported_asset_ids(
        self, sequence_fps: Optional[Rational] = None,
    ) -> list[str]:
        """Convenience: asset_ids of all assets that cannot be
        frame-edited (VFR, FPS mismatch, or unknown source timebase)."""
        return [
            r.asset_id for r in self.validate_media_conformance(sequence_fps)
            if not r.is_frame_editable
        ]


def _classify_asset(
    asset: Asset, sequence_fps: Rational,
) -> AssetConformanceResult:
    """Single-asset classifier used by Project.validate_media_conformance.

    Order of checks (most specific first):
      1. No source FPS  → "unsupported" (must run ffprobe first)
      2. VFR detected   → "needs_conform" (VFR editing is out of scope)
      3. FPS mismatch   → "needs_conform" (transcode recommended; TimeMap
                                      will still map correctly but every
                                      cross-timebase boundary will be a
                                      fractional frame)
      4. CFR + FPS match → "frame_editable"

    The check is deliberately NOT named "FPS-only" — it covers
    missing timebase, VFR, and FPS mismatch under a single
    AssetConformanceResult so future checks (resolution, codec,
    color space) can extend it without renaming.
    """
    base = {
        "asset_id": asset.asset_id,
        "sequence_fps": sequence_fps,
        "source_fps": asset.source_fps,
        "source_is_cfr": asset.source_is_cfr,
    }
    if asset.source_fps is None:
        return AssetConformanceResult(
            **base,
            status="unsupported",
            reason=(
                f"asset {asset.asset_id!r} has no source FPS set; "
                f"frame-native editing requires an explicit source timebase"
            ),
            recommended_action=(
                "run ffprobe/mediainfo on the source media and set "
                "Asset.source_fps + Asset.source_is_cfr before editing"
            ),
        )
    if asset.source_is_cfr is False:
        return AssetConformanceResult(
            **base,
            status="needs_conform",
            reason=(
                f"asset {asset.asset_id!r} source is VFR; "
                f"frame-native editing requires CFR source media"
            ),
            recommended_action=(
                "transcode source to CFR at the sequence FPS, then reload"
            ),
        )
    if asset.source_fps != sequence_fps:
        return AssetConformanceResult(
            **base,
            status="needs_conform",
            reason=(
                f"asset {asset.asset_id!r} source FPS "
                f"{asset.source_fps.num}/{asset.source_fps.den} "
                f"differs from sequence FPS "
                f"{sequence_fps.num}/{sequence_fps.den}"
            ),
            recommended_action=(
                "transcode to sequence FPS, OR accept heterogeneous "
                "editing via TimeMap (fractional-frame boundaries)"
            ),
        )
    return AssetConformanceResult(
        **base,
        status="frame_editable",
        reason=(
            f"asset {asset.asset_id!r} is CFR at sequence FPS "
            f"{sequence_fps.num}/{sequence_fps.den}"
        ),
        recommended_action=None,
    )
