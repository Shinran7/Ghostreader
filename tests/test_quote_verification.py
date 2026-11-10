"""#17: quote verification in the companion pipeline and analyze synthesis."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage

from ghostreader.agents.synthesis import quote_gate
from ghostreader.companion.discovery import DiscoveryResult
from ghostreader.companion.pipeline import run_companion_pipeline
from ghostreader.companion.progress import ProgressState
from ghostreader.ingestion import Chapter
from ghostreader.quotes import QuoteIndex, verify_finding
from ghostreader.report import ReportOutput
from ghostreader.report.json_export import ANALYZE_JSON_VERSION, _build_payload
from ghostreader.report.markdown_writer import write_markdown_report

# --- companion pipeline ---------------------------------------------------


CH1 = (
    "The rain tracked downward in slow paths across the window.\n"
    "Mara watched it and said nothing.\n\n"
    "“We leave at dawn,” she said — and meant it.\n"
    "Her eyes were blue as the harbor in winter."
)
CH2 = (
    "Two days later the harbor froze.\n\n"
    "He looked into her brown eyes and saw no fear there at all."
)


def _index() -> QuoteIndex:
    return QuoteIndex(
        [
            {"chapter_number": 1, "content": CH1},
            {"chapter_number": 2, "content": CH2},
        ]
    )


def _f(**kw: Any) -> dict[str, Any]:
    base = {
        "dimension": "consistency.character",
        "severity": "concern",
        "summary": "Eye colour changes",
        "chapter_ref": "1 vs 2",
        "evidence": "",
        "counter_evidence": "",
    }
    base.update(kw)
    return base


def _llm(payload: dict[str, Any] | Exception) -> MagicMock:
    llm = MagicMock()
    if isinstance(payload, Exception):
        llm.ainvoke = AsyncMock(side_effect=payload)
    else:
        llm.ainvoke = AsyncMock(return_value=AIMessage(content=json.dumps(payload)))
    return llm


def _paraphrase() -> dict[str, Any]:
    return verify_finding(
        _f(
            evidence="Ch 1: Mara's eyes described as blue",
            counter_evidence="Ch 2: Mara's eyes described as brown",
        ),
        _index(),
        demote=False,
    )


INVENTED = _f(
    evidence="Ch 1: 'Her eyes, blue as cornflowers, never wavered.'",
    counter_evidence="Ch 2: 'Her green eyes glittered in the lamplight tonight.'",
)


def _discovery(tmp_path: Path) -> DiscoveryResult:
    path = tmp_path / "chapter-002.md"
    path.write_text(CH2, encoding="utf-8")
    chapters = [
        Chapter(title="One", content=CH1, chapter_number=1, source_path=tmp_path / "c1.md"),
        Chapter(title="Two", content=CH2, chapter_number=2, source_path=path),
    ]
    return DiscoveryResult(
        mode="progressive",
        path=tmp_path,
        story_slug="s",
        story_dir=tmp_path,
        chapters_dir=tmp_path,
        chapter_number=2,
        chapters=chapters,
        gaps=[],
        warnings=[],
        seed_meta={},
        manuscript_name="s · Chapter 2",
    )


async def _run(tmp_path: Path, continuity_raw: list[dict[str, Any]], llm: Any, **kw: Any):
    store = MagicMock()
    store.ensure_facts = AsyncMock(return_value=[])
    store.last_reused = 0
    store.last_extracted = 0
    with (
        patch("ghostreader.companion.pipeline.FactMemoryStore", return_value=store),
        patch(
            "ghostreader.companion.pipeline._run_llm_consistency",
            new=AsyncMock(return_value=(continuity_raw, {}, {})),
        ),
        patch("ghostreader.companion.pipeline._chapter_note", new=AsyncMock(return_value="n")),
        patch("ghostreader.companion.pipeline.update_progress_after_run", return_value=None),
        patch(
            "ghostreader.companion.pipeline.clamp_progress_to_disk",
            return_value=ProgressState(),
        ),
        patch("ghostreader.companion.pipeline.compute_order_warnings", return_value=[]),
    ):
        return await run_companion_pipeline(
            _discovery(tmp_path),
            llm=llm,
            typesafe_client=None,
            typesafe_enabled=False,
            story_state_dir=tmp_path,
            genre=None,
            continuity_only=True,
            companion_light_narrative=False,
            json_mode=True,
            **kw,
        )


@pytest.mark.asyncio
async def test_invented_continuity_quote_never_gates(tmp_path: Path) -> None:
    brief = await _run(tmp_path, [INVENTED], _llm({"supported": False}))
    assert brief.continuity_findings == []
    assert brief.verdict == "ship"
    assert brief.quote_stats["unverified"] == 1
    assert brief.quote_stats["recovery_calls"] == 1


@pytest.mark.asyncio
async def test_recovered_continuity_concern_gates(tmp_path: Path) -> None:
    llm = _llm(
        {
            "supported": True,
            "evidence": "Ch 1: 'Her eyes were blue as the harbor in winter.'",
            "counter_evidence": "Ch 2: 'He looked into her brown eyes'",
        }
    )
    brief = await _run(tmp_path, [_paraphrase()], llm)
    assert len(brief.continuity_findings) == 1
    assert brief.continuity_findings[0].quote_verified is True
    assert brief.verdict == "watch"
    assert brief.quote_stats["recovered"] == 1


@pytest.mark.asyncio
async def test_kill_switch_restores_old_gate(tmp_path: Path) -> None:
    llm = _llm({"supported": False})
    brief = await _run(tmp_path, [INVENTED], llm, quote_verification=False)
    assert len(brief.continuity_findings) == 1
    assert brief.quote_stats == {}
    llm.ainvoke.assert_not_awaited()


# --- analyze --------------------------------------------------------------


def _state(**config: Any) -> dict[str, Any]:
    return {
        "chapters": [
            {"chapter_number": 1, "content": CH1},
            {"chapter_number": 2, "content": CH2},
        ],
        "config": config,
    }


@pytest.mark.asyncio
async def test_analyze_drops_unverified_concerns_and_reranks() -> None:
    rows = [
        {**INVENTED, "rank": 1},
        {
            **_f(dimension="prose.rhythm", severity="strength"),
            "evidence": "Ch 1: 'The rain tracked downward in slow paths'",
            "rank": 2,
        },
        {**_f(dimension="prose.rhythm", severity="neutral"), "evidence": "made up", "rank": 3},
    ]
    kept, dropped, stats = await quote_gate(rows, _state(), None)  # type: ignore[arg-type]
    assert [f["rank"] for f in kept] == [1, 2]
    assert kept[0]["quote_verified"] is True
    assert kept[1]["quote_verified"] is False  # neutral kept, tagged
    assert len(dropped) == 1
    assert stats == {"verified": 1, "unverified": 2, "dropped": 1}


@pytest.mark.asyncio
async def test_analyze_recovers_consistency_paraphrase() -> None:
    llm = _llm(
        {
            "supported": True,
            "evidence": "Ch 1: 'Her eyes were blue as the harbor in winter.'",
            "counter_evidence": "Ch 2: 'He looked into her brown eyes'",
        }
    )
    row = {**_f(evidence="Ch 1: blue eyes", counter_evidence="Ch 2: brown eyes"), "rank": 1}
    kept, dropped, stats = await quote_gate([row], _state(), llm)  # type: ignore[arg-type]
    assert dropped == []
    assert kept[0]["quote_recovered"] is True
    assert stats["recovered"] == 1


@pytest.mark.asyncio
async def test_analyze_kill_switch() -> None:
    row = {**INVENTED, "rank": 1}
    kept, dropped, stats = await quote_gate(
        [row], _state(quote_verification=False), None  # type: ignore[arg-type]
    )
    assert kept == [row]
    assert (dropped, stats) == ([], {})


def test_analyze_payload_and_markdown(tmp_path: Path) -> None:
    verified = verify_finding(
        _f(
            evidence="Ch 1: 'Her eyes were blue as the harbor in winter.'",
            counter_evidence="Ch 2: 'He looked into her brown eyes'",
        ),
        _index(),
    )
    report = ReportOutput.from_final_report(
        {
            "executive_summary": "s",
            "prioritized_findings": [{**verified, "rank": 1}],
            "unverified_findings": [INVENTED],
            "quote_stats": {"verified": 1, "unverified": 1, "dropped": 1},
        },
        manuscript_name="book",
    )
    payload = _build_payload(report)
    assert ANALYZE_JSON_VERSION == "0.2.5"
    assert payload["unverified_findings"] == [INVENTED]
    assert payload["quote_stats"]["dropped"] == 1
    row = payload["prioritized_findings"][0]
    assert row["quote_verified"] is True
    assert row["id"] == verified["id"]
    assert row["location"]["line"] == 5

    md = write_markdown_report(report, output_dir=tmp_path).read_text(encoding="utf-8")
    assert "(Ch 1, line 5)" in md
    assert "(Ch 2, line 3)" in md
    assert "## Unverified Findings" in md
