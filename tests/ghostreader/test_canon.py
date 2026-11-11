"""#16: Canon loader — filtering to chapters before N, checkpoints, block."""

from __future__ import annotations

import json
from pathlib import Path

from ghostreader.canon import (
    CanonEntry,
    find_canon_dir,
    format_canon_block,
    load_canon_state,
)
from tests.test_canon_continuity import write_canon


def _texts(state, prefix: str) -> list[str]:
    return [e.text for e in state.entries if e.id.startswith(prefix)]


def test_live_canon_filters_to_before_chapter(tmp_path: Path) -> None:
    write_canon(tmp_path / "canon")
    state = load_canon_state(tmp_path / "canon", 3)
    assert state
    assert not state.from_checkpoint
    cast = " | ".join(_texts(state, "C"))
    assert "Mara (protagonist)" in cast
    assert "Late Comer" not in cast
    assert "Old Tom (mentor); status deceased since Ch 2" in cast
    phys = _texts(state, "P")
    assert any("thrown into the harbor" in t for t in phys)
    assert not any("in her coat" in t or "ribs" in t for t in phys)
    assert any("fractured" in t and "(worsening)" in t for t in phys)
    kinds = {e.kind for e in state.entries if e.id.startswith("P")}
    assert kinds == {"physical state", "item location"}
    assert _texts(state, "O") == ["What is in the cellar? (open; critical)"]
    assert "characters/" in state.files_loaded


def test_death_in_or_after_focus_chapter_reads_active(tmp_path: Path) -> None:
    write_canon(tmp_path / "canon")
    state = load_canon_state(tmp_path / "canon", 2)
    tom = next(t for t in _texts(state, "C") if t.startswith("Old Tom"))
    assert "status active" in tom
    # Chapter 2 rows are excluded when checking chapter 2.
    assert not any("thrown into the harbor" in t for t in _texts(state, "P"))


def test_missing_death_chapter_is_flagged(tmp_path: Path) -> None:
    canon = tmp_path / "canon"
    (canon / "characters").mkdir(parents=True)
    (canon / "characters/dw.json").write_text(
        json.dumps({"name": "Dwayne", "status": "deceased", "died_chapter": 0}),
        encoding="utf-8",
    )
    state = load_canon_state(canon, 4)
    assert "death chapter not recorded" in _texts(state, "C")[0]


def test_checkpoint_preferred(tmp_path: Path) -> None:
    write_canon(tmp_path / "canon")
    cp = tmp_path / "checkpoints/chapter-003/canon"
    (cp / "style").mkdir(parents=True)
    (cp / "style/key-facts.json").write_text(json.dumps(["Checkpoint fact"]), encoding="utf-8")
    state = load_canon_state(tmp_path / "canon", 3)
    assert state.from_checkpoint
    assert state.source_dir == cp
    assert _texts(state, "K") == ["Checkpoint fact"]
    # Other chapters without a checkpoint read live Canon.
    assert not load_canon_state(tmp_path / "canon", 2).from_checkpoint


def test_missing_and_bad_files_fail_soft(tmp_path: Path) -> None:
    canon = tmp_path / "canon"
    (canon / "style").mkdir(parents=True)
    (canon / "style/physical-state.json").write_text("{not json", encoding="utf-8")
    (canon / "style/key-facts.json").write_text(json.dumps([{"fact": "F"}, 3]), encoding="utf-8")
    state = load_canon_state(canon, 1)
    assert _texts(state, "K") == ["F"]
    assert state.files_loaded == ["style/key-facts.json"]
    assert not load_canon_state(tmp_path / "nowhere", 1)


def test_find_canon_dir(tmp_path: Path) -> None:
    assert find_canon_dir(tmp_path, None) is None
    (tmp_path / "canon").mkdir()
    assert find_canon_dir(tmp_path) is None  # empty dir is not Canon
    (tmp_path / "canon/x.json").write_text("[]", encoding="utf-8")
    chapters = tmp_path / "chapters"
    chapters.mkdir()
    assert find_canon_dir(chapters) == tmp_path / "canon"


def test_block_and_entry_shapes(tmp_path: Path) -> None:
    write_canon(tmp_path / "canon")
    block = format_canon_block(load_canon_state(tmp_path / "canon", 3))
    assert block.startswith("### Cast")
    assert "### World rules" in block
    assert "[R1] No magic" in block
    assert "[T2] (Ch 2) starts Night, Day 1; ends Night, Day 2; elapsed 24 hours" in block
    e = CanonEntry(id="K1", kind="key fact", text="t", chapter=None, file="f")
    assert e.as_counter_evidence() == "Canon (key fact): t"
    e2 = CanonEntry(id="P1", kind="physical state", text="t", chapter=2, file="f")
    assert e2.as_counter_evidence() == "Canon Ch 2 (physical state): t"
    assert e2.as_ref() == {"id": "P1", "kind": "physical state", "chapter": 2, "file": "f"}


def _secret_state(tmp_path: Path, chapter_n: int, **row: object) -> str:
    canon = tmp_path / "canon"
    (canon / "plot").mkdir(parents=True)
    base = {"slug": "will", "name": "The will", "description_summary": "Tom left Mara the cellar"}
    (canon / "plot/secrets-registry.json").write_text(
        json.dumps([{**base, "planted_chapter": 1, **row}]), encoding="utf-8"
    )
    (text,) = _texts(load_canon_state(canon, chapter_n), "S")
    return text


def test_secret_state_changed_later_is_not_leaked(tmp_path: Path) -> None:
    later = {"state": "public", "state_since_chapter": 5, "knowers": ["mara", "ivo"]}
    # Hidden until a reveal in chapter 5: chapter 3 sees it hidden, no knowers.
    text = _secret_state(tmp_path / "a", 3, first_revealed_chapter=5, **later)
    assert "state hidden; knowers before Ch 3 not recorded" in text
    assert "public" not in text and "ivo" not in text
    # Partly revealed in 2, public in 5: chapter 3 knows only the first reveal.
    text = _secret_state(tmp_path / "b", 3, first_revealed_chapter=2, **later)
    assert "state revealed since Ch 2" in text
    assert "public" not in text
    # Chapter 6 comes after the change: the latest state applies.
    text = _secret_state(tmp_path / "c", 6, first_revealed_chapter=2, **later)
    assert "state public; known by mara, ivo" in text
