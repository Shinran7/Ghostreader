"""Tests for the ingestion pipeline modules."""

from __future__ import annotations

from pathlib import Path

import pytest

from ghostreader.ingestion import Chapter, SummaryHierarchy
from ghostreader.ingestion.chunking import TextChunk, chunk_text
from ghostreader.ingestion.markdown_loader import load_markdown


# ── markdown_loader ──────────────────────────────────────────────────


class TestLoadMarkdown:
    def test_load_single_file(self, tmp_path: Path) -> None:
        md = tmp_path / "story.md"
        md.write_text("# My Story\n\nOnce upon a time...", encoding="utf-8")
        chapters = load_markdown(md)
        assert len(chapters) == 1
        assert chapters[0].title == "My Story"
        assert chapters[0].chapter_number == 1

    def test_load_directory_numbered(self, tmp_manuscript_dir: Path) -> None:
        chapters = load_markdown(tmp_manuscript_dir)
        assert len(chapters) == 3
        assert chapters[0].chapter_number == 1
        assert chapters[2].chapter_number == 3

    def test_load_directory_extracts_titles(self, tmp_manuscript_dir: Path) -> None:
        chapters = load_markdown(tmp_manuscript_dir)
        assert chapters[0].title == "Chapter 1"

    def test_nonexistent_path_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            load_markdown(tmp_path / "nope")

    def test_non_md_file_raises(self, tmp_path: Path) -> None:
        txt = tmp_path / "story.txt"
        txt.write_text("hello", encoding="utf-8")
        with pytest.raises(ValueError, match="Expected a .md file"):
            load_markdown(txt)

    def test_empty_directory_raises(self, tmp_path: Path) -> None:
        empty = tmp_path / "empty"
        empty.mkdir()
        with pytest.raises(FileNotFoundError, match="No .md files"):
            load_markdown(empty)


# ── chunking ──────────────────────────────────────────────────────────


class TestChunkText:
    def test_short_text_single_chunk(self) -> None:
        text = "Hello, world."
        chunks = chunk_text(text, chunk_size=100, overlap=10)
        assert chunks == [text]

    def test_empty_text_returns_empty(self) -> None:
        assert chunk_text("", chunk_size=100, overlap=10) == []

    def test_whitespace_only_returns_empty(self) -> None:
        assert chunk_text("   \n\n  ", chunk_size=100, overlap=10) == []

    def test_multi_paragraph_chunking(self) -> None:
        paras = ["Paragraph one. " * 10, "Paragraph two. " * 10, "Paragraph three. " * 10]
        text = "\n\n".join(paras)
        chunks = chunk_text(text, chunk_size=200, overlap=50)
        assert len(chunks) >= 2
        # All original text should be recoverable
        for para in paras:
            assert any(para.strip() in chunk for chunk in chunks)

    def test_overlap_preserves_context(self) -> None:
        text = "A. " * 50 + "\n\n" + "B. " * 50
        chunks = chunk_text(text, chunk_size=100, overlap=30)
        if len(chunks) >= 2:
            # Some text should appear in consecutive chunks (overlap)
            last_of_first = chunks[0][-20:]
            assert any(last_of_first[:10] in c for c in chunks)

    def test_invalid_chunk_size_raises(self) -> None:
        with pytest.raises(ValueError, match="chunk_size must be positive"):
            chunk_text("hello", chunk_size=0, overlap=0)

    def test_overlap_gte_chunk_size_raises(self) -> None:
        with pytest.raises(ValueError, match="overlap must be in"):
            chunk_text("hello", chunk_size=10, overlap=10)


# ── summarizer ────────────────────────────────────────────────────────


class TestBuildSummaryHierarchy:
    @pytest.mark.asyncio()
    async def test_produces_chapter_summaries(
        self, sample_chapters: list[Chapter], stub_llm: object
    ) -> None:
        from ghostreader.ingestion.summarizer import build_summary_hierarchy

        hierarchy = await build_summary_hierarchy(sample_chapters, stub_llm)
        assert len(hierarchy.chapter_summaries) == 3
        assert hierarchy.chapter_summaries[0].chapter_number == 1

    @pytest.mark.asyncio()
    async def test_produces_act_summaries(
        self, sample_chapters: list[Chapter], stub_llm: object
    ) -> None:
        from ghostreader.ingestion.summarizer import build_summary_hierarchy

        hierarchy = await build_summary_hierarchy(
            sample_chapters, stub_llm, chapters_per_act=2
        )
        assert len(hierarchy.act_summaries) == 2  # 3 chapters / 2 per act = 2 acts

    @pytest.mark.asyncio()
    async def test_produces_global_summary(
        self, sample_chapters: list[Chapter], stub_llm: object
    ) -> None:
        from ghostreader.ingestion.summarizer import build_summary_hierarchy

        hierarchy = await build_summary_hierarchy(sample_chapters, stub_llm)
        assert hierarchy.global_summary  # non-empty string
