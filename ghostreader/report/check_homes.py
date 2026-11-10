"""One home per check (#19).

GhostCopyeditor owns sentence- and scene-level copy editing; Ghostreader owns
reader- and book-level critique. These helpers drop the soft dimensions a run
leaves to GhostCopyeditor and remove the overlap between the three repetition
surfaces in analyze: soft ``prose.repetition`` findings, ``repetition_findings``
and ``thrash_findings``. Machine rows win, because they carry exact phrases
and chapters.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any

from ghostreader.report import (
    SEVERITY_CONCERN,
    SEVERITY_STRENGTH,
    PrioritizedFinding,
    ReportOutput,
)

_WS = re.compile(r"\s+")
# A single word must be at least this long to count as a match; shorter words
# are too common to tie a soft finding to one machine row.
_MIN_WORD_KEY = 5


def _norm(text: str) -> str:
    return _WS.sub(" ", str(text or "").lower()).strip()


def drop_finding_dimensions(
    findings: list[dict[str, Any]], ratings: dict[str, Any], dims: Iterable[str]
) -> tuple[list[dict[str, Any]], dict[str, Any], int]:
    """Remove *dims* from raw finding rows and a ratings map.

    Returns ``(findings, ratings, dropped_finding_count)``.
    """
    drop = set(dims)
    if not drop:
        return findings, ratings, 0
    kept = [f for f in findings if str(f.get("dimension") or "") not in drop]
    kept_ratings = {d: r for d, r in ratings.items() if d not in drop}
    return kept, kept_ratings, len(findings) - len(kept)


def _remove_findings(report: ReportOutput, gone: list[PrioritizedFinding]) -> None:
    if not gone:
        return
    ids = {id(f) for f in gone}
    report.prioritized_findings = [f for f in report.prioritized_findings if id(f) not in ids]
    for rank, f in enumerate(report.prioritized_findings, start=1):
        f.rank = rank
    report.total_findings = max(0, report.total_findings - len(gone))
    report.concerns_count = max(
        0, report.concerns_count - sum(f.severity == SEVERITY_CONCERN for f in gone)
    )
    report.strengths_count = max(
        0, report.strengths_count - sum(f.severity == SEVERITY_STRENGTH for f in gone)
    )


def drop_report_dimensions(report: ReportOutput, dims: Iterable[str]) -> int:
    """Remove *dims* from an analyze report's findings and ratings; re-rank."""
    drop = set(dims)
    if not drop:
        return 0
    gone = [f for f in report.prioritized_findings if f.dimension in drop]
    _remove_findings(report, gone)
    report.dimension_ratings = [r for r in report.dimension_ratings if r.dimension not in drop]
    report.unverified_findings = [
        f for f in report.unverified_findings if str(f.get("dimension") or "") not in drop
    ]
    return len(gone)


def _machine_keys(report: ReportOutput) -> list[str]:
    keys: set[str] = set()
    for row in report.repetition_findings:
        keys.add(_norm(row.get("phrase") or ""))
    for row in report.thrash_findings:
        keys.add(_norm(row.get("phrase") or row.get("lemma") or ""))
    return sorted(k for k in keys if " " in k or len(k) >= _MIN_WORD_KEY)


def _mentions(text: str, key: str) -> bool:
    return re.search(rf"(?<!\w){re.escape(key)}(?!\w)", text) is not None


def dedupe_repetition(report: ReportOutput) -> dict[str, int]:
    """Drop overlap between the repetition surfaces in place.

    - A ``phrase`` thrash row whose phrase is already a ``repetition_findings``
      row is dropped (the repetition row is the avoid-list entry).
    - A ``prose.repetition`` concern whose summary or evidence names a
      machine row's phrase or word is dropped from ``prioritized_findings``.

    Returns ``{thrash_phrase_rows, prose_repetition_findings}`` drop counts.
    """
    rep_phrases = {_norm(r.get("phrase") or "") for r in report.repetition_findings}
    rep_phrases.discard("")
    before = len(report.thrash_findings)
    report.thrash_findings = [
        r
        for r in report.thrash_findings
        if not (r.get("kind") == "phrase" and _norm(r.get("phrase") or "") in rep_phrases)
    ]
    thrash_dropped = before - len(report.thrash_findings)

    keys = _machine_keys(report)
    gone: list[PrioritizedFinding] = []
    if keys:
        for f in report.prioritized_findings:
            if f.dimension != "prose.repetition" or f.severity != SEVERITY_CONCERN:
                continue
            text = _norm(f"{f.summary} {f.evidence}")
            if any(_mentions(text, k) for k in keys):
                gone.append(f)
    _remove_findings(report, gone)
    return {"thrash_phrase_rows": thrash_dropped, "prose_repetition_findings": len(gone)}


__all__ = [
    "dedupe_repetition",
    "drop_finding_dimensions",
    "drop_report_dimensions",
]
