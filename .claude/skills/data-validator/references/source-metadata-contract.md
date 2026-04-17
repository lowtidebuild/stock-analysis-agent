# Source Metadata Contract

This file defines the canonical metadata fields that every verified metric should carry after Step 5 validation.

## Why This Exists

The repository historically mixed provenance tags such as `[KR-Web]`, `[DART-API]`, `[Calculated]`, and `[≈]`. That made it hard to:

- enforce a single quality-check rule set
- distinguish issuer material from regulatory filings
- compare run artifacts reliably across US and Korean equities
- validate artifacts automatically

The active contract below replaces those ad-hoc tags.

## Canonical Fields

Every metric entry should include:

```json
{
  "value": 175.50,
  "grade": "A",
  "source_type": "filing",
  "source_authority": "regulatory",
  "display_tag": "[Filing]",
  "tag": "[Filing]",
  "sources": ["Financial Datasets MCP (SEC filing data)"],
  "source_values": null,
  "notes": null,
  "approximate": false,
  "as_of_date": "2026-03-28",
  "period_end": "2025-12-31"
}
```

## `source_type`

| Value | Meaning | Default `display_tag` |
|-------|---------|-----------------------|
| `filing` | SEC / DART regulatory filing data | `[Filing]` |
| `company_release` | Issuer IR release, earnings call, newsroom item | `[Company]` |
| `portal_global` | Yahoo Finance, MarketWatch, MacroTrends, etc. | `[Portal]` |
| `portal_kr` | 네이버금융, FnGuide, KIND, etc. | `[KR-Portal]` |
| `calculated` | Derived from verified inputs | `[Calc]` |
| `estimate` | Sell-side consensus or target-price estimate | `[Est]` |
| `macro` | Government / central-bank macro data | `[Macro]` |
| `internal` | Internal-only artifact metadata, not for user display | *(no display tag)* |

## `source_authority`

| Value | Meaning |
|-------|---------|
| `regulatory` | SEC, DART, or equivalent regulator |
| `issuer` | Company-published material |
| `government` | Government or central bank |
| `market_portal` | Financial portal / aggregator |
| `sell_side` | Analyst consensus / brokerage estimate |
| `derived` | Deterministic calculation from validated inputs |
| `internal` | Internal pipeline metadata |

## Canonical `display_tag`

Only these tags are valid in active artifacts:

- `[Filing]`
- `[Company]`
- `[Portal]`
- `[KR-Portal]`
- `[Calc]`
- `[Est]`
- `[Macro]`

## Legacy Alias Mapping

| Legacy Tag | Canonical Handling |
|------------|--------------------|
| `[DART-API]` | `source_type=filing`, `display_tag=[Filing]` |
| `[KR-Web]` | `source_type=portal_kr`, `display_tag=[KR-Portal]` |
| `[Calculated]` | `source_type=calculated`, `display_tag=[Calc]` |
| `[Web]` | `source_type=portal_global`, `display_tag=[Portal]` |
| `[≈]` | Set `approximate=true`; infer real provenance from `sources` |

## Non-Negotiable Rules

1. `grade` and `display_tag` are different things. A metric can be Grade B `[Company]` or Grade A `[Calc]`.
2. Issuer releases are not regulatory filings. Do not label them `[Filing]`.
3. Approximation is not provenance. Use `approximate=true`, not a fake tag.
4. Grade D metrics must have `value=null`, `display_tag=null`, and `exclusion_reason`.
5. Output generators should render `display_tag` and never invent a new tag inline.
