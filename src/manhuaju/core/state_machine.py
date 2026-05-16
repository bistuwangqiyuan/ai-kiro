"""Three-tier state machine (Project / Episode / Shot) per design §5.

Hard constraint (P-1 Autopilot Only): no state node may carry any
banned-token in its name (see `tools/lint/forbidden_terms.py` for the
exhaustive list). REQ-MO-008 / REQ-PILOT-011.
"""

from __future__ import annotations

from enum import StrEnum


class ProjectState(StrEnum):
    ACCEPTED = "Accepted"
    INGESTING = "Ingesting"
    PLANNING = "Planning"
    CHARACTER_BUILDING = "CharacterBuilding"
    STYLE_LOCKED = "StyleLocked"
    PRODUCING = "Producing"
    QUALITY_LOOP = "QualityLoop"
    RELEASING = "Releasing"
    RELEASED = "Released"
    FAILED = "Failed"
    FAILED_WITH_SALVAGE = "Failed_With_Salvage"


class EpisodeState(StrEnum):
    DRAFTED = "Drafted"
    STORYBOARDED = "Storyboarded"
    RENDERING = "Rendering"
    AUDIO_MIXING = "AudioMixing"
    POSTED = "Posted"
    IN_QA = "InQA"
    PROMOTED = "Promoted"
    REPAIRING = "Repairing"
    QUARANTINED = "Quarantined"


class ShotState(StrEnum):
    PENDING = "Pending"
    SUBMITTING = "Submitting"
    IN_GENERATION = "InGeneration"
    REVIEWING = "Reviewing"
    ACCEPTED = "Accepted"
    REPAIRING = "Repairing"
    DEGRADED = "Degraded"


# Allowed transitions (fully enumerated to support static check)
PROJECT_EDGES = {
    ProjectState.ACCEPTED: {ProjectState.INGESTING, ProjectState.FAILED},
    ProjectState.INGESTING: {ProjectState.PLANNING, ProjectState.FAILED},
    ProjectState.PLANNING: {ProjectState.CHARACTER_BUILDING},
    ProjectState.CHARACTER_BUILDING: {ProjectState.STYLE_LOCKED},
    ProjectState.STYLE_LOCKED: {ProjectState.PRODUCING},
    ProjectState.PRODUCING: {
        ProjectState.QUALITY_LOOP,
        ProjectState.FAILED_WITH_SALVAGE,
    },
    ProjectState.QUALITY_LOOP: {
        ProjectState.RELEASING,
        ProjectState.PRODUCING,  # repair_loop_back
    },
    ProjectState.RELEASING: {ProjectState.RELEASED, ProjectState.PRODUCING},
    ProjectState.RELEASED: set(),
    ProjectState.FAILED: set(),
    ProjectState.FAILED_WITH_SALVAGE: set(),
}

EPISODE_EDGES = {
    EpisodeState.DRAFTED: {EpisodeState.STORYBOARDED},
    EpisodeState.STORYBOARDED: {EpisodeState.RENDERING},
    EpisodeState.RENDERING: {EpisodeState.AUDIO_MIXING},
    EpisodeState.AUDIO_MIXING: {EpisodeState.POSTED},
    EpisodeState.POSTED: {EpisodeState.IN_QA},
    EpisodeState.IN_QA: {EpisodeState.PROMOTED, EpisodeState.REPAIRING},
    EpisodeState.REPAIRING: {
        EpisodeState.STORYBOARDED,
        EpisodeState.RENDERING,
        EpisodeState.AUDIO_MIXING,
        EpisodeState.QUARANTINED,
    },
    EpisodeState.PROMOTED: set(),
    EpisodeState.QUARANTINED: set(),
}

SHOT_EDGES = {
    ShotState.PENDING: {ShotState.SUBMITTING},
    ShotState.SUBMITTING: {ShotState.IN_GENERATION},
    ShotState.IN_GENERATION: {ShotState.REVIEWING},
    ShotState.REVIEWING: {ShotState.ACCEPTED, ShotState.REPAIRING},
    ShotState.REPAIRING: {ShotState.SUBMITTING, ShotState.DEGRADED},
    ShotState.ACCEPTED: set(),
    ShotState.DEGRADED: set(),
}


def static_no_human_paths() -> list[str]:
    """Return any state name that would violate P-1. Used by tests/static check."""
    bad = []
    for cls in (ProjectState, EpisodeState, ShotState):
        for s in cls:
            n = s.value.lower()
            for bad_token in ("waitfor", "manual", "approve", "operator", "human"):
                if bad_token in n:
                    bad.append(f"{cls.__name__}.{s.value}")
    return bad


def is_legal(edges: dict, src, dst) -> bool:
    return dst in edges.get(src, set())
