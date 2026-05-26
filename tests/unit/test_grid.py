"""Unit tests for the 9-25 grid storyboard service (REQ-GRID-001..006)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from manhuaju.services.grid_renderer import render
from manhuaju.services.storyboard_grid import layout, regenerate_cell


def _shots(n: int) -> list[dict[str, str]]:
    return [{"shot_id": f"s{i:03d}", "caption": f"shot {i}"} for i in range(1, n + 1)]


@pytest.mark.parametrize(
    "n,aspect,exp_capacity",
    [
        (1, "9:16", 9),
        (9, "9:16", 9),
        (10, "9:16", 12),
        (12, "16:9", 12),
        (16, "1:1", 16),
        (20, "9:16", 20),
        (25, "9:16", 25),
    ],
)
def test_grid_size_mapping(n: int, aspect: str, exp_capacity: int) -> None:
    """REQ-GRID-001: grid size table (count, aspect) → (rows, cols)."""

    layouts = layout("scene-1", _shots(n), aspect=aspect)
    assert len(layouts) == 1
    g = layouts[0]
    assert g.rows * g.cols == exp_capacity


def test_cell_numbers_in_order() -> None:
    """REQ-GRID-002: cell numbering 1..N matches shot order."""

    g = layout("s1", _shots(12), aspect="9:16")[0]
    assert [c.cell_index for c in g.cells] == list(range(1, 13))
    assert [c.shot_id for c in g.cells] == [s["shot_id"] for s in _shots(12)]


def test_grid_paginates_above_25() -> None:
    """REQ-GRID-003: scenes with > 25 shots paginate."""

    layouts = layout("scene-big", _shots(60), aspect="9:16")
    assert len(layouts) == 3
    assert all(g.total_pages == 3 for g in layouts)
    assert layouts[0].page == 1 and layouts[2].page == 3
    # No cell duplication across pages
    seen = set()
    for g in layouts:
        for c in g.cells:
            assert c.shot_id not in seen
            seen.add(c.shot_id)
    assert len(seen) == 60


def test_regen_single_cell_changes_only_cell() -> None:
    """REQ-GRID-004: regenerate one cell, others byte-identical."""

    g = layout("s1", _shots(9), aspect="1:1")[0]
    g2 = regenerate_cell(g, cell_index=3, new_shot_id="s003-v2", new_caption="alt")
    assert g.cells != g2.cells
    assert g.cells[2].shot_id == "s003" and g2.cells[2].shot_id == "s003-v2"
    # Other cells unchanged (same SHOT_ID)
    for i in range(9):
        if i == 2:
            continue
        assert g.cells[i].shot_id == g2.cells[i].shot_id
    # SHA changes only when content changes
    assert g.grid_sha != g2.grid_sha


def test_grid_metadata_present(tmp_path: Path) -> None:
    """REQ-GRID-005: grid_sha + grid_id present in sidecar JSON."""

    g = layout("scene-x", _shots(9), aspect="9:16")[0]
    out = tmp_path / "grid_p1.png"
    render(g, out)
    assert out.exists()
    sidecar = out.with_suffix(".json")
    payload = json.loads(sidecar.read_text(encoding="utf-8"))
    assert payload["grid_id"] == g.grid_id
    assert payload["grid_sha"] == g.grid_sha
    assert payload["rows"] == g.rows and payload["cols"] == g.cols
    assert len(payload["cells"]) == 9


def test_render_byte_identical(tmp_path: Path) -> None:
    """The PNG renderer is deterministic given the same layout."""

    g = layout("scene-x", _shots(12), aspect="16:9")[0]
    a = tmp_path / "a.png"
    b = tmp_path / "b.png"
    render(g, a)
    render(g, b)
    assert a.read_bytes() == b.read_bytes()


def test_invalid_cell_regen_raises() -> None:
    g = layout("s", _shots(9), aspect="1:1")[0]
    with pytest.raises(ValueError):
        regenerate_cell(g, cell_index=10, new_shot_id="x")


def test_empty_shots_raises() -> None:
    with pytest.raises(ValueError):
        layout("s", [], aspect="9:16")
