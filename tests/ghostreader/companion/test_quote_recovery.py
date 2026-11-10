"""#17: bounded verbatim-quote recovery for continuity concerns."""

from __future__ import annotations

import pytest

from ghostreader.companion.quote_recovery import recover_continuity_quotes
from tests.test_quote_verification import _index, _llm, _paraphrase

# --- recovery -------------------------------------------------------------


@pytest.mark.asyncio
async def test_recovery_replaces_paraphrase_with_verified_quotes() -> None:
    llm = _llm(
        {
            "supported": True,
            "evidence": "Ch 1: 'Her eyes were blue as the harbor in winter.'",
            "counter_evidence": "Ch 2: 'He looked into her brown eyes'",
        }
    )
    out, recovered, calls = await recover_continuity_quotes(
        [_paraphrase()], _index(), llm, chapter_n=2
    )
    assert (recovered, calls) == (1, 1)
    f = out[0]
    assert f["quote_verified"] is True
    assert f["quote_recovered"] is True
    assert f["evidence_claim"] == "Ch 1: Mara's eyes described as blue"
    sent = str(llm.ainvoke.call_args.args[0][1].content)
    assert "--- Chapter 2 ---" in sent
    assert "--- Chapter 1 ---" in sent


@pytest.mark.asyncio
async def test_recovery_rejects_invented_quotes() -> None:
    llm = _llm(
        {
            "supported": True,
            "evidence": "Ch 1: 'Her eyes, blue as cornflowers, never wavered.'",
            "counter_evidence": "Ch 2: 'He looked into her brown eyes'",
        }
    )
    out, recovered, calls = await recover_continuity_quotes(
        [_paraphrase()], _index(), llm, chapter_n=2
    )
    assert (recovered, calls) == (0, 1)
    assert out[0]["quote_verified"] is False
    assert "quote_recovered" not in out[0]


@pytest.mark.asyncio
async def test_recovery_unsupported_and_errors_keep_original() -> None:
    for llm in (_llm({"supported": False, "evidence": ""}), _llm(RuntimeError("boom"))):
        out, recovered, calls = await recover_continuity_quotes(
            [_paraphrase()], _index(), llm, chapter_n=2
        )
        assert (recovered, calls) == (0, 1)
        assert out[0]["evidence"] == "Ch 1: Mara's eyes described as blue"


@pytest.mark.asyncio
async def test_recovery_respects_call_cap() -> None:
    llm = _llm({"supported": False})
    _, _, calls = await recover_continuity_quotes(
        [_paraphrase()] * 4, _index(), llm, chapter_n=2, max_calls=2
    )
    assert calls == 2
    assert llm.ainvoke.await_count == 2
