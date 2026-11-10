"""#16: Canon checker — ref grounding and whole-book stats."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.messages import AIMessage

from ghostreader.agents.canon_consistency import (
    apply_canon_refs,
    check_book_against_canon,
)
from ghostreader.canon import load_canon_state
from ghostreader.quotes import QuoteIndex, canon_counter, verify_finding
from tests.test_canon_continuity import write_canon


def _state(tmp_path: Path, n: int = 3):
    write_canon(tmp_path / "canon")
    return load_canon_state(tmp_path / "canon", n)


def test_apply_refs_fills_canon_side(tmp_path: Path) -> None:
    state = _state(tmp_path)
    p_id = next(e.id for e in state.entries if "left_arm" in e.text)
    k_id = next(e.id for e in state.entries if e.id.startswith("K"))
    rows = [{"summary": "a"}, {"summary": "b"}, {"summary": "c"}, {"summary": "d"}]
    out = apply_canon_refs(rows, [f"[{p_id.lower()}]", k_id, "Q7"], state, 3)
    assert out[0]["counter_source"] == "canon"
    assert out[0]["chapter_ref"] == "2 vs 3"
    assert out[0]["counter_evidence"].startswith("Canon Ch 2 (physical state):")
    assert out[1]["chapter_ref"] == "Canon vs 3"
    assert out[2]["counter_evidence"] == ""
    assert out[2]["canon_ref"]["kind"] is None
    assert "counter_source" not in out[2]
    assert out[3] == {"summary": "d"}  # no ref: untouched
    assert rows[0] == {"summary": "a"}  # inputs not mutated


def test_canon_counter_is_not_looked_up_in_manuscript() -> None:
    f = {
        "dimension": "consistency.character",
        "evidence": "Ch 1: 'alpha beta gamma delta'",
        "counter_evidence": "Canon Ch 1 (character): not in the text",
        "counter_source": "canon",
    }
    assert canon_counter(f)
    assert canon_counter({"counter_evidence": "Canon (key fact): x"})
    assert not canon_counter({"counter_evidence": "Ch 1: 'x'"})
    idx = QuoteIndex([{"chapter_number": 1, "content": "alpha beta gamma delta epsilon"}])
    out = verify_finding(f, idx)
    assert out["quote_verified"] is True


@pytest.mark.asyncio
async def test_book_stats_skip_fail_and_parse_failed(tmp_path: Path) -> None:
    canon = tmp_path / "canon"
    (canon / "style").mkdir(parents=True)
    (canon / "style/chapter-ending-states.json").write_text(
        json.dumps([{"chapter": c, "ending_state": f"end {c}"} for c in (1, 2, 3)]),
        encoding="utf-8",
    )

    async def ainvoke(messages):
        user = messages[-1].content
        if "## Chapter 3" in user:
            raise RuntimeError("boom")
        if "## Chapter 4" in user:
            return AIMessage(content="not json at all")
        return AIMessage(
            content=json.dumps(
                [
                    {
                        "dimension": "consistency.timeline",
                        "severity": "concern",
                        "summary": "s",
                        "evidence": "Ch 2: 'x'",
                        "canon_ref": "E1",
                        "chapter_ref": "2",
                    }
                ]
            )
        )

    llm = MagicMock()
    llm.ainvoke = AsyncMock(side_effect=ainvoke)
    chapters = [{"chapter_number": n, "title": f"C{n}", "content": "x"} for n in (1, 2, 3, 4)]
    findings, stats = await check_book_against_canon(chapters, canon, llm, concurrency=2)
    assert stats == {"chapters": 3, "checkpoints": 0, "failed": 2, "skipped_empty": 1}
    assert len(findings) == 1
    assert findings[0]["chapter_ref"] == "1 vs 2"
    assert all(f["dimension"] != "consistency.general" for f in findings)
