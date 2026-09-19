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

_CH_PREFIX = re.compile(r"\bCh(?:apter)?\s*(\d+)\b", re.IGNORECASE)
_INT = re.compile(r"\d+")


def cited_chapters(finding: dict[str, Any]) -> set[int]:
    """Deterministic chapter set for partition / involves_N.

    Sources (union):
    1. All integers in ``chapter_ref``.
    2. ``Ch`` / ``Chapter`` prefixes in ``evidence`` and ``counter_evidence``.
    """
    nums: set[int] = set()
    ref = str(finding.get("chapter_ref") or "")
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


def is_grounded_progressive(finding: dict[str, Any], *, N: int) -> bool:
    evidence = str(finding.get("evidence") or "").strip()
    counter = str(finding.get("counter_evidence") or "").strip()
    chs = cited_chapters(finding)
    return bool(evidence) and bool(counter) and (N in chs) and (len(chs) >= 2)


def is_grounded_sweep(finding: dict[str, Any]) -> bool:
    evidence = str(finding.get("evidence") or "").strip()
    counter = str(finding.get("counter_evidence") or "").strip()
    chs = cited_chapters(finding)
    return bool(evidence) and bool(counter) and (len(chs) >= 2)


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
    "Partition",
    "cited_chapters",
    "involves_N",
    "is_clearly_preexisting",
    "is_grounded_progressive",
    "is_grounded_sweep",
    "partition_findings",
]
