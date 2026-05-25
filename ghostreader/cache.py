"""Analysis caching and checkpoint-resume for Ghostreader.

Two complementary persistence mechanisms:

**Cache** (hash-based skip) — SHA-256 of each chapter's content.  On re-analysis,
chapters whose hash matches the stored result are skipped entirely.  Stored in
``.ghostreader/cache.json``.

**Checkpoint** (failure recovery) — after each chapter's agent pipeline
completes, results are written to ``.ghostreader/checkpoint.json``.  On API
failure the caller saves progress; the next ``analyze`` run detects the partial
checkpoint and resumes from the first incomplete chapter.

Both files live under the per-manuscript state directory
(see ``ghostreader.paths.state_dir_for``).
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_CACHE_FILE = "cache.json"
_CHECKPOINT_FILE = "checkpoint.json"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _chapter_content_hash(content: str) -> str:
    """Return the SHA-256 hex digest of *content*."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Data containers
# ---------------------------------------------------------------------------

@dataclass
class CacheEntry:
    """A single cached chapter result."""

    chapter_number: int
    content_hash: str
    result: dict[str, Any]
    cached_at: str  # ISO-8601 timestamp


@dataclass
class CheckpointData:
    """Snapshot of a partially-completed analysis run."""

    total_chapters: int
    completed: dict[int, dict[str, Any]]  # chapter_number -> agent result
    remaining: list[int]  # chapter numbers not yet analysed
    started_at: str  # ISO-8601 timestamp
    updated_at: str


# ---------------------------------------------------------------------------
# CacheManager
# ---------------------------------------------------------------------------

