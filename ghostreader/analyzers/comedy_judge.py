"""Comedy source: is the humor in what happens, or only in the lines? (#21)

One LLM call per scene window (about 1,100 words). The judge sorts every comic
moment by where the fun comes from:

- ``situation``: what happens (a plan backfires, a fix makes it worse, events
  compound, an absurd rule played straight, dignity punctured).
- ``character``: who someone is, shown in action (vanity, obsession).
- ``verbal``: a quip, comeback, or witty line; the scene around it is not funny.
- ``announced``: narration says people are amused with no funny cause on the page.

Calibration, 2026-11-12, 15 windows per book (gemini-3.8-flash):

- Comic human novels (Three Men in a Boat, Jeeves, Piccadilly Jim, Tom Sawyer,
  Innocents Abroad): 33 to 84% of moments are situation or character; 27 to 73%
  of windows escalate.
- Serious human novels (Pride and Prejudice, Holmes): fewer moments, still 45 to
  62% situation or character.
- Autonomicon (six stories, some seeded "dry sarcasm" or "absurd observation"):
  almost no comic moments; where there are some, 81 to 100% are verbal, and no
  window escalates.

So the row is about the source of the humor, not its quality or amount.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from ghostreader.analyzers.dialogue_shape import split_paragraphs, word_count
from ghostreader.llm import extract_json_array, message_text

logger = logging.getLogger(__name__)

WINDOW_WORDS = 1100
KINDS = ("situation", "character", "verbal", "announced")
# Fewer comic moments than this in a chapter: too few to judge the mix.
QUIP_MIN_MOMENTS = 4
QUIP_MODERATE_SHARE = 0.25
QUIP_HIGH_SHARE = 0.10
ANNOUNCED_CAP = 3

SYSTEM = """You judge where the comedy in a passage of fiction comes from. You are not judging
whether the jokes are good. You are sorting each comic moment by its source.

A comic moment is anything the author means to be funny or light. Sort each into one kind:

- situation: the funny thing is what HAPPENS. A plan backfires, a mishap, a fix that makes
  things worse, events that compound, an absurd rule or premise played straight, dignity
  punctured by circumstance, a character's confident action going wrong, an incongruous
  thing nobody remarks on. The narration can be deadpan; the events carry it.
- character: the funny thing is how a person IS. Vanity, obsession, self-deception, a
  ridiculous habit, shown in action rather than stated.
- verbal: the funny thing is a LINE. A quip, comeback, sarcastic remark, pun, witty
  description, teasing one-liner. Funny out of context; the scene around it is not.
- announced: narration TELLS us something is funny or that people are amused (grinned,
  laughed, smirked, "the joke landed", "despite herself she smiled") and there is no
  funny cause on the page for it.

Also rate the whole passage:
- "intent": 0 = not trying to be funny at all, 1 = some lightness, 2 = clearly comic.
- "escalation": true if within the passage a problem or absurdity compounds, each step
  worse or stranger than the last.

