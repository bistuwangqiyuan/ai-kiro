"""Pydantic v2 schemas — produced artefacts of the pipeline.

All models are immutable and reject extra fields (REQ-NFR-PROV-001/002,
ADR-011 Schema-First, frozen=True).

Note: in M2 mock mode we relax `frozen=True` for a few internal mutable
state holders (Budget, ConsistencyMatrix) where in-place updates are
required for the in-process pipeline; these are clearly marked.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

# ---------------------------------------------------------------------------
# Common base
# ---------------------------------------------------------------------------


class Frozen(BaseModel):
    """Immutable base for produced artefacts."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class Mutable(BaseModel):
    """Mutable base for in-pipeline state (budget, matrices)."""

    model_config = ConfigDict(extra="forbid", frozen=False)


def now() -> datetime:
    return datetime.now(UTC)


# ---------------------------------------------------------------------------
# Project / Config / Budget
# ---------------------------------------------------------------------------


class ProjectConfig(Frozen):
    style_preset_id: str = "cinematic_2d_v1"
    aspect_ratio: Literal["9:16", "16:9", "1:1"] = "9:16"
    resolution: Literal["720p", "1080p", "2k"] = "1080p"
    fps: Literal[24, 25, 30] = 24
    target_locales: list[str] = ["zh-CN"]
    episode_count: int = 3
    target_seconds_per_ep: tuple[int, int] = (60, 180)
    consistency_tier: Literal["bible_only", "lora"] = "bible_only"
    model_tier: Literal["fast", "pro"] = "pro"
    budget_tier: Literal["S", "M", "L", "XL"] = "S"
    narration: bool = False
    mode: Literal["per_shot", "express"] = "per_shot"
    redlines_profile_id: str = "default"
    simhuman_consent: bool = False


class ProjectInput(Frozen):
    project_id: str  # uuid7-ish; mock pipeline accepts any non-empty id
    novel_uri: str
    novel_sha256: str
    config: ProjectConfig
    seed: int  # REQ-IN-004 : strictly required
    submitted_at: datetime = Field(default_factory=now)
    callback_urls: list[str] = []


class Budget(Mutable):
    max_tokens: int
    max_seconds: int
    max_credits: int
    used_tokens: int = 0
    used_seconds: int = 0
    used_credits: int = 0
    reserved_credits: int = 0  # >= 5%

    def remaining_credits(self) -> int:
        return max(0, self.max_credits - self.used_credits - self.reserved_credits)

    def charge(self, *, tokens: int = 0, seconds: int = 0, credits: int = 0) -> None:
        self.used_tokens += tokens
        self.used_seconds += seconds
        self.used_credits += credits

    def as_dict(self) -> dict[str, int]:
        return {
            "max_tokens": self.max_tokens,
            "max_seconds": self.max_seconds,
            "max_credits": self.max_credits,
            "used_tokens": self.used_tokens,
            "used_seconds": self.used_seconds,
            "used_credits": self.used_credits,
            "reserved_credits": self.reserved_credits,
        }


# ---------------------------------------------------------------------------
# Story Blueprint (A1)
# ---------------------------------------------------------------------------


class WorldRule(Frozen):
    rule_id: str
    text: str


class TimelineEvent(Frozen):
    event_id: str
    story_time: int  # ordinal
    description: str
    location_id: str
    characters_present: list[str]


class Location(Frozen):
    location_id: str
    name: str
    description: str
    palette_hex: list[str] = []


class CharacterStub(Frozen):
    char_id: str
    canonical_name: str
    aliases: list[str] = []
    screen_role: Literal["lead", "support", "cameo"] = "support"


class Relation(Frozen):
    src: str
    dst: str
    type: Literal["family", "friend", "rival", "lover", "mentor", "enemy", "neutral", "unknown"]


class CharacterGraph(Frozen):
    nodes: list[str]
    edges: list[Relation]


class Motif(Frozen):
    motif_id: str
    description: str


class JudgeScores(Frozen):
    faithfulness: float
    coverage: float
    structure: float


class StoryBlueprint(Frozen):
    blueprint_id: str
    blueprint_sha: str  # canonical-json sha256
    world_rules: list[WorldRule]
    timeline: list[TimelineEvent]
    locations: list[Location]
    characters: list[CharacterStub]
    relations: CharacterGraph
    motifs: list[Motif]
    judge_scores: JudgeScores
    provenance_passages: dict[str, list[tuple[int, int]]] = Field(
        default_factory=dict,
        description="char_id -> list of (start, end) byte offsets in source novel",
    )


