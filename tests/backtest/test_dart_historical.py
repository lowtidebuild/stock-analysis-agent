"""Tests for ``DartHistorical`` in tools.backtest.historical_adapters.

Covers Task 2.4b of the backtest harness plan
(``docs/superpowers/plans/2026-05-08-backtest-harness.md``):

- ``DartHistorical.fetch`` invokes the dart-collector subprocess with the
  expected ``--as-of``, ``--stock-code``, ``--output`` flags. ``--api-key``
  is added when set on the adapter.
- The adapter parses the script's output JSON and returns it.
- Non-zero subprocess exit raises ``HistoricalFetchError`` with stderr
  preserved and the failing ticker recorded for downstream telemetry.
- Default ``script_path`` resolves to the real dart-collector.py.
- Output paths are resolved before subprocess invocation so the script
  and adapter agree on the file location regardless of cwd.

Run via: ``python -m pytest tests/backtest/test_dart_historical.py -v``
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
    DartHistorical,
    HistoricalFetchError,
)


def test_dart_default_script_path_exists() -> None:
    adapter = DartHistorical()
    assert adapter.script_path.is_file(), (
        f"default script_path should resolve to a real file: {adapter.script_path}"
    )
    assert adapter.script_path.name == "dart-collector.py"


def test_dart_fetch_invokes_with_as_of_and_ticker(
    monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
) -> None:
    captured: dict[str, Any] = {}
    output_file = tmp_path / "dart-api-raw.json"

    def fake_run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        captured["cmd"] = cmd
        captured["kwargs"] = kwargs
        # Simulate a successful run by writing minimal output JSON.
        pathlib.Path(cmd[cmd.index("--output") + 1]).write_text(
            json.dumps(
                {
                    "stock_code": "005930",
                    "_backtest_meta": {
                        "as_of": "2025-03-31",
                        "freeze_strategy": "hybrid",
                        "caveats": ["dart_as_of_mode_applied"],
                    },
                }
            ),
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(
            args=cmd, returncode=0, stdout="{}", stderr=""
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    adapter = DartHistorical()
    adapter.fetch(
        ticker="005930",
        as_of=_dt.date(2025, 3, 31),
        output_path=output_file,
    )

    cmd = captured["cmd"]
    assert sys.executable in cmd[0] or cmd[0] == sys.executable
    assert str(adapter.script_path) in cmd

    def _flag_value(flag: str) -> str:
        idx = cmd.index(flag)
        return cmd[idx + 1]

    assert _flag_value("--stock-code") == "005930"
    assert _flag_value("--output") == str(output_file)
    assert _flag_value("--as-of") == "2025-03-31"
    # No api-key should appear unless the adapter was constructed with one.
    assert "--api-key" not in cmd


def test_dart_fetch_resolves_output_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
) -> None:
    """Adapter resolves output_path before invoking subprocess so the
    script and adapter agree on the file location regardless of cwd."""
    captured: dict[str, Any] = {}

    def fake_run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        captured["cmd"] = cmd
        out = pathlib.Path(cmd[cmd.index("--output") + 1])
        captured["output_arg"] = out
        out.write_text(
            json.dumps({"stock_code": "005930"}), encoding="utf-8"
        )
        return subprocess.CompletedProcess(
            args=cmd, returncode=0, stdout="{}", stderr=""
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.chdir(tmp_path)

    relative_output = pathlib.Path("subdir/dart.json")
    relative_output.parent.mkdir(parents=True, exist_ok=True)

    adapter = DartHistorical()
    adapter.fetch(
        ticker="005930",
        as_of=_dt.date(2025, 3, 31),
        output_path=relative_output,
    )
    assert captured["output_arg"].is_absolute()
    assert captured["output_arg"].resolve() == (tmp_path / relative_output).resolve()


def test_dart_fetch_raises_with_attributes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
) -> None:
    output_file = tmp_path / "dart-api-raw.json"

    def fake_run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            args=cmd,
            returncode=1,
            stdout="",
            stderr="DART API key not provided.",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    adapter = DartHistorical()
    with pytest.raises(HistoricalFetchError) as excinfo:
        adapter.fetch(
            ticker="005930",
            as_of=_dt.date(2025, 3, 31),
            output_path=output_file,
        )
    err = excinfo.value
    assert err.returncode == 1
    assert "DART API key not provided" in err.stderr
    assert err.ticker == "005930"
    assert err.as_of == _dt.date(2025, 3, 31)


def test_dart_fetch_returns_parsed_json(
    monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
) -> None:
    output_file = tmp_path / "dart-api-raw.json"
    fixture = {
        "stock_code": "005930",
        "corp_name": "삼성전자",
        "ttm_income_statement": {"revenue": 300000000},
        "_backtest_meta": {
            "as_of": "2025-03-31",
            "freeze_strategy": "hybrid",
            "caveats": ["dart_as_of_mode_applied"],
        },
    }

    def fake_run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        pathlib.Path(cmd[cmd.index("--output") + 1]).write_text(
            json.dumps(fixture, ensure_ascii=False), encoding="utf-8"
        )
        return subprocess.CompletedProcess(
            args=cmd, returncode=0, stdout="{}", stderr=""
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    adapter = DartHistorical()
    result = adapter.fetch(
        ticker="005930",
        as_of=_dt.date(2025, 3, 31),
        output_path=output_file,
    )

    assert result == fixture
    assert result["_backtest_meta"]["as_of"] == "2025-03-31"


def test_dart_api_key_passed_when_set(
    monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
) -> None:
    captured: dict[str, Any] = {}
    output_file = tmp_path / "dart-api-raw.json"

    def fake_run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        captured["cmd"] = cmd
        pathlib.Path(cmd[cmd.index("--output") + 1]).write_text(
            json.dumps({"stock_code": "005930"}), encoding="utf-8"
        )
        return subprocess.CompletedProcess(
            args=cmd, returncode=0, stdout="{}", stderr=""
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    adapter = DartHistorical(api_key="test-dart-key-456")
    adapter.fetch(
        ticker="005930",
        as_of=_dt.date(2025, 3, 31),
        output_path=output_file,
    )
    cmd = captured["cmd"]
    assert cmd[cmd.index("--api-key") + 1] == "test-dart-key-456"


def test_dart_custom_script_path_used(
    monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
) -> None:
    custom_script = tmp_path / "custom-dart.py"
    custom_script.write_text("# stub", encoding="utf-8")
    captured: dict[str, Any] = {}
    output_file = tmp_path / "dart-api-raw.json"

    def fake_run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        captured["cmd"] = cmd
        pathlib.Path(cmd[cmd.index("--output") + 1]).write_text(
            json.dumps({"stock_code": "005930"}), encoding="utf-8"
        )
        return subprocess.CompletedProcess(
            args=cmd, returncode=0, stdout="{}", stderr=""
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    adapter = DartHistorical(script_path=custom_script)
    adapter.fetch(
        ticker="005930",
        as_of=_dt.date(2025, 3, 31),
        output_path=output_file,
    )
    assert str(custom_script) in captured["cmd"]
