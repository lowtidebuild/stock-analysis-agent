#!/usr/bin/env python3
"""
DART OpenAPI Collector
Fetches structured financial data for Korean stocks from DART (금융감독원 전자공시).

Usage:
  python dart-collector.py --stock-code 005930 --output output/runs/20260424T000000Z_005930/005930/dart-api-raw.json
  python dart-collector.py --stock-code 005930 --output output/runs/20260424T000000Z_005930/005930/dart-api-raw.json --api-key YOUR_KEY
  python dart-collector.py --stock-code 005930 --output ... --as-of 2024-06-30

API Key priority:
  1. --api-key argument
  2. DART_API_KEY environment variable
  3. DART_API_KEY in <repo-root>/.env (auto-loaded if python-dotenv installed)

DART OpenAPI docs: https://opendart.fss.or.kr/guide/main.do
"""

from __future__ import annotations

import argparse
import datetime as _dt
import io
import json
import os
import sys
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path


def _parse_iso_date(value: str) -> _dt.date:
    """Parse a strict ``YYYY-MM-DD`` date for ``--as-of``.

    Mirrors ``tools/backtest_runner.py::_parse_iso_date`` and the matching
    helper in ``yfinance-collector.py`` / ``fred-collector.py``. Raises
    ``argparse.ArgumentTypeError`` on any deviation (wrong separator,
    wrong field widths, invalid calendar date) so argparse converts the
    failure into a clean exit code 2. The pattern is duplicated rather
    than imported because hyphenated script filenames are not valid
    Python module names — keeping the helper local keeps each collector
    self-contained.
    """
    try:
        parsed = datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"--as-of must be YYYY-MM-DD (got {value!r}): {exc}"
        ) from exc
    return parsed

# Repo-root import for the trust-boundary sanitizer (CLAUDE.md §12).
_REPO_ROOT = Path(__file__).resolve().parents[4]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# Auto-load <repo>/.env if present so DART_API_KEY in .env works without
# manually exporting it before each call.
try:
    from dotenv import load_dotenv  # type: ignore
    _env_file = _REPO_ROOT / ".env"
    if _env_file.exists():
        load_dotenv(_env_file, override=False)
except ImportError:
    pass

from tools.prompt_injection_filter import SANITIZER_VERSION, sanitize_record  # noqa: E402

DART_BASE = "https://opendart.fss.or.kr/api"

# DART report codes
REPORT_CODES = [
    ("11014", "Q3"),     # 3분기보고서 (9-month cumulative)
    ("11012", "H1"),     # 반기보고서 (6-month cumulative)
    ("11013", "Q1"),     # 1분기보고서 (3-month)
    ("11011", "Annual"), # 사업보고서 (annual)
]

# Key Korean financial account names → standardized field names
ACCOUNT_MAP = {
    # Income Statement (IS)
    "매출액": "revenue",
    "영업수익": "revenue",          # financial sector alternative
    "순영업수익": "revenue",         # bank alternative
    "영업이익": "operating_income",
    "영업손실": "operating_income",  # negative
    "법인세차감전 순이익": "pretax_income",
    "법인세차감전순이익": "pretax_income",
    "당기순이익": "net_income",
    "당기순손실": "net_income",      # negative
    "지배기업 소유주지분 순이익": "net_income_controlling",
    "기본주당이익(손실)": "eps_basic",
    "희석주당이익(손실)": "eps_diluted",
    "기본주당순이익(손실)": "eps_basic",
    "희석주당순이익(손실)": "eps_diluted",
    # Balance Sheet (BS)
    "자산총계": "total_assets",
    "부채총계": "total_liabilities",
    "자본총계": "total_equity",
    "단기차입금": "short_term_debt",
    "유동성장기부채": "current_portion_lt_debt",
    "장기차입금": "long_term_debt",
    "사채": "bonds_payable",
    "현금및현금성자산": "cash",
    "현금및단기금융상품": "cash",     # alternative
    # Cash Flow (CF)
    "영업활동현금흐름": "operating_cash_flow",
    "투자활동현금흐름": "investing_cash_flow",
    "재무활동현금흐름": "financing_cash_flow",
    "유형자산의 취득": "capex",
    "유형자산취득": "capex",
}


