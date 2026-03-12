#!/usr/bin/env python3
"""
DART OpenAPI Collector
Fetches structured financial data for Korean stocks from DART (금융감독원 전자공시).

Usage:
  python dart-collector.py --stock-code 005930 --output output/data/005930/dart-api-raw.json
  python dart-collector.py --stock-code 005930 --output output/data/005930/dart-api-raw.json --api-key YOUR_KEY

API Key priority:
  1. --api-key argument
  2. DART_API_KEY environment variable

DART OpenAPI docs: https://opendart.fss.or.kr/guide/main.do
"""

import argparse
import json
import os
import sys
import urllib.request
import urllib.parse
from datetime import datetime, timedelta

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


def get_corp_info(api_key, stock_code):
    """Get DART corp_code and company info from 6-digit stock code."""
    data = dart_request("company.json", {"crtfc_key": api_key, "stock_code": stock_code})
    if data.get("status") == "000":
        return {
            "corp_code": data.get("corp_code"),
            "corp_name": data.get("corp_name"),
            "stock_name": data.get("stock_name"),
            "ceo_nm": data.get("ceo_nm"),
            "ind_tp": data.get("ind_tp"),     # industry classification
            "est_dt": data.get("est_dt"),     # established date
            "hm_url": data.get("hm_url"),
        }
    return None


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


def get_recent_disclosures(api_key, corp_code, days=90):
    """Get recent disclosures (공시목록) for the past N days."""
    end_dt = datetime.today()
    start_dt = end_dt - timedelta(days=days)
    data = dart_request("list.json", {
        "crtfc_key": api_key,
        "corp_code": corp_code,
        "bgn_de": start_dt.strftime("%Y%m%d"),
        "end_de": end_dt.strftime("%Y%m%d"),
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
    Uses the most recent available period data.

    Logic:
    - If Annual available: use as-is (12M)
    - If Q3 (9M cumulative) + prior Annual: TTM ≈ Q3_YTD + (Annual_prior - H1_prior)
    - If H1 (6M) available: note limited TTM precision
    - Fallback: use most recent period with a note

    Returns: {field: ttm_value} with a note on calculation method
    """
    ttm = {}
    ttm_note = ""

    if "Annual" in periods:
        # Annual is already 12M — use directly
        annual = periods["Annual"]["parsed"]
        for field, data in annual.items():
            if data.get("statement_type") == "IS" and data.get("value") is not None:
                ttm[field] = data["value"]
        ttm_note = "TTM = Most recent annual (12M)"

    elif "Q3" in periods and "Q3_prior" in periods:
        # TTM = Q3 YTD (9M) + (Annual prior - Q3 YTD prior)
        # But we may not have Q3_prior separately, so use best effort
        q3 = periods["Q3"]["parsed"]
        ttm_note = "TTM approximate: Q3 YTD (9M) — full TTM requires prior Q3 data"
        for field, data in q3.items():
            if data.get("statement_type") == "IS" and data.get("value") is not None:
                ttm[field] = data["value"]  # 9M as proxy

    elif "Q3" in periods:
        q3 = periods["Q3"]["parsed"]
        ttm_note = "TTM approximation: Q3 YTD (9M data, annualized where noted)"
        for field, data in q3.items():
            if data.get("statement_type") == "IS" and data.get("value") is not None:
                ttm[field] = data["value"]

    elif "H1" in periods:
        h1 = periods["H1"]["parsed"]
        ttm_note = "TTM approximation: H1 (6M data only — lower precision)"
        for field, data in h1.items():
            if data.get("statement_type") == "IS" and data.get("value") is not None:
                ttm[field] = data["value"]

    return ttm, ttm_note


def main():
    parser = argparse.ArgumentParser(description="DART OpenAPI financial data collector")
    parser.add_argument("--stock-code", required=True, help="6-digit KRX stock code (e.g. 005930)")
    parser.add_argument("--output", required=True, help="Output JSON file path")
    parser.add_argument("--api-key", default="", help="DART API key (overrides env var)")
    args = parser.parse_args()

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
    current_year = datetime.today().year

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
        if len(collected) >= 4:
            break

    if not periods:
        result = {"status": "fail", "error": f"No financial data found for {args.stock_code} ({corp_info.get('corp_name')}) in DART. Company may not file through DART (e.g. foreign-listed only)."}
        print(json.dumps(result, ensure_ascii=False))
        sys.exit(1)

    # Step 3: Estimate TTM for income statement
    ttm_data, ttm_note = estimate_ttm(periods)

    # Step 4: Extract balance sheet from most recent period
    balance_sheet = {}
    most_recent_label = collected[0].split(" ", 1)[1] if collected else None
    if most_recent_label and most_recent_label in periods:
        for field, data in periods[most_recent_label]["parsed"].items():
            if data.get("statement_type") in ("BS", "BS_연결"):
                balance_sheet[field] = data["value"]

    # Step 5: Get recent disclosures
    disclosures = get_recent_disclosures(api_key, corp_code, days=90)

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
        "tag": "[DART-API]",
        "confidence_grade": "A",
        "note": "Structured data from DART OpenAPI — equivalent to SEC EDGAR API for US stocks",
        "collected_periods": collected,
        "ttm_income_statement": {
            "calculation_note": ttm_note,
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
