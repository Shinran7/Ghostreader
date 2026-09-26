"""S2: companion craft always names register dims (no live LLM)."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ghostreader.companion.craft import (
    _COMPANION_REGISTER_DIM_FRAGMENT,
    run_companion_craft,
)
from ghostreader.ingestion import Chapter
from ghostreader.typesafe.questions import (
    COMPANION_PROSE_DIMENSIONS,
    COMPANION_REGISTER_DIMENSIONS,
    PROSE_DIMENSIONS,
    companion_prose_questions,
)


def _ch(n: int, text: str) -> Chapter:
    return Chapter(
        title=f"Ch {n}",
        content=text,
        chapter_number=n,
        source_path=MagicMock(),
    )


class TestCompanionRegisterQuestions:
    def test_bank_merges_register_dims(self) -> None:
        bank = companion_prose_questions()
        assert "prose.human_door" in bank
        assert "prose.jargon_earn" in bank
        assert set(COMPANION_REGISTER_DIMENSIONS).issubset(set(bank))
        assert len(COMPANION_PROSE_DIMENSIONS) == 7
        assert len(PROSE_DIMENSIONS) == 5

    def test_llm_fragment_names_both_dims(self) -> None:
        assert "prose.human_door" in _COMPANION_REGISTER_DIM_FRAGMENT
        assert "prose.jargon_earn" in _COMPANION_REGISTER_DIM_FRAGMENT


@pytest.mark.asyncio
async def test_llm_path_system_prompt_names_register_dims() -> None:
    llm = AsyncMock()
    llm.ainvoke = AsyncMock(
        return_value=MagicMock(
            content=(
                '[{"dimension":"prose.human_door","severity":"concern",'
                '"summary":"late door","evidence":"x","chapter_ref":"1"}]'
            )
        )
    )
    await run_companion_craft(
        focus_chapters=[_ch(1, "The wind was tobhandari.")],
        repetition_block="No significant repetition patterns detected.",
        register_block="## Register heuristic\n  - [unearned_jargon/moderate] tobhandari",
        config={"typesafe_enabled": False},
        llm=llm,
        typesafe_client=None,
    )
    system_msg = llm.ainvoke.await_args.args[0][0].content
    user_msg = llm.ainvoke.await_args.args[0][1].content
    assert "prose.human_door" in system_msg
    assert "prose.jargon_earn" in system_msg
    assert "Register heuristic" in user_msg
    assert "tobhandari" in user_msg


@pytest.mark.asyncio
async def test_typesafe_path_uses_companion_prose_bank() -> None:
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
            register_block="## Register heuristic\nnone",
            config={"typesafe_enabled": True, "typesafe_confidence_floor": 0.55},
            llm=MagicMock(),
            typesafe_client=MagicMock(),
        )

    assert "prose.human_door" in captured["questions"]
    assert "prose.jargon_earn" in captured["questions"]
    assert set(PROSE_DIMENSIONS).issubset(set(captured["questions"]))
    dims_arg = choices_mock.call_args.args[1]
    assert dims_arg == COMPANION_PROSE_DIMENSIONS
    assert captured["ts_state"].get("register_data")