def dart_request(endpoint, params):
    """Make a GET request to DART API. Returns parsed JSON or None on error."""
    url = f"{DART_BASE}/{endpoint}?" + urllib.parse.urlencode(params)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "StockAnalysisAgent/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return data
    except Exception as e:
        return {"status": "error", "message": str(e)}


def lookup_corp_code(api_key, stock_code):
    """Look up corp_code from stock_code via DART's corpCode.xml master list."""
    url = f"{DART_BASE}/corpCode.xml?crtfc_key={api_key}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "StockAnalysisAgent/1.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            z = zipfile.ZipFile(io.BytesIO(resp.read()))
            xml_data = z.read(z.namelist()[0])
        root = ET.fromstring(xml_data)
        for item in root.findall(".//list"):
            sc = (item.findtext("stock_code") or "").strip()
            if sc == stock_code:
                return item.findtext("corp_code", "").strip(), (item.findtext("corp_name") or "").strip()
    except Exception:
        pass
    return None, None


def get_corp_info(api_key, stock_code):
    """Get DART corp_code and company info from 6-digit stock code."""
    # Step 1: Resolve stock_code → corp_code via corpCode.xml
    corp_code, corp_name_from_xml = lookup_corp_code(api_key, stock_code)
    if not corp_code:
        return None

    # Step 2: Get detailed company info using corp_code
    data = dart_request("company.json", {"crtfc_key": api_key, "corp_code": corp_code})
    if data.get("status") == "000":
        return {
            "corp_code": corp_code,
            "corp_name": data.get("corp_name") or corp_name_from_xml,
            "stock_name": data.get("stock_name"),
            "ceo_nm": data.get("ceo_nm"),
            "ind_tp": data.get("induty_code"),
            "est_dt": data.get("est_dt"),
            "hm_url": data.get("hm_url"),
        }
    # Fallback: return minimal info from XML if company.json fails
    return {
        "corp_code": corp_code,
        "corp_name": corp_name_from_xml,
        "stock_name": corp_name_from_xml,
        "ceo_nm": None,
        "ind_tp": None,
        "est_dt": None,
        "hm_url": None,
    }


def get_financial_statements(api_key, corp_code, bsns_year, reprt_code):
    """
    Get consolidated (연결) financial statements.
    reprt_code: 11011=Annual, 11012=H1, 11013=Q1, 11014=Q3
    Returns list of account rows or empty list.
    """
    data = dart_request("fnlttSinglAcntAll.json", {
        "crtfc_key": api_key,
        "corp_code": corp_code,
        "bsns_year": bsns_year,
        "reprt_code": reprt_code,
        "fs_div": "CFS",   # 연결재무제표 (Consolidated Financial Statements)
    })
    if data.get("status") == "000":
        return data.get("list", [])
    # Fallback: try standalone (별도) if consolidated not available
    if data.get("status") in ("013", "020"):  # no data / not found
        data2 = dart_request("fnlttSinglAcntAll.json", {
            "crtfc_key": api_key,
            "corp_code": corp_code,
            "bsns_year": bsns_year,
            "reprt_code": reprt_code,
            "fs_div": "OFS",   # 별도재무제표
        })
        if data2.get("status") == "000":
            return data2.get("list", [])
    return []


def parse_amount(amount_str):
    """Parse DART amount string (may include commas, may be empty)."""
    if not amount_str or amount_str.strip() in ("-", ""):
        return None
    cleaned = amount_str.replace(",", "").strip()
    try:
        return int(cleaned)
    except ValueError:
        try:
            return float(cleaned)
        except ValueError:
            return None


