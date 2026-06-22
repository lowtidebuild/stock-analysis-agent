# Codex Harness Entry

If you are Claude Code, ignore this file. Your session entry point is
`CLAUDE.md`, and the existing `.claude/agents/` plus `.claude/skills/`
harness remains authoritative for Claude Code.

If you are Codex or another non-Claude agent, follow this file. This repo was
built around Claude Code, so Codex should use the portable Python entrypoints
and read Claude skills as procedural documentation instead of trying to invoke
Claude-only tools.

## Operating Contract

- Preserve Claude behavior unless the user explicitly asks to change it.
- Prefer `python3`, not `python`, in this repo.
- Keep edits scoped. Do not refactor the Claude harness as part of a Codex run
  unless that is the stated task.
- Use blank over wrong: if a sourced value cannot be validated, leave it empty
  or let validation downgrade it instead of inventing a number.
- Keep raw tier artifacts out of analyst prompts by default. Facts should flow
  through `validated-data.json`, `evidence-pack.json`, and calculation outputs.
- Treat `_sanitization` blocks as trust-boundary metadata. Preserve them when
  generating or transforming portable artifacts.
- Do not read `.env*` files. Refer only to environment variable names in docs
  or guidance.

## Primary Commands

Mode A, headless single-stock analysis:

```bash
python3 scripts/run_analysis.py \
  --ticker AAPL \
  --mode A \
  --lang en \
  --market US \
  --run-id codex_aapl_a
```

Mode C, production dashboard path for Codex:

```bash
python3 scripts/run_mode_c.py \
  --ticker AAPL \
  --mode C \
  --lang en \
  --market US \
  --run-id codex_aapl_c
```

Useful Mode C flags:

- `--skip-network`: use offline/skipped collection paths where supported.
- `--reuse-collected`: reuse artifacts already present under
  `output/runs/{run_id}/`.
- `--peer-tickers MSFT,NVDA,GOOGL`: override peer selection.
- `--web-provider tavily|brave|none`: choose the portable web search wrapper.

`scripts/run_analysis.py` advertises `--mode C` for compatibility, but Codex
Mode C delivery should use `scripts/run_mode_c.py`.

## Claude-To-Codex Tool Mapping

| Claude concept | Codex equivalent |
| --- | --- |
| `CLAUDE.md` master orchestrator | Read for pipeline intent; use this `AGENTS.md` for Codex execution. |
| `.claude/skills/*/SKILL.md` | Read as step-by-step procedural docs, then run portable scripts manually. |
| `.claude/agents/*/AGENT.md` | Inline the role in the current Codex session; do not assume Claude Agent dispatch exists. |
| `WebSearch` | `python3 -m tools.web_search --query ... --ticker ... --market US --output ...` |
| `WebFetch` | `python3 -m tools.web_fetch --url ... --output ...` |
| Claude Read/Edit/Write tools | Use shell reads plus `apply_patch` for manual edits. |

When a Claude skill says to dispatch a subagent, Codex should inline that work
or use the existing Python runner that already encodes the stage. Keep the
artifact contract the same so Claude and Codex can share outputs.

## Environment Variables

Common names used by the portable path:

- `OPENAI_API_KEY`
- `OPENAI_ANALYST_MODEL`
- `ANALYST_BACKEND` (`fixture` enables deterministic offline analyst tests)
- `ANTHROPIC_API_KEY` (optional legacy/Claude-compatible backend support)
- `TAVILY_API_KEY` or `BRAVE_API_KEY` (optional portable web search providers)

Do not inspect local env files to discover these values. If a command needs a
missing key, report the variable name and use fixture/offline paths when
available.

## Verification

For docs-only changes, run the policy/documentation tests when relevant:

```bash
python3 -m pytest tests/test_prompt_examples_placeholders.py tests/test_standard_mode_search_policy.py -q
```

For runner or artifact changes, run the targeted tests first and then the full
suite:

```bash
python3 -m pytest tests/test_run_mode_c_entrypoint.py tests/test_web_search.py tests/test_web_fetch.py -q
python3 -m pytest tests/ -q
```

Mode C delivery is not complete unless
`output/runs/{run_id}/{ticker}/quality-report.json` has
`delivery_gate.result == "PASS"` and `ready_for_delivery == true`.
