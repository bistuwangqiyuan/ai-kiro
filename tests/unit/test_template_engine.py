"""Unit tests for the template engine (REQ-TPL-001..006)."""

from __future__ import annotations

import pytest

from manhuaju.services.template_engine import TemplateEngine, _substitute


@pytest.fixture(scope="module")
def engine() -> TemplateEngine:
    return TemplateEngine()


def test_three_templates_shipped(engine: TemplateEngine) -> None:
    """REQ-TPL-001: at least 3 viral genre templates ship."""

    ids = engine.list_templates()
    assert {"cdrama_classic", "sweet_pet", "xianxia_epic"}.issubset(set(ids))


def test_required_var_missing_raises(engine: TemplateEngine) -> None:
    """REQ-TPL-002: missing required variable → ValueError."""

    with pytest.raises(ValueError, match="missing required"):
        engine.render("cdrama_classic", {})


def test_render_with_required_vars_succeeds(engine: TemplateEngine) -> None:
    out = engine.render(
        "cdrama_classic",
        {"protagonist_name": "苏小晚", "setting_city": "上海", "dramatic_hook": "她从未想过那一天"},
        episode_count=2,
    )
    assert out.template_id == "cdrama_classic"
    assert len(out.shot_plans_per_episode) == 2
    # Each episode has 12 shots
    for ep in out.shot_plans_per_episode:
        assert len(ep) == 12


def test_variable_substitution_applied(engine: TemplateEngine) -> None:
    """REQ-TPL-002: {{ var }} placeholders fully substituted."""

    out = engine.render(
        "sweet_pet",
        {"heroine_name": "林夏", "hero_name": "顾澜"},
        episode_count=1,
    )
    shots = out.shot_plans_per_episode[0]
    purposes = " ".join(s["purpose"] for s in shots)
    assert "林夏" in purposes
    assert "顾澜" in purposes
    # No unsubstituted braces remain
    assert "{{" not in purposes


def test_default_value_used_when_optional_missing(engine: TemplateEngine) -> None:
    out = engine.render("sweet_pet", {"heroine_name": "A", "hero_name": "B"}, episode_count=1)
    # meet_cute_setting default = "咖啡店"
    purposes = " ".join(s["purpose"] for s in out.shot_plans_per_episode[0])
    assert "咖啡店" in purposes


def test_defaults_locked_thresholds(engine: TemplateEngine) -> None:
    """REQ-TPL-003: templates lock critical numeric defaults to whitepaper anchors."""

    out = engine.render(
        "xianxia_epic",
        {"cultivator_name": "玄机", "villain_name": "魔尊"},
    )
    assert out.defaults["scene_reuse_threshold"] == 0.85
    assert out.defaults["emotion_arcface_min"] == 0.94
    assert out.defaults["outfit_arcface_min"] == 0.94


def test_episode_count_applied(engine: TemplateEngine) -> None:
    out = engine.render(
        "cdrama_classic",
        {"protagonist_name": "X", "setting_city": "Y", "dramatic_hook": "Z"},
        episode_count=5,
    )
    assert len(out.shot_plans_per_episode) == 5
    assert out.defaults["episode_count"] == 5


def test_distribution_block_substituted(engine: TemplateEngine) -> None:
    out = engine.render(
        "xianxia_epic",
        {"cultivator_name": "玄机", "villain_name": "魔尊"},
    )
    assert "douyin" in out.distribution["platforms"]
    assert "玄机" in out.distribution["hashtags"]


def test_unknown_template_raises(engine: TemplateEngine) -> None:
    with pytest.raises(FileNotFoundError):
        engine.render("does_not_exist", {})


def test_substitute_helper_is_safe() -> None:
    """The substituter must not evaluate code; missing keys remain as-is."""

    s = "hello {{ name }} and {{ unknown }}"
    out = _substitute(s, {"name": "A"})
    assert out == "hello A and {{ unknown }}"


def test_template_render_byte_identical(engine: TemplateEngine) -> None:
    """REQ-TPL-005: same inputs → identical render output."""

    a = engine.render(
        "cdrama_classic",
        {"protagonist_name": "P", "setting_city": "C", "dramatic_hook": "H"},
        episode_count=2,
    )
    b = engine.render(
        "cdrama_classic",
        {"protagonist_name": "P", "setting_city": "C", "dramatic_hook": "H"},
        episode_count=2,
    )
    assert a.shot_plans_per_episode == b.shot_plans_per_episode
    assert a.defaults == b.defaults


def test_get_variables_lists_required(engine: TemplateEngine) -> None:
    vs = engine.get_variables("cdrama_classic")
    required = {v.name for v in vs if v.required}
    assert "protagonist_name" in required
    assert "setting_city" in required
