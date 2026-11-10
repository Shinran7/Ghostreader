"""Anti-tidy narrative shape watch (#8)."""

from __future__ import annotations

import asyncio
import json
from contextlib import ExitStack
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ghostreader.companion.brief import brief_to_payload
from ghostreader.companion.discovery import DiscoveryResult
from ghostreader.companion.pipeline import run_companion_pipeline
from ghostreader.companion.progress import ProgressState
from ghostreader.companion.shape import (
    SHAPE_CAP,
    SHAPE_KINDS,
    asked_kinds,
    parse_shape_rows,
    run_shape_watch,
)
from ghostreader.config import GhostreaderConfig
from ghostreader.ingestion import Chapter

TEXT = (
    "Mara set the lantern on the step and did not go in.\n\n"
    "Her brother had lied to the council, and she had let him.\n\n"
    "In the end, she understood that loyalty was a kind of love that asked "
    "nothing back, and that was the lesson of the long night.\n"
)
LESSON = "she understood that loyalty was a kind of love that asked nothing back"


def _chapter(n: int = 5) -> Chapter:
    return Chapter(title="Step", content=TEXT, chapter_number=n, source_path=Path("ch.md"))


def _rows(*items: dict[str, Any]) -> str:
    return json.dumps(list(items))


class TestAskedKinds:
    def test_early_chapter_skips_book_kinds(self) -> None:
        kinds = asked_kinds(2)
        assert "anti_tidy_single_track" not in kinds
        assert "anti_tidy_flat_escalation" not in kinds
        assert len(kinds) == 3

    def test_later_chapter_asks_all_five(self) -> None:
        assert asked_kinds(4) == list(SHAPE_KINDS)


class TestParse:
    def test_grounded_row_kept_with_contract_fields(self) -> None:
        raw = _rows({"kind": "anti_tidy_theme_announce", "quote": LESSON, "message": "Glosses."})
        rows, dropped = parse_shape_rows(raw, focus=_chapter(), kinds=list(SHAPE_KINDS))
        assert dropped == 0
        (row,) = rows
        assert row["kind"] == "anti_tidy_theme_announce"
        assert row["severity"] == "watch"
        assert row["chapter"] == 5
        assert row["quote"] == LESSON
        assert row["message"] == row["summary"] == "Glosses."
        assert row["suggested_fix"] == SHAPE_KINDS["anti_tidy_theme_announce"][2]
        assert row["location"]["chapter"] == 5
        assert len(row["id"]) == 12

    def test_ungrounded_and_unknown_rows_dropped(self) -> None:
        raw = _rows(
            {"kind": "anti_tidy_moral_tidy", "quote": "words that are not in this chapter at all"},
            {"kind": "anti_tidy_moral_tidy", "quote": ""},
            {"kind": "ai_tell", "quote": LESSON},
            "not a dict",
        )
        rows, dropped = parse_shape_rows(raw, focus=_chapter(), kinds=list(SHAPE_KINDS))
        assert rows == []
        assert dropped == 3

    def test_book_kind_may_have_no_quote_but_must_be_asked(self) -> None:
        raw = _rows({"kind": "anti_tidy_flat_escalation", "quote": ""})
        rows, _ = parse_shape_rows(raw, focus=_chapter(), kinds=list(SHAPE_KINDS))
        assert rows[0]["quote"] == ""
        assert rows[0]["location"] is None
        assert rows[0]["message"] == SHAPE_KINDS["anti_tidy_flat_escalation"][1]
        rows, dropped = parse_shape_rows(raw, focus=_chapter(2), kinds=asked_kinds(2))
        assert (rows, dropped) == ([], 1)

    def test_duplicates_collapse_and_cap(self) -> None:
        same = {"kind": "anti_tidy_theme_announce", "quote": LESSON}
        raw = _rows(
            same,
            same,
            {"kind": "anti_tidy_moral_tidy", "quote": "Her brother had lied to the council"},
            {"kind": "anti_tidy_single_track", "quote": ""},
            {"kind": "anti_tidy_flat_escalation", "quote": ""},
        )
        rows, dropped = parse_shape_rows(raw, focus=_chapter(), kinds=list(SHAPE_KINDS))
        assert len(rows) == SHAPE_CAP
        assert dropped == 1

    def test_not_json(self) -> None:
        assert parse_shape_rows("no rows here", focus=_chapter(), kinds=list(SHAPE_KINDS)) == (
            [],
            0,
        )


