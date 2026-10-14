"""Companion progress cursor and order/gap warnings."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

logger = logging.getLogger(__name__)

_PROGRESS_VERSION = 1


def _iso_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _clamp_last(last: int | None, max_chapter_on_disk: int | None) -> int | None:
    """Lower high-water cursor to max chapter still on disk when truncated."""
    if last is None or max_chapter_on_disk is None:
        return last
    return min(last, max_chapter_on_disk)


@dataclass
class ProgressState:
    version: int = _PROGRESS_VERSION
    last_chapter_companioned: int | None = None
    last_run_at: str | None = None
    last_mode: Literal["progressive", "sweep"] | None = None
    gaps_known: list[int] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "last_chapter_companioned": self.last_chapter_companioned,
            "last_run_at": self.last_run_at,
            "last_mode": self.last_mode,
            "gaps_known": list(self.gaps_known),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ProgressState:
        gaps = data.get("gaps_known") or []
        return cls(
            version=int(data.get("version") or _PROGRESS_VERSION),
            last_chapter_companioned=(
                int(data["last_chapter_companioned"])
                if data.get("last_chapter_companioned") is not None
                else None
            ),
            last_run_at=data.get("last_run_at"),
            last_mode=data.get("last_mode"),
            gaps_known=[int(g) for g in gaps],
        )


def progress_path(story_state_dir: Path) -> Path:
    return story_state_dir / "companion" / "progress.json"


def load_progress(story_state_dir: Path) -> ProgressState:
    path = progress_path(story_state_dir)
    if not path.exists():
        return ProgressState()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return ProgressState()
        return ProgressState.from_dict(data)
    except (json.JSONDecodeError, OSError, TypeError, ValueError) as exc:
        logger.warning("Corrupt companion progress (%s); resetting", exc)
        return ProgressState()


def save_progress(story_state_dir: Path, state: ProgressState) -> None:
    path = progress_path(story_state_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state.to_dict(), indent=2) + "\n", encoding="utf-8")


def clamp_progress_to_disk(
    story_state_dir: Path,
    max_chapter_on_disk: int | None,
) -> ProgressState:
    """Persist cursor clamp when later chapters were removed (restore/truncate)."""
    current = load_progress(story_state_dir)
    clamped = _clamp_last(current.last_chapter_companioned, max_chapter_on_disk)
    if clamped == current.last_chapter_companioned:
        return current
    updated = ProgressState(
        version=current.version,
        last_chapter_companioned=clamped,
        last_run_at=current.last_run_at,
        last_mode=current.last_mode,
        gaps_known=list(current.gaps_known),
    )
    save_progress(story_state_dir, updated)
    logger.info(
        "Clamped companion progress cursor %s → %s (max on disk %s)",
        current.last_chapter_companioned,
        clamped,
        max_chapter_on_disk,
    )
    return updated


def compute_order_warnings(
    *,
    mode: Literal["progressive", "sweep"],
    chapter_number: int,
    gaps: list[int],
    progress: ProgressState,
    max_chapter_on_disk: int | None = None,
) -> list[str]:
    """Regression / skip warnings (still run). Does not mutate progress.

    When ``max_chapter_on_disk`` is set, the high-water cursor is clamped before
    comparing so phantom later chapters (post-restore truncate) do not warn.
    """
    warnings: list[str] = []
    last = _clamp_last(progress.last_chapter_companioned, max_chapter_on_disk)

    if mode == "progressive":
        if last is not None and chapter_number < last:
            warnings.append(
                f"Regression/rewrite: companioning chapter {chapter_number} after "
                f"chapter {last}; later chapters' continuity may be stale relative "
                f"to this rewrite."
            )
        if last is not None and chapter_number > last + 1:
            skipped = list(range(last + 1, chapter_number))
            warnings.append(
                f"Skip/gap: jumped from last companioned chapter {last} to "
                f"{chapter_number}; intermediate not yet companioned: {skipped}."
            )
        elif last is None and chapter_number > 1:
            warnings.append(
                f"Skip/gap: first companion run at chapter {chapter_number}; "
                f"chapters 1…{chapter_number - 1} not yet companioned."
            )
    else:
        if gaps:
            warnings.append(f"Sweep gaps: missing chapter numbers {gaps}.")

    return warnings


def update_progress_after_run(
    story_state_dir: Path,
    *,
    mode: Literal["progressive", "sweep"],
    chapter_number: int,
    gaps: list[int],
    max_chapter_in_run: int | None = None,
    max_chapter_on_disk: int | None = None,
) -> ProgressState:
    """Persist cursor after a successful companion run.

    Progressive rewrite of an earlier chapter does not lower the cursor while
    later chapters still exist. When the story was truncated, clamp down to
    ``max_chapter_on_disk``. Sweep sets cursor to max chapter in the run.
    """
    current = load_progress(story_state_dir)
    if mode == "sweep":
        n = max_chapter_in_run if max_chapter_in_run is not None else chapter_number
        new_last = (
            n
            if current.last_chapter_companioned is None
            else max(current.last_chapter_companioned, n)
        )
    else:
        if current.last_chapter_companioned is None:
            new_last = chapter_number
        else:
            new_last = max(current.last_chapter_companioned, chapter_number)

    new_last = _clamp_last(new_last, max_chapter_on_disk)

    updated = ProgressState(
        version=_PROGRESS_VERSION,
        last_chapter_companioned=new_last,
        last_run_at=_iso_now(),
        last_mode=mode,
        gaps_known=list(gaps),
    )
    save_progress(story_state_dir, updated)
    return updated


__all__ = [
    "ProgressState",
    "clamp_progress_to_disk",
    "compute_order_warnings",
    "load_progress",
    "progress_path",
    "save_progress",
    "update_progress_after_run",
]
