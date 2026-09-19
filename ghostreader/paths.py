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


# Directory names that are too generic to use as a manuscript identifier.
_GENERIC_DIR_NAMES = {"chapters", "src", "manuscript", "manuscripts", "content", "text", "docs"}

# Matches chapter-001.md / chapter-18.md (same convention as markdown_loader).
_CHAPTER_FILE_RE = re.compile(r"^chapter-(\d+)\.md$", re.IGNORECASE)


def _slug_token(name: str) -> str:
    """Sanitize one path segment to a filesystem-safe slug token."""
    slug = re.sub(r"[^\w\-]", "-", name.lower()).strip("-")
    return slug or "manuscript"


def _skip_generic_parents(directory: Path) -> Path:
    """Walk up past generic folder names like ``chapters``."""
    current = directory
    while current.name.lower() in _GENERIC_DIR_NAMES and current.parent != current:
        current = current.parent
    return current


def _manuscript_slug_parts(manuscript_path: Path) -> list[str]:
    """Derive state-dir path parts under ``.ghostreader/``.

    Examples:
        ``novel.epub`` → ``[novel]``
        ``my-novel/`` (dir) → ``[my-novel]``
        ``bay-four/chapters/`` → ``[bay-four]``
        ``the-jailer-s-wound/chapters/chapter-018.md``
            → ``[the-jailer-s-wound, chapter-018]``
        ``standalone.md`` → ``[standalone]``
    """
    resolved = manuscript_path.resolve()

    if resolved.is_file():
        chapter_match = _CHAPTER_FILE_RE.match(resolved.name)
        if chapter_match:
            story_dir = _skip_generic_parents(resolved.parent)
            story = _slug_token(story_dir.name)
            chapter = f"chapter-{int(chapter_match.group(1)):03d}"
            # Avoid story/story when the file sits directly under a non-generic dir
            # named like the chapter; still nest under the story folder.
            if story_dir == resolved.parent and story == _slug_token(resolved.stem):
                return [chapter]
            return [story, chapter]
        return [_slug_token(resolved.stem)]

    # Directory manuscript
    target = _skip_generic_parents(resolved)
    return [_slug_token(target.name)]


def _manuscript_slug(manuscript_path: Path) -> str:
    """Flat slug for display/compat (joins nested parts with ``/``)."""
    return "/".join(_manuscript_slug_parts(manuscript_path))


def manuscript_display_name(manuscript_path: Path) -> str:
    """Human label for reports and terminal headers.

    ``.../the-jailer-s-wound/chapters/chapter-018.md``
        → ``the-jailer-s-wound · Chapter 18``
    """
    resolved = manuscript_path.resolve()
    if resolved.is_file():
        chapter_match = _CHAPTER_FILE_RE.match(resolved.name)
        if chapter_match:
            story_dir = _skip_generic_parents(resolved.parent)
            return f"{story_dir.name} · Chapter {int(chapter_match.group(1))}"
        return resolved.stem
    target = _skip_generic_parents(resolved)
    return target.name


def state_dir_for(manuscript_path: Path, project_root: Path | None = None) -> Path:
    """Return the per-manuscript state directory, creating it if needed.

    The directory lives under ``<project_root>/.ghostreader/<slug>/``.
    Single ``chapter-NNN.md`` files nest as
    ``.ghostreader/<story>/chapter-NNN/`` so Autonomicon-style per-chapter
    calls group under the story without colliding.
    """
    if project_root is None:
        project_root = (
            find_project_root(manuscript_path)
            or find_project_root(Path.cwd())
            or manuscript_path.parent
        )

    parts = _manuscript_slug_parts(manuscript_path)
    state = project_root / ".ghostreader"
    for part in parts:
        state = state / part
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
    "manuscript_display_name",
    "next_report_path",
    "state_dir_for",
]