def parse_financial_rows(rows):
    """
    Parse raw DART account rows into structured dict.
    Returns: {standardized_field: {current, prior, account_name, statement_type}}
    """
    result = {}
    raw = {}  # keyed by account_name for reference

    for row in rows:
        acnt_nm = (row.get("account_nm") or "").strip()
        sj_div = (row.get("sj_div") or "").strip()   # IS / BS / CFS
        current = parse_amount(row.get("thstrm_amount"))
        prior = parse_amount(row.get("frmtrm_amount"))

        raw[acnt_nm] = {
            "current": current,
            "prior": prior,
            "statement_type": sj_div,
        }

        std_field = ACCOUNT_MAP.get(acnt_nm)
        if std_field and std_field not in result:
            result[std_field] = {
                "value": current,
                "prior_period": prior,
                "account_name_kr": acnt_nm,
                "statement_type": sj_div,
            }

    return result, raw


def get_recent_disclosures(api_key, corp_code, days=90, end_dt=None):
    """Get recent disclosures (공시목록) for the past N days.

    ``end_dt`` (optional ``datetime.date``) caps the disclosure window via
    DART's native ``end_de`` parameter — i.e. true historical state for
    backtest mode, never disclosures filed after that date. When unset,
    the window ends today (existing production behavior).
    """
    if end_dt is None:
        end_anchor = datetime.today()
    elif isinstance(end_dt, _dt.date):
        end_anchor = datetime(end_dt.year, end_dt.month, end_dt.day)
    else:
        end_anchor = end_dt
    start_dt = end_anchor - timedelta(days=days)
    data = dart_request("list.json", {
        "crtfc_key": api_key,
        "corp_code": corp_code,
        "bgn_de": start_dt.strftime("%Y%m%d"),
        "end_de": end_anchor.strftime("%Y%m%d"),
        "page_count": "15",
    })
    if data.get("status") in ("000", "013"):
        items = data.get("list", [])
        return [
            {
                "date": item.get("rcept_dt"),
                "title": item.get("report_nm"),
                "type": item.get("pblntf_ty"),
                "url": f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={item.get('rcept_no')}",
            }
            for item in items
        ]
    return []


def estimate_ttm(periods):
    """
    Estimate TTM (Trailing Twelve Months) for income statement items.

    Logic:
    - If Q3 + prior Annual + prior Q3 are available:
      TTM = current Q3 YTD + prior annual - prior Q3 YTD
    - If only a current YTD period is available: expose it as a low-precision
      YTD proxy, not as verified TTM
    - If only Annual is available: expose latest annual as a 12M period, not
      current TTM

    Returns: ({field: value}, calculation_note, precision)
    """
    ttm = {}

    def income_fields(label):
        parsed = periods.get(label, {}).get("parsed", {})
        return {
            field: data.get("value")
            for field, data in parsed.items()
            if data.get("statement_type") == "IS" and data.get("value") is not None
        }

    q3 = income_fields("Q3")
    annual = income_fields("Annual")
    q3_prior = income_fields("Q3_prior")
    if q3 and annual and q3_prior:
        for field, current_value in q3.items():
            prior_annual_value = annual.get(field)
            prior_q3_value = q3_prior.get(field)
            if prior_annual_value is not None and prior_q3_value is not None:
                ttm[field] = current_value + prior_annual_value - prior_q3_value
        if ttm:
            return (
                ttm,
                "TTM = current Q3 YTD + prior annual - prior Q3 YTD",
                "high",
            )

    if q3:
        return (
            q3,
            "YTD proxy only: current Q3 YTD (9M). True TTM requires prior annual and prior Q3 YTD.",
            "low",
        )

    h1 = income_fields("H1")
    if h1:
        return (
            h1,
            "YTD proxy only: current H1 (6M). True TTM requires prior annual and prior H1 YTD.",
            "low",
        )

    if annual:
        return (
            annual,
            "Latest annual 12M period; current trailing twelve months unavailable.",
            "medium",
        )

    return {}, "No income statement period available for TTM calculation.", "unavailable"


