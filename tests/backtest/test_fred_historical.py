"""Tests for ``FredHistorical`` in tools.backtest.historical_adapters.

Covers Task 2.2b of the backtest harness plan
(``docs/superpowers/plans/2026-05-08-backtest-harness.md``):

- ``FredHistorical.fetch`` invokes the fred-collector subprocess with the
  expected ``--as-of``, ``--output`` flags. ``--market KR`` is added when
  ``include_kr=True``.
- The adapter parses the script's output JSON and returns it.
- Non-zero subprocess exit raises ``HistoricalFetchError`` with stderr
  preserved. FRED is series-based (not ticker-based), so ``ticker`` is
  recorded as the sentinel ``"<fred>"`` on the exception (we still want
  the attribute present for callers that uniformly read it).
- Default ``script_path`` resolves to the real fred-collector.py.

Run via: ``python -m pytest tests/backtest/test_fred_historical.py -v``
"""

from __future__ import annotations

import datetime as _dt
import json
import pathlib
import subprocess
import sys
from typing import Any

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.backtest.historical_adapters import (  # noqa: E402
    FredHistorical,
    HistoricalFetchError,
)


def test_fred_default_script_path_exists() -> None:
    adapter = FredHistorical()
    assert adapter.script_path.is_file(), (
        f"default script_path should resolve to a real file: {adapter.script_path}"
    )
    assert adapter.script_path.name == "fred-collector.py"


