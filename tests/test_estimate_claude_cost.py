"""Tests for tools/estimate_claude_cost.py."""

from __future__ import annotations

import json
import pathlib
import subprocess
import sys
import tempfile
import unicodedata
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.estimate_claude_cost import discover_project_dirs, summarize_session  # noqa: E402

CLI = ROOT / "tools" / "estimate_claude_cost.py"


def _write_jsonl(path: pathlib.Path, records: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = "\n".join(json.dumps(record, ensure_ascii=False) for record in records) + "\n"
    path.write_text(payload, encoding="utf-8")


class EstimateClaudeCostTests(unittest.TestCase):
    def test_summarize_session_dedupes_streamed_assistant_updates(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo_cwd = pathlib.Path(tmp) / "repo"
            session_path = pathlib.Path(tmp) / "session.jsonl"
            _write_jsonl(
                session_path,
                [
                    {
                        "type": "user",
                        "timestamp": "2026-04-17T10:00:00Z",
                        "cwd": str(repo_cwd),
                        "sessionId": "abc",
                        "message": {
                            "role": "user",
                            "content": [{"type": "text", "text": "  Analyze   NVDA in Mode C   "}],
                        },
                    },
                    {
                        "type": "ai-title",
                        "timestamp": "2026-04-17T10:00:01Z",
                        "cwd": str(repo_cwd),
                        "sessionId": "abc",
                        "aiTitle": "NVDA Mode C",
                    },
                    {
                        "type": "assistant",
                        "timestamp": "2026-04-17T10:00:02Z",
                        "cwd": str(repo_cwd),
                        "sessionId": "abc",
                        "uuid": "u-1a",
                        "message": {
                            "id": "msg-1",
                            "model": "claude-opus-4-6",
                            "usage": {
                                "input_tokens": 100,
                                "output_tokens": 10,
                                "cache_creation_input_tokens": 1000,
                                "cache_read_input_tokens": 500,
                            },
                        },
                    },
                    {
                        "type": "assistant",
                        "timestamp": "2026-04-17T10:00:03Z",
                        "cwd": str(repo_cwd),
                        "sessionId": "abc",
                        "uuid": "u-1b",
                        "message": {
                            "id": "msg-1",
                            "model": "claude-opus-4-6",
                            "usage": {
                                "input_tokens": 100,
                                "output_tokens": 120,
                                "cache_creation_input_tokens": 1000,
                                "cache_read_input_tokens": 500,
                            },
                        },
                    },
                    {
                        "type": "assistant",
                        "timestamp": "2026-04-17T10:01:00Z",
                        "cwd": str(repo_cwd),
                        "sessionId": "abc",
                        "uuid": "u-2",
                        "message": {
                            "id": "msg-2",
                            "model": "claude-sonnet-4-5",
                            "usage": {
                                "input_tokens": 50,
                                "output_tokens": 25,
                                "cache_creation_input_tokens": 0,
                                "cache_read_input_tokens": 10,
                            },
                        },
                    },
                ],
            )

            summary = summarize_session(session_path)

            self.assertEqual(summary["session_id"], "abc")
            self.assertEqual(summary["title"], "NVDA Mode C")
            self.assertEqual(summary["first_user_text"], "Analyze NVDA in Mode C")
            self.assertEqual(summary["assistant_messages"], 2)
            self.assertEqual(
                summary["tokens"],
                {
                    "input_tokens": 150,
                    "output_tokens": 145,
                    "cache_creation_input_tokens": 1000,
                    "cache_read_input_tokens": 510,
                },
            )
            self.assertEqual(summary["models"]["claude-opus-4-6"]["assistant_messages"], 1)
            self.assertEqual(summary["models"]["claude-sonnet-4-5"]["assistant_messages"], 1)

    def test_discover_project_dirs_matches_repo_cwd(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            repo_a = root / "repo-a"
            repo_b = root / "repo-b"
            projects_dir = root / "projects"

            _write_jsonl(
                projects_dir / "project-a" / "s1.jsonl",
                [
                    {
                        "type": "user",
                        "timestamp": "2026-04-17T00:00:00Z",
                        "cwd": str(repo_a),
                        "sessionId": "a",
                        "message": {"role": "user", "content": [{"type": "text", "text": "A"}]},
                    }
                ],
            )
            _write_jsonl(
                projects_dir / "project-b" / "s2.jsonl",
                [
                    {
                        "type": "user",
                        "timestamp": "2026-04-17T00:00:00Z",
                        "cwd": str(repo_b),
                        "sessionId": "b",
                        "message": {"role": "user", "content": [{"type": "text", "text": "B"}]},
                    }
                ],
            )

            matches = discover_project_dirs(projects_dir, repo_a)
            self.assertEqual(matches, [projects_dir / "project-a"])

    def test_discover_project_dirs_normalizes_unicode_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            repo = root / "코딩 프로젝트" / "stock-analysis-agent"
            projects_dir = root / "projects"
            stored_cwd = unicodedata.normalize("NFD", str(repo))
            lookup_cwd = pathlib.Path(unicodedata.normalize("NFC", str(repo)))

            _write_jsonl(
                projects_dir / "unicode-project" / "s1.jsonl",
                [
                    {
                        "type": "user",
                        "timestamp": "2026-04-17T00:00:00Z",
                        "cwd": stored_cwd,
                        "sessionId": "unicode",
                        "message": {"role": "user", "content": [{"type": "text", "text": "A"}]},
                    }
                ],
            )

            matches = discover_project_dirs(projects_dir, lookup_cwd)
            self.assertEqual(matches, [projects_dir / "unicode-project"])

    def test_cli_applies_pricing_and_latest_filter(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            repo = root / "repo"
            projects_dir = root / "projects"
            project_dir = projects_dir / "stock-analysis"
            pricing_path = root / "pricing.json"

            _write_jsonl(
                project_dir / "older.jsonl",
                [
                    {
                        "type": "user",
                        "timestamp": "2026-04-16T00:00:00Z",
                        "cwd": str(repo),
                        "sessionId": "older",
                        "message": {"role": "user", "content": [{"type": "text", "text": "older"}]},
                    },
                    {
                        "type": "assistant",
                        "timestamp": "2026-04-16T00:00:01Z",
                        "cwd": str(repo),
                        "sessionId": "older",
                        "uuid": "older-a",
                        "message": {
                            "id": "older-msg",
                            "model": "claude-opus-4-6",
                            "usage": {
                                "input_tokens": 1_000_000,
                                "output_tokens": 500_000,
                                "cache_creation_input_tokens": 0,
                                "cache_read_input_tokens": 0,
                            },
                        },
                    },
                ],
            )
            _write_jsonl(
                project_dir / "newer.jsonl",
                [
                    {
                        "type": "user",
                        "timestamp": "2026-04-17T00:00:00Z",
                        "cwd": str(repo),
                        "sessionId": "newer",
                        "message": {"role": "user", "content": [{"type": "text", "text": "newer"}]},
                    },
                    {
                        "type": "assistant",
                        "timestamp": "2026-04-17T00:00:01Z",
                        "cwd": str(repo),
                        "sessionId": "newer",
                        "uuid": "newer-a",
                        "message": {
                            "id": "newer-msg",
                            "model": "claude-opus-4-6",
                            "usage": {
                                "input_tokens": 2_000_000,
                                "output_tokens": 1_000_000,
                                "cache_creation_input_tokens": 0,
                                "cache_read_input_tokens": 0,
                            },
                        },
                    },
                ],
            )
            pricing_path.write_text(
                json.dumps(
                    {
                        "default": {
                            "input_per_million": 2.0,
                            "output_per_million": 4.0,
                            "cache_write_per_million": 0.0,
                            "cache_read_per_million": 0.0,
                        }
                    }
                ),
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(CLI),
                    "--claude-projects-dir",
                    str(projects_dir),
                    "--repo-cwd",
                    str(repo),
                    "--pricing",
                    str(pricing_path),
                    "--latest",
                    "1",
                ],
                capture_output=True,
                text=True,
                cwd=str(ROOT),
            )
            self.assertEqual(result.returncode, 0, result.stderr)

            payload = json.loads(result.stdout)
            self.assertEqual(payload["session_count"], 1)
            self.assertEqual(payload["sessions"][0]["session_id"], "newer")
            self.assertEqual(payload["tokens"]["input_tokens"], 2_000_000)
            self.assertEqual(payload["cost"]["total_cost_usd"], 8.0)
            self.assertEqual(payload["sessions"][0]["cost"]["total_cost_usd"], 8.0)


if __name__ == "__main__":
    unittest.main()
