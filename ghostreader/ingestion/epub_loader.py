"""Epub manuscript loader using ebooklib + stdlib xml.etree.ElementTree."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

import ebooklib
from ebooklib import epub

from ghostreader.ingestion import Chapter


def load_epub(path: Path) -> list[Chapter]:
    """Load chapters from an .epub file.

    Reads the spine-ordered XHTML documents, strips markup via
    ElementTree, and returns one Chapter per document.
    """
    path = path.resolve()

    if not path.is_file():
        msg = f"Epub file not found: {path}"
        raise FileNotFoundError(msg)

    if path.suffix.lower() != ".epub":
        msg = f"Expected an .epub file, got: {path.name}"
        raise ValueError(msg)

    book = epub.read_epub(str(path), options={"ignore_ncx": True})

    chapters: list[Chapter] = []
    chapter_num = 0

    for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
        raw_html = item.get_content()
        text = _xhtml_to_text(raw_html)

        # Skip near-empty documents (e.g. cover pages, copyright)
        if len(text.strip()) < 50:
            continue

        chapter_num += 1
        title = _extract_xhtml_title(raw_html, fallback=f"Chapter {chapter_num}")

        chapters.append(
            Chapter(
                title=title,
                content=text,
                chapter_number=chapter_num,
                source_path=path,
            )
        )

    if not chapters:
        msg = f"No readable chapters found in {path}"
        raise ValueError(msg)

    return chapters


def _xhtml_to_text(raw: bytes) -> str:
    """Convert XHTML bytes to plain text by stripping all tags."""
    try:
        root = ET.fromstring(raw)  # noqa: S314
    except ET.ParseError:
        # Fallback: decode and strip angle-bracket content crudely
        return _crude_strip(raw.decode("utf-8", errors="replace"))

    return _element_text(root)


def _element_text(elem: ET.Element) -> str:
    """Recursively collect all text nodes from an element tree."""
    parts: list[str] = []
    if elem.text:
        parts.append(elem.text)
    for child in elem:
        parts.append(_element_text(child))
        if child.tail:
            parts.append(child.tail)

    tag = _local_tag(elem.tag)
    if tag in ("p", "div", "h1", "h2", "h3", "h4", "h5", "h6", "br", "li"):
        return "\n".join(parts) + "\n"
    return " ".join(parts)


def _extract_xhtml_title(raw: bytes, *, fallback: str) -> str:
    """Try to pull a <title> or first <h1>/<h2> from XHTML."""
    try:
        root = ET.fromstring(raw)  # noqa: S314
    except ET.ParseError:
        return fallback

    # Search for <title> anywhere (namespace-agnostic)
    for elem in root.iter():
        tag = _local_tag(elem.tag)
        if tag == "title" and elem.text and elem.text.strip():
            return elem.text.strip()

    # Fallback to first heading
    for elem in root.iter():
        tag = _local_tag(elem.tag)
        if tag in ("h1", "h2") and elem.text and elem.text.strip():
            return elem.text.strip()

    return fallback


def _local_tag(tag: str) -> str:
    """Strip namespace prefix from an ElementTree tag, e.g. {http://...}body -> body."""
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag


def _crude_strip(html: str) -> str:
    """Last-resort: strip anything between < and >."""
    import re

    return re.sub(r"<[^>]+>", " ", html)
