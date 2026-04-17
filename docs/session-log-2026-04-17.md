# Session Log - 2026-04-17

## Scope completed in this session

- Executed the 2026-04-17 security hardening follow-up plan.
- Added trust-boundary guidance and a prompt-injection sanitizer flow.
- Wired sanitization metadata into fetched artifact collectors, including yfinance and FRED.
- Updated artifact validation so fetched artifacts missing `_sanitization` are flagged and downgraded.
- Switched path handling toward env-var-based separation for private docs and outputs.
- Rewrote Git history to remove sensitive material from repository history and force-pushed the rewritten refs.
- Removed the stale remote `master` branch so the remote now uses `main` only.
- Published the artifact-contract / patch-loop bundle at commit `a4c7970`.
- Added release notes at `docs/releases/2026-04-17-security-and-contracts.md`.

## Current canonical repo state

- Primary working folder: this `stock-analysis-agent` directory.
- Primary branch: `main`
- Remote tracking branch: `origin/main`
- Current published head: `a4c7970` (`feat: add run-local artifact contracts and patch loop`)
- Working tree status at handoff time: clean

## Local folder layout

- Use this folder as the main working repo going forward.
- The previous local clone was renamed to a sibling archive folder ending with `-archive-2026-04-17`.
- Treat the archive folder as backup only. It may contain older local-only state and should not be used as the active repo.

## Verification completed

- `python3 -m unittest discover tests -v` -> `29/29 OK`
- `python3 tools/contract_checks.py` -> `10 manifests / 44 cases OK`
- Remote branch cleanup verified so only `main` remains on `origin`
- Release notes file verified in the clean repo

## Important references

- Release notes: `docs/releases/2026-04-17-security-and-contracts.md`
- Sanitizer module: `tools/prompt_injection_filter.py`
- Artifact validator: `tools/artifact_validation.py`
- Contract checker: `tools/contract_checks.py`

## Resume guidance

- Open the clean `stock-analysis-agent` folder, not the archive folder.
- Assume `main` is the only active branch on the remote unless intentionally changed later.
- If a future session needs context, start with this file and the release notes.
- If something appears to be "missing" compared with the old local clone, check the archive folder before assuming it was deleted from the active repo.

## Follow-up continuation

- Added `tools/estimate_claude_cost.py` to summarize Claude Code session usage from local `~/.claude/projects/.../*.jsonl` logs.
- The estimator de-duplicates streamed assistant updates by message id, ignores zero-token synthetic events, and supports optional per-model pricing via a user-supplied JSON file.
- Added regression coverage in `tests/test_estimate_claude_cost.py`, including Unicode path normalization for macOS Korean paths and pricing / `--latest` CLI behavior.
- Added a bilingual pull note for the published `a4c7970` bundle at `docs/releases/2026-04-18-bilingual-pull-note.md`.
- Verification after the follow-up:
  - `python3 -m unittest discover tests -v` -> `32/32 OK`
  - `python3 tools/estimate_claude_cost.py --repo-cwd . --latest 5` -> recent repo sessions summarized successfully
- Latest 5 repo sessions observed in local Claude logs:
  - `assistant_messages`: `144`
  - `input_tokens`: `2260`
  - `output_tokens`: `127818`
  - `cache_creation_input_tokens`: `868743`
  - `cache_read_input_tokens`: `18620873`
  - model mix: `claude-opus-4-6` only
- Important limitation: the recent sessions found were mostly repo-maintenance / security-hardening work, not 2-3 representative end-user stock-analysis runs. The private design-doc TODO about per-analysis Claude cost is now unblocked tooling-wise, but still needs representative analysis sessions (or future live runs) before writing a defensible per-analysis estimate.
