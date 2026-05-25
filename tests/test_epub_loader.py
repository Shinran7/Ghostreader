"""Tests for the epub loader module."""

from __future__ import annotations

from pathlib import Path

import pytest
from ebooklib import epub

from ghostreader.ingestion.epub_loader import (
    _crude_strip,
    _element_text,
    _extract_xhtml_title,
    _local_tag,
    _xhtml_to_text,
    load_epub,
)


# ── Helpers ──────────────────────────────────────────────────────────


def _make_epub(tmp_path: Path, chapters: list[tuple[str, str]], filename: str = "test.epub") -> Path:
    """Create a minimal epub with the given (title, body_html) chapters."""
    book = epub.EpubBook()
    book.set_identifier("test-id-123")
    book.set_title("Test Novel")
    book.set_language("en")
    book.add_author("Test Author")

    items = []
    for i, (title, body) in enumerate(chapters, 1):
        ch = epub.EpubHtml(title=title, file_name=f"ch{i}.xhtml", lang="en")
        ch.content = (
            f'<?xml version="1.0" encoding="UTF-8"?>'
            f'<html xmlns="http://www.w3.org/1999/xhtml">'
            f"<head><title>{title}</title></head>"
            f"<body>{body}</body></html>"
        ).encode("utf-8")
        book.add_item(ch)
        items.append(ch)

    book.toc = items
    book.spine = ["nav", *items]
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())

    out = tmp_path / filename
    epub.write_epub(str(out), book)
    return out


# ── load_epub tests ──────────────────────────────────────────────────


class TestLoadEpub:
    def test_loads_chapters(self, tmp_path: Path) -> None:
        body = "<p>" + "Word " * 20 + "</p>"
        path = _make_epub(tmp_path, [("Chapter 1", body), ("Chapter 2", body)])
        chapters = load_epub(path)
        assert len(chapters) >= 1
        assert chapters[0].chapter_number == 1
        assert len(chapters[0].content.strip()) > 0

    def test_file_not_found(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            load_epub(tmp_path / "nonexistent.epub")

    def test_wrong_extension(self, tmp_path: Path) -> None:
        bad = tmp_path / "novel.txt"
        bad.write_text("not an epub", encoding="utf-8")
        with pytest.raises(ValueError, match="Expected an .epub"):
            load_epub(bad)

    def test_skips_short_documents(self, tmp_path: Path) -> None:
        """Documents under 50 chars should be skipped (e.g. cover pages)."""
        short = "<p>Hi</p>"
        long = "<p>" + "This is substantial content. " * 10 + "</p>"
        path = _make_epub(tmp_path, [("Cover", short), ("Chapter 1", long)])
        chapters = load_epub(path)
        # The short doc should be skipped; at least the long one present
        for ch in chapters:
            assert len(ch.content.strip()) >= 50

    def test_empty_epub_raises(self, tmp_path: Path) -> None:
        """An epub with no substantial documents should raise ValueError."""
        book = epub.EpubBook()
        book.set_identifier("empty-id")
        book.set_title("Empty")
        book.set_language("en")
        book.add_item(epub.EpubNcx())
        book.add_item(epub.EpubNav())
        book.spine = ["nav"]

        path = tmp_path / "empty.epub"
        epub.write_epub(str(path), book)
        with pytest.raises(ValueError, match="No readable chapters"):
            load_epub(path)


# ── XHTML parsing helpers ────────────────────────────────────────────


class TestXhtmlToText:
    def test_basic_paragraph(self) -> None:
        html = b"<html><body><p>Hello world</p></body></html>"
        text = _xhtml_to_text(html)
        assert "Hello world" in text

    def test_nested_tags(self) -> None:
        html = b"<html><body><p>This is <em>important</em> text.</p></body></html>"
        text = _xhtml_to_text(html)
        assert "important" in text
        assert "This is" in text

    def test_malformed_html_fallback(self) -> None:
        bad = b"<not valid xml <>"
        text = _xhtml_to_text(bad)
        assert isinstance(text, str)


class TestExtractXhtmlTitle:
    def test_finds_title_tag(self) -> None:
        html = b'<html><head><title>My Title</title></head><body></body></html>'
        assert _extract_xhtml_title(html, fallback="nope") == "My Title"

    def test_finds_h1_fallback(self) -> None:
        html = b"<html><body><h1>Heading One</h1></body></html>"
        assert _extract_xhtml_title(html, fallback="nope") == "Heading One"

    def test_returns_fallback_on_empty(self) -> None:
        html = b"<html><body><p>Just text.</p></body></html>"
        assert _extract_xhtml_title(html, fallback="Fallback") == "Fallback"

    def test_returns_fallback_on_parse_error(self) -> None:
        bad = b"<<<not xml"
        assert _extract_xhtml_title(bad, fallback="oops") == "oops"


class TestLocalTag:
    def test_strips_namespace(self) -> None:
        assert _local_tag("{http://www.w3.org/1999/xhtml}body") == "body"

    def test_no_namespace(self) -> None:
        assert _local_tag("div") == "div"


class TestCrudeStrip:
    def test_strips_tags(self) -> None:
        result = _crude_strip("<p>Hello <b>world</b></p>")
        assert "Hello" in result
        assert "world" in result
        assert "<" not in result


class TestElementText:
    def test_collects_nested_text(self) -> None:
        import xml.etree.ElementTree as ET
        root = ET.fromstring("<div><p>one</p><p>two</p></div>")
        text = _element_text(root)
        assert "one" in text
        assert "two" in text
