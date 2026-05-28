"""Tests for DART TTM reconstruction."""

from __future__ import annotations

import importlib.util
import io
import json
import pathlib
import unittest
import zipfile

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
