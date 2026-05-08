"""Tests for tools.backtest.historical_adapters.

Covers Task 2.1 of the backtest harness plan
(``docs/superpowers/plans/2026-05-08-backtest-harness.md``):

- ``YFinanceHistorical.fetch`` invokes the yfinance-collector subprocess
  with the expected ``--as-of``, ``--ticker``, ``--market``, ``--output``,
  and ``--bundle`` flags.
- The adapter parses the script's output JSON and returns it.
- Non-zero subprocess exit raises ``HistoricalFetchError`` with stderr
  preserved.
- Default ``script_path`` resolves to the real yfinance-collector.py.

Run via: ``python -m pytest tests/backtest/test_historical_adapters.py -v``
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
    HistoricalFetchError,
    YFinanceHistorical,
)


def test_default_script_path_exists() -> None:
    adapter = YFinanceHistorical()
    assert adapter.script_path.is_file(), (
        f"default script_path should resolve to a real file: {adapter.script_path}"
    )
    assert adapter.script_path.name == "yfinance-collector.py"


def test_fetch_invokes_script_with_as_of_flag(
    monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
) -> None:
    captured: dict[str, Any] = {}
    output_file = tmp_path / "yfinance-raw.json"

    def fake_run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        captured["cmd"] = cmd
        captured["kwargs"] = kwargs
        # Simulate a successful run by writing minimal output JSON.
        pathlib.Path(cmd[cmd.index("--output") + 1]).write_text(
            json.dumps({"ticker": "AAPL", "current_price": {"price": 150.0}}),
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(
            args=cmd, returncode=0, stdout="{}", stderr=""
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    adapter = YFinanceHistorical()
    adapter.fetch(
        ticker="AAPL",
        market="US",
        as_of=_dt.date(2025, 3, 31),
        output_path=output_file,
        bundle="standard",
    )

    cmd = captured["cmd"]
    # python interpreter + script path + flags
    assert sys.executable in cmd[0] or cmd[0] == sys.executable
    assert str(adapter.script_path) in cmd

    def _flag_value(flag: str) -> str:
        idx = cmd.index(flag)
        return cmd[idx + 1]

    assert _flag_value("--ticker") == "AAPL"
    assert _flag_value("--market") == "US"
    assert _flag_value("--output") == str(output_file)
    assert _flag_value("--bundle") == "standard"
    assert _flag_value("--as-of") == "2025-03-31"


def test_fetch_returns_parsed_json(
    monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
) -> None:
    output_file = tmp_path / "yfinance-raw.json"
    fixture = {
        "ticker": "AAPL",
        "market": "US",
        "current_price": {"price": 150.0, "currency": "USD"},
        "_backtest_meta": {
            "as_of": "2025-03-31",
            "freeze_strategy": "hybrid",
            "caveats": ["info_fields_use_current_state"],
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

    adapter = YFinanceHistorical()
    result = adapter.fetch(
        ticker="AAPL",
        market="US",
        as_of=_dt.date(2025, 3, 31),
        output_path=output_file,
    )

    assert result == fixture
    assert result["_backtest_meta"]["as_of"] == "2025-03-31"


def test_fetch_raises_on_nonzero_exit(
    monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
) -> None:
    output_file = tmp_path / "yfinance-raw.json"

    def fake_run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            args=cmd,
            returncode=2,
            stdout="",
            stderr="Current price unavailable for AAPL",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    adapter = YFinanceHistorical()
    with pytest.raises(HistoricalFetchError) as excinfo:
        adapter.fetch(
            ticker="AAPL",
            market="US",
            as_of=_dt.date(2025, 3, 31),
            output_path=output_file,
        )
    assert "Current price unavailable" in str(excinfo.value)
    err = excinfo.value
    assert err.returncode == 2
    assert err.stderr == "Current price unavailable for AAPL"
    assert err.ticker == "AAPL"
    assert err.as_of == _dt.date(2025, 3, 31)


def test_fetch_resolves_relative_output_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
) -> None:
    """Adapter resolves output_path before invoking subprocess so the
    script and adapter agree on the file location regardless of cwd."""
    captured: dict[str, Any] = {}

    def fake_run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        captured["cmd"] = cmd
        out = pathlib.Path(cmd[cmd.index("--output") + 1])
        captured["output_arg"] = out
        out.write_text(json.dumps({"ticker": "AAPL"}), encoding="utf-8")
        return subprocess.CompletedProcess(
            args=cmd, returncode=0, stdout="{}", stderr=""
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.chdir(tmp_path)

    relative_output = pathlib.Path("subdir/raw.json")
    relative_output.parent.mkdir(parents=True, exist_ok=True)

    adapter = YFinanceHistorical()
    adapter.fetch(
        ticker="AAPL",
        market="US",
        as_of=_dt.date(2025, 3, 31),
        output_path=relative_output,
    )
    assert captured["output_arg"].is_absolute()
    assert captured["output_arg"].resolve() == (tmp_path / relative_output).resolve()


def test_fetch_default_bundle_is_standard(
    monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
) -> None:
    captured: dict[str, Any] = {}
    output_file = tmp_path / "yfinance-raw.json"

    def fake_run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        captured["cmd"] = cmd
        pathlib.Path(cmd[cmd.index("--output") + 1]).write_text(
            json.dumps({"ticker": "AAPL"}), encoding="utf-8"
        )
        return subprocess.CompletedProcess(
            args=cmd, returncode=0, stdout="{}", stderr=""
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    adapter = YFinanceHistorical()
    adapter.fetch(
        ticker="AAPL",
        market="US",
        as_of=_dt.date(2025, 3, 31),
        output_path=output_file,
    )
    cmd = captured["cmd"]
    assert cmd[cmd.index("--bundle") + 1] == "standard"


def test_custom_script_path_used(
    monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
) -> None:
    custom_script = tmp_path / "custom-collector.py"
    custom_script.write_text("# stub", encoding="utf-8")
    captured: dict[str, Any] = {}
    output_file = tmp_path / "yfinance-raw.json"

    def fake_run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        captured["cmd"] = cmd
        pathlib.Path(cmd[cmd.index("--output") + 1]).write_text(
            json.dumps({"ticker": "AAPL"}), encoding="utf-8"
        )
        return subprocess.CompletedProcess(
            args=cmd, returncode=0, stdout="{}", stderr=""
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    adapter = YFinanceHistorical(script_path=custom_script)
    adapter.fetch(
        ticker="AAPL",
        market="US",
        as_of=_dt.date(2025, 3, 31),
        output_path=output_file,
    )
    assert str(custom_script) in captured["cmd"]
