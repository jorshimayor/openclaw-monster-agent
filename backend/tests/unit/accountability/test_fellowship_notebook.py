"""The generated notebook has to be a notebook Jupyter will actually open."""

import json
import sys
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

from fellowship.notebook import write_notebook  # noqa: E402
from src.agents.fellowship import load_config, position  # noqa: E402

START = date(2026, 9, 28)


def plan_for(week: int, path=None):
    config = load_config()
    config["start_date"] = START.isoformat()
    config["path"] = path
    from datetime import timedelta

    return position(START + timedelta(weeks=week - 1), config).plan


def test_the_notebook_is_valid_nbformat(tmp_path):
    nbformat = pytest.importorskip("nbformat")
    path = write_notebook(plan_for(1), tmp_path, today=START)
    notebook = nbformat.read(str(path), as_version=4)
    nbformat.validate(notebook)  # raises if not


def test_every_cell_has_an_id(tmp_path):
    """Declared nbformat_minor 5, so a missing id is a hard error in newer readers."""
    path = write_notebook(plan_for(1), tmp_path, today=START)
    cells = json.loads(path.read_text())["cells"]
    assert cells and all(c.get("id") for c in cells)
    assert len({c["id"] for c in cells}) == len(cells)


def test_the_week_is_carried_in_metadata(tmp_path):
    path = write_notebook(plan_for(9), tmp_path, today=START)
    meta = json.loads(path.read_text())["metadata"]["fellowship"]
    assert meta["week"] == 9


def test_an_existing_notebook_is_never_clobbered(tmp_path):
    """That file is where the week's thinking lives."""
    path = write_notebook(plan_for(1), tmp_path, today=START)
    path.write_text('{"cells": [], "mine": true}')
    again = write_notebook(plan_for(1), tmp_path, today=START)
    assert again == path
    assert json.loads(path.read_text()).get("mine") is True

    write_notebook(plan_for(1), tmp_path, today=START, force=True)
    assert json.loads(path.read_text()).get("mine") is None


def test_a_path_split_week_produces_that_path(tmp_path):
    path = write_notebook(plan_for(17, path="B"), tmp_path, today=START)
    assert json.loads(path.read_text())["metadata"]["fellowship"]["path"] == "B"


def test_regenerating_is_stable(tmp_path):
    """Positional ids, so --force gives a clean diff rather than churn."""
    first = write_notebook(plan_for(1), tmp_path, today=START).read_text()
    second = write_notebook(plan_for(1), tmp_path, today=START, force=True).read_text()
    assert first == second
