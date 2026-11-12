"""Tennis returns: statement, then a retort that recasts it to deny it (#21).

One LLM call per 60 statement/reply pairs. The judge labels retorts in four
forms. Only two are reported, because only they separate machine dialogue
from human dialogue in a 2026-11-12 calibration (ten public-domain novels,
1,500 pairs, against eight Autonomicon stories, about 1,260 pairs):

- ``recast``: B takes A's word or claim and swaps it ("Sentiment." /
  "Logistics."; "You dropped it." / "I was lowering it.").
- ``x_not_y``: B corrects A with "X, not Y" or "It isn't X. It's Y."

Human novels: 3 in 1,500 pairs (0.2%). Autonomicon: 39 in 1,260 (3.1%), and
every story had some. Plain contradiction and flat denial ran 7 to 12% in
both, so they are judged but not reported.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from ghostreader.analyzers.dialogue_shape import extract_turns, split_paragraphs, word_count
from ghostreader.llm import extract_json_array, message_text

logger = logging.getLogger(__name__)

PAIRS_PER_CALL = 60
# Narration longer than this between two lines means they are not an exchange.
EXCHANGE_BREAK_WORDS = 30
REPORTED_FORMS = ("recast", "x_not_y")
# Instance rows kept per chapter; the habit row carries the count.
INSTANCE_CAP = 5
HABIT_MIN_RETURNS = 2
HABIT_MODERATE_SHARE = 0.02
HABIT_HIGH_SHARE = 0.035
_CLIP = 300

SYSTEM = """You read pairs of adjacent lines of dialogue from fiction. Line A is said by one
character; line B is the next spoken line, usually by the other character.

Mark a pair as a RETORT when B's main job is to contradict, correct, or deny what A just
said: B tells A they are wrong, recasts A's words as something worse or smaller ("That's
dry poultry, not a succulent meal"), or flatly negates A's claim. The negation can be
in meaning only, with no "no" or "not".

NOT a retort: answering a question, agreeing, adding information, a joke that does not
deny A, refusing a request, changing the subject, B continuing the same speaker's thought,
or disagreement that offers a new idea rather than negating A's statement.

Return only a JSON array of objects for the RETORT pairs:
[{"id": <pair id>, "form": "flat_denial" | "x_not_y" | "recast" | "contradiction"}]
Return [] when none are retorts."""


@dataclass
class ExchangePair:
    """A statement (not a question) and the spoken line that answers it."""

    statement: str
    reply: str
    reply_paragraph: int  # 1-based


def exchange_pairs(text: str) -> list[ExchangePair]:
    """Adjacent spoken lines where the first is not a question."""
    paragraphs = split_paragraphs(text)
    out: list[ExchangePair] = []
    prev = None
    gap = 0
    for para, turn in zip(paragraphs, extract_turns(paragraphs), strict=True):
        if turn is None:
            gap += word_count(para)
            if gap > EXCHANGE_BREAK_WORDS:
                prev = None
            continue
        if prev is not None and not prev.spoken.rstrip().rstrip('"\u201d').endswith("?"):
            out.append(ExchangePair(prev.spoken, turn.spoken, turn.paragraph + 1))
        prev = turn
        gap = 0
    return out


async def _judge_chunk(llm: BaseChatModel, pairs: list[ExchangePair]) -> list[dict[str, Any]]:
    body = "\n\n".join(
        f"[{i}]\nA: {p.statement[:_CLIP]}\nB: {p.reply[:_CLIP]}" for i, p in enumerate(pairs)
    )
    response = await llm.ainvoke([SystemMessage(content=SYSTEM), HumanMessage(content=body)])
    rows = extract_json_array(message_text(response.content)) or []
    return [r for r in rows if isinstance(r, dict)]


def _instance_row(pair: ExchangePair, form: str, chapter: int) -> dict[str, Any]:
    how = (
        "corrects it with an X-not-Y swap"
        if form == "x_not_y"
        else "recasts the same words to deny them"
    )
    summary = (
        f"Statement, then a retort that {how}. Once is a character beat; as a habit it is "
        "the tennis-match pattern. Consider letting B answer the person, not the wording."
    )
    return {
        "kind": "tennis_return",
        "severity": "low",
        "chapter": chapter,
        "summary": summary,
        "message": summary,
        "quote": f"{pair.statement[:120]} / {pair.reply[:120]}",
        "turns": 2,
        "start_paragraph": pair.reply_paragraph,
        "metric": 1.0,
        "form": form,
    }


def _habit_row(chapter: int, returns: int, pairs: int) -> dict[str, Any] | None:
    share = returns / pairs if pairs else 0.0
    if returns < HABIT_MIN_RETURNS or share < HABIT_MODERATE_SHARE:
        return None
    summary = (
        f"{returns} of {pairs} statement-and-reply exchanges end in a recast retort "
        f"({round(share * 100, 1)}%). Human novels run about 0.2%. This is the tennis "
        "match: each line exists to knock back the last one."
    )
    return {
        "kind": "tennis_habit",
        "severity": "high" if share >= HABIT_HIGH_SHARE else "moderate",
        "chapter": chapter,
        "summary": summary,
        "message": summary,
        "quote": "",
        "turns": pairs,
        "start_paragraph": 0,
        "metric": round(share, 4),
    }


async def judge_tennis_returns(
    llm: BaseChatModel, text: str, *, chapter_number: int = 1
) -> tuple[list[dict[str, Any]], dict[str, Any], list[str]]:
    """Return ``(rows, stats, warnings)`` for one chapter. Fail-soft."""
    pairs = exchange_pairs(text)
    stats: dict[str, Any] = {"chapter": chapter_number, "pairs": len(pairs), "forms": {}}
    if not pairs:
        stats["tennis_returns"] = 0
        return [], stats, []
    chunks = [pairs[i : i + PAIRS_PER_CALL] for i in range(0, len(pairs), PAIRS_PER_CALL)]
    results = await asyncio.gather(*(_judge_chunk(llm, c) for c in chunks), return_exceptions=True)
    warnings: list[str] = []
    hits: list[tuple[ExchangePair, str]] = []
    forms: dict[str, int] = {}
    for chunk, result in zip(chunks, results, strict=True):
        if isinstance(result, BaseException):
            logger.warning("Dialogue judge call failed: %s", result)
            warnings.append(
                f"dialogue judge: ch {chapter_number} call failed "
                f"({type(result).__name__}); some pairs not judged"
            )
            continue
        seen: set[int] = set()
        for row in result:
            try:
                idx = int(row.get("id", -1))
            except (TypeError, ValueError):
                continue
            form = str(row.get("form") or "")
            if not 0 <= idx < len(chunk) or idx in seen:
                continue
            seen.add(idx)
            forms[form] = forms.get(form, 0) + 1
            if form in REPORTED_FORMS:
                hits.append((chunk[idx], form))
    stats["forms"] = forms
    stats["tennis_returns"] = len(hits)
    rows = [_instance_row(p, f, chapter_number) for p, f in hits[:INSTANCE_CAP]]
    habit = _habit_row(chapter_number, len(hits), len(pairs))
    if habit:
        rows.insert(0, habit)
    return rows, stats, warnings


__all__ = [
    "REPORTED_FORMS",
    "ExchangePair",
    "exchange_pairs",
    "judge_tennis_returns",
]
