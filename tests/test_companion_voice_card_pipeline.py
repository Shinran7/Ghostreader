"""S4a: pipeline voice-card watch wire (stubbed craft; no live LLM)."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ghostreader.companion.discovery import DiscoveryResult
from ghostreader.companion.pipeline import run_companion_pipeline
from ghostreader.companion.progress import ProgressState
from ghostreader.ingestion import Chapter

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "voice_card"


def _chapter_from(story: str, *, n: int = 1) -> tuple[Path, Chapter]:
    root = FIXTURES / story
    path = root / "chapters" / "chapter-001.md"
    ch = Chapter(
        title=f"Ch {n}",
        content=path.read_text(encoding="utf-8"),
        chapter_number=n,
        source_path=path,
    )
    return root, ch


def _discovery(story: str, tmp_path: Path | None = None) -> DiscoveryResult:
    root, ch = _chapter_from(story)
    # Prefer real story root so canon/characters resolves; tmp_path only for state.
    return DiscoveryResult(
        mode="progressive",
        path=root,
        story_slug=story,
        story_dir=root,
        chapters_dir=root / "chapters",
        chapter_number=1,
        chapters=[ch],
        gaps=[],
        warnings=[],
        seed_meta={},
        manuscript_name=f"{story} · Chapter 1",
    )


def _patch_pipeline_base(
    *,
    fake_craft: Any,
    store: MagicMock,
) -> list[Any]:
    return [
        patch("ghostreader.companion.pipeline.FactMemoryStore", return_value=store),
        patch("ghostreader.companion.pipeline.run_companion_craft", new=fake_craft),
        patch(
            "ghostreader.companion.pipeline._run_llm_consistency",
            new=AsyncMock(return_value=([], {}, {})),
        ),
        patch(
            "ghostreader.companion.pipeline.run_companion_narrative",
            new=AsyncMock(return_value=([], {}, 0)),
        ),
        patch(
            "ghostreader.companion.pipeline._chapter_note",
            new=AsyncMock(return_value="note"),
        ),
        patch(
            "ghostreader.companion.pipeline.update_progress_after_run",
            return_value=None,
        ),
        patch(
            "ghostreader.companion.pipeline.clamp_progress_to_disk",
            return_value=ProgressState(),
        ),
        patch(
            "ghostreader.companion.pipeline.compute_order_warnings",
            return_value=[],
        ),
    ]


def _empty_store() -> MagicMock:
    store = MagicMock()
    store.ensure_facts = AsyncMock(return_value=[])
    store.last_reused = 0
    store.last_extracted = 0
    return store


@pytest.mark.asyncio
async def test_voice_card_watch_on_emits_rows_and_bias(tmp_path: Path) -> None:
    discovery = _discovery("story_terse", tmp_path)
    captured: dict[str, Any] = {}

    async def fake_craft(**kwargs: Any) -> dict[str, Any]:
        captured.update(kwargs)
        return {
            "prose_output": {
                "findings": [],
                "raw_response": {
                    "dimension_ratings": {
                        "prose.voice_card": {"severity": "neutral", "note": ""},
                        "prose.repetition": {"severity": "neutral", "note": ""},
                    }
                },
            }
        }

    ctxs = _patch_pipeline_base(fake_craft=fake_craft, store=_empty_store())
    with ctxs[0], ctxs[1], ctxs[2], ctxs[3], ctxs[4], ctxs[5], ctxs[6], ctxs[7]:
        brief = await run_companion_pipeline(
            discovery,
            llm=MagicMock(),
            typesafe_client=None,
            typesafe_enabled=False,
            story_state_dir=tmp_path,
            genre=None,
            companion_register_watch=False,
            companion_voice_card_watch=True,
            companion_light_narrative=False,
            json_mode=True,
        )

    assert brief.voice_card_findings
    assert all(r["kind"] in {"card_mismatch", "card_collapse"} for r in brief.voice_card_findings)
    assert captured.get("include_voice_card_dims") is True
    assert "Voice-vs-card heuristic" in (captured.get("voice_card_block") or "")
    assert any(r["speaker"] == "fixture-terse-warden" for r in brief.voice_card_findings)
    dims = {r.dimension for r in brief.craft_ratings}
    assert "prose.voice_card" in dims
    # Machine rows alone do not flip watch.
    assert brief.verdict == "ship"
    assert "craft" not in brief.verdict_drivers


@pytest.mark.asyncio
async def test_voice_card_kill_switch_empties(tmp_path: Path) -> None:
    discovery = _discovery("story_terse", tmp_path)
    captured: dict[str, Any] = {}

    async def fake_craft(**kwargs: Any) -> dict[str, Any]:
        captured.update(kwargs)
        return {
            "prose_output": {
                "findings": [],
                "raw_response": {
                    "dimension_ratings": {
                        "prose.repetition": {"severity": "neutral", "note": ""},
                        "prose.rhythm": {"severity": "neutral", "note": ""},
                        "prose.show_vs_tell": {"severity": "neutral", "note": ""},
                        "prose.dialogue": {"severity": "neutral", "note": ""},
                        "prose.vocabulary": {"severity": "neutral", "note": ""},
                    }
                },
            }
        }

    ctxs = _patch_pipeline_base(fake_craft=fake_craft, store=_empty_store())
    with ctxs[0], ctxs[1], ctxs[2], ctxs[3], ctxs[4], ctxs[5], ctxs[6], ctxs[7]:
        brief = await run_companion_pipeline(
            discovery,
            llm=MagicMock(),
            typesafe_client=None,
            typesafe_enabled=False,
            story_state_dir=tmp_path,
            genre=None,
            companion_register_watch=False,
            companion_voice_card_watch=False,
            companion_light_narrative=False,
            json_mode=True,
        )

    assert brief.voice_card_findings == []
    assert captured.get("include_voice_card_dims") is False
    assert (captured.get("voice_card_block") or "") == ""
    dims = {r.dimension for r in brief.craft_ratings}
    assert "prose.voice_card" not in dims
    assert not any(w.startswith("voice_card watch:") for w in brief.warnings)


@pytest.mark.asyncio
async def test_continuity_only_skips_voice_card(tmp_path: Path) -> None:
    discovery = _discovery("story_terse", tmp_path)
    ctxs = _patch_pipeline_base(
        fake_craft=AsyncMock(side_effect=AssertionError("craft should not run")),
        store=_empty_store(),
    )
    with ctxs[0], ctxs[1], ctxs[2], ctxs[3], ctxs[4], ctxs[5], ctxs[6], ctxs[7]:
        brief = await run_companion_pipeline(
            discovery,
            llm=MagicMock(),
            typesafe_client=None,
            typesafe_enabled=False,
            story_state_dir=tmp_path,
            genre=None,
            continuity_only=True,
            companion_voice_card_watch=True,
            companion_light_narrative=False,
            json_mode=True,
        )

    assert brief.voice_card_findings == []
    assert brief.repetition_findings == []
    assert brief.register_findings == []


@pytest.mark.asyncio
async def test_missing_cards_warning_and_empty_rows(tmp_path: Path) -> None:
    # story_empty has chapters only — no canon/characters.
    empty_root = FIXTURES / "story_empty"
    empty_root.mkdir(parents=True, exist_ok=True)
    (empty_root / "chapters").mkdir(parents=True, exist_ok=True)
    ch_path = empty_root / "chapters" / "chapter-001.md"
    if not ch_path.exists():
        ch_path.write_text('Someone said, "Hello there friend."\n', encoding="utf-8")
    ch = Chapter(
        title="Ch 1",
        content=ch_path.read_text(encoding="utf-8"),
        chapter_number=1,
        source_path=ch_path,
    )
    discovery = DiscoveryResult(
        mode="progressive",
        path=empty_root,
        story_slug="story_empty",
        story_dir=empty_root,
        chapters_dir=empty_root / "chapters",
        chapter_number=1,
        chapters=[ch],
        gaps=[],
        warnings=[],
        seed_meta={},
        manuscript_name="story_empty · Chapter 1",
    )
    captured: dict[str, Any] = {}

    async def fake_craft(**kwargs: Any) -> dict[str, Any]:
        captured.update(kwargs)
        return {
            "prose_output": {
                "findings": [],
                "raw_response": {
                    "dimension_ratings": {
                        "prose.voice_card": {"severity": "neutral", "note": "fail soft"},
                    }
                },
            }
        }

    ctxs = _patch_pipeline_base(fake_craft=fake_craft, store=_empty_store())
    with ctxs[0], ctxs[1], ctxs[2], ctxs[3], ctxs[4], ctxs[5], ctxs[6], ctxs[7]:
        brief = await run_companion_pipeline(
            discovery,
            llm=MagicMock(),
            typesafe_client=None,
            typesafe_enabled=False,
            story_state_dir=tmp_path,
            genre=None,
            companion_register_watch=False,
            companion_voice_card_watch=True,
            companion_light_narrative=False,
            json_mode=True,
        )

    assert brief.voice_card_findings == []
    assert any(w == "voice_card watch: no canon/characters cards found" for w in brief.warnings)
    assert captured.get("include_voice_card_dims") is True
    assert "Voice-vs-card heuristic" in (captured.get("voice_card_block") or "")


@pytest.mark.asyncio
async def test_machine_rows_alone_never_flip_watch(tmp_path: Path) -> None:
    discovery = _discovery("story_collapse", tmp_path)

    async def fake_craft(**kwargs: Any) -> dict[str, Any]:
        return {
            "prose_output": {
                "findings": [],
                "raw_response": {"dimension_ratings": {}},
            }
        }

    ctxs = _patch_pipeline_base(fake_craft=fake_craft, store=_empty_store())
    with ctxs[0], ctxs[1], ctxs[2], ctxs[3], ctxs[4], ctxs[5], ctxs[6], ctxs[7]:
        brief = await run_companion_pipeline(
            discovery,
            llm=MagicMock(),
            typesafe_client=None,
            typesafe_enabled=False,
            story_state_dir=tmp_path,
            genre=None,
            companion_register_watch=False,
            companion_voice_card_watch=True,
            companion_light_narrative=False,
            json_mode=True,
        )

    assert brief.voice_card_findings
    assert any(r["kind"] == "card_collapse" for r in brief.voice_card_findings)
    assert brief.verdict == "ship"
    assert brief.verdict_drivers == []
    assert brief.craft_findings == []


@pytest.mark.asyncio
async def test_partial_invalid_cards_surface_warning(tmp_path: Path) -> None:
    """Unreadable/invalid cards must appear in brief.warnings (not only debug logs)."""
    story = tmp_path / "story_partial_cards"
    chapters = story / "chapters"
    characters = story / "canon" / "characters"
    chapters.mkdir(parents=True)
    characters.mkdir(parents=True)
    ch_path = chapters / "chapter-001.md"
    ch_path.write_text(
        'Warden said, "Move."\nHe said, "Now."\n',
        encoding="utf-8",
    )
    (characters / "warden.json").write_text(
        '{"slug":"warden","name":"Warden","dialogue_voice":"Terse, clipped."}\n',
        encoding="utf-8",
    )
    (characters / "broken.json").write_text("{nope", encoding="utf-8")
    ch = Chapter(
        title="Ch 1",
        content=ch_path.read_text(encoding="utf-8"),
        chapter_number=1,
        source_path=ch_path,
    )
    discovery = DiscoveryResult(
        mode="progressive",
        path=story,
        story_slug="story_partial_cards",
        story_dir=story,
        chapters_dir=chapters,
        chapter_number=1,
        chapters=[ch],
        gaps=[],
        warnings=[],
        seed_meta={},
        manuscript_name="story_partial_cards · Chapter 1",
    )

    async def fake_craft(**kwargs: Any) -> dict[str, Any]:
        return {
            "prose_output": {
                "findings": [],
                "raw_response": {
                    "dimension_ratings": {
                        "prose.voice_card": {"severity": "neutral", "note": ""},
                    }
                },
            }
        }

    ctxs = _patch_pipeline_base(fake_craft=fake_craft, store=_empty_store())
    with ctxs[0], ctxs[1], ctxs[2], ctxs[3], ctxs[4], ctxs[5], ctxs[6], ctxs[7]:
        brief = await run_companion_pipeline(
            discovery,
            llm=MagicMock(),
            typesafe_client=None,
            typesafe_enabled=False,
            story_state_dir=tmp_path / "state",
            genre=None,
            companion_register_watch=False,
            companion_voice_card_watch=True,
            companion_light_narrative=False,
            json_mode=True,
        )

    assert any(
        "skipped 1 unreadable/invalid card(s)" in w and "broken.json" in w
        for w in brief.warnings
    )
