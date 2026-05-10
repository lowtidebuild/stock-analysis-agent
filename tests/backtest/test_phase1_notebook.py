"""Tests for the Phase 1 analysis notebook (Task 5.3).

The notebook ships **without execution outputs** — it's a clean
template intended to be opened and run after a cohort actually
completes (Chunk 6). These tests validate notebook structure, not
runtime behaviour.

Run via: ``python -m pytest tests/backtest/test_phase1_notebook.py -v``
"""

from __future__ import annotations

import json
import pathlib

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
NOTEBOOK_PATH = (
    REPO_ROOT
    / "evals"
    / "backtest"
    / "notebook"
    / "2026-05-08-phase1-results.ipynb"
)
README_PATH = REPO_ROOT / "evals" / "backtest" / "notebook" / "README.md"


@pytest.fixture(scope="module")
def notebook() -> dict:
    assert NOTEBOOK_PATH.exists(), f"notebook missing at {NOTEBOOK_PATH}"
    with NOTEBOOK_PATH.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def test_notebook_path_under_repo() -> None:
    assert NOTEBOOK_PATH.is_file()
    # Sanity: lives where the spec says it should.
    assert NOTEBOOK_PATH.parent.name == "notebook"
    assert NOTEBOOK_PATH.parent.parent.name == "backtest"


def test_notebook_is_valid_json() -> None:
    # Re-parse independently of the fixture so a parse failure surfaces
    # as a clear, isolated test failure.
    with NOTEBOOK_PATH.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    assert isinstance(data, dict)
    assert data.get("nbformat") == 4
    assert "cells" in data and isinstance(data["cells"], list)


def test_notebook_has_expected_cell_count(notebook: dict) -> None:
    assert len(notebook["cells"]) >= 12


def test_notebook_has_no_execution_outputs(notebook: dict) -> None:
    for idx, cell in enumerate(notebook["cells"]):
        if cell.get("cell_type") != "code":
            continue
        assert cell.get("outputs") == [], (
            f"code cell #{idx} has non-empty outputs — notebook should "
            f"ship clean"
        )
        assert cell.get("execution_count") is None, (
            f"code cell #{idx} has execution_count set — notebook should "
            f"ship clean"
        )


def _cell_source_text(cell: dict) -> str:
    src = cell.get("source", "")
    if isinstance(src, list):
        return "".join(src)
    return str(src)


def test_notebook_imports_metrics_module(notebook: dict) -> None:
    code_cells = [c for c in notebook["cells"] if c.get("cell_type") == "code"]
    assert code_cells, "notebook has no code cells"
    first_text = _cell_source_text(code_cells[0])
    assert "compute_ic" in first_text, (
        "first code cell should import compute_ic from tools.backtest.metrics"
    )


def test_notebook_uses_jsonl_path(notebook: dict) -> None:
    found = any(
        "results.jsonl" in _cell_source_text(c) for c in notebook["cells"]
    )
    assert found, "no cell mentions results.jsonl"


def test_notebook_metadata_python(notebook: dict) -> None:
    meta = notebook.get("metadata", {})
    kernelspec = meta.get("kernelspec", {})
    assert kernelspec.get("name") == "python3"


def test_notebook_readme_exists() -> None:
    assert README_PATH.is_file(), f"README missing at {README_PATH}"
    text = README_PATH.read_text(encoding="utf-8")
    # Light content checks — just enough to ensure it's a real README.
    assert "pandas" in text
    assert "matplotlib" in text
