"""Chapter-ref parsing and total partition for companion continuity gates."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Literal

COMPANION_GATE_DIMS = frozenset({
    "consistency.character",
    "consistency.timeline",
    "consistency.plot_holes",
})

COMPANION_INFO_DIMS = frozenset({
    "consistency.foreshadowing",
    "consistency.unresolved",
})

_CH_PREFIX = re.compile(r"\bCh(?:apters?|s)?\.?\s*(\d+)\b", re.IGNORECASE)
_INT = re.compile(r"\d+")
# Sub-chapter locators in chapter_ref ("scene 3", "line 40") are not chapters.
_SUB_LOCATOR = re.compile(
    r"\b(?:scenes?|lines?|para(?:graph)?s?|pages?|pp?\.|beats?|parts?|sections?)"
    r"\.?\s*\d+(?:\s*(?:-|–|and|,)\s*\d+)*",
    re.IGNORECASE,
)
_WS = re.compile(r"\s+")


def cited_chapters(finding: dict[str, Any]) -> set[int]:
    """Deterministic chapter set for partition / involves_N.

    Sources (union):
    1. Integers in ``chapter_ref``, after removing sub-chapter locators
       (``scene 3``, ``line 40``, ``para 2``, ``p. 7``).
    2. ``Ch`` / ``Chapter`` prefixes in ``evidence`` and ``counter_evidence``.
    """
    nums: set[int] = set()
    ref = _SUB_LOCATOR.sub(" ", str(finding.get("chapter_ref") or ""))
    nums.update(int(x) for x in _INT.findall(ref))
    for field_name in ("evidence", "counter_evidence"):
        text = str(finding.get(field_name) or "")
        nums.update(int(m.group(1)) for m in _CH_PREFIX.finditer(text))
    return nums


def involves_N(finding: dict[str, Any], *, N: int) -> bool:
    return N in cited_chapters(finding)


def is_clearly_preexisting(finding: dict[str, Any], *, N: int) -> bool:
    """True only when we parsed ≥1 chapter and every cited chapter is < N."""
    chs = cited_chapters(finding)
    return bool(chs) and all(c < N for c in chs)


def _norm_quote(text: str) -> str:
    return _WS.sub(" ", text).strip().lower()


def _two_distinct_quotes(finding: dict[str, Any]) -> bool:
    evidence = _norm_quote(str(finding.get("evidence") or ""))
    counter = _norm_quote(str(finding.get("counter_evidence") or ""))
    return bool(evidence) and bool(counter) and evidence != counter


def is_grounded_progressive(finding: dict[str, Any], *, N: int) -> bool:
    """Evidence + counter, chapter N cited, and either another chapter cited
    or a same-chapter contradiction (N only, two different quotes)."""
    if not _two_distinct_quotes(finding):
        return False
    chs = cited_chapters(finding)
    return N in chs and (len(chs) >= 2 or chs == {N})


def is_grounded_sweep(finding: dict[str, Any]) -> bool:
    """Evidence + counter (two different quotes) and ≥1 cited chapter."""
    return _two_distinct_quotes(finding) and len(cited_chapters(finding)) >= 1


def is_grounded_info_progressive(finding: dict[str, Any], *, N: int) -> bool:
    """Soft grounding: non-empty evidence + involves N (counter optional)."""
    evidence = str(finding.get("evidence") or "").strip()
    return bool(evidence) and involves_N(finding, N=N)


def is_grounded_info_sweep(finding: dict[str, Any]) -> bool:
    """Soft grounding: non-empty evidence + ≥1 cited chapter."""
    evidence = str(finding.get("evidence") or "").strip()
    return bool(evidence) and bool(cited_chapters(finding))


def collect_info_findings(
    findings: list[dict[str, Any]],
    *,
    N: int,
    mode: Literal["progressive", "sweep"],
) -> tuple[list[dict[str, Any]], int]:
    """Collect watch-only info-dim concerns.

    Returns ``(grounded_findings, ungrounded_count)``. Strengths are skipped.
    Progressive: clearly preexisting info (all cited chapters < N) is omitted
    from the chapter-N list (not counted as ungrounded). No preexisting_info
    bucket in v1.
    """
    kept: list[dict[str, Any]] = []
    ungrounded = 0

    for f in findings:
        if f.get("dimension") not in COMPANION_INFO_DIMS:
            continue
        if f.get("severity") != "concern":
            continue
        if mode == "progressive" and is_clearly_preexisting(f, N=N):
            continue
        if mode == "sweep":
            if is_grounded_info_sweep(f):
                kept.append(f)
            else:
                ungrounded += 1
        elif is_grounded_info_progressive(f, N=N):
            kept.append(f)
        else:
            ungrounded += 1

    return kept, ungrounded


def ensure_info_ratings(
    ratings: dict[str, dict[str, str]] | None = None,
) -> dict[str, dict[str, str]]:
    """Always both foreshadowing + unresolved (neutral default)."""
    src = ratings or {}
    out: dict[str, dict[str, str]] = {}
    for dim in sorted(COMPANION_INFO_DIMS):
        if dim in src:
            out[dim] = {
                "severity": str(src[dim].get("severity") or "neutral"),
                "note": str(src[dim].get("note") or ""),
            }
        else:
            out[dim] = {"severity": "neutral", "note": ""}
    return out


CONSISTENCY_PARSE_FAILED_DIM = "consistency.general"


def continuity_parse_failed(findings: list[dict[str, Any]]) -> bool:
    """True when the consistency pass returned no usable structured findings.

    The parser surfaces that as a ``consistency.general`` concern. It is not a
    gate dim, so without this check a failed pass would look like a clean one.
    """
    return any(
        f.get("dimension") == CONSISTENCY_PARSE_FAILED_DIM and f.get("severity") == "concern"
        for f in findings
    )


@dataclass
class Partition:
    """Total partition of gate-dim concerns: gate / preexisting / ungrounded."""

    gate: list[dict[str, Any]] = field(default_factory=list)
    preexisting: list[dict[str, Any]] = field(default_factory=list)
    ungrounded: list[dict[str, Any]] = field(default_factory=list)


def partition_findings(
    findings: list[dict[str, Any]],
    *,
    N: int,
    mode: Literal["progressive", "sweep"],
) -> Partition:
    """Total partition — every gate-dim concern lands in exactly one list."""
    gate: list[dict[str, Any]] = []
    preexisting: list[dict[str, Any]] = []
    ungrounded: list[dict[str, Any]] = []

    for f in findings:
        if f.get("dimension") not in COMPANION_GATE_DIMS:
            continue
        if f.get("severity") != "concern":
            continue
        if mode == "sweep":
            if is_grounded_sweep(f):
                gate.append(f)
            else:
                ungrounded.append(f)
            continue
        # progressive
        if is_clearly_preexisting(f, N=N):
            preexisting.append(f)
        elif involves_N(f, N=N) and is_grounded_progressive(f, N=N):
            gate.append(f)
        else:
            ungrounded.append(f)

    return Partition(gate=gate, preexisting=preexisting, ungrounded=ungrounded)


__all__ = [
    "COMPANION_GATE_DIMS",
    "COMPANION_INFO_DIMS",
    "CONSISTENCY_PARSE_FAILED_DIM",
    "Partition",
    "cited_chapters",
    "collect_info_findings",
    "continuity_parse_failed",
    "ensure_info_ratings",
    "involves_N",
    "is_grounded_info_progressive",
    "is_grounded_info_sweep",
    "is_clearly_preexisting",
    "is_grounded_progressive",
    "is_grounded_sweep",
    "partition_findings",
]