Return only JSON: [{"intent": 0|1|2, "escalation": true|false,
"moments": [{"kind": "situation"|"character"|"verbal"|"announced", "quote": "<= 15 words"}]}]
Return an empty moments list when nothing is meant to be funny."""


def scene_windows(text: str) -> list[str]:
    """Consecutive paragraph runs of about ``WINDOW_WORDS`` words."""
    out: list[str] = []
    cur: list[str] = []
    n = 0
    for para in split_paragraphs(text):
        cur.append(para)
        n += word_count(para)
        if n >= WINDOW_WORDS:
            out.append("\n\n".join(cur))
            cur, n = [], 0
    if cur and (n > WINDOW_WORDS // 2 or not out):
        out.append("\n\n".join(cur))
    return out


async def _judge_window(llm: BaseChatModel, window: str) -> dict[str, Any]:
    response = await llm.ainvoke([SystemMessage(content=SYSTEM), HumanMessage(content=window)])
    rows = extract_json_array(message_text(response.content)) or []
    return rows[0] if rows and isinstance(rows[0], dict) else {}


def _quip_row(
    chapter: int, kinds: dict[str, int], verbal_quotes: list[str]
) -> dict[str, Any] | None:
    comic = kinds["situation"] + kinds["character"] + kinds["verbal"]
    if comic < QUIP_MIN_MOMENTS:
        return None
    share = (kinds["situation"] + kinds["character"]) / comic
    if share >= QUIP_MODERATE_SHARE:
        return None
    summary = (
        f"{comic} comic moments and {kinds['verbal']} of them are lines (quips, comebacks, "
        f"wry remarks); only {kinds['situation'] + kinds['character']} come from what happens "
        "or who someone is. Comic novels get a third or more of their fun from situation: "
        "a plan that backfires, a fix that makes it worse, an absurd rule played straight. "
        "Consider letting the circumstances be funny and the characters play it straight."
    )
    return {
        "kind": "quip_humor",
        "severity": "high" if share < QUIP_HIGH_SHARE else "moderate",
        "chapter": chapter,
        "summary": summary,
        "message": summary,
        "quote": " / ".join(q[:80] for q in verbal_quotes[:3]),
        "turns": comic,
        "start_paragraph": 0,
        "metric": round(share, 4),
    }


def _announced_row(chapter: int, quote: str) -> dict[str, Any]:
    summary = (
        "The narration says someone is amused, but nothing on the page is funny. "
        "Either give them something to laugh at or cut the laugh."
    )
    return {
        "kind": "announced_levity",
        "severity": "low",
        "chapter": chapter,
        "summary": summary,
        "message": summary,
        "quote": quote[:160],
        "turns": 0,
        "start_paragraph": 0,
        "metric": 1.0,
    }


async def judge_comedy(
    llm: BaseChatModel, text: str, *, chapter_number: int = 1
) -> tuple[list[dict[str, Any]], dict[str, Any], list[str]]:
    """Return ``(rows, stats, warnings)`` for one chapter. Fail-soft."""
    windows = scene_windows(text)
    kinds = dict.fromkeys(KINDS, 0)
    stats: dict[str, Any] = {
        "chapter": chapter_number,
        "windows": 0,
        "comic_windows": 0,
        "escalating_windows": 0,
        "moments": kinds,
    }
    if not windows:
        return [], stats, []
    results = await asyncio.gather(
        *(_judge_window(llm, w) for w in windows), return_exceptions=True
    )
    warnings: list[str] = []
    verbal_quotes: list[str] = []
    announced: list[str] = []
    for result in results:
        if isinstance(result, BaseException):
            logger.warning("Comedy judge call failed: %s", result)
            warnings.append(
                f"comedy judge: ch {chapter_number} call failed "
                f"({type(result).__name__}); one scene not judged"
            )
            continue
        stats["windows"] += 1
        try:
            intent = int(result.get("intent") or 0)
        except (TypeError, ValueError):
            intent = 0
        if intent > 0:
            stats["comic_windows"] += 1
        if result.get("escalation") is True:
            stats["escalating_windows"] += 1
        for m in result.get("moments") or []:
            if not isinstance(m, dict):
                continue
            kind = str(m.get("kind") or "")
            if kind not in kinds:
                continue
            kinds[kind] += 1
            quote = str(m.get("quote") or "").strip()
            if quote and kind == "verbal":
                verbal_quotes.append(quote)
            elif quote and kind == "announced":
                announced.append(quote)
    rows: list[dict[str, Any]] = []
    quip = _quip_row(chapter_number, kinds, verbal_quotes)
    if quip:
        rows.append(quip)
    rows.extend(_announced_row(chapter_number, q) for q in announced[:ANNOUNCED_CAP])
    return rows, stats, warnings


def comedy_totals(stats: list[dict[str, Any]]) -> dict[str, Any]:
    """Book summary of per-chapter comedy stats."""
    kinds = dict.fromkeys(KINDS, 0)
    for s in stats:
        for k in KINDS:
            kinds[k] += int((s.get("moments") or {}).get(k) or 0)
    windows = sum(int(s.get("windows") or 0) for s in stats)
    comic = kinds["situation"] + kinds["character"] + kinds["verbal"]
    return {
        "windows": windows,
        "comic_windows": sum(int(s.get("comic_windows") or 0) for s in stats),
        "escalating_windows": sum(int(s.get("escalating_windows") or 0) for s in stats),
        "moments": kinds,
        "situation_share": (
            round((kinds["situation"] + kinds["character"]) / comic, 4) if comic else 0.0
        ),
    }


__all__ = [
    "KINDS",
    "comedy_totals",
    "judge_comedy",
    "scene_windows",
]