def _attempt_typical_filing_deadline(year: int, reprt_code: str) -> _dt.date:
    """Conservative latest filing deadline for a (year, reprt_code) report.

    DART filers must submit periodic reports within statutory deadlines
    measured from the period end:

    - Annual (11011): period end Dec 31 → filed within 90 days → ~Mar 31
    - Q1 (11013): period end Mar 31 → filed within 45 days → ~May 15
    - H1 (11012): period end Jun 30 → filed within 45 days → ~Aug 14
    - Q3 (11014): period end Sep 30 → filed within 45 days → ~Nov 14

    We take the **latest** statutory deadline (not the earliest typical
    date) so that an attempt is allowed only when *every* filer of that
    period has had time to submit. Erring on the side of skipping a
    period is better than leaking a not-yet-filed report into a
    historical snapshot.
    """
    if reprt_code == "11011":
        return _dt.date(year + 1, 3, 31)
    if reprt_code == "11013":
        return _dt.date(year, 5, 15)
    if reprt_code == "11012":
        return _dt.date(year, 8, 14)
    if reprt_code == "11014":
        return _dt.date(year, 11, 14)
    # Unknown code: assume worst case — anchor to year end + 90 days.
    return _dt.date(year + 1, 3, 31)


def main():
    parser = argparse.ArgumentParser(description="DART OpenAPI financial data collector")
    parser.add_argument("--stock-code", required=True, help="6-digit KRX stock code (e.g. 005930)")
    parser.add_argument("--output", required=True, help="Output JSON file path")
    parser.add_argument("--api-key", default="", help="DART API key (overrides env var)")
    parser.add_argument(
        "--as-of",
        dest="as_of",
        type=_parse_iso_date,
        default=None,
        help=(
            "Historical as-of date (YYYY-MM-DD) for backtest mode. When "
            "set: disclosures are capped via DART's native end_de param "
            "and only periodic reports whose statutory filing deadline "
            "is on or before --as-of are considered. Skipping a period "
            "is preferred over leaking a not-yet-filed report. The "
            "snapshot carries top-level _backtest_meta and "
            "_backtest_caveats blocks mirroring yfinance/fred collectors."
        ),
    )
    args = parser.parse_args()

    if args.as_of is not None and args.as_of > _dt.date.today():
        parser.error(
            f"--as-of {args.as_of.isoformat()} is in the future "
            f"(today is {_dt.date.today().isoformat()})."
        )

    backtest_mode = args.as_of is not None
    backtest_caveats: list[str] = []

    api_key = args.api_key or os.environ.get("DART_API_KEY", "")
    if not api_key:
        result = {"status": "fail", "error": "DART API key not provided. Set DART_API_KEY env var or use --api-key."}
        print(json.dumps(result, ensure_ascii=False))
        sys.exit(1)

    # Step 1: Get corp info
    corp_info = get_corp_info(api_key, args.stock_code)
    if not corp_info:
        result = {"status": "fail", "error": f"Cannot find DART corp_code for stock code {args.stock_code}. Verify the 6-digit code is correct and listed on KRX."}
        print(json.dumps(result, ensure_ascii=False))
        sys.exit(1)

    corp_code = corp_info["corp_code"]
    if backtest_mode:
        anchor_year = args.as_of.year
    else:
        anchor_year = datetime.today().year
    current_year = anchor_year

    # Step 2: Collect financial statements across multiple periods
    periods = {}
    collected = []

    attempts = [
        (current_year, "11014", "Q3"),
        (current_year, "11012", "H1"),
        (current_year, "11013", "Q1"),
        (current_year - 1, "11011", "Annual"),
        (current_year - 1, "11014", "Q3_prior"),
        (current_year - 2, "11011", "Annual_prior2"),
    ]

    if backtest_mode:
        # Defensive filter: only consider attempts whose statutory filing
        # deadline is on or before --as-of. Reports whose deadline is
        # later than --as-of may not have been filed yet — including them
        # would leak future data into the backtest snapshot.
        filtered_attempts = [
            (year, reprt_code, label)
            for (year, reprt_code, label) in attempts
            if _attempt_typical_filing_deadline(year, reprt_code) <= args.as_of
        ]
        if len(filtered_attempts) < len(attempts):
            backtest_caveats.append("dart_attempts_filtered_by_filing_deadline")
        attempts = filtered_attempts
        backtest_caveats.append("dart_as_of_mode_applied")

    # Keep collecting the prior same-period report when available so true
    # TTM can be reconstructed instead of using current YTD as a proxy.
    for year, reprt_code, label in attempts:
        rows = get_financial_statements(api_key, corp_code, str(year), reprt_code)
        if rows:
            parsed, raw = parse_financial_rows(rows)
            periods[label] = {
                "year": year,
                "reprt_code": reprt_code,
                "label": label,
                "parsed": parsed,
                "row_count": len(rows),
            }
            collected.append(f"{year} {label}")

    if not periods:
        result = {"status": "fail", "error": f"No financial data found for {args.stock_code} ({corp_info.get('corp_name')}) in DART. Company may not file through DART (e.g. foreign-listed only)."}
        print(json.dumps(result, ensure_ascii=False))
        sys.exit(1)

    # Step 3: Estimate TTM for income statement
    ttm_data, ttm_note, ttm_precision = estimate_ttm(periods)

    # Step 4: Extract balance sheet from most recent period
    balance_sheet = {}
    most_recent_label = collected[0].split(" ", 1)[1] if collected else None
    if most_recent_label and most_recent_label in periods:
        for field, data in periods[most_recent_label]["parsed"].items():
            if data.get("statement_type") in ("BS", "BS_연결"):
                balance_sheet[field] = data["value"]

    # Step 5: Get recent disclosures
    disclosures = get_recent_disclosures(
        api_key,
        corp_code,
        days=90,
        end_dt=args.as_of if backtest_mode else None,
    )

    # Build structured output
    output = {
        "stock_code": args.stock_code,
        "corp_code": corp_code,
        "corp_name": corp_info.get("corp_name"),
        "stock_name": corp_info.get("stock_name"),
        "ceo": corp_info.get("ceo_nm"),
        "industry": corp_info.get("ind_tp"),
        "collection_timestamp": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "data_source": "DART OpenAPI (금융감독원 전자공시)",
        "tag": "[Filing]",
        "confidence_grade": "A",
        "note": "Structured data from DART OpenAPI — equivalent to SEC EDGAR API for US stocks",
        "collected_periods": collected,
        "ttm_income_statement": {
            "calculation_note": ttm_note,
            "precision": ttm_precision,
            "currency": "KRW",
            "unit": "백만원 (millions KRW) — verify unit from source filing",
            **ttm_data,
        },
        "balance_sheet_latest": {
            "period": most_recent_label,
            "currency": "KRW",
            **balance_sheet,
        },
        "periods_detail": {
            label: {
                "year": info["year"],
                "period_type": info["label"],
                "metrics": {
                    field: {"value": d["value"], "prior": d["prior_period"], "account_kr": d["account_name_kr"]}
                    for field, d in info["parsed"].items()
                }
            }
            for label, info in periods.items()
        },
        "recent_disclosures": disclosures,
    }

    if backtest_mode:
        # Mirror the contract established by yfinance-collector.py and
        # fred-collector.py: top-level _backtest_caveats list +
        # _backtest_meta block so downstream consumers (validators,
        # leakage detector) can detect historical snapshots without
        # opening every nested object.
        seen: set[str] = set()
        deduped: list[str] = []
        for c in backtest_caveats:
            if c not in seen:
                deduped.append(c)
                seen.add(c)
        output["_backtest_caveats"] = deduped
        output["_backtest_meta"] = {
            "as_of": args.as_of.isoformat(),
            "freeze_strategy": "hybrid",
            "caveats": deduped,
        }

    # Trust-boundary sanitization (CLAUDE.md §12) — required before any
    # downstream agent reads this artifact. DART account names and
    # disclosure titles are filer-controlled text and have to be treated
    # as untrusted data.
    output, sanitization_findings = sanitize_record(output)
    output["_sanitization"] = {
        "tool": "tools/prompt_injection_filter.py",
        "version": SANITIZER_VERSION,
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "redactions": len(sanitization_findings),
        "findings": sanitization_findings,
    }

    # Write output
    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    summary = {
        "status": "success",
        "corp_name": corp_info.get("corp_name"),
        "stock_code": args.stock_code,
        "collected_periods": collected,
        "ttm_fields": list(ttm_data.keys()),
        "balance_sheet_fields": list(balance_sheet.keys()),
        "disclosures_found": len(disclosures),
        "output_path": args.output,
    }
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
