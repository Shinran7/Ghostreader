"""Anti-tidy narrative shape watch (#8, Autonomicon #268 S4).

One LLM call per progressive companion run looks for five tidy-shape craft
patterns in the focus chapter. Rows are additive ``shape_findings`` with
severity ``watch``: they never change the verdict, never gate, and never
feed craft ratings. This is craft framing only, never a claim about who or
what wrote the text.

A quote must be found in the focus chapter or the row is dropped. The two
book-level kinds (single track, flat escalation) may carry no quote, and
are only asked once enough chapters came before.
"""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from ghostreader.agents.fact_extractor import ChapterFact, format_fact_sheets
from ghostreader.agents.genre_prompts import get_genre_preamble
from ghostreader.excerpts import whole_chapter_block
from ghostreader.ingestion import Chapter
from ghostreader.llm import extract_json_array, message_text
from ghostreader.quotes import QuoteIndex, finding_id
from ghostreader.seed import build_author_intent_block

logger = logging.getLogger(__name__)

SHAPE_SEVERITY = "watch"
# Rows kept per chapter.
SHAPE_CAP = 3
# Book-level kinds need this many chapters before the focus chapter.
BOOK_KIND_MIN_PRIOR = 3

# kind -> (what it is, default message, default suggested fix)
SHAPE_KINDS: dict[str, tuple[str, str, str]] = {
    "anti_tidy_theme_announce": (
        "The narrator or a character states the lesson or theme a scene has already shown.",
        "The text restates a lesson the scene already paid for.",
        "Cut the gloss; leave the dramatized cost.",
    ),
    "anti_tidy_dialogue_philosophy": (
        "Characters trade abstract positions or theses instead of wanting "
        "something from each other in the scene.",
        "Dialogue debates ideas instead of carrying wants.",
        "Tie each line to what the speaker wants from the other person now.",
    ),
    "anti_tidy_moral_tidy": (
        "A hard choice resolves cleanly: the cost is erased, explained away, or forgiven at once.",
        "A hard choice resolves with its cost erased.",
        "Let the choice leave a mark that stays on the page.",
    ),
    "anti_tidy_single_track": (
        "The book runs on one thread: no subplot or second pressure touches "
        "this chapter, across several chapters in a row.",
        "One thread carries the book with no second pressure.",
        "Let a second thread press on this chapter, even briefly.",
    ),
    "anti_tidy_flat_escalation": (
        "Stakes stay level: this chapter's danger or cost is about the same "
        "as the chapters before it.",
        "Stakes stay level with the chapters before.",
        "Raise or turn the cost here, or change its kind.",
    ),
}
BOOK_KINDS = frozenset({"anti_tidy_single_track", "anti_tidy_flat_escalation"})

_SYSTEM = """{genre_preamble}
{author_intent}
You are a sharp editor checking ONE chapter for tidy narrative shape.
These are craft patterns, not faults of any writer or tool. Never say or
imply the text was machine-written.

Check only these patterns:
{kinds}

Report a pattern only when it clearly happens in the focus chapter. Most
chapters have none; an empty array is the normal answer.

OUTPUT FORMAT: a JSON array, at most {cap} items. Each item:
- "kind": one of the names above
- "quote": words copied exactly from the focus chapter that show it (at
  least 5 words){quote_rule}
- "message": one sentence on what happens in this chapter
- "suggested_fix": one short sentence

Return ONLY the JSON array."""


def _kind_lines(kinds: list[str]) -> str:
    return "\n".join(f"- {k}: {SHAPE_KINDS[k][0]}" for k in kinds)


def asked_kinds(focus_n: int) -> list[str]:
    """The kinds asked for chapter *focus_n* (book kinds need prior chapters)."""
    book_ok = focus_n - 1 >= BOOK_KIND_MIN_PRIOR
    return [k for k in SHAPE_KINDS if book_ok or k not in BOOK_KINDS]


