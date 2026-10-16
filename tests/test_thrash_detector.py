"""Tests for Zipf thrash detector parity (8c6c4513 / #285 KD-5)."""

from __future__ import annotations

import json
from pathlib import Path

from ghostreader.analyzers.thrash_detector import (
    COMMON_ENGLISH,
    DEFAULT_ZIPF_THRESHOLD,
    detect_thrash_in_chapter,
    ensure_zipf_loaded,
    is_uncommon,
    lemma,
    reset_zipf_cache_for_tests,
    zipf_path_active,
)

_VENDOR = Path(__file__).resolve().parents[1] / "ghostreader" / "data" / "en_zipf_small.json"


def setup_function() -> None:
    reset_zipf_cache_for_tests()


def test_vendor_json_load_strict() -> None:
    assert _VENDOR.is_file()
    raw = json.loads(_VENDOR.read_text(encoding="utf-8"))
    assert isinstance(raw, dict)
    assert "firn" in raw
    assert float(raw["firn"]) < DEFAULT_ZIPF_THRESHOLD


def test_zipf_path_active_and_threshold() -> None:
    assert zipf_path_active() is True
    scores = ensure_zipf_loaded()
    assert scores
    assert DEFAULT_ZIPF_THRESHOLD == 4.0
    assert is_uncommon("firn", scores) is True
    # Missing from small vendor → not uncommon (KD-5 §3).
    assert is_uncommon("main", scores) is False
    assert is_uncommon("bring", scores) is False


def test_firn_times_three_within_scene_hit() -> None:
    text = "The firn cracked. She kicked the firn aside. Firn dust rose."
    findings = detect_thrash_in_chapter(text, chapter_number=1)
    firn = [f for f in findings if f.lemma == "firn" and f.kind == "within_scene"]
    assert len(firn) == 1
    assert firn[0].count == 3
    assert firn[0].severity == "moderate"
    assert firn[0].chapter == 1
    assert firn[0].foothold_token
    assert firn[0].later_surfaces


def test_firn_firns_morphology() -> None:
    assert lemma("Firn") == "firn"
    assert lemma("firns") == "firn"
    text = "Firn underfoot. She crossed the firns carefully."
    findings = detect_thrash_in_chapter(text, chapter_number=2)
    firn = [f for f in findings if f.lemma == "firn"]
    assert len(firn) == 1
    assert firn[0].count == 2


def test_common_dog_teeth_quiet() -> None:
    assert "dog" in COMMON_ENGLISH
    assert "teeth" in COMMON_ENGLISH
    dogs = "The dog barked. The dog waited. The dog slept. The dog woke."
    assert detect_thrash_in_chapter(dogs, chapter_number=1) == []
    teeth = "His teeth ached. Her teeth clenched. Their teeth rattled."
    assert detect_thrash_in_chapter(teeth, chapter_number=1) == []


def test_missing_vendor_fail_soft(tmp_path: Path) -> None:
    missing = tmp_path / "absent_zipf.json"
    reset_zipf_cache_for_tests(path=missing)
    assert zipf_path_active() is False
    assert ensure_zipf_loaded() == {}
    text = "The firn cracked. She kicked the firn aside. Firn dust rose."
    assert detect_thrash_in_chapter(text, chapter_number=1) == []
    # Restore default path for later tests in this process.
    reset_zipf_cache_for_tests()


def test_once_ok_no_finding() -> None:
    text = "The firn cracked under her boot."
    assert detect_thrash_in_chapter(text, chapter_number=1) == []


def test_frontmatter_stripped() -> None:
    text = "---\ntitle: Ch1\n---\nThe firn cracked. She kicked the firn aside.\n"
    findings = detect_thrash_in_chapter(text, chapter_number=1)
    assert any(f.lemma == "firn" for f in findings)


def test_s1_phrase_stub_still_empty() -> None:
    """#10 S1 leftover: phrase stub identity until S4."""
    from ghostreader.analyzers.phrase_thrash import detect_phrase_thrash

    text = "The firn cracked. She kicked the firn aside. Firn dust rose."
    assert detect_phrase_thrash(text, chapter_number=1) == []


