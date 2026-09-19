"""Resolve progressive vs sweep companion invoke scope and load chapters 1…N."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from ghostreader.ingestion import Chapter
from ghostreader.ingestion.markdown_loader import load_markdown
from ghostreader.paths import (
    _CHAPTER_FILE_RE,
    _skip_generic_parents,
    manuscript_display_name,
    story_slug_for,
)
from ghostreader.seed import load_seed_meta

CompanionMode = Literal["progressive", "sweep"]


@dataclass
class DiscoveryResult:
    """Resolved companion input: mode, chapters 1…N, gaps, seed."""

    mode: CompanionMode
    path: Path
    story_slug: str
    story_dir: Path
    chapters_dir: Path
    chapter_number: int  # N (progressive target or sweep focus/max)
    chapters: list[Chapter]
    gaps: list[int] = field(default_factory=list)
    seed_meta: dict[str, Any] = field(default_factory=dict)
    manuscript_name: str = ""
    warnings: list[str] = field(default_factory=list)


def _list_chapter_files(chapters_dir: Path) -> dict[int, Path]:
    found: dict[int, Path] = {}
    for filepath in sorted(chapters_dir.glob("chapter-*.md")):
        match = _CHAPTER_FILE_RE.match(filepath.name)
        if match:
            found[int(match.group(1))] = filepath
    return found


def _load_up_to(chapters_dir: Path, n: int) -> tuple[list[Chapter], list[int]]:
    """Load chapter-*.md with number <= n; report missing numbers in 1…n."""
    files = _list_chapter_files(chapters_dir)
    present = sorted(num for num in files if num <= n)
    gaps = [i for i in range(1, n + 1) if i not in files]
    chapters: list[Chapter] = []
    for num in present:
        chapters.extend(load_markdown(files[num]))
    return chapters, gaps


def discover(
    path: Path,
    *,
    chapter_override: int | None = None,
) -> DiscoveryResult:
    """Resolve story root, mode, and chapters 1…N for companion.

    Raises
    ------
    FileNotFoundError
        Path missing.
    ValueError
        Non-numbered standalone .md or empty chapter series.
    """
    path = path.resolve()
    if not path.exists():
        raise FileNotFoundError(f"Path does not exist: {path}")

    warnings: list[str] = []

    if path.is_file():
        match = _CHAPTER_FILE_RE.match(path.name)
        if not match:
            raise ValueError(
                f"Companion needs a numbered chapter-NNN.md or a chapters directory; "
                f"got '{path.name}'. Use `ghostreader analyze` for standalone files."
            )
        n = int(match.group(1))
        chapters_dir = path.parent
        story_dir = _skip_generic_parents(chapters_dir)
        mode: CompanionMode = "progressive"
        chapters, gaps = _load_up_to(chapters_dir, n)
        if not chapters:
            raise ValueError(f"No chapter-*.md files found under {chapters_dir}")
        if gaps:
            warnings.append(
                f"Gap: missing chapter file(s) in 1…{n}: {gaps}"
            )
        manuscript_name = manuscript_display_name(path)
        seed_meta = load_seed_meta(path)
        return DiscoveryResult(
            mode=mode,
            path=path,
            story_slug=story_slug_for(path),
            story_dir=story_dir,
            chapters_dir=chapters_dir,
            chapter_number=n,
            chapters=chapters,
            gaps=gaps,
            seed_meta=seed_meta,
            manuscript_name=manuscript_name,
            warnings=warnings,
        )

    # Directory: treat as chapters dir or story path containing chapters/
    chapters_dir = path
    files = _list_chapter_files(chapters_dir)
    if not files:
        nested = path / "chapters"
        if nested.is_dir() and _list_chapter_files(nested):
            chapters_dir = nested
            files = _list_chapter_files(chapters_dir)
    if not files:
        raise ValueError(
            f"No chapter-*.md files found in {path}. "
            "Companion sweep needs a numbered chapter series."
        )

    max_n = max(files)
    focus = chapter_override if chapter_override is not None else max_n
    if focus not in files:
        raise ValueError(
            f"Chapter {focus} not found under {chapters_dir} "
            f"(available: {sorted(files)})"
        )
    # Sweep continuity uses full loaded set ≤ max present; craft focus = override or max.
    chapters, gaps = _load_up_to(chapters_dir, max_n)
    if gaps:
        warnings.append(f"Sweep gaps: missing chapter file(s) in 1…{max_n}: {gaps}")
    story_dir = _skip_generic_parents(chapters_dir)
    seed_meta = load_seed_meta(chapters_dir)
    manuscript_name = f"{story_dir.name} · Sweep"
    if chapter_override is not None:
        manuscript_name = f"{story_dir.name} · Chapter {focus} (sweep)"

    return DiscoveryResult(
        mode="sweep",
        path=path,
        story_slug=story_slug_for(path),
        story_dir=story_dir,
        chapters_dir=chapters_dir,
        chapter_number=focus,
        chapters=chapters,
        gaps=gaps,
        seed_meta=seed_meta,
        manuscript_name=manuscript_name,
        warnings=warnings,
    )


__all__ = ["DiscoveryResult", "discover"]
