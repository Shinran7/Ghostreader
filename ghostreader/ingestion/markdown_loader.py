"""Markdown manuscript loader with chapter-NNN.md detection."""

from __future__ import annotations

import re
from pathlib import Path

from ghostreader.ingestion import Chapter

# Matches filenames like chapter-001.md, chapter-42.md, etc.
_CHAPTER_RE = re.compile(r"^chapter-(\d+)\.md$", re.IGNORECASE)


def load_markdown(path: Path) -> list[Chapter]:
    """Load chapters from a markdown file or directory.

    Auto-detects whether *path* is a single .md file or a directory of
    chapter-NNN.md files, and returns sorted Chapter objects.
    """
    path = path.resolve()

    if path.is_file():
        return _load_single_file(path)

    if path.is_dir():
        return _load_directory(path)

    msg = f"Path does not exist or is not a file/directory: {path}"
    raise FileNotFoundError(msg)


def _load_single_file(path: Path) -> list[Chapter]:
    """Treat a single .md file as one chapter (chapter 1)."""
    if path.suffix.lower() != ".md":
        msg = f"Expected a .md file, got: {path.name}"
        raise ValueError(msg)

    content = path.read_text(encoding="utf-8")
    title = _extract_title(content, fallback=path.stem)
    return [Chapter(title=title, content=content, chapter_number=1, source_path=path)]


def _load_directory(directory: Path) -> list[Chapter]:
    """Load all chapter-NNN.md files from *directory*, sorted by filename."""
    md_files = sorted(directory.glob("*.md"))

    if not md_files:
        msg = f"No .md files found in {directory}"
        raise FileNotFoundError(msg)

    chapters: list[Chapter] = []

    for filepath in md_files:
        match = _CHAPTER_RE.match(filepath.name)
        chapter_num = int(match.group(1)) if match else len(chapters) + 1
        content = filepath.read_text(encoding="utf-8")
        title = _extract_title(content, fallback=filepath.stem)
        chapters.append(
            Chapter(
                title=title,
                content=content,
                chapter_number=chapter_num,
                source_path=filepath,
            )
        )

    return chapters


def _extract_title(content: str, *, fallback: str) -> str:
    """Pull the first Markdown heading (# ...) as the chapter title."""
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped.removeprefix("# ").strip()
    return fallback