def test_rim_carpet_common_word_said_and_names_quiet() -> None:
    from ghostreader.analyzers.common_word_thrash import detect_common_word_thrash
    from ghostreader.report.thrash_export import analyze_thrash_findings

    fixture = Path(__file__).resolve().parent / "fixtures" / "thrash" / "rim-carpet.md"
    text = fixture.read_text(encoding="utf-8")
    rows = detect_common_word_thrash(text, chapter_number=1)
    rim = [f for f in rows if f.lemma == "rim" and f.kind == "common_word"]
    assert len(rim) == 1
    assert rim[0].count >= 6
    assert rim[0].severity in {"moderate", "high"}
    assert all(f.lemma not in {"said", "says", "say"} for f in rows)
    # Mid-sentence Title Case names must not crown common_word.
    assert all(f.lemma not in {"hollis", "mira"} for f in rows)
    export = analyze_thrash_findings(
        [{"chapter_number": 1, "content": text}],
        enabled=True,
    )
    assert any(r["kind"] == "common_word" and r["lemma"] == "rim" for r in export)
    assert all(r.get("lemma") not in {"said", "says", "say"} for r in export)


def test_muttered_dialogue_tag_not_common_word() -> None:
    from ghostreader.analyzers.common_word_thrash import (
        detect_common_word_thrash,
        detect_dialogue_tag_thrash,
    )
    from ghostreader.report.thrash_export import analyze_thrash_findings

    fixture = Path(__file__).resolve().parent / "fixtures" / "thrash" / "muttered-tags.md"
    text = fixture.read_text(encoding="utf-8")
    tags = detect_dialogue_tag_thrash(text, chapter_number=1)
    muttered = [f for f in tags if f.lemma == "muttered" and f.kind == "dialogue_tag"]
    assert len(muttered) == 1
    assert muttered[0].count >= 3
    common = detect_common_word_thrash(text, chapter_number=1)
    assert all(f.lemma != "muttered" for f in common)
    export = analyze_thrash_findings(
        [{"chapter_number": 1, "content": text}],
        enabled=True,
    )
    assert any(r["kind"] == "dialogue_tag" and r["lemma"] == "muttered" for r in export)
    assert all(not (r["kind"] == "common_word" and r.get("lemma") == "muttered") for r in export)
    assert all(r.get("lemma") not in {"said", "says", "say"} for r in export)


def test_si_noise_meters_not_primary_common_word() -> None:
    from ghostreader.analyzers.common_word_thrash import detect_common_word_thrash

    fixture = Path(__file__).resolve().parent / "fixtures" / "thrash" / "si-noise.md"
    text = fixture.read_text(encoding="utf-8")
    rows = detect_common_word_thrash(text, chapter_number=1)
    assert all(f.lemma not in {"meter", "meters", "metre"} for f in rows)


def test_chapter_spread_firn_fires_chapter_rare() -> None:
    """1× firn in two blank-line scenes → chapter_rare; no within_scene."""
    from ghostreader.analyzers.thrash_detector import detect_chapter_rare

    fixture = Path(__file__).resolve().parent / "fixtures" / "thrash" / "chapter-spread-firn.md"
    text = fixture.read_text(encoding="utf-8")
    within = detect_thrash_in_chapter(text, chapter_number=1)
    assert within == []
    rare = detect_chapter_rare(text, chapter_number=1)
    firn = [f for f in rare if f.lemma == "firn" and f.kind == "chapter_rare"]
    assert len(firn) == 1
    assert firn[0].count == 2
    assert firn[0].severity == "moderate"
    assert firn[0].chapter == 1


def test_within_scene_wins_over_chapter_rare_export() -> None:
    """≥2/scene → within_scene; export drops duplicate chapter_rare."""
    from ghostreader.report.thrash_export import analyze_thrash_findings

    fixture = Path(__file__).resolve().parent / "fixtures" / "thrash" / "within-scene-firn.md"
    text = fixture.read_text(encoding="utf-8")
    rows = analyze_thrash_findings(
        [{"chapter_number": 1, "content": text}],
        enabled=True,
    )
    within = [r for r in rows if r["kind"] == "within_scene" and r["lemma"] == "firn"]
    rare = [r for r in rows if r["kind"] == "chapter_rare" and r["lemma"] == "firn"]
    assert len(within) == 1
    assert rare == []


def test_chapter_rare_orphan_cross_chapter_rollup() -> None:
    """chapter_rare in ≥2 chapters → cross_chapter when no within_scene rollup."""
    from ghostreader.analyzers.thrash_detector import (
        aggregate_cross_chapter,
        detect_chapter_rare,
    )

    ch1 = "The basalt rim held.\n\nLater she tapped the basalt again."
    ch2 = "Basalt under the boot.\n\nCold basalt at the hatch."
    rare = detect_chapter_rare(ch1, chapter_number=1) + detect_chapter_rare(ch2, chapter_number=2)
    assert all(r.kind == "chapter_rare" for r in rare)
    cross = aggregate_cross_chapter([], chapter_rare=rare)
    basalt = [r for r in cross if r.lemma == "basalt" and r.kind == "cross_chapter"]
    assert len(basalt) == 1
    assert basalt[0].chapters == [1, 2]
    assert basalt[0].count >= 4
