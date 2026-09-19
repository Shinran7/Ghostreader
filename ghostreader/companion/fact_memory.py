"""Story-level persistent fact sheets for companion mode.

Stores hash-keyed ``ChapterFact`` records under ``.ghostreader/<story>/facts/``.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from langchain_core.language_models import BaseChatModel

from ghostreader.agents.fact_extractor import ChapterFact, extract_chapter_facts
from ghostreader.cache import chapter_content_hash
from ghostreader.ingestion import Chapter
from ghostreader.paths import story_facts_dir

logger = logging.getLogger(__name__)

_MANIFEST_NAME = "manifest.json"
_RECORD_VERSION = 1


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class FactRecord:
    """On-disk fact sheet plus freshness metadata."""

    chapter_number: int
    content_hash: str
    extracted_at: str
    fact: ChapterFact
    source_path: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": _RECORD_VERSION,
            "chapter_number": self.chapter_number,
            "content_hash": self.content_hash,
            "extracted_at": self.extracted_at,
            "source_path": self.source_path,
            "fact": dict(self.fact),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FactRecord:
        fact_raw = data.get("fact") or {}
        fact = ChapterFact(
            chapter_number=int(fact_raw.get("chapter_number", data.get("chapter_number", 0))),
            characters=list(fact_raw.get("characters") or []),
            location=str(fact_raw.get("location") or ""),
            timeline_markers=list(fact_raw.get("timeline_markers") or []),
            established_facts=list(fact_raw.get("established_facts") or []),
            key_objects=list(fact_raw.get("key_objects") or []),
        )
        return cls(
            chapter_number=int(data["chapter_number"]),
            content_hash=str(data.get("content_hash") or ""),
            extracted_at=str(data.get("extracted_at") or ""),
            fact=fact,
            source_path=str(data.get("source_path") or ""),
        )


class FactMemoryStore:
    """Load/save/invalidate hash-keyed chapter facts at story level."""

    def __init__(self, story_state_dir: Path) -> None:
        self.story_state_dir = story_state_dir
        self.facts_dir = story_facts_dir(story_state_dir)
        self.facts_dir.mkdir(parents=True, exist_ok=True)
        self.last_reused: int = 0
        self.last_extracted: int = 0

    def _record_path(self, chapter_number: int) -> Path:
        return self.facts_dir / f"chapter-{chapter_number:03d}.json"

    def load_manifest(self) -> dict[str, Any]:
        path = self.facts_dir / _MANIFEST_NAME
        if not path.exists():
            return {"version": 1, "story_slug": self.story_state_dir.name, "updated_at": None}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Corrupt facts manifest (%s); treating as empty", exc)
            return {"version": 1, "story_slug": self.story_state_dir.name, "updated_at": None}

    def _save_manifest(self) -> None:
        path = self.facts_dir / _MANIFEST_NAME
        payload = {
            "version": 1,
            "story_slug": self.story_state_dir.name,
            "updated_at": _iso_now(),
        }
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    def get(self, chapter_number: int) -> FactRecord | None:
        path = self._record_path(chapter_number)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return None
            return FactRecord.from_dict(data)
        except (json.JSONDecodeError, OSError, KeyError, TypeError, ValueError) as exc:
            logger.warning(
                "Corrupt fact record for chapter %s (%s); treating as missing",
                chapter_number,
                exc,
            )
            return None

    def is_fresh(self, chapter_number: int, content: str) -> bool:
        record = self.get(chapter_number)
        if record is None:
            return False
        return record.content_hash == chapter_content_hash(content)

    def save(self, record: FactRecord) -> None:
        path = self._record_path(record.chapter_number)
        path.write_text(json.dumps(record.to_dict(), indent=2) + "\n", encoding="utf-8")
        self._save_manifest()

    def invalidate(self, chapter_number: int) -> None:
        path = self._record_path(chapter_number)
        if path.exists():
            path.unlink()

    def invalidate_from(self, chapter_number: int) -> None:
        """Drop records for chapter_number..max present on disk."""
        for path in self.facts_dir.glob("chapter-*.json"):
            try:
                num = int(path.stem.split("-", 1)[1])
            except (IndexError, ValueError):
                continue
            if num >= chapter_number:
                path.unlink(missing_ok=True)

    async def ensure_facts(
        self,
        chapters: list[Chapter],
        llm: BaseChatModel,
        *,
        max_concurrent: int = 10,
        force: bool = False,
    ) -> list[ChapterFact]:
        """Return facts for all chapters; extract only missing/stale (or all if force)."""
        reused = 0
        to_extract: list[Chapter] = []
        cached: dict[int, ChapterFact] = {}

        for ch in chapters:
            if not force and self.is_fresh(ch.chapter_number, ch.content):
                record = self.get(ch.chapter_number)
                assert record is not None
                cached[ch.chapter_number] = record.fact
                reused += 1
            else:
                to_extract.append(ch)

        extracted_facts: dict[int, ChapterFact] = {}
        if to_extract:
            semaphore = asyncio.Semaphore(max_concurrent)

            async def _bounded(chapter: Chapter) -> tuple[Chapter, ChapterFact]:
                async with semaphore:
                    fact = await extract_chapter_facts(chapter, llm)
                    return chapter, fact

            results = await asyncio.gather(*[_bounded(ch) for ch in to_extract])
            for chapter, fact in results:
                record = FactRecord(
                    chapter_number=chapter.chapter_number,
                    content_hash=chapter_content_hash(chapter.content),
                    extracted_at=_iso_now(),
                    fact=fact,
                    source_path=str(chapter.source_path),
                )
                self.save(record)
                extracted_facts[chapter.chapter_number] = fact
                logger.info("Extracted facts for chapter %s", chapter.chapter_number)

        self.last_reused = reused
        self.last_extracted = len(extracted_facts)

        out: list[ChapterFact] = []
        for ch in chapters:
            if ch.chapter_number in cached:
                out.append(cached[ch.chapter_number])
            else:
                out.append(extracted_facts[ch.chapter_number])
        return out
