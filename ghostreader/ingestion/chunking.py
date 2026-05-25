"""Text chunking utility with configurable chunk size and overlap."""

from __future__ import annotations

from dataclasses import dataclass

DEFAULT_CHUNK_SIZE = 1500
DEFAULT_OVERLAP = 200


@dataclass
class TextChunk:
    """A chunk of text with metadata about its origin."""

    text: str
    chapter_number: int
    chunk_index: int
    source_path: str


def chunk_text(
    text: str,
    *,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_OVERLAP,
) -> list[str]:
    """Split *text* into overlapping chunks.

    Splits on paragraph boundaries where possible, falling back to
    character-level splitting for very long paragraphs.
    """
    if chunk_size <= 0:
        msg = f"chunk_size must be positive, got {chunk_size}"
        raise ValueError(msg)
    if overlap < 0 or overlap >= chunk_size:
        msg = f"overlap must be in [0, chunk_size), got {overlap}"
        raise ValueError(msg)

    if len(text) <= chunk_size:
        return [text] if text.strip() else []

    paragraphs = text.split("\n\n")
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue

        para_len = len(para)

        # If a single paragraph exceeds chunk_size, split it by characters
        if para_len > chunk_size:
            # Flush current buffer first
            if current:
                chunks.append("\n\n".join(current))
                current, current_len = _overlap_buffer(current, overlap)

            for sub in _split_long_paragraph(para, chunk_size, overlap):
                chunks.append(sub)
            continue

        # Would adding this paragraph exceed the limit?
        separator_cost = 2 if current else 0  # "\n\n" between paragraphs
        if current_len + separator_cost + para_len > chunk_size:
            chunks.append("\n\n".join(current))
            current, current_len = _overlap_buffer(current, overlap)

        current.append(para)
        current_len += (2 if len(current) > 1 else 0) + para_len

    if current:
        chunks.append("\n\n".join(current))

    return chunks


def _overlap_buffer(
    paragraphs: list[str], overlap: int
) -> tuple[list[str], int]:
    """Return trailing paragraphs that fit within *overlap* characters."""
    if overlap <= 0:
        return [], 0

    kept: list[str] = []
    total = 0

    for para in reversed(paragraphs):
        cost = len(para) + (2 if kept else 0)
        if total + cost > overlap:
            break
        kept.insert(0, para)
        total += cost

    return kept, total


def _split_long_paragraph(text: str, chunk_size: int, overlap: int) -> list[str]:
    """Character-level split for paragraphs that exceed chunk_size."""
    chunks: list[str] = []
    start = 0
    step = chunk_size - overlap

    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end])
        start += step

    return chunks