class CacheManager:
    """Unified interface for chapter-hash caching and checkpoint persistence.

    Parameters
    ----------
    state_dir:
        Per-manuscript state directory (from ``paths.state_dir_for``).
    """

    def __init__(self, state_dir: Path) -> None:
        self._state_dir = Path(state_dir)
        self._cache_path = self._state_dir / _CACHE_FILE
        self._checkpoint_path = self._state_dir / _CHECKPOINT_FILE

        # In-memory mirrors — populated by load_*() calls.
        self._cache: dict[int, CacheEntry] = {}
        self._checkpoint: CheckpointData | None = None

    # -- directory bootstrap ------------------------------------------------

    def _ensure_dir(self) -> None:
        self._state_dir.mkdir(parents=True, exist_ok=True)

    # ======================================================================
    # Cache (hash-based skip)
    # ======================================================================

    def load_cache(self) -> dict[int, CacheEntry]:
        """Load the on-disk cache into memory.  Returns the loaded entries."""
        self._cache.clear()
        if not self._cache_path.exists():
            logger.debug("No cache file at %s", self._cache_path)
            return self._cache

        try:
            raw = json.loads(self._cache_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Corrupt cache file, starting fresh: %s", exc)
            return self._cache

        for entry in raw.get("entries", []):
            ch = entry["chapter_number"]
            self._cache[ch] = CacheEntry(
                chapter_number=ch,
                content_hash=entry["content_hash"],
                result=entry["result"],
                cached_at=entry["cached_at"],
            )

        logger.info("Loaded cache with %d chapter(s)", len(self._cache))
        return self._cache

    def save_cache(self) -> None:
        """Persist the current in-memory cache to disk."""
        self._ensure_dir()
        payload = {
            "version": 1,
            "entries": [
                {
                    "chapter_number": e.chapter_number,
                    "content_hash": e.content_hash,
                    "result": e.result,
                    "cached_at": e.cached_at,
                }
                for e in self._cache.values()
            ],
        }
        self._cache_path.write_text(
            json.dumps(payload, indent=2), encoding="utf-8",
        )
        logger.debug("Cache saved (%d entries)", len(self._cache))

    def get_chapter_hash(self, content: str) -> str:
        """Compute the SHA-256 hash for chapter *content*."""
        return _chapter_content_hash(content)

    def is_chapter_cached(self, chapter_number: int, content: str) -> bool:
        """Return ``True`` if *chapter_number* is cached **and** its hash matches *content*."""
        entry = self._cache.get(chapter_number)
        if entry is None:
            return False
        return entry.content_hash == _chapter_content_hash(content)

    def get_cached_result(self, chapter_number: int) -> dict[str, Any] | None:
        """Return the cached agent result for *chapter_number*, or ``None``."""
        entry = self._cache.get(chapter_number)
        return entry.result if entry is not None else None

    def update_cache_entry(
        self, chapter_number: int, content: str, result: dict[str, Any],
    ) -> None:
        """Insert or replace the cache entry for a chapter."""
        self._cache[chapter_number] = CacheEntry(
            chapter_number=chapter_number,
            content_hash=_chapter_content_hash(content),
            result=result,
            cached_at=_iso_now(),
        )

    def invalidate_chapter(self, chapter_number: int) -> None:
        """Remove the cache entry for *chapter_number* if present."""
        self._cache.pop(chapter_number, None)

    def clear_cache(self) -> None:
        """Drop all cached entries (in memory; call ``save_cache`` to persist)."""
        self._cache.clear()

    # ======================================================================
    # Checkpoint (failure recovery)
    # ======================================================================

    def save_checkpoint(
        self,
        total_chapters: int,
        completed: dict[int, dict[str, Any]],
        remaining: list[int],
    ) -> None:
        """Persist a checkpoint of the current analysis run.

        Called after each chapter completes so that progress is not lost on
        API failure.
        """
        self._ensure_dir()
        now = _iso_now()
        self._checkpoint = CheckpointData(
            total_chapters=total_chapters,
            completed=completed,
            remaining=remaining,
            started_at=(
                self._checkpoint.started_at if self._checkpoint else now
            ),
            updated_at=now,
        )
        payload = {
            "version": 1,
            "total_chapters": self._checkpoint.total_chapters,
            "completed": {
                str(k): v for k, v in self._checkpoint.completed.items()
            },
            "remaining": self._checkpoint.remaining,
            "started_at": self._checkpoint.started_at,
            "updated_at": self._checkpoint.updated_at,
        }
        self._checkpoint_path.write_text(
            json.dumps(payload, indent=2), encoding="utf-8",
        )
        logger.debug(
            "Checkpoint saved: %d/%d complete",
            len(completed),
            total_chapters,
        )

    def load_checkpoint(self) -> CheckpointData | None:
        """Load a prior checkpoint from disk.  Returns ``None`` if none exists."""
        if not self._checkpoint_path.exists():
            logger.debug("No checkpoint file at %s", self._checkpoint_path)
            self._checkpoint = None
            return None

        try:
            raw = json.loads(
                self._checkpoint_path.read_text(encoding="utf-8"),
            )
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Corrupt checkpoint file, ignoring: %s", exc)
            self._checkpoint = None
            return None

        completed = {int(k): v for k, v in raw.get("completed", {}).items()}
        self._checkpoint = CheckpointData(
            total_chapters=raw["total_chapters"],
            completed=completed,
            remaining=raw.get("remaining", []),
            started_at=raw.get("started_at", ""),
            updated_at=raw.get("updated_at", ""),
        )
        logger.info(
            "Loaded checkpoint: %d/%d chapters complete",
            len(completed),
            self._checkpoint.total_chapters,
        )
        return self._checkpoint

    def get_resume_point(
        self, chapters: list[dict[str, Any]],
    ) -> tuple[dict[int, dict[str, Any]], list[int]]:
        """Determine which chapters to skip and which to (re-)analyse.

        Combines checkpoint data with the hash cache: a chapter marked
        *completed* in the checkpoint is still re-analysed if its content hash
        changed since the cached result was stored.

        Parameters
        ----------
        chapters:
            Serialised ``Chapter`` dicts (must contain ``chapter_number`` and
            ``content`` keys).

        Returns
        -------
        (reusable, pending)
            *reusable* maps chapter numbers to their cached/checkpointed
            results that can be carried forward.  *pending* is the ordered
            list of chapter numbers that require (re-)analysis.
        """
        checkpoint = self._checkpoint
        reusable: dict[int, dict[str, Any]] = {}
        pending: list[int] = []

        for ch in chapters:
            ch_num: int = ch["chapter_number"]
            content: str = ch["content"]

            # 1. If cache says content is unchanged → reuse cached result.
            if self.is_chapter_cached(ch_num, content):
                cached = self.get_cached_result(ch_num)
                if cached is not None:
                    reusable[ch_num] = cached
                    continue

            # 2. If checkpoint has a result BUT content changed → re-analyse.
            if checkpoint and ch_num in checkpoint.completed:
                prior_hash = self._cache.get(ch_num)
                current_hash = _chapter_content_hash(content)
                if prior_hash is not None and prior_hash.content_hash == current_hash:
                    reusable[ch_num] = checkpoint.completed[ch_num]
                    continue

            # 3. Otherwise → needs analysis.
            pending.append(ch_num)

        logger.info(
            "Resume point: %d reusable, %d pending",
            len(reusable),
            len(pending),
        )
        return reusable, pending

    def clear_checkpoint(self) -> None:
        """Remove the checkpoint file (e.g. after a successful full run)."""
        self._checkpoint = None
        if self._checkpoint_path.exists():
            self._checkpoint_path.unlink()
            logger.debug("Checkpoint file removed")

    # ======================================================================
    # Convenience
    # ======================================================================

    def status_summary(self) -> dict[str, Any]:
        """Return a human-readable status dict for CLI display."""
        cp = self._checkpoint
        return {
            "cache_entries": len(self._cache),
            "cache_path": str(self._cache_path),
            "has_checkpoint": cp is not None,
            "checkpoint_completed": len(cp.completed) if cp else 0,
            "checkpoint_remaining": len(cp.remaining) if cp else 0,
            "checkpoint_path": str(self._checkpoint_path),
        }


# ---------------------------------------------------------------------------
# Module-private helpers
# ---------------------------------------------------------------------------

def _iso_now() -> str:
    """Return the current UTC time as an ISO-8601 string."""
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


__all__ = [
    "CacheEntry",
    "CacheManager",
    "CheckpointData",
]
