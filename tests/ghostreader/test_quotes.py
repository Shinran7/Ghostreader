"""#17: ghostreader.quotes matching, verification and ids."""

from __future__ import annotations

from ghostreader.quotes import (
    QuoteIndex,
    check_field,
    finding_id,
    quote_parts,
    verify_finding,
    verify_findings,
)
from tests.test_quote_verification import CH1, _f, _index

# --- matching -------------------------------------------------------------


def test_exact_match_has_location() -> None:
    loc = _index().locate("Mara watched it and said nothing.")
    assert loc is not None
    assert (loc.chapter, loc.paragraph, loc.line, loc.match) == (1, 1, 2, "exact")
    assert CH1[loc.char_start : loc.char_end] == "Mara watched it and said nothing."


def test_normalized_match_curly_quotes_dashes_and_wraps() -> None:
    loc = _index().locate("\"We leave at dawn,\" she said - and meant it.")
    assert loc is not None
    assert loc.match == "normalized"
    assert loc.paragraph == 2
    wrapped = _index().locate("slow paths across the\n   window. Mara watched it")
    assert wrapped is not None
    assert wrapped.match == "normalized"


def test_fuzzy_match_tolerates_one_word_slip() -> None:
    loc = _index().locate("He looked into her brown eyes and saw no fear in there at all")
    assert loc is not None
    assert loc.chapter == 2
    assert loc.match == "fuzzy"


def test_near_miss_is_rejected() -> None:
    # Same shape, changed facts: must not verify.
    assert _index().locate("He looked into her green eyes and saw great fear there") is None
    assert _index().locate("Her eyes were brown as the harbor in summer.") is None


def test_short_quotes_do_not_verify_alone() -> None:
    assert not check_field(_index(), "Ch 1: 'the window'").verified


def test_ellipsis_parts_must_all_match() -> None:
    ok = check_field(_index(), "Ch 1: 'The rain tracked downward ... slow paths'")
    assert ok.verified
    bad = check_field(_index(), "Ch 1: 'The rain tracked downward ... fast roads'")
    assert not bad.verified


def test_quote_parts_split_chapter_prefixes() -> None:
    parts = quote_parts("Ch 1: 'Her eyes were blue' and Ch 2: 'her brown eyes'")
    assert [c for c, _ in parts] == [1, 2]


def test_prefer_chooses_cited_chapter() -> None:
    idx = QuoteIndex(
        [
            {"chapter_number": 1, "content": "The door was locked tight again."},
            {"chapter_number": 5, "content": "The door was locked tight again."},
        ]
    )
    loc = idx.locate("The door was locked tight again.", prefer=[5])
    assert loc is not None
    assert loc.chapter == 5


# --- verify_finding -------------------------------------------------------


def test_verified_finding_tags_both_sides() -> None:
    f = verify_finding(
        _f(
            evidence="Ch 1: 'Her eyes were blue as the harbor in winter.'",
            counter_evidence="Ch 2: 'He looked into her brown eyes'",
        ),
        _index(),
    )
    assert f["quote_verified"] is True
    assert f["severity"] == "concern"
    assert f["location"]["chapter"] == 1
    assert f["counter_location"]["chapter"] == 2


def test_invented_quote_is_demoted() -> None:
    f = verify_finding(
        _f(dimension="prose.rhythm", evidence="Ch 1: 'The storm broke the mast in two.'"),
        _index(),
    )
    assert f["quote_verified"] is False
    assert f["severity"] == "neutral"
    assert f["summary"].startswith("Unverified quote: ")


def test_invented_counter_evidence_fails_the_finding() -> None:
    f = verify_finding(
        _f(
            evidence="Ch 1: 'Her eyes were blue as the harbor in winter.'",
            counter_evidence="Ch 2: 'Her green eyes glittered in the lamplight.'",
        ),
        _index(),
        demote=False,
    )
    assert f["quote_verified"] is False
    assert f["severity"] == "concern"


def test_strengths_are_tagged_not_changed() -> None:
    out, demoted = verify_findings(
        [_f(severity="strength", evidence="invented words that are not there at all")],
        _index(),
    )
    assert demoted == 0
    assert out[0]["severity"] == "strength"
    assert out[0]["quote_verified"] is False


def test_repetition_dimension_is_exempt() -> None:
    f = verify_finding(
        _f(dimension="prose.repetition", evidence="'harbor' x12, 'rain' x9"), _index()
    )
    assert f["quote_verified"] is False
    assert f["severity"] == "concern"


def test_finding_id_is_stable_across_wording() -> None:
    a = verify_finding(_f(evidence="Ch 2: 'He looked into her brown eyes'"), _index())
    b = verify_finding(
        _f(summary="Different words", evidence="Ch 2: ‘He looked into her brown eyes’"),
        _index(),
    )
    assert a["id"] == b["id"]
    assert len(a["id"]) == 12
    other = verify_finding(
        _f(dimension="consistency.timeline", evidence="Ch 2: 'He looked into her brown eyes'"),
        _index(),
    )
    assert other["id"] != a["id"]
    assert finding_id(_f(evidence="x")) == finding_id(_f(evidence="  x "))
