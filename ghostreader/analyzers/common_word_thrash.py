"""Common-word carpet + fancy dialogue-tag thrash (#10 / compose Autonomicon #355).

S1: identity stubs return []. Real detectors land in S3.
"""

from __future__ import annotations

from ghostreader.analyzers.thrash_detector import ThrashFinding


def detect_common_word_thrash(
    content: str,
    *,
    chapter_number: int,
) -> list[ThrashFinding]:
    """Common-word carpet (kind=common_word). S1 no-op wire — returns []."""
    _ = (content, chapter_number)
    return []


def detect_dialogue_tag_thrash(
    content: str,
    *,
    chapter_number: int,
) -> list[ThrashFinding]:
    """Fancy dialogue-tag carpet (kind=dialogue_tag). S1 no-op wire — returns []."""
    _ = (content, chapter_number)
    return []


__all__ = ["detect_common_word_thrash", "detect_dialogue_tag_thrash"]
