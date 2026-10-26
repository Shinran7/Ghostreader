"""S3: companion craft soft prose.voice_card bank (no live LLM)."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ghostreader.companion.craft import (
    _COMPANION_VOICE_CARD_DIM_FRAGMENT,
    run_companion_craft,
)
from ghostreader.ingestion import Chapter
from ghostreader.typesafe.questions import (
    COMPANION_PROSE_DIMENSIONS,
    COMPANION_REGISTER_DIMENSIONS,
    COMPANION_VOICE_CARD_DIMENSIONS,
    PROSE_DIMENSIONS,
    build_companion_prose_dimensions,
    companion_prose_questions,
)


def _ch(n: int, text: str) -> Chapter:
    return Chapter(
        title=f"Ch {n}",
        content=text,
        chapter_number=n,
        source_path=MagicMock(),
    )


class TestCompanionVoiceCardQuestions:
    def test_bank_includes_voice_card_when_on(self) -> None:
        bank = companion_prose_questions(include_voice_card=True)
        assert "prose.voice_card" in bank
        assert set(COMPANION_VOICE_CARD_DIMENSIONS).issubset(set(bank))
        assert set(PROSE_DIMENSIONS).issubset(set(bank))
        full = companion_prose_questions()
        assert set(full) == set(COMPANION_PROSE_DIMENSIONS)
        assert len(COMPANION_PROSE_DIMENSIONS) == 9
        assert len(PROSE_DIMENSIONS) == 5

    def test_stock_five_when_watches_off(self) -> None:
        bank = companion_prose_questions(include_register=False, include_voice_card=False)
        assert set(bank) == set(PROSE_DIMENSIONS)
        assert "prose.voice_card" not in bank
        assert "prose.human_door" not in bank
        dims = build_companion_prose_dimensions(
            include_register=False,
            include_voice_card=False,
        )
        assert dims == PROSE_DIMENSIONS

    def test_register_without_voice_card(self) -> None:
        bank = companion_prose_questions(include_register=True, include_voice_card=False)
        assert "prose.human_door" in bank
        assert "prose.voice_card" not in bank
        assert set(COMPANION_REGISTER_DIMENSIONS).issubset(set(bank))

    def test_instructions_forbid_eye_dialect_and_name_prior(self) -> None:
        bank = companion_prose_questions(include_voice_card=True)
        text = str(bank["prose.voice_card"].instructions).lower()
        assert "eye-dialect" in text or "eye dialect" in text
        assert "prior" in text
        assert "fail soft" in text or "cards" in text
        assert "prose.voice_card" in _COMPANION_VOICE_CARD_DIM_FRAGMENT
        assert "eye-dialect" in _COMPANION_VOICE_CARD_DIM_FRAGMENT


@pytest.mark.asyncio
async def test_llm_path_includes_voice_card_when_on() -> None:
    llm = AsyncMock()
    llm.ainvoke = AsyncMock(
        return_value=MagicMock(
            content=(
                '[{"dimension":"prose.voice_card","severity":"concern",'
                '"summary":"collapse","evidence":"x","chapter_ref":"1"}]'
            )
        )
    )
    await run_companion_craft(
        focus_chapters=[_ch(1, 'Orin said, "No."')],
        repetition_block="No significant repetition patterns detected.",
        register_block="",
        voice_card_block=(
            "## Voice-vs-card heuristic\n"
            "  - [card_mismatch/moderate] speaker=fixture-sermon-orin "
            "chapters=[1] (focus)"
        ),
        include_register_dims=False,
        include_voice_card_dims=True,
        config={"typesafe_enabled": False},
        llm=llm,
        typesafe_client=None,
    )
    system_msg = llm.ainvoke.await_args.args[0][0].content
    user_msg = llm.ainvoke.await_args.args[0][1].content
    assert "prose.voice_card" in system_msg
    assert "Voice-vs-card heuristic" in user_msg
    assert "fixture-sermon-orin" in user_msg


@pytest.mark.asyncio
async def test_llm_path_stock_five_when_voice_off() -> None:
    llm = AsyncMock()
    llm.ainvoke = AsyncMock(
        return_value=MagicMock(
            content='[{"dimension":"prose.rhythm","severity":"neutral","summary":"ok"}]'
        )
    )
    await run_companion_craft(
        focus_chapters=[_ch(1, "Hello.")],
        repetition_block="No significant repetition patterns detected.",
        include_register_dims=False,
        include_voice_card_dims=False,
        voice_card_block="## Voice-vs-card heuristic\nshould not appear",
        config={"typesafe_enabled": False},
        llm=llm,
        typesafe_client=None,
    )
    system_msg = llm.ainvoke.await_args.args[0][0].content
    user_msg = llm.ainvoke.await_args.args[0][1].content
    assert "prose.voice_card" not in system_msg
    assert "should not appear" not in user_msg


@pytest.mark.asyncio
async def test_typesafe_path_uses_voice_card_when_on() -> None:
    captured: dict[str, Any] = {}

    class FakeResponse:
        answers: dict[str, Any] = {}

    async def fake_ask(client: Any, *, state: dict[str, Any], questions: Any) -> Any:
        captured["questions"] = questions
        captured["ts_state"] = state
        return FakeResponse()

    with (
        patch("ghostreader.typesafe.client.ask", new=fake_ask),
        patch(
            "ghostreader.typesafe.adapters.choices_to_findings",
            return_value=([], {}),
        ) as choices_mock,
        patch(
            "ghostreader.typesafe.adapters.serialize_choice_answers",
            return_value={},
        ),
        patch(
            "ghostreader.typesafe.adapters.build_typesafe_raw_response",
            return_value={},
        ),
    ):
        await run_companion_craft(
            focus_chapters=[_ch(1, "Hello.")],
            repetition_block="No significant repetition patterns detected.",
            register_block="",
            voice_card_block="## Voice-vs-card heuristic\nnone",
            include_register_dims=False,
            include_voice_card_dims=True,
            config={"typesafe_enabled": True, "typesafe_confidence_floor": 0.55},
            llm=MagicMock(),
            typesafe_client=MagicMock(),
        )

    assert "prose.voice_card" in captured["questions"]
    assert set(PROSE_DIMENSIONS).issubset(set(captured["questions"]))
    assert "prose.human_door" not in captured["questions"]
    dims_arg = choices_mock.call_args.args[1]
    assert dims_arg == build_companion_prose_dimensions(
        include_register=False,
        include_voice_card=True,
    )
    assert captured["ts_state"].get("voice_card_data")


@pytest.mark.asyncio
async def test_pipeline_voice_card_kill_switch_gates_dims(tmp_path: Path) -> None:
    from ghostreader.companion.discovery import DiscoveryResult
    from ghostreader.companion.pipeline import run_companion_pipeline
    from ghostreader.companion.progress import ProgressState

    fixture = (
        Path(__file__).resolve().parent / "fixtures" / "register" / "shatterbound-ch1-opening.md"
    )
    raw = fixture.read_text(encoding="utf-8")
    ch = Chapter(
        title="Ch 1",
        content=raw,
        chapter_number=1,
        source_path=fixture,
    )
    discovery = DiscoveryResult(
        mode="progressive",
        path=tmp_path,
        story_slug="s",
        story_dir=tmp_path,
        chapters_dir=tmp_path,
        chapter_number=1,
        chapters=[ch],
        gaps=[],
        warnings=[],
        seed_meta={},
        manuscript_name="s · Chapter 1",
    )
    captured: dict[str, Any] = {}

    async def fake_craft(**kwargs: Any) -> dict[str, Any]:
        captured.update(kwargs)
        return {
            "prose_output": {
                "findings": [],
                "raw_response": {"dimension_ratings": {}},
            }
        }

    store = MagicMock()
    store.ensure_facts = AsyncMock(return_value=[])
    store.last_reused = 0
    store.last_extracted = 0
    with (
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
    ):
        await run_companion_pipeline(
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

    assert captured.get("include_voice_card_dims") is False
    assert (captured.get("voice_card_block") or "") == ""
