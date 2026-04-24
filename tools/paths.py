"""Repository-aware path resolution.

Centralizes the env-var override pattern used to keep run-time work
product (``output/``) and private design docs (``docs/superpowers/``)
out of the repo when desired, while preserving the historical in-repo
defaults for back-compat.

Env vars
--------
- ``STOCK_ANALYSIS_DATA_DIR`` — overrides where pipeline artifacts go.
  Defaults to ``<repo>/output``.
- ``STOCK_ANALYSIS_PRIVATE_DOCS_DIR`` — overrides where internal plans
  and specs live. Defaults to ``<repo>/docs/superpowers``.

Both env vars accept ``~`` and are returned as ``pathlib.Path``. The
helpers do **not** create the directory; the caller decides.
"""

from __future__ import annotations

import os
import pathlib

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent

_DEFAULT_DATA_DIR = REPO_ROOT / "output"
_DEFAULT_PRIVATE_DOCS_DIR = REPO_ROOT / "docs" / "superpowers"


def _resolve(env_name: str, default: pathlib.Path) -> pathlib.Path:
    raw = os.environ.get(env_name)
    if not raw:
        return default
    path = pathlib.Path(os.path.expanduser(raw))
    return path if path.is_absolute() else REPO_ROOT / path


def data_dir() -> pathlib.Path:
    """Return the runtime data directory.

    Honors ``$STOCK_ANALYSIS_DATA_DIR`` if set, else ``<repo>/output``.
    """
    return _resolve("STOCK_ANALYSIS_DATA_DIR", _DEFAULT_DATA_DIR)


def private_docs_dir() -> pathlib.Path:
    """Return the directory holding private internal plans and specs.

    Honors ``$STOCK_ANALYSIS_PRIVATE_DOCS_DIR`` if set, else
    ``<repo>/docs/superpowers``.
    """
    return _resolve("STOCK_ANALYSIS_PRIVATE_DOCS_DIR", _DEFAULT_PRIVATE_DOCS_DIR)


def data_path(*parts: str) -> pathlib.Path:
    """Build a path under the resolved data directory."""
    return data_dir().joinpath(*parts)


def runtime_path(path: str | pathlib.Path) -> pathlib.Path:
    """Resolve a runtime or repo-relative path.

    Historical manifests and eval cases store runtime paths as ``output/...``.
    When ``$STOCK_ANALYSIS_DATA_DIR`` is set, those paths should resolve under
    the configured data root instead of the repository's ``output/``.
    Non-runtime relative paths remain repository-relative.
    """
    candidate = pathlib.Path(os.path.expanduser(str(path)))
    if candidate.is_absolute():
        return candidate
    parts = candidate.parts
    if parts and parts[0] == "output":
        return data_path(*parts[1:])
    return REPO_ROOT / candidate


__all__ = [
    "REPO_ROOT",
    "data_dir",
    "data_path",
    "private_docs_dir",
    "runtime_path",
]
