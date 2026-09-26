"""Book-wide algorithmic register_findings for analyze JSON export (#7)."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from ghostreader.analyzers.register_detector import detect_register
from ghostreader.companion.register import companion_register_to_dicts
from ghostreader.companion.register_constants import REGISTER_FINDINGS_CAP

_SEVERITY_RANK = {"high": 0, "moderate": 1, "low": 2}
_ALLOWED_KINDS = frozenset({"unearned_jargon", "initiation_budget"})


def analyze_register_findings(
    chapters: Sequence[Mapping[str, Any]],
    *,
    cap: int = REGISTER_FINDINGS_CAP,
    enabled: bool = True,
) -> list[dict[str, Any]]:
    """Run per-chapter opening register heuristics and merge for analyze JSON.

    Soft ``prose.human_door`` / ``prose.jargon_earn`` stay companion-only in v1.
    Callers gate *enabled* on ``analyze_register_watch`` and depth ∈
    ``{standard, deep}`` (not ``quick``).
    """
    if not enabled:
        return []

    rows: list[dict[str, Any]] = []
    for ch in chapters:
        content = str(ch.get("content") or "")
        chapter_number = int(ch.get("chapter_number") or 0)
        report = detect_register(content, chapter_number=chapter_number)
        rows.extend(companion_register_to_dicts(report, max_entries=cap))

    def _sort_key(row: dict[str, Any]) -> tuple[int, int, int, str]:
        sev = _SEVERITY_RANK.get(str(row.get("severity") or "low"), 99)
        kind_rank = 0 if row.get("kind") == "initiation_budget" else 1
        chapter = int(row.get("chapter") or 0)
        key = str(row.get("normalized_key") or row.get("term") or "")
        return (sev, kind_rank, chapter, key)

    cleaned = [r for r in rows if str(r.get("kind") or "") in _ALLOWED_KINDS]
    cleaned.sort(key=_sort_key)
    limit = max(0, int(cap))
    return cleaned[:limit]


__all__ = ["analyze_register_findings"]
