"""Tests for involves_N / total partition (gate / preexisting / ungrounded)."""

from __future__ import annotations

from ghostreader.companion.continuity import (
    cited_chapters,
    involves_N,
    is_clearly_preexisting,
    partition_findings,
)


def _finding(
    *,
    dimension: str = "consistency.character",
    severity: str = "concern",
    chapter_ref: str = "",
    evidence: str = "",
    counter_evidence: str = "",
    summary: str = "x",
) -> dict:
    return {
        "dimension": dimension,
        "severity": severity,
        "summary": summary,
        "chapter_ref": chapter_ref,
        "evidence": evidence,
        "counter_evidence": counter_evidence,
    }


class TestCitedChapters:
    def test_digit_scan_chapter_ref(self) -> None:
        assert cited_chapters(_finding(chapter_ref="12 vs 18")) == {12, 18}
        assert cited_chapters(_finding(chapter_ref="Ch 3 vs Ch 7")) == {3, 7}

    def test_evidence_ch_prefix(self) -> None:
        f = _finding(
            evidence="Ch 12: she was tall",
            counter_evidence="Chapter 18: he was short",
        )
        assert cited_chapters(f) == {12, 18}


class TestInvolvesAndPreexisting:
    def test_involves_n(self) -> None:
        f = _finding(chapter_ref="12 vs 18")
        assert involves_N(f, N=18)
        assert not involves_N(f, N=7)

    def test_clearly_preexisting_3_vs_7(self) -> None:
        f = _finding(chapter_ref="3 vs 7")
        assert is_clearly_preexisting(f, N=18)
        assert not is_clearly_preexisting(f, N=5)


class TestPartitionProgressive:
    def test_12_vs_18_gate(self) -> None:
        f = _finding(
            chapter_ref="12 vs 18",
            evidence="Ch 12: cousin is male",
            counter_evidence="Ch 18: cousin is female",
        )
        part = partition_findings([f], N=18, mode="progressive")
        assert part.gate == [f]
        assert part.preexisting == []
        assert part.ungrounded == []

    def test_3_vs_7_preexisting(self) -> None:
        f = _finding(
            chapter_ref="3 vs 7",
            evidence="Ch 3: red door",
            counter_evidence="Ch 7: blue door",
        )
        part = partition_findings([f], N=18, mode="progressive")
        assert part.preexisting == [f]
        assert part.gate == []
        assert part.ungrounded == []

    def test_empty_citation_ungrounded(self) -> None:
        f = _finding(chapter_ref="", evidence="", counter_evidence="")
        part = partition_findings([f], N=18, mode="progressive")
        assert part.ungrounded == [f]
        assert part.gate == []
        assert part.preexisting == []

    def test_foreshadowing_does_not_gate(self) -> None:
        f = _finding(
            dimension="consistency.foreshadowing",
            chapter_ref="1 vs 18",
            evidence="Ch 1: gun",
            counter_evidence="Ch 18: never fired",
        )
        part = partition_findings([f], N=18, mode="progressive")
        assert part.gate == []
        assert part.preexisting == []
        assert part.ungrounded == []

    def test_involves_n_but_missing_counter_is_ungrounded(self) -> None:
        f = _finding(
            chapter_ref="12 vs 18",
            evidence="Ch 12: x",
            counter_evidence="",
        )
        part = partition_findings([f], N=18, mode="progressive")
        assert part.ungrounded == [f]


class TestPartitionSweep:
    def test_3_vs_7_grounded_is_gate_not_preexisting(self) -> None:
        f = _finding(
            chapter_ref="3 vs 7",
            evidence="Ch 3: red",
            counter_evidence="Ch 7: blue",
        )
        part = partition_findings([f], N=18, mode="sweep")
        assert part.gate == [f]
        assert part.preexisting == []
        assert part.ungrounded == []

    def test_ungrounded_in_sweep(self) -> None:
        f = _finding(chapter_ref="", evidence="x", counter_evidence="")
        part = partition_findings([f], N=18, mode="sweep")
        assert part.ungrounded == [f]
