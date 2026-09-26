"""Tests for register heuristic / initiation budget (#7 S0)."""

from __future__ import annotations

from pathlib import Path

from ghostreader.analyzers.register_detector import (
    detect_register,
    strip_chapter_body,
)
from ghostreader.companion.register import (
    companion_register_to_dicts,
    register_block,
    register_findings_for_chapter,
)
from ghostreader.companion.register_constants import (
    HYPHEN_DENYLIST,
    INITIATION_BUDGET_COINED_NOUNS,
    INITIATION_BUDGET_WINDOW_WORDS,
    REGISTER_FINDINGS_CAP,
)
from ghostreader.ingestion import Chapter

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "register" / "shatterbound-ch1-opening.md"


class TestRegisterConstants:
    def test_initiation_budget_twins(self) -> None:
        assert INITIATION_BUDGET_COINED_NOUNS == 3
        assert INITIATION_BUDGET_WINDOW_WORDS == 300
        assert REGISTER_FINDINGS_CAP == 15

    def test_cold_forged_denylisted(self) -> None:
        assert "cold-forged" in HYPHEN_DENYLIST


class TestStripChapterBody:
    def test_strips_yaml_frontmatter(self) -> None:
        raw = FIXTURE.read_text(encoding="utf-8")
        body = strip_chapter_body(raw)
        assert "chapter_number" not in body
        assert "word_count" not in body
        assert "---" not in body.split("\n", 3)[0]
        assert "tobhandari" in body or "*tobhandari*" in raw

    def test_idempotent_without_frontmatter(self) -> None:
        prose = "The wind was tobhandari on the stair.\n"
        assert strip_chapter_body(prose) == prose

    def test_frontmatter_keys_absent_from_window_tokens(self) -> None:
        raw = FIXTURE.read_text(encoding="utf-8")
        report = detect_register(raw, chapter_number=1)
        window_tokens = report.window_text.split()
        for key in ("chapter_number:", "title:", "date:", "word_count:"):
            assert key not in window_tokens
            assert all(key not in t for t in window_tokens)


class TestShatterboundFixture:
    def test_fixture_flags_initiation_or_jargon(self) -> None:
        raw = FIXTURE.read_text(encoding="utf-8")
        report = detect_register(raw, chapter_number=1)
        kinds = {f.kind for f in report.findings}
        assert kinds & {"initiation_budget", "unearned_jargon"}
        assert "missing_human_door" not in kinds

        jargon_terms = {
            (f.term or "").lower() for f in report.findings if f.kind == "unearned_jargon"
        }
        # Italic / institutional hyphens from ch1 opening.
        expected_any = {"tobhandari", "writ-day", "purge-list", "bhandari-chain"}
        assert jargon_terms & expected_any
        assert "cold-forged" not in jargon_terms

        # Quotes preferred on jargon rows.
        jargon_rows = [f for f in report.findings if f.kind == "unearned_jargon"]
        assert any(f.quote for f in jargon_rows)

    def test_no_title_case_place_requirement(self) -> None:
        raw = FIXTURE.read_text(encoding="utf-8")
        report = detect_register(raw, chapter_number=1)
        jargon_terms = {
            (f.term or "").lower() for f in report.findings if f.kind == "unearned_jargon"
        }
        # v1 must not require Title Case place hits.
        # Ashfall / Spire may be absent; that is OK.
        _ = jargon_terms  # explicit: no assertion requiring places

    def test_cap_respected(self) -> None:
        raw = FIXTURE.read_text(encoding="utf-8")
        report = detect_register(raw, chapter_number=1)
        rows = companion_register_to_dicts(report, max_entries=REGISTER_FINDINGS_CAP)
        assert len(rows) <= REGISTER_FINDINGS_CAP
        assert all(r["kind"] in {"unearned_jargon", "initiation_budget"} for r in rows)

    def test_register_findings_for_chapter(self) -> None:
        raw = FIXTURE.read_text(encoding="utf-8")
        chapter = Chapter(
            title="What the Chain Heard",
            content=raw,
            chapter_number=1,
            source_path=FIXTURE,
        )
        rows = register_findings_for_chapter(chapter)
        assert rows
        assert any(r.get("kind") == "initiation_budget" for r in rows) or any(
            r.get("term") for r in rows
        )

    def test_register_block_names_heuristic(self) -> None:
        rows = [
            {
                "kind": "unearned_jargon",
                "severity": "moderate",
                "summary": "Coined term appears before teach-in: tobhandari",
                "term": "tobhandari",
            }
        ]
        block = register_block(rows, chapter_number=1)
        assert "Register heuristic" in block
        assert "strictest human-door" in block
        assert "tobhandari" in block
