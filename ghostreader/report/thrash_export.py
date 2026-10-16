"""Book-wide algorithmic thrash_findings for analyze JSON export (#285 / #10)."""

from __future__ import annotations

import logging
from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any

from ghostreader.analyzers.common_word_thrash import (
    detect_common_word_thrash,
    detect_dialogue_tag_thrash,
)
from ghostreader.analyzers.phrase_thrash import detect_phrase_thrash
from ghostreader.analyzers.thrash_detector import (
    aggregate_cross_chapter,
    detect_chapter_rare,
    detect_thrash_in_chapter,
    finding_to_dict,
)

logger = logging.getLogger(__name__)

_SEVERITY_RANK = {"high": 0, "moderate": 1, "low": 2}
_ALLOWED_KINDS = frozenset(
    {
        "within_scene",
        "cross_chapter",
        "chapter_rare",
        "common_word",
        "phrase",
        "dialogue_tag",
    }
)
_KIND_PRIORITY = {
    "within_scene": 0,
    "chapter_rare": 1,
    "phrase": 2,
    "dialogue_tag": 3,
    "common_word": 4,
    "cross_chapter": 5,
}
DEFAULT_THRASH_FINDINGS_CAP = 40


def analyze_thrash_findings(
    chapters: Sequence[Mapping[str, Any]],
    *,
    cap: int = DEFAULT_THRASH_FINDINGS_CAP,
    enabled: bool = True,
) -> list[dict[str, Any]]:
    """Run thrash heuristics and merge for analyze JSON.

    Soft ``prose.uncommon_thrash`` is deferred (KD-4). Callers gate *enabled*
    on ``analyze_thrash_watch`` and depth ∈ ``{standard, deep}`` (not ``quick``).
    Kill switch / disabled → ``[]``.
    """
    if not enabled:
        return []

    within_rows = []
    chapter_rare_rows = []
    other_additive = []
    for ch in chapters:
        content = str(ch.get("content") or "")
        chapter_number = int(ch.get("chapter_number") or 0)
        within_rows.extend(detect_thrash_in_chapter(content, chapter_number=chapter_number))
        chapter_rare_rows.extend(detect_chapter_rare(content, chapter_number=chapter_number))
        other_additive.extend(detect_common_word_thrash(content, chapter_number=chapter_number))
        other_additive.extend(detect_phrase_thrash(content, chapter_number=chapter_number))
        other_additive.extend(detect_dialogue_tag_thrash(content, chapter_number=chapter_number))

    # KD-3: within_scene wins — drop chapter_rare for same lemma+chapter.
    within_keys = {(r.lemma, int(r.chapter or 0)) for r in within_rows if r.kind == "within_scene"}
    chapter_rare_rows = [
        r for r in chapter_rare_rows if (r.lemma, int(r.chapter or 0)) not in within_keys
    ]

    cross_rows = aggregate_cross_chapter(within_rows, chapter_rare=chapter_rare_rows)
    merged = [
        finding_to_dict(r) for r in within_rows + chapter_rare_rows + other_additive + cross_rows
    ]
    cleaned = [r for r in merged if str(r.get("kind") or "") in _ALLOWED_KINDS]

    def _sort_key(row: dict[str, Any]) -> tuple[int, int, int, str]:
        sev = _SEVERITY_RANK.get(str(row.get("severity") or "low"), 99)
        kind_rank = _KIND_PRIORITY.get(str(row.get("kind") or ""), 99)
        count = -int(row.get("count") or 0)
        key = str(row.get("normalized_key") or row.get("lemma") or row.get("phrase") or "")
        return (sev, kind_rank, count, key)

    cleaned.sort(key=_sort_key)
    limit = max(0, int(cap))
    capped = cleaned[:limit]

    counts = Counter(str(r.get("kind") or "") for r in capped)
    logger.info(
        "thrash_findings: within=%d chapter_rare=%d common=%d phrase=%d "
        "dialogue_tag=%d cross=%d capped=%d",
        counts.get("within_scene", 0),
        counts.get("chapter_rare", 0),
        counts.get("common_word", 0),
        counts.get("phrase", 0),
        counts.get("dialogue_tag", 0),
        counts.get("cross_chapter", 0),
        len(capped),
    )
    return capped


__all__ = ["DEFAULT_THRASH_FINDINGS_CAP", "analyze_thrash_findings"]