# ---------------------------------------------------------------------------
# Episode Plan (A2)
# ---------------------------------------------------------------------------


class Beat(Frozen):
    beat_id: str
    summary: str
    seconds: int


class OpeningHook(Frozen):
    seconds: int  # <= 6
    summary: str


class ClosingCliffhanger(Frozen):
    summary: str
    cliffhanger_strength: int  # 1..5


class EpisodeBlueprint(Frozen):
    episode_id: str
    title: str
    synopsis_short: str  # <= 80 chars
    synopsis_long: str  # <= 600 chars
    target_seconds: int
    beats: list[Beat]
    opening: OpeningHook
    closing: ClosingCliffhanger
    characters_present: list[str]
    locations_present: list[str]


class BudgetAllocation(Frozen):
    per_episode_credits: list[int]
    reserve_credits: int


class EpisodePlan(Frozen):
    plan_id: str
    plan_sha: str
    episodes: list[EpisodeBlueprint]
    budgets: BudgetAllocation
    judge_scores: JudgeScores


# ---------------------------------------------------------------------------
# Character Bible (A3)
# ---------------------------------------------------------------------------


class Appearance(Frozen):
    gender: Literal["female", "male", "nonbinary", "unknown"]
    ethnicity: str = "unspecified"
    age_band: Literal["child", "teen", "young_adult", "adult", "middle_age", "elder"]
    height_band: Literal["short", "average", "tall"]
    body_type: Literal["slim", "average", "athletic", "stocky"]
    eye_color: str
    hair_length: Literal["short", "medium", "long", "very_long"]
    hair_color: str
    hair_texture: Literal["straight", "wavy", "curly"]
    hairstyle: str
    distinguishing_marks: list[str] = []
    essence: str  # <= 240 chars
    face_palette_hex: list[str] = Field(default_factory=lambda: ["#cdb79e", "#3a3a3a"])


class Outfit(Frozen):
    outfit_id: str
    name: str
    palette_hex: list[str]  # exactly 5
    fabric: str
    silhouette: str
    accessories: list[str] = []


class VoiceProfile(Frozen):
    voice_id: str
    base_pitch_hz: int
    timbre: Literal["warm", "bright", "soft", "raspy", "neutral"] = "neutral"
    energy: Literal["low", "medium", "high"] = "medium"
    locale: str = "zh-CN"


class Personality(Frozen):
    summary: str
    traits: list[str] = []


class StateNode(Frozen):
    node_id: str
    age_band: str
    hair_state: str
    wound_state: str
    outfit_id: str


class StateTransition(Frozen):
    from_node: str
    to_node: str
    trigger_beat_id: str
    justification: str


class BibleStateMachine(Frozen):
    nodes: list[StateNode]
    transitions: list[StateTransition]
    initial_node: str


class CharacterBible(Frozen):
    char_id: str
    bible_sha: str
    canonical_name: str
    aliases: list[str]
    screen_role: Literal["lead", "support", "cameo"]
    appearance: Appearance
    outfit_library: list[Outfit]  # >= 3 (>= 5 for lead)
    voice_profile: VoiceProfile
    personality: Personality
    state_machine: BibleStateMachine
    relations: list[Relation] = []
    provenance_passages: list[tuple[int, int]] = []


# ---------------------------------------------------------------------------
# Style Lock (A7)
# ---------------------------------------------------------------------------


class StyleLock(Frozen):
    style_sha: str
    preset_id: str
    aspect_ratio: str
    resolution: str
    fps: int
    duration_units: list[int] = Field(default_factory=lambda: [5, 10, 15])
    project_palette_hex: list[str]  # 8 master colors
    location_palette: dict[str, list[str]]
    locked_at: datetime = Field(default_factory=now)
    immutable: bool = True


# ---------------------------------------------------------------------------
# Script (A5) + Storyboard (A6)
# ---------------------------------------------------------------------------


class DialogueLine(Frozen):
    line_id: str
    speaker_char_id: str
    text: str
    emotion: str = "neutral"
    prosody: str = "normal"
    seconds: float
    source_spans: list[tuple[int, int]] = []


class NarrationLine(Frozen):
    line_id: str
    text: str
    seconds: float


class ShotInScript(Frozen):
    shot_id: str
    intent: Literal["establish", "build", "turn", "climax", "resolve"]
    characters: list[str]
    location_id: str
    mood: str
    estimated_seconds: int  # 5/10/15
    music_cue: str = ""
    sfx_cue: str = ""
    dialogue_line_ids: list[str] = []
    key_action: str = ""


class Scene(Frozen):
    scene_id: str
    location_id: str
    description: str
    shots: list[ShotInScript]


