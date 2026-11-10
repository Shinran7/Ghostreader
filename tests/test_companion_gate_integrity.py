"""#15: the companion continuity gate cannot silently ship."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from typer.testing import CliRunner

from ghostreader.cli import app
from ghostreader.companion.brief import CompanionBrief, brief_to_payload
from ghostreader.companion.continuity import (
    cited_chapters,
    continuity_parse_failed,
    is_grounded_progressive,
    is_grounded_sweep,
    partition_findings,
)
from ghostreader.companion.discovery import DiscoveryResult
from ghostreader.companion.pipeline import run_companion_pipeline
from ghostreader.companion.progress import ProgressState
from ghostreader.ingestion import Chapter


def _f(**kw: Any) -> dict[str, Any]:
    base = {
        "dimension": "consistency.character",
        "severity": "concern",
        "summary": "x",
        "chapter_ref": "",
        "evidence": "",
        "counter_evidence": "",
    }
    base.update(kw)
    return base


# --- chapter_ref parsing --------------------------------------------------


@pytest.mark.parametrize(
    ("ref", "expected"),
    [
        ("Ch 12, scene 3", {12}),
        ("Ch. 12", {12}),
        ("Chapters 3 and 7", {3, 7}),
        ("12", {12}),
        ("12 vs 18", {12, 18}),
        ("Chapter 5, line 40", {5}),
        ("Ch 4, para 2", {4}),
        ("Ch 9 p. 7", {9}),
        ("Ch 2, scenes 1-3", {2}),
    ],
)
def test_cited_chapters_ignores_sub_locators(ref: str, expected: set[int]) -> None:
    assert cited_chapters(_f(chapter_ref=ref)) == expected


def test_ch_dot_prefix_in_evidence() -> None:
    f = _f(evidence="Ch. 4: blue eyes", counter_evidence="Chs 9: brown eyes")
    assert cited_chapters(f) == {4, 9}


# --- same-chapter contradictions -----------------------------------------


def test_same_chapter_two_quotes_gates() -> None:
    f = _f(
        chapter_ref="Ch 5",
        evidence="Her eyes were blue.",
        counter_evidence="He looked into her brown eyes.",
    )
    assert is_grounded_progressive(f, N=5)
    assert partition_findings([f], N=5, mode="progressive").gate == [f]
    assert is_grounded_sweep(f)


def test_same_chapter_one_quote_stays_ungrounded() -> None:
    f = _f(chapter_ref="Ch 5", evidence="Her eyes were blue.", counter_evidence="")
    part = partition_findings([f], N=5, mode="progressive")
    assert part.gate == []
    assert part.ungrounded == [f]


def test_same_chapter_identical_quotes_stay_ungrounded() -> None:
    f = _f(
        chapter_ref="Ch 5",
        evidence="Her eyes were blue.",
        counter_evidence=" her eyes  were blue. ",
    )
    part = partition_findings([f], N=5, mode="progressive")
    assert part.gate == []
    assert part.ungrounded == [f]
    assert not is_grounded_sweep(f)


def test_scene_number_no_longer_fakes_a_second_chapter() -> None:
    # Before #15, "scene 3" counted as chapter 3, so this gated as cross-chapter.
    f = _f(chapter_ref="Ch 12, scene 3", evidence="a", counter_evidence="a")
    assert partition_findings([f], N=12, mode="progressive").gate == []


# --- parse-failure detection --------------------------------------------


def test_continuity_parse_failed() -> None:
    assert continuity_parse_failed([_f(dimension="consistency.general")])
    assert not continuity_parse_failed([_f(dimension="consistency.general", severity="neutral")])
    assert not continuity_parse_failed([_f()])
    assert not continuity_parse_failed([])


# --- pipeline -------------------------------------------------------------


def _discovery(tmp_path: Path) -> DiscoveryResult:
    path = tmp_path / "chapter-001.md"
    path.write_text("# Chapter 1\n\nHer eyes were blue.\n", encoding="utf-8")
    content = "Her eyes were blue.\n\nHe looked into her brown eyes."
    ch = Chapter(title="One", content=content, chapter_number=1, source_path=path)
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


async def _run(
    tmp_path: Path, continuity_raw: list[dict[str, Any]], facts: list[Any] | None = None
):
    store = MagicMock()
    store.ensure_facts = AsyncMock(return_value=facts or [])
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
            llm=MagicMock(),
            typesafe_client=None,
            typesafe_enabled=False,
            story_state_dir=tmp_path,
            genre=None,
            continuity_only=True,
            companion_light_narrative=False,
            json_mode=True,
        )


@pytest.mark.asyncio
async def test_pipeline_parse_failure_marks_failed_and_watch(tmp_path: Path) -> None:
    raw = [
        _f(
            dimension="consistency.general",
            summary="Consistency check failed to parse structured findings",
            evidence="garbage",
            chapter_ref="all",
        )
    ]
    brief = await _run(tmp_path, raw)
    assert brief.continuity_status == "failed"
    assert brief.verdict == "watch"
    assert "continuity" in brief.verdict_drivers
    assert brief.continuity_findings == []
    assert brief_to_payload(brief)["continuity_status"] == "failed"


@pytest.mark.asyncio
async def test_pipeline_clean_is_ok(tmp_path: Path) -> None:
    brief = await _run(tmp_path, [])
    assert brief.continuity_status == "ok"
    assert brief.verdict == "ship"


@pytest.mark.asyncio
async def test_pipeline_poisoned_facts_marks_failed(tmp_path: Path) -> None:
    from ghostreader.agents.fact_extractor import _empty_parse_failed

    facts = [_empty_parse_failed(_discovery(tmp_path).chapters[0])]
    brief = await _run(tmp_path, [], facts=facts)
    assert brief.continuity_status == "failed"
    assert brief.verdict == "watch"


@pytest.mark.asyncio
async def test_pipeline_demotes_tone_understatement(tmp_path: Path) -> None:
    raw = [
        _f(
            dimension="consistency.plot_holes",
            chapter_ref="Ch 1",
            evidence="The vault was sealed.",
            counter_evidence="She walked into the vault.",
            signal_kind="tone_understatement",
        )
    ]
    brief = await _run(tmp_path, raw)
    assert brief.continuity_findings == []
    assert brief.verdict == "ship"


@pytest.mark.asyncio
async def test_pipeline_same_chapter_contradiction_gates(tmp_path: Path) -> None:
    raw = [
        _f(
            chapter_ref="Ch 1",
            evidence="Her eyes were blue.",
            counter_evidence="He looked into her brown eyes.",
        )
    ]
    brief = await _run(tmp_path, raw)
    assert len(brief.continuity_findings) == 1
    assert brief.verdict == "watch"
    assert brief.continuity_status == "ok"


# --- CLI exit codes -------------------------------------------------------

runner = CliRunner()


def _series(tmp_path: Path) -> Path:
    chapters = tmp_path / "story" / "chapters"
    chapters.mkdir(parents=True)
    for n in (1, 2):
        (chapters / f"chapter-{n:03d}.md").write_text(
            f"# Chapter {n}\n\nText {n}.\n", encoding="utf-8"
        )
    (tmp_path / "config.yaml").write_text(
        "model: stub\ntypesafe_enabled: false\n", encoding="utf-8"
    )
    return chapters / "chapter-002.md"


def _brief(**kw: Any) -> CompanionBrief:
    base: dict[str, Any] = {
        "manuscript_name": "story · Chapter 2",
        "story_slug": "story",
        "mode": "progressive",
        "chapter_number": 2,
        "chapters_considered": [1, 2],
        "facts_reused": 0,
        "facts_extracted": 2,
        "verdict": "watch",
        "chapter_note": "n",
        "generated_at": "2026-11-10T00:00:00+00:00",
    }
    base.update(kw)
    return CompanionBrief(**base)


def _invoke(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, brief: CompanionBrief, *flags: str):
    target = _series(tmp_path)
    monkeypatch.chdir(tmp_path)
    with patch(
        "ghostreader.commands.companion.run_companion_pipeline",
        new=AsyncMock(return_value=brief),
    ):
        return runner.invoke(
            app,
            [
                "companion",
                str(target),
                "--format",
                "json",
                "--model",
                "stub",
                "--no-typesafe",
                *flags,
            ],
        )


def test_cli_failed_status_exits_2_under_hard_gate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = _invoke(
        tmp_path, monkeypatch, _brief(continuity_status="failed"), "--fail-on-continuity"
    )
    assert result.exit_code == 2
    stdout = result.stdout or ""
    payload = json.loads(stdout[stdout.find("{") :])
    assert payload["continuity_status"] == "failed"


def test_cli_failed_status_exits_0_without_hard_gate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = _invoke(tmp_path, monkeypatch, _brief(continuity_status="failed"))
    assert result.exit_code == 0


def test_cli_fact_poison_exits_2_under_hard_gate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    brief = _brief(warnings=["Fact extraction JSON parse failed for 1/2 chapter(s)."])
    result = _invoke(tmp_path, monkeypatch, brief, "--fail-on-continuity")
    assert result.exit_code == 2


def test_cli_fact_poison_exits_1_without_hard_gate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    brief = _brief(warnings=["Fact extraction JSON parse failed for 1/2 chapter(s)."])
    result = _invoke(tmp_path, monkeypatch, brief)
    assert result.exit_code == 1
