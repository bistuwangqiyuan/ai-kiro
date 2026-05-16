from manhuaju.adapters.render.video_prompt import compose_fluent_video_prompt


def test_compose_no_pipes() -> None:
    s = compose_fluent_video_prompt(
        prompt="wide | shot | tense",
        characters=[{"name": "yunque"}],
        location_id="old_alley",
        mood="wistful",
        key_action="looks up",
    )
    assert "|" not in s
    assert "yunque" in s.lower()
    assert len(s) <= 1200


def test_compose_skips_numeric_ids() -> None:
    s = compose_fluent_video_prompt(
        prompt="wide establishing shot",
        characters=[{"char_id": "char_07619845"}, {"char_id": "char_33097626"}],
        location_id="archive_hall",
        mood="tense",
        key_action="exchange a glance",
    )
    assert "07619845" not in s
    assert "33097626" not in s
    assert "premium manga" in s.lower() or "protagonists" in s.lower()