class ScriptTiming(Frozen):
    cumulative_seconds: int
    target_seconds: int
    delta_pct: float


class Script(Frozen):
    episode_id: str
    fountain_uri: str
    scenes: list[Scene]
    dialogues: list[DialogueLine]
    narration: list[NarrationLine] = []
    timing: ScriptTiming
    judge_scores: JudgeScores


class CharacterOnScreen(Frozen):
    char_id: str
    outfit_id: str
    state_node_id: str


class PromptBrief(Frozen):
    clauses: list[str]  # >= 10


class StoryboardShot(Frozen):
    shot_id: str
    scene_id: str
    sequence_index: int
    target_seconds: Literal[5, 10, 15]
    shot_size: Literal["ECU", "CU", "MS", "WS", "EWS"]
    camera_angle: Literal["eye", "high", "low", "top", "dutch"]
    camera_movement: Literal["static", "pan", "tilt", "dolly", "zoom", "tracking", "handheld"]
    lens_focal_mm: int
    depth_of_field: Literal["shallow", "medium", "deep"]
    lighting_preset: str
    palette_ref: list[str]
    weather: str
    characters: list[CharacterOnScreen]  # length <= 2
    key_action: str
    key_emotion: str
    mood: str
    music_cue: str
    sfx_cue: str
    prompt_brief: PromptBrief
    parent_shot_id: str | None = None

    @field_validator("characters")
    @classmethod
    def _max_two(cls, v: list[CharacterOnScreen]) -> list[CharacterOnScreen]:
        if len(v) > 2:
            raise ValueError("REQ-SD-003 violation: max 2 characters per shot")
        return v


class Storyboard(Frozen):
    episode_id: str
    shots: list[StoryboardShot]
    continuity_score: float


# ---------------------------------------------------------------------------
# Voice / Music (A8 / A9)
# ---------------------------------------------------------------------------


class VoiceAssignmentBundle(Frozen):
    project_id: str
    assignments: dict[str, VoiceProfile]
    pinned: bool = True


class MixCue(Frozen):
    at_seconds: float
    bgm_gain_db: float
    dialogue_gain_db: float
    sfx_gain_db: float


class EpisodeMix(Frozen):
    episode_id: str
    cues: list[MixCue]
    target_lufs: float = -16.0
    true_peak_max_dbtp: float = -1.0


# ---------------------------------------------------------------------------
# Render (A10)
# ---------------------------------------------------------------------------


class RenderMetadata(Frozen):
    duration_s: float
    fps: int
    resolution: str
    model_version: str
    credits_spent: int
    width: int
    height: int


class RenderJob(Mutable):
    task_id: str
    shot_id: str
    provider: Literal["xiaoyunque", "seedance"]
    model_tier: Literal["fast", "pro"]
    submitted_at: datetime = Field(default_factory=now)
    status: Literal[
        "pending",
        "running",
        "succeeded",
        "failed",
        "timeout",
        "content_review_required",
    ] = "pending"
    prompt: str = ""
    prompt_sha: str = ""
    refs_image_uris: list[str] = []
    refs_video_uris: list[str] = []
    refs_audio_uris: list[str] = []
    seed: int = 0
    request_payload_uri: str = ""
    response_payload_uri: str | None = None
    output_mp4_uri: str | None = None
    metadata: RenderMetadata | None = None
    retries: int = 0
    degraded: bool = False


# ---------------------------------------------------------------------------
# QA / Continuity / Iteration
# ---------------------------------------------------------------------------


class TechnicalChecks(Frozen):
    codec_ok: bool
    fps_match: bool
    resolution_match: bool
    no_watermark: bool
    no_text_artifact: bool


class SemanticChecks(Frozen):
    intent_match_score: float  # 0..10
    characters_present_ok: bool
    mood_match_score: float  # 0..10


class AestheticChecks(Frozen):
    laion_mean: float
    laion_worst: float


class ConsistencyChecks(Frozen):
    arcface_mean: float
    arcface_worst: float
    outfit_clip: float
    vbench_subject: float


class SyncChecks(Frozen):
    syncnet_offset_frames: float


class ModerationCheck(Frozen):
    openai_hit: bool
    bytedance_hit: bool

    @property
    def any_hit(self) -> bool:
        return self.openai_hit or self.bytedance_hit


class ShotQAReport(Frozen):
    shot_id: str
    technical: TechnicalChecks
    semantic: SemanticChecks
    aesthetic: AestheticChecks
    consistency: ConsistencyChecks
    sync: SyncChecks
    moderation: ModerationCheck
    utmos: float
    verdict: Literal["pass", "fail"]
    reasons: list[str] = []


