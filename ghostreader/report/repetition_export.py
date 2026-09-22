"""Book-wide algorithmic repetition_findings for analyze JSON export."""

from __future__ import annotations

import re
from typing import Any, Mapping, Sequence

from ghostreader.excerpts import quote_from_text

_SEVERITY_RANK = {"high": 0, "moderate": 1, "low": 2}
_WS_RE = re.compile(r"\s+")
_ALLOWED_KINDS = frozenset({"word", "phrase", "sentence_pattern"})


def _normalized_key(phrase: str) -> str:
    return _WS_RE.sub(" ", phrase.strip().lower())


def _chapter_text(
    chapters: Sequence[Mapping[str, Any]],
    chapter_number: int,
) -> str:
    for ch in chapters:
        if int(ch.get("chapter_number") or 0) == chapter_number:
            return str(ch.get("content") or "")
    return ""


def _quote_for_row(
    entry: Mapping[str, Any],
    chapters: Sequence[Mapping[str, Any]],
) -> str | None:
    kind = str(entry.get("kind") or "phrase")
    if kind == "sentence_pattern":
        examples = [
            str(ex).strip()
            for ex in (entry.get("examples") or [])
            if str(ex).strip()
        ]
        if examples:
            return examples[0][:160]

    phrase = str(entry.get("phrase") or "")
    if not phrase:
        return None
    chapter_nums = [int(c) for c in (entry.get("chapters") or [])]
    for num in chapter_nums:
        text = _chapter_text(chapters, num)
        q = quote_from_text(phrase, text)
        if q:
            return q
    return None


def analyze_repetition_findings(
    repetition_data: Sequence[Mapping[str, Any]],
    chapters: Sequence[Mapping[str, Any]],
    *,
    cap: int = 40,
) -> list[dict[str, Any]]:
    """Project analyze ``repetition_data`` into export ``repetition_findings``.

    Builds from ``repetition_report_to_dicts`` rows only (no dialogue tags).
    Every row has ``focus_count: 0``. Cap defaults to 40.
    """
    rows: list[dict[str, Any]] = []
    for entry in repetition_data:
        kind = str(entry.get("kind") or "phrase")
        if kind not in _ALLOWED_KINDS:
            continue
        phrase = str(entry.get("phrase") or "")
        chapter_nums = sorted({int(c) for c in (entry.get("chapters") or [])})
        scope = "cross_chapter" if len(chapter_nums) > 1 else "local"
        severity = str(entry.get("severity") or "low")
        if severity not in _SEVERITY_RANK:
            severity = "low"
        rows.append(
            {
                "phrase": phrase,
                "kind": kind,
                "count": int(entry.get("count") or 0),
                "chapters": chapter_nums,
                "scope": scope,
                "severity": severity,
                "quote": _quote_for_row(entry, chapters),
                "normalized_key": (
                    _normalized_key(phrase) if phrase else None
                ),
                "focus_count": 0,
            }
        )

    def _sort_key(row: dict[str, Any]) -> tuple[int, int, int]:
        sev = _SEVERITY_RANK.get(str(row.get("severity") or "low"), 99)
        count = -int(row.get("count") or 0)
        multi = 0 if len(row.get("chapters") or []) > 1 else 1
        return (sev, count, multi)

    rows.sort(key=_sort_key)
    limit = max(0, int(cap))
    return rows[:limit]


__all__ = ["analyze_repetition_findings"]
