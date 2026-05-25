"""Path resolution for Ghostreader config and per-manuscript state.

Config:
    config.yaml in the project root (found by walking up from CWD or
    the manuscript path).

Per-manuscript state (LanceDB index, cache, reports):
    <project_root>/.ghostreader/<manuscript-name>/
"""

from __future__ import annotations

import datetime
import re
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


def _manuscript_slug(manuscript_path: Path) -> str:
    """Derive a human-readable directory name from the manuscript path."""
    name = manuscript_path.stem if manuscript_path.is_file() else manuscript_path.name
    # Sanitize to filesystem-safe slug
    slug = re.sub(r"[^\w\-]", "-", name.lower()).strip("-")
    return slug or "manuscript"


def state_dir_for(manuscript_path: Path, project_root: Path | None = None) -> Path:
    """Return the per-manuscript state directory, creating it if needed.

    The directory lives under ``<project_root>/.ghostreader/<name>/``
    using the manuscript's human-readable name.
    """
    if project_root is None:
        project_root = (
            find_project_root(manuscript_path)
            or find_project_root(Path.cwd())
            or manuscript_path.parent
        )

    slug = _manuscript_slug(manuscript_path)
    state = project_root / ".ghostreader" / slug
    state.mkdir(parents=True, exist_ok=True)

    # Breadcrumb so we can trace slug back to the original path
    breadcrumb = state / "source.txt"
    if not breadcrumb.exists():
        breadcrumb.write_text(str(manuscript_path.resolve()), encoding="utf-8")

    return state


def next_report_path(state: Path) -> Path:
    """Return the next available report path in ``<state>/reports/``.

    Naming: ``report-YYYY-MM-DD.md``, ``report-YYYY-MM-DD-2.md``, etc.
    """
    reports_dir = state / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    today = datetime.date.today().isoformat()
    base = f"report-{today}"
    candidate = reports_dir / f"{base}.md"
    if not candidate.exists():
        return candidate

    n = 2
    while True:
        candidate = reports_dir / f"{base}-{n}.md"
        if not candidate.exists():
            return candidate
        n += 1


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
    "next_report_path",
    "state_dir_for",
]
