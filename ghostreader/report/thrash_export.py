"""Book-wide algorithmic thrash_findings for analyze JSON export (#285 / #10)."""

from __future__ import annotations

import logging
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
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
# Keep some cross_chapter rows under the shared cap (KD-9 priority ranks them last).
_CROSS_CHAPTER_RESERVE_FRAC = 4  # up to cap // 4


def analyze_thrash_findings(
    chapters: Sequence[Mapping[str, Any]],
    *,
    cap: int = DEFAULT_THRASH_FINDINGS_CAP,
    enabled: bool = True,
    load_bearing: set[str] | frozenset[str] | None = None,
) -> list[dict[str, Any]]:
    """Run thrash heuristics and merge for analyze JSON.

    Soft ``prose.uncommon_thrash`` is deferred (KD-4). Callers gate *enabled*
    on ``analyze_thrash_watch`` and depth ∈ ``{standard, deep}`` (not ``quick``).
    Kill switch / disabled → ``[]``.

    ``load_bearing`` raises common-word thresholds (LOAD_BEARING_*) for those
    lemmas on the analyze product path.
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
        other_additive.extend(
            detect_common_word_thrash(
                content,
                chapter_number=chapter_number,
                load_bearing=load_bearing,
            )
        )
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
    capped = _cap_with_cross_chapter_reserve(cleaned, limit, sort_key=_sort_key)

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


def _cap_with_cross_chapter_reserve(
    rows: list[dict[str, Any]],
    limit: int,
    *,
    sort_key: Callable[[dict[str, Any]], tuple],
) -> list[dict[str, Any]]:
    """Apply cap while reserving seats so cross_chapter is not starved out."""
    if limit <= 0:
        return []
    if len(rows) <= limit:
        return rows
    cross = [r for r in rows if str(r.get("kind") or "") == "cross_chapter"]
    others = [r for r in rows if str(r.get("kind") or "") != "cross_chapter"]
    reserve = min(len(cross), max(1, limit // _CROSS_CHAPTER_RESERVE_FRAC)) if cross else 0
    other_budget = max(0, limit - reserve)
    picked = others[:other_budget] + cross[:reserve]
    # Fill any unused reserve from remaining others (short books / few cross rows).
    if len(picked) < limit:
        used = {id(r) for r in picked}
        for r in others[other_budget:]:
            if len(picked) >= limit:
                break
            if id(r) in used:
                continue
            picked.append(r)
    picked.sort(key=sort_key)
    return picked[:limit]


__all__ = ["DEFAULT_THRASH_FINDINGS_CAP", "analyze_thrash_findings"]
