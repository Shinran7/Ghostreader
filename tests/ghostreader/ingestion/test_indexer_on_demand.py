"""#18: chat-only index, built on demand and only when stale."""

from __future__ import annotations

from pathlib import Path

from ghostreader.cache import load_last_report, save_last_report
from ghostreader.ingestion import (
    ActSummary,
    Chapter,
    ChapterSummary,
    SummaryHierarchy,
    indexer,
    load_chapters,
)
from ghostreader.ingestion.indexer import ensure_index, load_summaries, save_summaries


def _chapters(extra: str = "") -> list[Chapter]:
    return [
        Chapter(
            title="One",
            content="First chapter text. " * 20 + extra,
            chapter_number=1,
            source_path=Path(""),
        ),
        Chapter(
            title="Two",
            content="Second chapter text. " * 20,
            chapter_number=2,
            source_path=Path(""),
        ),
    ]


def _hierarchy() -> SummaryHierarchy:
    return SummaryHierarchy(
        chapter_summaries=[ChapterSummary(1, "One", "s1"), ChapterSummary(2, "Two", "s2")],
        act_summaries=[ActSummary(1, (1, 2), "act")],
        global_summary="all",
    )


def test_summaries_roundtrip(tmp_path: Path) -> None:
    assert load_summaries(tmp_path) == SummaryHierarchy()
    save_summaries(tmp_path, _hierarchy())
    assert load_summaries(tmp_path) == _hierarchy()
    (tmp_path / indexer.SUMMARIES_FILE).write_text("{bad", encoding="utf-8")
    assert load_summaries(tmp_path) == SummaryHierarchy()


def test_ensure_index_rebuilds_only_when_stale(tmp_path: Path, monkeypatch) -> None:
    calls: list[int] = []
    real = indexer.index_manuscript

    def counting(*a, **k):  # type: ignore[no-untyped-def]
        calls.append(1)
        return real(*a, **k)

    monkeypatch.setattr(indexer, "index_manuscript", counting)
    h = _hierarchy()
    assert ensure_index(_chapters(), h, tmp_path)[0] is True
    assert (tmp_path / "lancedb").is_dir()
    assert ensure_index(_chapters(), h, tmp_path)[0] is False
    assert ensure_index(_chapters(" Edited."), h, tmp_path)[0] is True
    assert ensure_index(_chapters(" Edited."), SummaryHierarchy(), tmp_path)[0] is True
    assert len(calls) == 3


def test_last_report_roundtrip(tmp_path: Path) -> None:
    assert load_last_report(tmp_path) is None
    save_last_report(tmp_path / "s", {"executive_summary": "x"})
    assert load_last_report(tmp_path / "s") == {"executive_summary": "x"}


def test_load_chapters_markdown(tmp_path: Path) -> None:
    md = tmp_path / "book.md"
    md.write_text("# Chapter 1\n\nHello there.\n\n# Chapter 2\n\nAgain.\n", encoding="utf-8")
    chapters = load_chapters(md)
    assert chapters
    assert "Hello there." in "".join(c.content for c in chapters)
