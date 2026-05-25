"""Tests for the seed module (seed.yaml discovery, parsing, author-intent block)."""

from __future__ import annotations

from pathlib import Path

from ghostreader.seed import build_author_intent_block, find_seed_yaml, load_seed_meta


class TestFindSeedYaml:
    def test_finds_in_manuscript_dir(self, tmp_path: Path) -> None:
        seed = tmp_path / "seed.yaml"
        seed.write_text("meta:\n  genre: fantasy\n", encoding="utf-8")
        assert find_seed_yaml(tmp_path) == seed

    def test_finds_in_parent_dir(self, tmp_path: Path) -> None:
        seed = tmp_path / "seed.yaml"
        seed.write_text("meta:\n  genre: thriller\n", encoding="utf-8")
        child = tmp_path / "chapters"
        child.mkdir()
        assert find_seed_yaml(child) == seed

    def test_finds_from_file_path(self, tmp_path: Path) -> None:
        seed = tmp_path / "seed.yaml"
        seed.write_text("meta:\n  genre: romance\n", encoding="utf-8")
        manuscript = tmp_path / "novel.epub"
        manuscript.write_text("fake epub", encoding="utf-8")
        assert find_seed_yaml(manuscript) == seed

    def test_returns_none_when_missing(self, tmp_path: Path) -> None:
        assert find_seed_yaml(tmp_path) is None


class TestLoadSeedMeta:
    def test_loads_meta_block(self, tmp_path: Path) -> None:
        (tmp_path / "seed.yaml").write_text(
            "meta:\n"
            "  genre: fantasy\n"
            "  target_chapters: 25\n"
            "  arc_archetype: long_defeat\n",
            encoding="utf-8",
        )
        meta = load_seed_meta(tmp_path)
        assert meta["genre"] == "fantasy"
        assert meta["target_chapters"] == 25
        assert meta["arc_archetype"] == "long_defeat"

    def test_returns_empty_when_no_seed(self, tmp_path: Path) -> None:
        assert load_seed_meta(tmp_path) == {}

    def test_returns_empty_when_no_meta_block(self, tmp_path: Path) -> None:
        (tmp_path / "seed.yaml").write_text(
            "title: My Novel\nauthor: Test\n",
            encoding="utf-8",
        )
        assert load_seed_meta(tmp_path) == {}

    def test_returns_empty_on_invalid_yaml(self, tmp_path: Path) -> None:
        (tmp_path / "seed.yaml").write_text(
            "{{invalid yaml content",
            encoding="utf-8",
        )
        assert load_seed_meta(tmp_path) == {}

    def test_returns_empty_when_meta_is_not_dict(self, tmp_path: Path) -> None:
        (tmp_path / "seed.yaml").write_text(
            "meta: just-a-string\n",
            encoding="utf-8",
        )
        assert load_seed_meta(tmp_path) == {}

    def test_ignores_non_meta_blocks(self, tmp_path: Path) -> None:
        (tmp_path / "seed.yaml").write_text(
            "meta:\n  genre: sci-fi\n"
            "characters:\n  - name: Alice\n",
            encoding="utf-8",
        )
        meta = load_seed_meta(tmp_path)
        assert "characters" not in meta
        assert meta["genre"] == "sci-fi"


class TestBuildAuthorIntentBlock:
    def test_empty_meta_returns_empty_string(self) -> None:
        assert build_author_intent_block({}) == ""

    def test_none_values_skipped(self) -> None:
        assert build_author_intent_block({"unknown_field": "value"}) == ""

    def test_formats_known_fields(self) -> None:
        meta = {
            "genre": "fantasy",
            "target_chapters": 30,
            "dialogue_density": "high",
        }
        block = build_author_intent_block(meta)
        assert "AUTHOR-STATED INTENT" in block
        assert "Genre: fantasy" in block
        assert "Target chapter count: 30" in block
        assert "Intended dialogue density: high" in block

    def test_all_known_fields(self) -> None:
        meta = {
            "genre": "literary",
            "target_chapters": 12,
            "target_chapter_length": 5000,
            "arc_archetype": "rebirth",
            "dialogue_density": "low",
            "content_rating": "R",
            "reading_level": "adult",
            "story_epoch": "medieval",
            "time_units": "days",
        }
        block = build_author_intent_block(meta)
        assert "Genre: literary" in block
        assert "Target chapter count: 12" in block
        assert "Target chapter length (words): 5000" in block
        assert "Arc archetype: rebirth" in block
        assert "Intended dialogue density: low" in block
        assert "Content rating: R" in block
        assert "Reading level: adult" in block
        assert "Story epoch / era: medieval" in block
        assert "Time units: days" in block

    def test_calibration_instruction_present(self) -> None:
        block = build_author_intent_block({"genre": "thriller"})
        assert "calibrate" in block.lower()
        assert "do not penalize" in block.lower()
