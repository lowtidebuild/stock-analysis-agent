# Catalyst Schema

`output/catalyst-calendar.json` records, per ticker:

| Field | Type | Required | Notes |
|---|---|---|---|
| `ticker` | string | yes | |
| `date` | YYYY-MM-DD | yes | |
| `event` | string | yes | Human-readable event name |
| `category` | enum | yes | Earnings / Corporate / Industry / Macro (added 2026-05-06) |
| `impact` | enum | yes | H / M / L (added 2026-05-06) |
| `pre_announce_risk` | boolean | yes | True if ticker has >=2 prior pre-announces in last 8 quarters (added 2026-05-06) |
| `source` | string | yes | Source tag or snapshot reference per CLAUDE.md source contract |
| `description` | string | no | Display text, if different from `event` |
| `notes` | string | no | |

Backwards compatibility: legacy records without `category`, `impact`, or
`pre_announce_risk` default to `Corporate`, `M`, and `false` at read time.
