"""S6 acceptance checklist for GhostReader #10 thrash widen."""

from __future__ import annotations

from pathlib import Path

from ghostreader.analyzers.thrash_detector import reset_zipf_cache_for_tests
from ghostreader.report.json_export import ANALYZE_JSON_VERSION
from ghostreader.report.thrash_export import analyze_thrash_findings

_FIX = Path(__file__).resolve().parent / "fixtures" / "thrash"


def setup_function() -> None:
    reset_zipf_cache_for_tests()


def _rows(name: str, *, enabled: bool = True, cap: int = 40):
    text = (_FIX / name).read_text(encoding="utf-8")
    return analyze_thrash_findings(
        [{"chapter_number": 1, "content": text}],
        enabled=enabled,
        cap=cap,
    )


def test_acceptance_checklist_10() -> None:
    # 1. Chapter-spread uncommon → chapter_rare
    spread = _rows("chapter-spread-firn.md")
    assert any(r["kind"] == "chapter_rare" and r["lemma"] == "firn" for r in spread)
    assert not any(r["kind"] == "within_scene" and r["lemma"] == "firn" for r in spread)

    # 2. Within-scene wins; no duplicate chapter_rare
    within = _rows("within-scene-firn.md")
    assert any(r["kind"] == "within_scene" and r["lemma"] == "firn" for r in within)
    assert not any(r["kind"] == "chapter_rare" and r["lemma"] == "firn" for r in within)

    # 3. rim carpet; said + names quiet
    rim = _rows("rim-carpet.md")
    assert any(r["kind"] == "common_word" and r["lemma"] == "rim" for r in rim)
    assert all(r.get("lemma") not in {"said", "says", "say", "hollis", "mira"} for r in rim)

    # 4. blue ice phrase; lemma null
    blue = _rows("blue-ice-phrase.md")
    hit = [r for r in blue if r["kind"] == "phrase" and r.get("phrase") == "blue ice"]
    assert len(hit) == 1
    assert hit[0]["count"] == 2
    assert hit[0]["lemma"] is None

    # 5. muttered dialogue_tag; not common_word; never said
    mut = _rows("muttered-tags.md")
    assert any(r["kind"] == "dialogue_tag" and r["lemma"] == "muttered" for r in mut)
    assert not any(r["kind"] == "common_word" and r.get("lemma") == "muttered" for r in mut)
    assert all(r.get("lemma") not in {"said", "says", "say"} for r in mut)

    # 6. Kill switch
    assert _rows("within-scene-firn.md", enabled=False) == []

    # 7. Cap
    assert len(_rows("rim-carpet.md", cap=40)) <= 40

    # 8. Contract version
    assert ANALYZE_JSON_VERSION == "0.2.1"

    # SI noise
    si = _rows("si-noise.md")
    assert all(r.get("lemma") not in {"meter", "meters", "metre"} for r in si)
