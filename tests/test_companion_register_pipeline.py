"""S3: pipeline register watch kill switch + craft dim gating (stubbed)."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ghostreader.companion.discovery import DiscoveryResult
from ghostreader.companion.pipeline import run_companion_pipeline
from ghostreader.ingestion import Chapter

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "register" / "shatterbound-ch1-opening.md"


def _discovery(tmp_path: Path | None = None) -> DiscoveryResult:
    raw = FIXTURE.read_text(encoding="utf-8")
    root = tmp_path or FIXTURE.parent
    ch = Chapter(
        title="What the Chain Heard",
        content=raw,
        chapter_number=1,
        source_path=FIXTURE,
    )
    return DiscoveryResult(
        mode="progressive",
        path=root,
        story_slug="shatterbound",
        story_dir=root,
        chapters_dir=root,
        chapter_number=1,
        chapters=[ch],
        gaps=[],
        warnings=[],
        seed_meta={},
        manuscript_name="shatterbound · Chapter 1",
    )


@pytest.mark.asyncio
async def test_register_watch_on_emits_rows_and_dims(tmp_path: Path) -> None:
    discovery = _discovery(tmp_path)
    captured: dict[str, Any] = {}

    async def fake_craft(**kwargs: Any) -> dict[str, Any]:
        captured.update(kwargs)
        return {
            "prose_output": {
                "findings": [
                    {
                        "dimension": "prose.human_door",
                        "severity": "concern",
                        "summary": "late door",
                        "evidence": "x",
                        "chapter_ref": "1",
                    }
                ],
                "raw_response": {
                    "dimension_ratings": {
                        "prose.human_door": {
                            "severity": "concern",
                            "note": "late door",
                        },
                        "prose.jargon_earn": {
                            "severity": "concern",
                            "note": "unearned",
                        },
                        "prose.repetition": {"severity": "neutral", "note": ""},
                    }
                },
            }
        }

    with (
        patch(
            "ghostreader.companion.pipeline.FactMemoryStore.ensure_facts",
            new=AsyncMock(return_value=[]),
        ),
        patch(
            "ghostreader.companion.pipeline.FactMemoryStore.last_reused",
            new=0,
            create=True,
        ),
        patch(
            "ghostreader.companion.pipeline.run_companion_craft",
            new=fake_craft,
        ),
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
            "ghostreader.companion.pipeline.load_progress",
            return_value={},
        ),
        patch(
            "ghostreader.companion.pipeline.compute_order_warnings",
            return_value=[],
        ),
    ):
        # FactMemoryStore is constructed; patch instance methods via class.
        store = MagicMock()
        store.ensure_facts = AsyncMock(return_value=[])
        store.last_reused = 0
        store.last_extracted = 0
        with patch(
            "ghostreader.companion.pipeline.FactMemoryStore",
            return_value=store,
        ):
            brief = await run_companion_pipeline(
                discovery,
                llm=MagicMock(),
                typesafe_client=None,
                typesafe_enabled=False,
                story_state_dir=tmp_path,
                genre=None,
                companion_register_watch=True,
                companion_light_narrative=False,
                json_mode=True,
            )

    assert brief.register_findings
    assert all(
        r["kind"] in {"unearned_jargon", "initiation_budget"} for r in brief.register_findings
    )
    assert captured.get("include_register_dims") is True
    assert "Register heuristic" in (captured.get("register_block") or "")
    dims = {r.dimension for r in brief.craft_ratings}
    assert "prose.human_door" in dims
    assert "prose.jargon_earn" in dims


@pytest.mark.asyncio
async def test_register_kill_switch_empties_and_stock_dims(tmp_path: Path) -> None:
    discovery = _discovery(tmp_path)
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

    store = MagicMock()
    store.ensure_facts = AsyncMock(return_value=[])
    store.last_reused = 0
    store.last_extracted = 0
    with (
        patch(
            "ghostreader.companion.pipeline.FactMemoryStore",
            return_value=store,
        ),
        patch(
            "ghostreader.companion.pipeline.run_companion_craft",
            new=fake_craft,
        ),
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
            "ghostreader.companion.pipeline.load_progress",
            return_value={},
        ),
        patch(
            "ghostreader.companion.pipeline.compute_order_warnings",
            return_value=[],
        ),
    ):
        brief = await run_companion_pipeline(
            discovery,
            llm=MagicMock(),
            typesafe_client=None,
            typesafe_enabled=False,
            story_state_dir=tmp_path,
            genre=None,
            companion_register_watch=False,
            companion_light_narrative=False,
            json_mode=True,
        )

    assert brief.register_findings == []
    assert captured.get("include_register_dims") is False
    assert (captured.get("register_block") or "") == ""
    dims = {r.dimension for r in brief.craft_ratings}
    assert "prose.human_door" not in dims
    assert "prose.jargon_earn" not in dims


@pytest.mark.asyncio
async def test_continuity_only_skips_register(tmp_path: Path) -> None:
    discovery = _discovery(tmp_path)
    store = MagicMock()
    store.ensure_facts = AsyncMock(return_value=[])
    store.last_reused = 0
    store.last_extracted = 0
    with (
        patch(
            "ghostreader.companion.pipeline.FactMemoryStore",
            return_value=store,
        ),
        patch(
            "ghostreader.companion.pipeline.run_companion_craft",
            new=AsyncMock(side_effect=AssertionError("craft should not run")),
        ),
        patch(
            "ghostreader.companion.pipeline._run_llm_consistency",
            new=AsyncMock(return_value=([], {}, {})),
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
            "ghostreader.companion.pipeline.load_progress",
            return_value={},
        ),
        patch(
            "ghostreader.companion.pipeline.compute_order_warnings",
            return_value=[],
        ),
    ):
        brief = await run_companion_pipeline(
            discovery,
            llm=MagicMock(),
            typesafe_client=None,
            typesafe_enabled=False,
            story_state_dir=tmp_path,
            genre=None,
            continuity_only=True,
            companion_register_watch=True,
            companion_light_narrative=False,
            json_mode=True,
        )

    assert brief.register_findings == []
    assert brief.repetition_findings == []