def test_fred_fetch_invokes_with_as_of(
    monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
) -> None:
    captured: dict[str, Any] = {}
    output_file = tmp_path / "fred-snapshot.json"

    def fake_run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        captured["cmd"] = cmd
        captured["kwargs"] = kwargs
        # Simulate a successful run by writing minimal output JSON.
        pathlib.Path(cmd[cmd.index("--output") + 1]).write_text(
            json.dumps(
                {
                    "source": "FRED",
                    "_backtest_meta": {
                        "as_of": "2025-03-31",
                        "freeze_strategy": "hybrid",
                        "caveats": ["macro_observation_end_applied"],
                    },
                }
            ),
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(
            args=cmd, returncode=0, stdout="{}", stderr=""
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    adapter = FredHistorical()
    adapter.fetch(
        as_of=_dt.date(2025, 3, 31),
        output_path=output_file,
    )

    cmd = captured["cmd"]
    assert sys.executable in cmd[0] or cmd[0] == sys.executable
    assert str(adapter.script_path) in cmd

    def _flag_value(flag: str) -> str:
        idx = cmd.index(flag)
        return cmd[idx + 1]

    assert _flag_value("--output") == str(output_file)
    assert _flag_value("--as-of") == "2025-03-31"
    # FRED is series-based — no --ticker, no --market by default.
    assert "--ticker" not in cmd
    assert "--market" not in cmd


def test_fred_fetch_passes_market_kr_when_include_kr(
    monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
) -> None:
    captured: dict[str, Any] = {}
    output_file = tmp_path / "fred-snapshot.json"

    def fake_run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        captured["cmd"] = cmd
        pathlib.Path(cmd[cmd.index("--output") + 1]).write_text(
            json.dumps({"source": "FRED"}), encoding="utf-8"
        )
        return subprocess.CompletedProcess(
            args=cmd, returncode=0, stdout="{}", stderr=""
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    adapter = FredHistorical()
    adapter.fetch(
        as_of=_dt.date(2025, 3, 31),
        output_path=output_file,
        include_kr=True,
    )
    cmd = captured["cmd"]
    assert cmd[cmd.index("--market") + 1] == "KR"


def test_fred_fetch_passes_api_key_when_set(
    monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
) -> None:
    captured: dict[str, Any] = {}
    output_file = tmp_path / "fred-snapshot.json"

    def fake_run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        captured["cmd"] = cmd
        pathlib.Path(cmd[cmd.index("--output") + 1]).write_text(
            json.dumps({"source": "FRED"}), encoding="utf-8"
        )
        return subprocess.CompletedProcess(
            args=cmd, returncode=0, stdout="{}", stderr=""
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    adapter = FredHistorical(api_key="test-key-123")
    adapter.fetch(
        as_of=_dt.date(2025, 3, 31),
        output_path=output_file,
    )
    cmd = captured["cmd"]
    assert cmd[cmd.index("--api-key") + 1] == "test-key-123"


def test_fred_fetch_resolves_relative_output_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
) -> None:
    """Adapter resolves output_path before invoking subprocess so the
    script and adapter agree on the file location regardless of cwd."""
    captured: dict[str, Any] = {}

    def fake_run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        captured["cmd"] = cmd
        out = pathlib.Path(cmd[cmd.index("--output") + 1])
        captured["output_arg"] = out
        out.write_text(json.dumps({"source": "FRED"}), encoding="utf-8")
        return subprocess.CompletedProcess(
            args=cmd, returncode=0, stdout="{}", stderr=""
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.chdir(tmp_path)

    relative_output = pathlib.Path("subdir/fred.json")
    relative_output.parent.mkdir(parents=True, exist_ok=True)

    adapter = FredHistorical()
    adapter.fetch(
        as_of=_dt.date(2025, 3, 31),
        output_path=relative_output,
    )
    assert captured["output_arg"].is_absolute()
    assert captured["output_arg"].resolve() == (tmp_path / relative_output).resolve()


def test_fred_fetch_raises_with_attributes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
) -> None:
    output_file = tmp_path / "fred-snapshot.json"

    def fake_run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            args=cmd,
            returncode=1,
            stdout="",
            stderr="FRED API key not provided.",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    adapter = FredHistorical()
    with pytest.raises(HistoricalFetchError) as excinfo:
        adapter.fetch(
            as_of=_dt.date(2025, 3, 31),
            output_path=output_file,
        )
    err = excinfo.value
    assert err.returncode == 1
    assert "FRED API key not provided" in err.stderr
    # FRED is series-based; we use a sentinel ticker so the exception
    # contract stays uniform with YFinanceHistorical / SECHistorical.
    assert err.ticker == "<fred>"
    assert err.as_of == _dt.date(2025, 3, 31)


def test_fred_fetch_returns_parsed_json(
    monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
) -> None:
    output_file = tmp_path / "fred-snapshot.json"
    fixture = {
        "source": "FRED",
        "common": {"DGS10": {"value": 4.25, "date": "2025-03-31"}},
        "_backtest_meta": {
            "as_of": "2025-03-31",
            "freeze_strategy": "hybrid",
            "caveats": ["macro_observation_end_applied"],
        },
    }

    def fake_run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        pathlib.Path(cmd[cmd.index("--output") + 1]).write_text(
            json.dumps(fixture), encoding="utf-8"
        )
        return subprocess.CompletedProcess(
            args=cmd, returncode=0, stdout="{}", stderr=""
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    adapter = FredHistorical()
    result = adapter.fetch(
        as_of=_dt.date(2025, 3, 31),
        output_path=output_file,
    )

    assert result == fixture
    assert result["_backtest_meta"]["as_of"] == "2025-03-31"


def test_fred_custom_script_path_used(
    monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
) -> None:
    custom_script = tmp_path / "custom-fred.py"
    custom_script.write_text("# stub", encoding="utf-8")
    captured: dict[str, Any] = {}
    output_file = tmp_path / "fred-snapshot.json"

    def fake_run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        captured["cmd"] = cmd
        pathlib.Path(cmd[cmd.index("--output") + 1]).write_text(
            json.dumps({"source": "FRED"}), encoding="utf-8"
        )
        return subprocess.CompletedProcess(
            args=cmd, returncode=0, stdout="{}", stderr=""
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    adapter = FredHistorical(script_path=custom_script)
    adapter.fetch(
        as_of=_dt.date(2025, 3, 31),
        output_path=output_file,
    )
    assert str(custom_script) in captured["cmd"]
