"""Book-wide algorithmic thrash_findings for analyze JSON export (#285)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from ghostreader.analyzers.thrash_detector import (
    aggregate_cross_chapter,
    detect_thrash_in_chapter,
    finding_to_dict,
)

_SEVERITY_RANK = {"high": 0, "moderate": 1, "low": 2}
_ALLOWED_KINDS = frozenset({"within_scene", "cross_chapter"})
DEFAULT_THRASH_FINDINGS_CAP = 40


def analyze_thrash_findings(
    chapters: Sequence[Mapping[str, Any]],
    *,
    cap: int = DEFAULT_THRASH_FINDINGS_CAP,
    enabled: bool = True,
) -> list[dict[str, Any]]:
    """Run Zipf uncommon-noun thrash heuristics and merge for analyze JSON.

    Soft ``prose.uncommon_thrash`` is deferred (KD-4). Callers gate *enabled*
    on ``analyze_thrash_watch`` and depth ∈ ``{standard, deep}`` (not ``quick``).
    Kill switch / disabled → ``[]``.
    """
    if not enabled:
        return []

    within_rows = []
    for ch in chapters:
        content = str(ch.get("content") or "")
        chapter_number = int(ch.get("chapter_number") or 0)
        within_rows.extend(detect_thrash_in_chapter(content, chapter_number=chapter_number))

    cross_rows = aggregate_cross_chapter(within_rows)
    merged = [finding_to_dict(r) for r in within_rows + cross_rows]
    cleaned = [r for r in merged if str(r.get("kind") or "") in _ALLOWED_KINDS]

    def _sort_key(row: dict[str, Any]) -> tuple[int, int, int, str]:
        sev = _SEVERITY_RANK.get(str(row.get("severity") or "low"), 99)
        kind_rank = 0 if row.get("kind") == "within_scene" else 1
        count = -int(row.get("count") or 0)
        key = str(row.get("normalized_key") or row.get("lemma") or "")
        return (sev, kind_rank, count, key)

    cleaned.sort(key=_sort_key)
    limit = max(0, int(cap))
    return cleaned[:limit]


__all__ = ["DEFAULT_THRASH_FINDINGS_CAP", "analyze_thrash_findings"]
