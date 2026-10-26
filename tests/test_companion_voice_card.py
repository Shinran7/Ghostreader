"""Tests for voice-card companion projection / bias block (#11 S2)."""

from __future__ import annotations

from pathlib import Path

from ghostreader.companion.voice_card import (
    companion_voice_card_to_dicts,
    voice_card_block,
    voice_card_finding_to_dict,
    voice_card_findings_for_chapters,
)
from ghostreader.companion.voice_card_constants import VOICE_CARD_FINDINGS_CAP
from ghostreader.companion.voice_cards import (
    load_voice_cards,
    load_voice_cards_with_warnings,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "voice_card"


class TestVoiceCardProjection:
    def test_sanitizes_unknown_kind(self) -> None:
        row = voice_card_finding_to_dict(
            {
                "kind": "not_a_kind",
                "severity": "extreme",
                "summary": "x",
                "speaker": "s",
            }
        )
        assert row["kind"] == "card_mismatch"
        assert row["severity"] == "low"
        assert row["speaker_b"] is None
        assert row["metrics"] is None

    def test_cap_respected(self) -> None:
        rows = [
            {
                "kind": "card_mismatch",
                "severity": "moderate",
                "summary": f"row {i}",
                "speaker": f"s{i}",
                "normalized_key": f"card_mismatch:s{i}",
            }
            for i in range(VOICE_CARD_FINDINGS_CAP + 5)
        ]
        capped = companion_voice_card_to_dicts(rows, max_entries=VOICE_CARD_FINDINGS_CAP)
        assert len(capped) == VOICE_CARD_FINDINGS_CAP
        assert all(r["kind"] in {"card_mismatch", "card_collapse"} for r in capped)

    def test_findings_for_chapters_fixture(self) -> None:
        story = FIXTURES / "story_terse"
        cards = load_voice_cards(story)
        chapter = (story / "chapters" / "chapter-001.md").read_text(encoding="utf-8")
        rows = voice_card_findings_for_chapters([(1, chapter)], cards, focus_n=1)
        assert rows
        assert all(r["kind"] in {"card_mismatch", "card_collapse"} for r in rows)


class TestVoiceCardBlock:
    def test_empty_block(self) -> None:
        block = voice_card_block([], chapter_number=18)
        assert "Voice-vs-card heuristic" in block
        assert "No voice/card machine rows" in block

    def test_labels_prior_and_focus(self) -> None:
        findings = [
            {
                "kind": "card_collapse",
                "severity": "moderate",
                "speaker": "garen-solwick",
                "speaker_b": "ysolde-kestrel",
                "chapters": [3, 7, 12],
            },
            {
                "kind": "card_mismatch",
                "severity": "moderate",
                "speaker": "fixture-terse-warden",
                "speaker_b": None,
                "chapters": [3, 7],
            },
        ]
        block = voice_card_block(findings, chapter_number=12)
        assert "prior+focus" in block
        assert "prior — context only" in block
        assert "speaker=garen-solwick" in block
        assert "speaker_b=ysolde-kestrel" in block
        assert "Focus-chapter 12 quotes" in block


class TestVoiceCardPartialLoadWarnings:
    def test_partial_invalid_cards_warn_with_names(self, tmp_path: Path) -> None:
        characters = tmp_path / "canon" / "characters"
        characters.mkdir(parents=True)
        (characters / "good.json").write_text(
            '{"slug":"warden","name":"Warden","dialogue_voice":"Terse, clipped."}\n',
            encoding="utf-8",
        )
        (characters / "broken.json").write_text("{not-json", encoding="utf-8")
        (characters / "array.yml").write_text("- just a list\n", encoding="utf-8")

        cards, warnings = load_voice_cards_with_warnings(tmp_path)
        assert len(cards) == 1
        assert cards[0].slug == "warden"
        assert len(warnings) == 1
        assert "skipped 2 unreadable/invalid card(s)" in warnings[0]
        assert "broken.json" in warnings[0]
        assert "array.yml" in warnings[0]
        # Compatibility wrapper still returns only cards.
        assert len(load_voice_cards(tmp_path)) == 1

    def test_all_valid_cards_no_skip_warning(self, tmp_path: Path) -> None:
        characters = tmp_path / "canon" / "characters"
        characters.mkdir(parents=True)
        (characters / "a.json").write_text(
            '{"slug":"a","name":"A","dialogue_voice":"Soft."}\n',
            encoding="utf-8",
        )
        cards, warnings = load_voice_cards_with_warnings(tmp_path)
        assert len(cards) == 1
        assert warnings == []
