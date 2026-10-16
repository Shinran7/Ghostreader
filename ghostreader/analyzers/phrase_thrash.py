"""Literary multi-word phrase thrash (#10 / compose Autonomicon #355).

S1: identity stub returns []. Real detector lands in S4.
"""

from __future__ import annotations

from ghostreader.analyzers.thrash_detector import ThrashFinding


def detect_phrase_thrash(
    content: str,
    *,
    chapter_number: int,
) -> list[ThrashFinding]:
    """Adjacent 2–3 content-gram thrash (kind=phrase). S1 no-op wire — returns []."""
    _ = (content, chapter_number)
    return []


__all__ = ["detect_phrase_thrash"]
