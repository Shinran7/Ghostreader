"""#19 cost and input: note skip, probe cache, whole chapter, usage key."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ghostreader.companion.brief import CompanionBrief, brief_to_payload
from ghostreader.companion.discovery import DiscoveryResult
from ghostreader.companion.pipeline import run_companion_pipeline
from ghostreader.companion.progress import ProgressState
from ghostreader.excerpts import COMPANION_CHAPTER_CHARS, whole_chapter_block
from ghostreader.ingestion import Chapter
from ghostreader.llm import PROBE_CACHE_FILE, probe_json_contract_cached
from ghostreader.report import ReportOutput
from ghostreader.report.json_export import _build_payload


def _discovery(tmp_path: Path) -> DiscoveryResult:
    path = tmp_path / "chapter-001.md"
    path.write_text("# Chapter 1\n\nText.\n", encoding="utf-8")
    ch = Chapter(title="One", content="Text.", chapter_number=1, source_path=path)
    return DiscoveryResult(
        mode="progressive",
        path=tmp_path,
        story_slug="s",
        story_dir=tmp_path,
        chapters_dir=tmp_path,
        chapter_number=1,
        chapters=[ch],
        gaps=[],
        warnings=[],
        seed_meta={},
        manuscript_name="s · Chapter 1",
    )


async def _run(tmp_path: Path, *, chapter_note: bool) -> tuple[CompanionBrief, AsyncMock]:
    store = MagicMock()
    store.ensure_facts = AsyncMock(return_value=[])
    store.last_reused = 0
    store.last_extracted = 0
    note = AsyncMock(return_value="the note")
    with (
        patch("ghostreader.companion.pipeline.FactMemoryStore", return_value=store),
        patch(
            "ghostreader.companion.pipeline._run_llm_consistency",
            new=AsyncMock(return_value=([], {}, {})),
        ),
        patch("ghostreader.companion.pipeline._chapter_note", new=note),
        patch("ghostreader.companion.pipeline.update_progress_after_run", return_value=None),
        patch(
            "ghostreader.companion.pipeline.clamp_progress_to_disk",
            return_value=ProgressState(),
        ),
        patch("ghostreader.companion.pipeline.compute_order_warnings", return_value=[]),
    ):
        brief = await run_companion_pipeline(
            _discovery(tmp_path),
            llm=MagicMock(),
            typesafe_client=None,
            typesafe_enabled=False,
            story_state_dir=tmp_path,
            genre=None,
            continuity_only=True,
            companion_light_narrative=False,
            json_mode=True,
            chapter_note=chapter_note,
        )
    return brief, note


@pytest.mark.asyncio
async def test_note_skipped_saves_a_call(tmp_path: Path) -> None:
    brief, note = await _run(tmp_path, chapter_note=False)
    assert note.await_count == 0
    assert brief.chapter_note == ""
    assert "chapter_note" in brief_to_payload(brief)


@pytest.mark.asyncio
async def test_note_on_by_default(tmp_path: Path) -> None:
    brief, note = await _run(tmp_path, chapter_note=True)
    assert note.await_count == 1
    assert brief.chapter_note == "the note"


def test_usage_in_both_payloads() -> None:
    usage = {"llm_calls": 2, "total_tokens": 9, "by_model": {}}
    base = {
        "manuscript_name": "m",
        "story_slug": "s",
        "mode": "progressive",
        "chapter_number": 1,
        "chapters_considered": [1],
        "facts_reused": 0,
        "facts_extracted": 0,
        "verdict": "ship",
        "chapter_note": "",
    }
    assert brief_to_payload(CompanionBrief(**base, usage=usage))["usage"] == usage
    assert brief_to_payload(CompanionBrief(**base))["usage"] == {}
    report = ReportOutput(executive_summary="", usage=usage)
    assert _build_payload(report)["usage"] == usage


class TestProbeCache:
    def _llm(self) -> MagicMock:
        return MagicMock(_llm_type="fake")

    def test_pass_is_cached_for_today(self, tmp_path: Path) -> None:
        probe = AsyncMock(return_value=(True, "{}"))
        with patch("ghostreader.llm.probe_json_contract", new=probe):
            for _ in range(2):
                ok, _d = asyncio.run(
                    probe_json_contract_cached(self._llm(), model="m", state_dir=tmp_path)
                )
                assert ok
        assert probe.await_count == 1
        saved = json.loads((tmp_path / PROBE_CACHE_FILE).read_text(encoding="utf-8"))
        assert saved == {"m": datetime.now(UTC).date().isoformat()}

    def test_failure_not_cached(self, tmp_path: Path) -> None:
        probe = AsyncMock(return_value=(False, "nope"))
        with patch("ghostreader.llm.probe_json_contract", new=probe):
            for _ in range(2):
                asyncio.run(probe_json_contract_cached(self._llm(), model="m", state_dir=tmp_path))
        assert probe.await_count == 2
        assert not (tmp_path / PROBE_CACHE_FILE).exists()

    def test_stale_day_and_no_cache_probe_again(self, tmp_path: Path) -> None:
        (tmp_path / PROBE_CACHE_FILE).write_text('{"m": "2000-01-01"}', encoding="utf-8")
        probe = AsyncMock(return_value=(True, "{}"))
        with patch("ghostreader.llm.probe_json_contract", new=probe):
            asyncio.run(probe_json_contract_cached(self._llm(), model="m", state_dir=tmp_path))
            asyncio.run(
                probe_json_contract_cached(
                    self._llm(), model="m", state_dir=tmp_path, use_cache=False
                )
            )
        assert probe.await_count == 2


class TestWholeChapter:
    def test_short_chapter_whole(self) -> None:
        text = "word " * 2000
        block = whole_chapter_block([{"chapter_number": 3, "title": "T", "content": text}])
        assert block.startswith("--- Chapter 3: T ---\n")
        assert text in block

    def test_long_chapter_capped_with_ending(self) -> None:
        text = "start " + ("middle " * 20_000) + "THE END"
        block = whole_chapter_block([{"chapter_number": 1, "content": text}])
        assert len(block) < COMPANION_CHAPTER_CHARS + 200
        assert "THE END" in block
        assert block.startswith("--- Chapter 1: Chapter 1 ---")
