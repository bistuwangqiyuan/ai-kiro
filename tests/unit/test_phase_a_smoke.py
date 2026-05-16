"""Phase A smoke gate: schemas + core load and basic invariants."""

from __future__ import annotations

import json
from pathlib import Path

from manhuaju.core.budget_service import make_budget
from manhuaju.core.checkpoint import StateJournal
from manhuaju.core.event_bus import InMemoryEventBus
from manhuaju.core.failure_modes import RETRY_BUDGETS, TABLE
from manhuaju.core.provenance import ProvenanceStore
from manhuaju.core.seed import episode_seed, project_seed, shot_seed
from manhuaju.core.state_machine import (
    EPISODE_EDGES,
    PROJECT_EDGES,
    SHOT_EDGES,
    EpisodeState,
    ProjectState,
    ShotState,
    is_legal,
    static_no_human_paths,
)
from manhuaju.core.storage import LocalFSStorage
from manhuaju.schemas import (
    Budget,
    FailureMode,
    ProjectConfig,
    ProjectInput,
    StoryboardShot,
)
from manhuaju.utils.canonical_json import sha256_of, to_canonical


def test_state_machine_no_human_path() -> None:
    assert static_no_human_paths() == []


def test_state_machine_edges() -> None:
    assert is_legal(PROJECT_EDGES, ProjectState.ACCEPTED, ProjectState.INGESTING)
    assert is_legal(EPISODE_EDGES, EpisodeState.IN_QA, EpisodeState.PROMOTED)
    assert is_legal(SHOT_EDGES, ShotState.PENDING, ShotState.SUBMITTING)
    assert not is_legal(SHOT_EDGES, ShotState.PENDING, ShotState.ACCEPTED)


def test_seed_determinism() -> None:
    a = project_seed(42)
    b = project_seed(42)
    assert a == b
    e1 = episode_seed(a, "ep01")
    e2 = episode_seed(a, "ep02")
    assert e1 != e2
    s1 = shot_seed(e1, "ep01_sh01", retry_count=0)
    s1_again = shot_seed(e1, "ep01_sh01", retry_count=0)
    assert s1 == s1_again


def test_canonical_json_stable() -> None:
    a = sha256_of({"b": 1, "a": 2, "c": [3, 2, 1]})
    b = sha256_of({"a": 2, "c": [3, 2, 1], "b": 1})
    assert a == b
    assert "\n" not in to_canonical({"x": 1})


def test_budget_tier_S() -> None:
    b: Budget = make_budget("S")
    assert b.max_credits == 6_000
    assert b.reserved_credits >= 1
    b.charge(credits=100)
    assert b.used_credits == 100
    assert b.remaining_credits() == 6_000 - 100 - b.reserved_credits


def test_failure_table_complete() -> None:
    assert len(TABLE) == 20
    for fm in FailureMode:
        assert fm in TABLE
    assert RETRY_BUDGETS["shot"] == 3


def test_storyboard_shot_max_two_chars() -> None:
    bad = {
        "shot_id": "ep01_sh01",
        "scene_id": "ep01_sc01",
        "sequence_index": 1,
        "target_seconds": 5,
        "shot_size": "MS",
        "camera_angle": "eye",
        "camera_movement": "static",
        "lens_focal_mm": 50,
        "depth_of_field": "medium",
        "lighting_preset": "soft_key",
        "palette_ref": ["#222", "#888"],
        "weather": "clear",
        "characters": [
            {"char_id": "lead_a", "outfit_id": "lead_a_default", "state_node_id": "n0"},
            {"char_id": "lead_b", "outfit_id": "lead_b_default", "state_node_id": "n0"},
            {"char_id": "lead_c", "outfit_id": "lead_c_default", "state_node_id": "n0"},
        ],
        "key_action": "discuss",
        "key_emotion": "tense",
        "mood": "tense",
        "music_cue": "underscore",
        "sfx_cue": "",
        "prompt_brief": {"clauses": ["a"] * 10},
    }
    try:
        StoryboardShot.model_validate(bad)
    except Exception as e:
        assert "REQ-SD-003" in str(e) or "max" in str(e).lower()
    else:
        raise AssertionError("expected REQ-SD-003 violation")


def test_provenance_chain(tmp_path: Path) -> None:
    p = ProvenanceStore(tmp_path / "prov")
    p.record(
        artefact_uri="x.json",
        sha256="a" * 64,
        size=10,
        producer_agent="TestAgent",
        seed=1,
    )
    p.record(
        artefact_uri="y.json",
        sha256="b" * 64,
        size=11,
        producer_agent="TestAgent",
        seed=2,
    )
    assert p.verify() is True


def test_event_bus_publish_and_journal(tmp_path: Path) -> None:
    bus = InMemoryEventBus(tmp_path / "events.jsonl")
    seen: list[str] = []
    bus.subscribe("manhuaju.test.start", lambda e: seen.append(e.subject))
    bus.publish(
        "manhuaju.test.start", project_id="proj_x", payload={"a": 1}
    )
    assert seen == ["manhuaju.test.start"]
    assert len(bus.events) == 1
    j = (tmp_path / "events.jsonl").read_text(encoding="utf-8").splitlines()
    assert json.loads(j[0])["subject"] == "manhuaju.test.start"


def test_state_journal_replay(tmp_path: Path) -> None:
    j = StateJournal(tmp_path / "state.jsonl")
    j.append({"k": 1})
    j.append({"k": 2})
    rs = j.replay()
    assert [r["k"] for r in rs] == [1, 2]


def test_storage_round_trip(tmp_path: Path) -> None:
    s = LocalFSStorage(tmp_path)
    s.write_text("a/b.txt", "hi")
    s.write_json("a/c.json", {"k": 1})
    assert s.read_text("a/b.txt") == "hi"
    assert s.exists("a/c.json")


def test_project_input_requires_seed() -> None:
    cfg = ProjectConfig()
    pi = ProjectInput(
        project_id="p1",
        novel_uri="file://novel.md",
        novel_sha256="0" * 64,
        config=cfg,
        seed=42,
    )
    assert pi.seed == 42