class EpisodeQAReport(Frozen):
    episode_id: str
    shots: list[str]
    pass_rate: float
    aesthetic_mean: float
    arcface_mean: float
    vbench_mean: float
    utmos_mean: float
    syncnet_offset_max: float
    promoted: bool
    reasons: list[str] = []


class ConsistencyMatrix(Mutable):
    episodes_compared: list[str]
    matrix: dict[str, dict[str, dict[str, float]]] = {}
    drifted_chars: list[str] = []
    timestamp: datetime = Field(default_factory=now)
    hash_chain_prev: str | None = None
    hash_chain_self: str = ""


class FailureMode(StrEnum):
    F001_PROMPT_TOO_LONG = "F-001"
    F002_REFERENCE_IMAGE_MISSING = "F-002"
    F003_CONSISTENCY_FACE_LOW = "F-003"
    F004_OUTFIT_MISMATCH = "F-004"
    F005_AESTHETIC_LOW = "F-005"
    F006_VBENCH_SUBJECT_LOW = "F-006"
    F007_SYNCNET_OFFSET_HIGH = "F-007"
    F008_UTMOS_LOW = "F-008"
    F009_MODERATION_HIT = "F-009"
    F010_API_5XX = "F-010"
    F011_API_429 = "F-011"
    F012_BUDGET_OVERSHOOT = "F-012"
    F013_SCHEMA_BLUEPRINT = "F-013"
    F014_SCHEMA_SCRIPT = "F-014"
    F015_DURATION_OVERRUN = "F-015"
    F016_GROUP_SCENE = "F-016"
    F017_DRIFT_TREND = "F-017"
    F018_VOICE_CONSENT = "F-018"
    F019_MIME_MISMATCH = "F-019"
    F020_REDLINE_INPUT = "F-020"


class IterationCycle(Frozen):
    cycle_id: str
    parent_target: Literal["shot", "scene", "episode", "project"]
    target_id: str
    failure_mode: str
    strategy: str
    before_metrics: dict[str, float]
    after_metrics: dict[str, float]
    delta: dict[str, float]
    cost_credits: float
    started_at: datetime = Field(default_factory=now)
    finished_at: datetime = Field(default_factory=now)
    outcome: Literal["fixed", "not_improved", "escalated"]


# ---------------------------------------------------------------------------
# Provenance + Event
# ---------------------------------------------------------------------------


class Provenance(Frozen):
    artefact_uri: str
    sha256: str
    size: int
    producer_agent: str
    model: str = "mock"
    model_version: str = "v1"
    seed: int = 0
    parent_artefact_uri: str | None = None
    prompt_sha256: str | None = None
    response_sha256: str | None = None
    created_at: datetime = Field(default_factory=now)
    chain_prev_sha: str | None = None
    chain_self_sha: str = ""


class Event(Frozen):
    event_id: str
    subject: str  # manhuaju.event.<stage>.<status>
    project_id: str
    episode_id: str | None = None
    shot_id: str | None = None
    trace_id: str = ""
    ts: datetime = Field(default_factory=now)
    payload: dict[str, Any] = {}


__all__ = [
    "Appearance",
    "Beat",
    "BibleStateMachine",
    "Budget",
    "BudgetAllocation",
    "CharacterBible",
    "CharacterGraph",
    "CharacterOnScreen",
    "CharacterStub",
    "ClosingCliffhanger",
    "ConsistencyChecks",
    "ConsistencyMatrix",
    "DialogueLine",
    "EpisodeBlueprint",
    "EpisodeMix",
    "EpisodePlan",
    "EpisodeQAReport",
    "Event",
    "FailureMode",
    "Frozen",
    "IterationCycle",
    "JudgeScores",
    "Location",
    "MixCue",
    "ModerationCheck",
    "Motif",
    "Mutable",
    "NarrationLine",
    "OpeningHook",
    "Outfit",
    "Personality",
    "ProjectConfig",
    "ProjectInput",
    "PromptBrief",
    "Provenance",
    "Relation",
    "RenderJob",
    "RenderMetadata",
    "Scene",
    "Script",
    "ScriptTiming",
    "ShotInScript",
    "ShotQAReport",
    "StateNode",
    "StateTransition",
    "StoryBlueprint",
    "Storyboard",
    "StoryboardShot",
    "StyleLock",
    "SyncChecks",
    "TechnicalChecks",
    "TimelineEvent",
    "VoiceAssignmentBundle",
    "VoiceProfile",
    "WorldRule",
    "now",
]
