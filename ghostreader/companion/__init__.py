"""Chapter Companion — progressive continuity + craft brief for Autonomicon hooks."""

from __future__ import annotations

from ghostreader.companion.brief import CompanionBrief, compute_verdict
from ghostreader.companion.continuity import (
    COMPANION_GATE_DIMS,
    cited_chapters,
    involves_N,
    partition_findings,
)
from ghostreader.companion.fact_memory import FactMemoryStore, FactRecord

__all__ = [
    "COMPANION_GATE_DIMS",
    "CompanionBrief",
    "FactMemoryStore",
    "FactRecord",
    "cited_chapters",
    "compute_verdict",
    "involves_N",
    "partition_findings",
]