def parse_shape_rows(
    raw: str, *, focus: Chapter, kinds: list[str]
) -> tuple[list[dict[str, Any]], int]:
    """Parse, ground and cap model rows. Returns ``(rows, dropped)``.

    A row is dropped when its kind is not asked, or when its quote is not
    in the focus chapter (book kinds may have no quote).
    """
    data = extract_json_array(raw.strip())
    if not isinstance(data, list):
        return [], 0
    index = QuoteIndex([focus])
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, int]] = set()
    dropped = 0
    for item in data:
        if not isinstance(item, dict):
            continue
        kind = str(item.get("kind") or "").strip()
        if kind not in kinds:
            dropped += 1
            continue
        quote = str(item.get("quote") or "").strip()
        location = index.locate(quote) if quote else None
        if location is None and (quote or kind not in BOOK_KINDS):
            dropped += 1
            continue
        key = (kind, location.char_start if location else -1)
        if key in seen:
            continue
        seen.add(key)
        _, default_msg, default_fix = SHAPE_KINDS[kind]
        span = ""
        if location is not None:
            span = (index.text(focus.chapter_number) or "")[location.char_start : location.char_end]
        message = str(item.get("message") or "").strip() or default_msg
        row: dict[str, Any] = {
            "kind": kind,
            "severity": SHAPE_SEVERITY,
            "chapter": focus.chapter_number,
            "quote": span,
            "message": message,
            # Autonomicon's ledger renders ``summary``; same text as message.
            "summary": message,
            "suggested_fix": str(item.get("suggested_fix") or "").strip() or default_fix,
            "location": location.as_dict() if location else None,
        }
        row["id"] = finding_id(
            {
                "dimension": f"shape.{kind}",
                "location": row["location"],
                "chapter_ref": str(focus.chapter_number),
                "evidence": kind,
            }
        )
        rows.append(row)
    return rows[:SHAPE_CAP], dropped + max(0, len(rows) - SHAPE_CAP)


async def run_shape_watch(
    *,
    focus: Chapter,
    prior_facts: list[ChapterFact],
    llm: BaseChatModel,
    genre: str | None,
    seed_meta: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[str]]:
    """Run the shape watch for *focus*. Returns ``(rows, warnings)``. Fail-soft."""
    kinds = asked_kinds(focus.chapter_number)
    has_book = any(k in BOOK_KINDS for k in kinds)
    system = _SYSTEM.format(
        genre_preamble=get_genre_preamble(genre),
        author_intent=build_author_intent_block(seed_meta) or "",
        kinds=_kind_lines(kinds),
        cap=SHAPE_CAP,
        quote_rule=(
            "; may be empty only for anti_tidy_single_track or anti_tidy_flat_escalation"
            if has_book
            else ""
        ),
    )
    chapter_block = whole_chapter_block(
        [
            {
                "chapter_number": focus.chapter_number,
                "title": focus.title,
                "content": focus.content,
            }
        ]
    )
    prior = format_fact_sheets(prior_facts) if has_book else ""
    user = (
        f"Focus chapter: {focus.chapter_number}\n\n"
        + (f"## Prior chapters (fact sheets)\n{prior or '(none)'}\n\n" if has_book else "")
        + f"## Focus chapter\n{chapter_block}"
    )
    try:
        response = await llm.ainvoke([SystemMessage(content=system), HumanMessage(content=user)])
    except Exception as exc:  # noqa: BLE001 - advisory watch, fail-soft
        logger.warning("Shape watch LLM failed: %s", exc)
        return [], [f"shape watch: model call failed ({type(exc).__name__}); no rows"]
    rows, dropped = parse_shape_rows(message_text(response.content), focus=focus, kinds=kinds)
    warnings = [f"shape watch: dropped {dropped} ungrounded row(s)"] if dropped else []
    return rows, warnings


__all__ = [
    "BOOK_KINDS",
    "SHAPE_CAP",
    "SHAPE_KINDS",
    "SHAPE_SEVERITY",
    "asked_kinds",
    "parse_shape_rows",
    "run_shape_watch",
]
