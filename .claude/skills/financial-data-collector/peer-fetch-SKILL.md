# Peer Mini-Fetch — SKILL.md

**Role**: Step 2.7 — After the research plan is written, fetch a lightweight 8-metric snapshot for each `peer_tickers[]` so that the Mode C Peer Comparison table renders with real `[Portal]` Grade B numbers instead of `[Est] peer reference` placeholders.
**Triggered by**: market-router Step 2.7 (Mode C and Mode D only — never Mode A or Mode B)
**Reads**: `output/runs/{run_id}/{ticker}/research-plan.json` → `peer_tickers[]`
**Writes**: `output/runs/{run_id}/peers/{TICKER}.json` (run-local) AND `output/data/peers-cache/{TICKER}.json` (24h shared cache)
**Script**: `.claude/skills/financial-data-collector/scripts/peer-fetch.py`

---

## When to invoke

| Output Mode | Invoke peer-fetch? | Reason |
|-------------|---------------------|--------|
| Mode A (briefing) | No | Briefing has no peer table |
| Mode B (comparison HTML) | No | Each ticker is fetched as a *subject*, not a peer |
| Mode C (dashboard) | **Yes** | Section 6 peer table requires symmetric data |
| Mode D (memo DOCX) | **Yes** | Section 8 peer comparison requires symmetric data |

Skip the call if `peer_tickers[]` is empty (rare, but possible for SPACs / brand-new IPOs).

## Inputs

| Input | Source | Required |
|-------|--------|----------|
| `peer_tickers` | `research-plan.json` | yes (3–5 tickers) |
| `run_id` | session state / artifact-manager | yes |
| Cache directory | `output/data/peers-cache/` | yes (auto-created) |
| Per-ticker timeout | 30 seconds | default |
| Cache TTL | 24 hours | default |

## CLI invocation

```bash
python .claude/skills/financial-data-collector/scripts/peer-fetch.py \
  --tickers MSFT META AMZN AAPL \
  --output-dir output/runs/{run_id}/peers/ \
  --cache-dir  output/data/peers-cache/ \
  --cache-ttl-hours 24 \
  --timeout 30
```

The script prints a JSON summary to stdout and exits **0** if at least one peer was collected, **1** if every peer failed.

## Per-ticker output schema

`output/runs/{run_id}/peers/{TICKER}.json` (and the cache mirror) contain:

```json
{
  "ticker": "MSFT",
  "company_name": "Microsoft Corporation",
  "currency": "USD",
  "collection_timestamp": "2026-05-07T00:00:00Z",
  "data_source": "yfinance (peer mini-fetch)",
  "tag": "[Portal]",
  "confidence_grade": "B",
  "metrics": {
    "current_price": 425.30,
    "market_cap": 3158000000000,
    "pe_forward": 31.5,
    "ev_ebitda": 22.5,
    "revenue_growth_yoy": 16.0,
    "operating_margin": 44.5,
    "fcf_yield": 2.22,
    "beta": 0.91
  },
  "_sanitization": {
    "tool": "tools/prompt_injection_filter.py",
    "version": "1",
    "redactions": 0,
    "findings": []
  },
  "cache_expires_at": "2026-05-08T00:00:00Z"
}
```

`metrics` is a fixed 8-key dict. Missing metrics become `null` (Grade D for that field), but the key always exists so downstream renderers do not need to special-case schema variants.

A failed peer (network error, invalid symbol, malformed payload) gets:

```json
{
  "ticker": "BAD",
  "status": "error",
  "error": "RuntimeError: yfinance exploded",
  "confidence_grade": "D",
  "metrics": { "current_price": null, ... },
  "_sanitization": { ... }
}
```

## Cache behavior (24h TTL)

- Cache key = `output/data/peers-cache/{TICKER}.json`
- Hit (file exists AND `cache_expires_at` > now) → no yfinance call. The cached payload is also mirrored into the run-local `output/runs/{run_id}/peers/`.
- Miss / expired → fresh `yfinance.Ticker(t).info` call; cache file is rewritten with a new `cache_expires_at = now + 24h`.
- Cache shared across runs ⇒ second analysis of the same sector within 24h pays no yfinance latency.

## Trust boundary (CLAUDE.md §12)

Every peer payload passes through `tools.prompt_injection_filter.sanitize_record` BEFORE it hits disk. `_sanitization` is mandatory; analysts must refuse peer files that lack it.

## Error handling

| Failure | Behavior |
|---------|----------|
| `yfinance` not installed | Per-peer error record (Grade D), other peers continue |
| Network/HTTP error on one ticker | Per-peer error record, other peers continue |
| Per-ticker timeout (>30s) | Per-peer error record |
| Empty `peer_tickers[]` | No-op; orchestrator skips Step 2.7 |
| All peers fail | Exit code 1; analyst still runs but Mode C peer table renders the ⚠️ "데이터 미수집" row |

## Downstream consumers

- **Analyst Agent (`.claude/agents/analyst/AGENT.md`)** — reads every `output/runs/{run_id}/peers/*.json` and merges the metrics into `sections.peer_comparison[]` with `tag="[Portal]"` and `grade="B"`. Subject ticker keeps its own (richer) metrics.
- **Dashboard template** (`.claude/skills/dashboard-generator/references/html-template.md`) — peer rows show grade badges; missing metrics render as `—`; entirely absent peers render as a `⚠️ 데이터 미수집` row.

## Completion check

- [ ] Mode is C or D (otherwise skip)
- [ ] `peer_tickers[]` non-empty
- [ ] `output/runs/{run_id}/peers/` exists
- [ ] One JSON file written per peer ticker
- [ ] Each JSON contains `_sanitization` block
- [ ] Cache directory updated for every freshly fetched ticker
