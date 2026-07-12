"""Tests for DART TTM reconstruction."""

from __future__ import annotations

import importlib.util
import io
import json
import pathlib
import sys
import unittest
import zipfile

from scripts.parity.validation import metrics_from_dart

ROOT = pathlib.Path(__file__).resolve().parents[1]
DART_COLLECTOR = ROOT / ".claude" / "skills" / "web-researcher" / "scripts" / "dart-collector.py"


def _load_dart_collector():
    spec = importlib.util.spec_from_file_location("test_dart_collector", DART_COLLECTOR)
    if spec is None or spec.loader is None:
        raise AssertionError("failed to load DART collector")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _is_field(value):
    return {"statement_type": "IS", "value": value}


class _FakeResponse:
    def __init__(self, payload: bytes):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return self.payload


def _corp_code_zip() -> bytes:
    xml = """<?xml version="1.0" encoding="UTF-8"?>
<result>
  <list>
    <corp_code>00126380</corp_code>
    <corp_name>삼성전자</corp_name>
    <stock_code>005930</stock_code>
  </list>
  <list>
    <corp_code>00164779</corp_code>
    <corp_name>SK하이닉스</corp_name>
    <stock_code>000660</stock_code>
  </list>
</result>
"""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("CORPCODE.xml", xml)
    return buffer.getvalue()


def _dart_payload(precision: str, *, fs_div_used: list[str] | None = None) -> dict:
    payload = {
        "confidence_grade": "A",
        "collection_timestamp": "2026-05-21T00:00:00Z",
        "ttm_income_statement": {
            "precision": precision,
            "calculation_note": "Current YTD proxy used because prior same-period filing was unavailable",
            "revenue": 333_000_000_000_000,
            "operating_income": 43_000_000_000_000,
            "net_income": 45_000_000_000_000,
        },
        "balance_sheet_latest": {
            "cash": 58_000_000_000_000,
            "short_term_debt": 18_000_000_000_000,
            "current_portion_lt_debt": 1_000_000_000_000,
            "long_term_debt": 6_000_000_000_000,
            "bonds_payable": 1_000_000_000_000,
        },
        "periods_detail": {
            "Annual": {
                "year": 2025,
                "metrics": {
                    "revenue": {"value": 333_000_000_000_000, "prior": 300_000_000_000_000},
                    "operating_cash_flow": {"value": 85_000_000_000_000},
                    "capex": {"value": 47_000_000_000_000},
                },
            }
        },
    }
    if fs_div_used is not None:
        payload["fs_div_used"] = fs_div_used
    return payload


def _yfinance_payload() -> dict:
    return {
        "status": "success",
        "collection_timestamp": "2026-05-21T00:00:00Z",
        "current_price": {"price": 60_000, "as_of": "2026-05-21"},
        "info": {"market_cap": 400_000_000_000_000},
    }


def test_corp_code_master_cache_reuses_download(monkeypatch, tmp_path):
    collector = _load_dart_collector()
    cache_path = tmp_path / "corp-code-map.json"
    monkeypatch.setenv("SAA_DART_CORP_CODE_CACHE_PATH", str(cache_path))
    monkeypatch.setenv("SAA_DART_CORP_CODE_CACHE_TTL_SECONDS", "86400")
    calls = []

    def fake_urlopen(_req, timeout):
        calls.append(timeout)
        return _FakeResponse(_corp_code_zip())

    monkeypatch.setattr(collector.urllib.request, "urlopen", fake_urlopen)

    assert collector.lookup_corp_code("test-key", "005930") == ("00126380", "삼성전자")
    assert collector.lookup_corp_code("test-key", "000660") == ("00164779", "SK하이닉스")
    assert calls == [30]

    cache_payload = json.loads(cache_path.read_text(encoding="utf-8"))
    assert cache_payload["schema_version"] == "dart-corp-code-map-v1"
    assert cache_payload["ttl_seconds"] == 86400
    assert cache_payload["entry_count"] == 2
    assert cache_payload["entries"]["005930"]["corp_code"] == "00126380"
    assert cache_payload["source_timestamp"]
    assert cache_payload["expires_at"]


def test_get_financial_statements_records_ofs_fallback(monkeypatch):
    collector = _load_dart_collector()
    requested_divisions = []

    def fake_dart_request(_endpoint, params):
        requested_divisions.append(params["fs_div"])
        if params["fs_div"] == "CFS":
            return {"status": "013"}
        return {"status": "000", "list": [{"account_id": "ifrs-full_Revenue"}]}

    monkeypatch.setattr(collector, "dart_request", fake_dart_request)

    rows, fs_div = collector.get_financial_statements("key", "corp", "2025", "11011")

    assert rows == [{"account_id": "ifrs-full_Revenue"}]
    assert fs_div == "OFS"
    assert requested_divisions == ["CFS", "OFS"]


