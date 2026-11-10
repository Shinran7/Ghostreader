"""Usage tracking (#19): calls and tokens per run."""

from __future__ import annotations

import asyncio

from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, LLMResult

from ghostreader.usage import UsageTracker, start_usage, track_usage


def _result(model: str, inp: int, out: int, *, total: int | None = None) -> LLMResult:
    usage = {"input_tokens": inp, "output_tokens": out, "total_tokens": total or inp + out}
    msg = AIMessage(content="x", usage_metadata=usage, response_metadata={"model_name": model})
    return LLMResult(generations=[[ChatGeneration(message=msg)]])


def test_sums_calls_and_tokens_by_model() -> None:
    t = UsageTracker()
    t.on_llm_end(_result("a", 10, 5))
    t.on_llm_end(_result("a", 1, 1, total=3))
    t.on_llm_end(_result("b", 2, 2))
    s = t.summary()
    assert s["llm_calls"] == 3
    assert s["input_tokens"] == 13
    assert s["output_tokens"] == 8
    assert s["total_tokens"] == 15 + 3 + 4
    assert s["by_model"]["a"]["calls"] == 2
    assert s["by_model"]["b"]["total_tokens"] == 4


def test_no_usage_counts_call_only() -> None:
    t = UsageTracker()
    msg = AIMessage(content="x")
    t.on_llm_end(LLMResult(generations=[[ChatGeneration(message=msg)]]))
    s = t.summary()
    assert s["llm_calls"] == 1
    assert s["total_tokens"] == 0
    assert list(s["by_model"]) == ["unknown"]


def _fake() -> GenericFakeChatModel:
    return GenericFakeChatModel(messages=iter([AIMessage(content="hi")] * 5))


def test_track_usage_sees_calls_in_block_and_tasks() -> None:
    llm = _fake()

    async def run() -> None:
        await llm.ainvoke("a")
        await asyncio.gather(asyncio.create_task(llm.ainvoke("b")))

    with track_usage() as t:
        asyncio.run(run())
    assert t.summary()["llm_calls"] == 2
    llm.invoke("outside")
    assert t.summary()["llm_calls"] == 2


def test_start_usage_replaces_tracker() -> None:
    llm = _fake()
    first = start_usage()
    llm.invoke("a")
    second = start_usage()
    llm.invoke("b")
    assert first.summary()["llm_calls"] == 1
    assert second.summary()["llm_calls"] == 1
