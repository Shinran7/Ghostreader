"""Tests for voice-vs-card load + attribution + heuristic (#11 S1)."""

from __future__ import annotations

from pathlib import Path

from ghostreader.analyzers.register_detector import strip_chapter_body
from ghostreader.analyzers.voice_card_detector import (
    active_cue_families,
    attribute_quotes,
    detect_voice_card_issues,
    given_name_alias,
    speaker_surface_metrics,
)
from ghostreader.companion.voice_card_constants import (
    TITLE_SKIP_TOKENS,
    VOICE_CARD_FINDINGS_CAP,
    VOICE_CARD_MIN_LINES,
)
from ghostreader.companion.voice_cards import (
    VoiceCard,
    find_canon_characters_dir,
    load_voice_cards,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "voice_card"


def _chapter_pair(story: str, name: str = "chapter-001.md") -> tuple[int, str]:
    path = FIXTURES / story / "chapters" / name
    return 1, path.read_text(encoding="utf-8")


def _story_dir(story: str) -> Path:
    return FIXTURES / story


class TestVoiceCardConstants:
    def test_caps_and_title_skip(self) -> None:
        assert VOICE_CARD_FINDINGS_CAP == 15
        assert VOICE_CARD_MIN_LINES == 4
        assert "dr." in TITLE_SKIP_TOKENS
        assert "doctor" in TITLE_SKIP_TOKENS
        assert "captain" in TITLE_SKIP_TOKENS
        assert "professor" in TITLE_SKIP_TOKENS


class TestGivenNameAlias:
    def test_titled_name_skips_dr(self) -> None:
        assert given_name_alias("Dr. Selah Abe") == "selah"

    def test_plain_name(self) -> None:
        assert given_name_alias("Orin Drevane") == "orin"

    def test_captain_title(self) -> None:
        assert given_name_alias("Captain Bram Wexford") == "bram"


class TestLoadVoiceCards:
    def test_loads_json_cards(self) -> None:
        cards = load_voice_cards(_story_dir("story_sermon"))
        assert len(cards) == 1
        assert cards[0].slug == "fixture-sermon-orin"
        assert "sermon" in cards[0].dialogue_voice.casefold()

    def test_loads_yaml_cards(self) -> None:
        cards = load_voice_cards(_story_dir("story_yaml_card"))
        assert len(cards) == 1
        assert cards[0].slug == "fixture-yaml-speaker"
        assert cards[0].weight == "supporting"

    def test_missing_characters_dir_returns_empty(self) -> None:
        assert find_canon_characters_dir(_story_dir("story_empty")) is None
        assert load_voice_cards(_story_dir("story_empty")) == []

    def test_skips_empty_dialogue_voice(self, tmp_path: Path) -> None:
        chars = tmp_path / "canon" / "characters"
        chars.mkdir(parents=True)
        (chars / "blank.json").write_text(
            '{"slug":"blank","name":"Blank","dialogue_voice":"  "}',
            encoding="utf-8",
        )
        (chars / "ok.json").write_text(
            '{"slug":"ok","name":"Ok","dialogue_voice":"Terse clipped."}',
            encoding="utf-8",
        )
        cards = load_voice_cards(tmp_path)
        assert [c.slug for c in cards] == ["ok"]

    def test_ignores_unknown_keys(self, tmp_path: Path) -> None:
        chars = tmp_path / "canon" / "characters"
        chars.mkdir(parents=True)
        (chars / "extra.json").write_text(
            '{"slug":"extra","name":"Extra","dialogue_voice":"Terse.",'
            '"arc_summary":"ignore me","traits":["x"]}',
            encoding="utf-8",
        )
        cards = load_voice_cards(tmp_path)
        assert len(cards) == 1
        assert cards[0].slug == "extra"


class TestAttribution:
    def test_titled_name_alias_attributes_selah(self) -> None:
        cards = load_voice_cards(_story_dir("story_titled"))
        cast = [(c.slug, c.name) for c in cards]
        _, raw = _chapter_pair("story_titled")
        body = strip_chapter_body(raw)
        attributed = attribute_quotes(body, cast)
        assert "dr-selah-abe" in attributed
        assert len(attributed["dr-selah-abe"]) >= VOICE_CARD_MIN_LINES
        # Alias must not be the title token.
        assert given_name_alias(cards[0].name) == "selah"

    def test_form_c_bare_quote_unattributed(self) -> None:
        cards = load_voice_cards(_story_dir("story_form_c"))
        cast = [(c.slug, c.name) for c in cards]
        _, raw = _chapter_pair("story_form_c")
        attributed = attribute_quotes(strip_chapter_body(raw), cast)
        assert attributed == {}
        rows = detect_voice_card_issues([_chapter_pair("story_form_c")], cards, focus_chapter=1)
        assert rows == []

    def test_frontmatter_stripped_before_scan(self) -> None:
        _, raw = _chapter_pair("story_frontmatter")
        body = strip_chapter_body(raw)
        assert "chapter_number" not in body
        assert "word_count" not in body
        cards = load_voice_cards(_story_dir("story_frontmatter"))
        rows = detect_voice_card_issues([(1, raw)], cards, focus_chapter=1)
        assert any(r["kind"] == "card_mismatch" for r in rows)
        assert all("chapter_number" not in (r.get("quote") or "") for r in rows)


class TestCuePolarity:
    def test_sermon_long_card_short_speech_mismatch(self) -> None:
        cards = load_voice_cards(_story_dir("story_sermon"))
        assert "sermon" in active_cue_families(cards[0])
        assert "monotone" not in active_cue_families(cards[0])
        rows = detect_voice_card_issues(
            [_chapter_pair("story_sermon")],
            cards,
            focus_chapter=1,
        )
        mismatch = [r for r in rows if r["kind"] == "card_mismatch"]
        assert mismatch
        assert mismatch[0]["speaker"] == "fixture-sermon-orin"
        assert mismatch[0]["normalized_key"] == "card_mismatch:fixture-sermon-orin"
        assert mismatch[0]["severity"] in {"moderate", "high"}
        metrics = mismatch[0]["metrics"]
        assert metrics is not None
        assert "interruption_rate" in metrics
        assert metrics["avg_words"] <= 4.0

    def test_terse_card_long_speech_mismatch(self) -> None:
        cards = load_voice_cards(_story_dir("story_terse"))
        assert "terse" in active_cue_families(cards[0])
        rows = detect_voice_card_issues(
            [_chapter_pair("story_terse")],
            cards,
            focus_chapter=1,
        )
        mismatch = [r for r in rows if r["kind"] == "card_mismatch"]
        assert mismatch
        assert mismatch[0]["speaker"] == "fixture-terse-warden"
        assert mismatch[0]["metrics"]["avg_words"] >= 12.0

    def test_radio_monotone_card_long_speech_mismatch(self) -> None:
        cards = load_voice_cards(_story_dir("story_radio"))
        families = active_cue_families(cards[0])
        assert "monotone" in families
        assert "sermon" not in families
        rows = detect_voice_card_issues(
            [_chapter_pair("story_radio")],
            cards,
            focus_chapter=1,
        )
        mismatch = [r for r in rows if r["kind"] == "card_mismatch"]
        assert mismatch
        assert mismatch[0]["speaker"] == "fixture-radio-warden"

    def test_bare_measured_protocol_soft_only(self) -> None:
        card = VoiceCard(
            slug="bare-measured",
            name="Bare Measured",
            dialogue_voice="Measured protocol. Nothing else.",
            voice_wildcards=[],
        )
        assert active_cue_families(card) == set()


class TestCardCollapse:
    def test_pairwise_collapse_distinct_cards(self) -> None:
        cards = load_voice_cards(_story_dir("story_collapse"))
        assert len(cards) == 2
        rows = detect_voice_card_issues(
            [_chapter_pair("story_collapse")],
            cards,
            focus_chapter=1,
        )
        collapses = [r for r in rows if r["kind"] == "card_collapse"]
        assert collapses
        row = collapses[0]
        assert row["speaker_b"] is not None
        key = row["normalized_key"]
        assert key is not None
        assert key.startswith("card_collapse:")
        pair = key.removeprefix("card_collapse:")
        left, right = pair.split("|")
        assert left <= right
        assert {left, right} == {"fixture-collapse-alpha", "fixture-collapse-beta"}
        assert "interruption_rate" in row["metrics"]


class TestEmptyAndFloor:
    def test_empty_cards_returns_empty(self) -> None:
        rows = detect_voice_card_issues(
            [_chapter_pair("story_terse")],
            [],
            focus_chapter=1,
        )
        assert rows == []

    def test_below_min_lines_no_row(self) -> None:
        card = VoiceCard(
            slug="thin",
            name="Thin",
            dialogue_voice="Terse clipped short laconic curt.",
        )
        text = (
            'Thin said, "I would prefer that we reconsider the entire arrangement before dawn."\n'
        )
        rows = detect_voice_card_issues([(1, text)], [card], focus_chapter=1)
        assert rows == []


class TestSurfaceMetrics:
    def test_metrics_include_interruption_rate(self) -> None:
        metrics = speaker_surface_metrics(["Wait— hold on...", "Sure thing."])
        assert metrics["line_count"] == 2.0
        assert "interruption_rate" in metrics
        assert metrics["interruption_rate"] == 0.5