def test_collector_output_records_fs_div_and_won_units(monkeypatch, tmp_path):
    collector = _load_dart_collector()
    output_path = tmp_path / "dart-api-raw.json"
    parsed = {
        "revenue": {
            "statement_type": "IS",
            "value": 120_000_000_000,
            "prior_period": 100_000_000_000,
            "account_name_kr": "매출액",
        },
        "operating_income": {
            "statement_type": "IS",
            "value": 12_000_000_000,
            "prior_period": 10_000_000_000,
            "account_name_kr": "영업이익",
        },
        "net_income": {
            "statement_type": "IS",
            "value": 9_000_000_000,
            "prior_period": 8_000_000_000,
            "account_name_kr": "당기순이익",
        },
        "cash": {
            "statement_type": "BS",
            "value": 30_000_000_000,
            "prior_period": 25_000_000_000,
            "account_name_kr": "현금및현금성자산",
        },
    }

    monkeypatch.setattr(
        collector,
        "get_corp_info",
        lambda _key, _stock: {
            "corp_code": "00126380",
            "corp_name": "삼성전자",
            "stock_name": "삼성전자",
            "ceo_nm": None,
            "ind_tp": None,
        },
    )
    monkeypatch.setattr(
        collector,
        "get_financial_statements",
        lambda _key, _corp, _year, report: ([{"report": report}], "OFS")
        if report == "11011"
        else ([], None),
    )
    monkeypatch.setattr(collector, "parse_financial_rows", lambda _rows: (parsed, []))
    monkeypatch.setattr(collector, "get_recent_disclosures", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "dart-collector.py",
            "--stock-code",
            "005930",
            "--output",
            str(output_path),
            "--api-key",
            "test-key",
        ],
    )

    collector.main()

    output = json.loads(output_path.read_text(encoding="utf-8"))
    expected_unit = "원 (KRW, raw amounts as filed — fnlttSinglAcntAll returns won)"
    assert output["fs_div_used"] == ["OFS"]
    assert output["periods_detail"]["Annual"]["fs_div"] == "OFS"
    assert output["ttm_income_statement"]["unit"] == expected_unit
    assert output["balance_sheet_latest"]["unit"] == expected_unit


def test_low_precision_dart_metrics_are_grade_c_with_note():
    metrics = metrics_from_dart(
        _dart_payload("low"),
        currency="KRW",
        yfinance=_yfinance_payload(),
    )

    for metric_name in ("revenue_ttm", "operating_margin", "net_margin"):
        assert metrics[metric_name]["grade"] == "C"
        assert "YTD proxy" in metrics[metric_name]["notes"]
    assert metrics["fcf_ttm"]["grade"] == "A"
    assert metrics["fcf_ttm"]["notes"].startswith("FY2025 full-year FCF")
    assert metrics["fcf_yield"]["notes"] == metrics["fcf_ttm"]["notes"]


def test_high_precision_dart_metrics_remain_grade_a():
    metrics = metrics_from_dart(
        _dart_payload("high"),
        currency="KRW",
        yfinance=_yfinance_payload(),
    )

    for metric_name in ("revenue_ttm", "operating_margin", "net_margin"):
        assert metrics[metric_name]["grade"] == "A"
        assert "notes" not in metrics[metric_name]


def test_medium_precision_annual_metrics_remain_grade_a_with_note():
    metrics = metrics_from_dart(
        _dart_payload("medium"),
        currency="KRW",
        yfinance=_yfinance_payload(),
    )

    assert metrics["revenue_ttm"]["grade"] == "A"
    assert "YTD proxy" in metrics["revenue_ttm"]["notes"]


def test_ofs_basis_is_prefixed_to_all_dart_metric_notes():
    metrics = metrics_from_dart(
        _dart_payload("high", fs_div_used=["OFS"]),
        currency="KRW",
        yfinance=_yfinance_payload(),
    )

    assert metrics
    assert all("별도(OFS) 재무 기준" in entry["notes"] for entry in metrics.values())


class DartTtmTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.collector = _load_dart_collector()

    def test_q3_prior_annual_and_prior_q3_compute_true_ttm(self):
        periods = {
            "Q3": {"parsed": {"revenue": _is_field(90), "operating_income": _is_field(9)}},
            "Annual": {"parsed": {"revenue": _is_field(120), "operating_income": _is_field(12)}},
            "Q3_prior": {"parsed": {"revenue": _is_field(80), "operating_income": _is_field(8)}},
        }

        ttm, note, precision = self.collector.estimate_ttm(periods)

        self.assertEqual(ttm["revenue"], 130)
        self.assertEqual(ttm["operating_income"], 13)
        self.assertIn("current Q3 YTD + prior annual - prior Q3 YTD", note)
        self.assertEqual(precision, "high")

    def test_q3_without_prior_period_is_labeled_ytd_proxy(self):
        periods = {
            "Q3": {"parsed": {"revenue": _is_field(90)}},
        }

        ttm, note, precision = self.collector.estimate_ttm(periods)

        self.assertEqual(ttm["revenue"], 90)
        self.assertIn("YTD proxy", note)
        self.assertEqual(precision, "low")

    def test_annual_only_is_not_labeled_current_ttm(self):
        periods = {
            "Annual": {"parsed": {"revenue": _is_field(120)}},
        }

        ttm, note, precision = self.collector.estimate_ttm(periods)

        self.assertEqual(ttm["revenue"], 120)
        self.assertIn("Latest annual 12M period", note)
        self.assertEqual(precision, "medium")


if __name__ == "__main__":
    unittest.main()
