"""Import-only tests for collector sanitization wiring."""

from __future__ import annotations

import importlib.util
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _load_module(path: pathlib.Path):
    module_name = "test_" + path.stem.replace("-", "_")
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"failed to load module spec for {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class CollectorSanitizationTests(unittest.TestCase):
    def test_collectors_expose_sanitize_record(self):
        collector_paths = [
            ROOT / ".claude" / "skills" / "financial-data-collector" / "scripts" / "yfinance-collector.py",
            ROOT / ".claude" / "skills" / "web-researcher" / "scripts" / "fred-collector.py",
        ]

        for path in collector_paths:
            with self.subTest(path=str(path.relative_to(ROOT))):
                module = _load_module(path)
                self.assertTrue(hasattr(module, "sanitize_record"))
                self.assertTrue(callable(module.sanitize_record))


if __name__ == "__main__":
    unittest.main()