class TestRun:
    def test_prompt_and_rows(self) -> None:
        llm = MagicMock()
        llm.ainvoke = AsyncMock(
            return_value=MagicMock(
                content=_rows({"kind": "anti_tidy_theme_announce", "quote": LESSON})
            )
        )
        rows, warnings = asyncio.run(
            run_shape_watch(focus=_chapter(2), prior_facts=[], llm=llm, genre=None, seed_meta={})
        )
        assert [r["kind"] for r in rows] == ["anti_tidy_theme_announce"]
        assert warnings == []
        system, user = llm.ainvoke.call_args.args[0]
        assert "machine-written" in system.content
        assert "anti_tidy_single_track" not in system.content
        assert "Prior chapters" not in user.content

    def test_model_failure_is_soft(self) -> None:
        llm = MagicMock()
        llm.ainvoke = AsyncMock(side_effect=RuntimeError("down"))
        rows, warnings = asyncio.run(
            run_shape_watch(focus=_chapter(), prior_facts=[], llm=llm, genre=None, seed_meta={})
        )
        assert rows == []
        assert "RuntimeError" in warnings[0]


def _discovery(tmp_path: Path, mode: str) -> DiscoveryResult:
    return DiscoveryResult(
        mode=mode,  # type: ignore[arg-type]
        path=tmp_path,
        story_slug="s",
        story_dir=tmp_path,
        chapters_dir=tmp_path,
        chapter_number=5,
        chapters=[_chapter()],
        manuscript_name="s · Chapter 5",
    )


def _pipeline(tmp_path: Path, mode: str, **kw: Any):
    row = {"kind": "anti_tidy_theme_announce", "severity": "watch", "chapter": 5}
    shape = AsyncMock(return_value=([row], []))
    store = MagicMock()
    store.ensure_facts = AsyncMock(return_value=[])
    store.last_reused = store.last_extracted = 0
    patches = {
        "ghostreader.companion.pipeline.FactMemoryStore": MagicMock(return_value=store),
        "ghostreader.companion.pipeline.run_companion_craft": AsyncMock(
            return_value={"prose_output": {"findings": [], "raw_response": {}}}
        ),
        "ghostreader.companion.pipeline._run_llm_consistency": AsyncMock(return_value=([], {}, {})),
        "ghostreader.companion.pipeline._chapter_note": AsyncMock(return_value="note"),
        "ghostreader.companion.pipeline.update_progress_after_run": MagicMock(),
        "ghostreader.companion.pipeline.clamp_progress_to_disk": MagicMock(
            return_value=ProgressState()
        ),
        "ghostreader.companion.pipeline.compute_order_warnings": MagicMock(return_value=[]),
        "ghostreader.companion.shape.run_shape_watch": shape,
    }
    with ExitStack() as stack:
        for target, new in patches.items():
            stack.enter_context(patch(target, new=new))
        brief = asyncio.run(
            run_companion_pipeline(
                _discovery(tmp_path, mode),
                llm=MagicMock(),
                typesafe_client=None,
                typesafe_enabled=False,
                story_state_dir=tmp_path,
                genre=None,
                companion_light_narrative=False,
                companion_voice_card_watch=False,
                continuity_canon=False,
                json_mode=True,
                chapter_note=False,
                **kw,
            )
        )
    return brief, shape


class TestPipeline:
    def test_progressive_emits_rows_verdict_untouched(self, tmp_path: Path) -> None:
        brief, shape = _pipeline(tmp_path, "progressive")
        assert shape.await_count == 1
        assert brief.shape_findings[0]["kind"] == "anti_tidy_theme_announce"
        assert brief.verdict == "ship"
        assert brief_to_payload(brief)["shape_findings"] == brief.shape_findings

    @pytest.mark.parametrize(
        ("mode", "kw"),
        [
            ("sweep", {}),
            ("progressive", {"companion_shape_watch": False}),
            ("progressive", {"continuity_only": True}),
        ],
    )
    def test_off_paths_emit_nothing(self, tmp_path: Path, mode: str, kw: dict[str, Any]) -> None:
        brief, shape = _pipeline(tmp_path, mode, **kw)
        assert shape.await_count == 0
        assert brief.shape_findings == []
        assert brief_to_payload(brief)["shape_findings"] == []


def test_config_kill_switch_round_trip(tmp_path: Path) -> None:
    assert GhostreaderConfig().companion_shape_watch is True
    GhostreaderConfig(companion_shape_watch=False).save(tmp_path)
    assert GhostreaderConfig.load(tmp_path / "book.md").companion_shape_watch is False
