"""Path resolution for Ghostreader config and per-manuscript state.

Config:
    config.yaml in the project root (found by walking up from CWD or
    the manuscript path).

Per-manuscript state (cache, LanceDB index, checkpoints):
    <project_root>/.ghostreader/cache/<sha256(resolved_path)[:16]>/

A ``source.txt`` breadcrumb inside each state dir records the original
manuscript path for discoverability.
"""

from __future__ import annotations

import hashlib
from pathlib import Path


def find_project_root(start: Path | None = None) -> Path | None:
    """Walk up from *start* (default: CWD) looking for ``config.yaml``.

    Returns the directory containing ``config.yaml``, or ``None``.
    """
    current = (start or Path.cwd()).resolve()
    if current.is_file():
        current = current.parent
    for directory in [current, *current.parents]:
        if (directory / "config.yaml").is_file():
            return directory
    return None


def config_path(start: Path | None = None) -> Path | None:
    """Return the path to ``config.yaml``, or ``None`` if not found.

    Searches from *start* first (e.g. manuscript path), then falls back
    to CWD so the config is found even when analyzing external manuscripts.
    """
    root = find_project_root(start)
    if root is not None:
        return root / "config.yaml"
    # Fallback: try CWD if start was something else
    if start is not None:
        root = find_project_root(Path.cwd())
        if root is not None:
            return root / "config.yaml"
    return None


def state_dir_for(manuscript_path: Path, project_root: Path | None = None) -> Path:
    """Return the per-manuscript state directory, creating it if needed.

    The directory lives under ``<project_root>/.ghostreader/cache/<hash>/``.
    If *project_root* is not given, it is discovered via ``find_project_root``
    (falling back to the manuscript's parent directory).

    A ``source.txt`` breadcrumb is written so the user can discover
    which manuscript a state dir belongs to.
    """
    if project_root is None:
        project_root = (
            find_project_root(manuscript_path)
            or find_project_root(Path.cwd())
            or manuscript_path.parent
        )

    resolved = str(manuscript_path.resolve())
    path_hash = hashlib.sha256(resolved.encode("utf-8")).hexdigest()[:16]
    state = project_root / ".ghostreader" / "cache" / path_hash
    state.mkdir(parents=True, exist_ok=True)

    breadcrumb = state / "source.txt"
    if not breadcrumb.exists():
        breadcrumb.write_text(resolved, encoding="utf-8")

    return state


def find_secrets_env(start: Path | None = None) -> Path | None:
    """Locate ``secrets/llm.env`` by walking up from *start* (default: CWD)."""
    current = (start or Path.cwd()).resolve()
    if current.is_file():
        current = current.parent
    for directory in [current, *current.parents]:
        candidate = directory / "secrets" / "llm.env"
        if candidate.is_file():
            return candidate
    return None


__all__ = [
    "config_path",
    "find_project_root",
    "find_secrets_env",
    "state_dir_for",
]
