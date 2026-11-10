"""Check a chapter's prose against Canon as of the chapter before (#16).

One LLM call per chapter: the Canon state block (id-tagged entries) plus the
chapter's full prose. Each finding quotes the chapter and cites the Canon
entry it breaks by id. Code fills the Canon side of the finding from that
entry, so ``counter_evidence`` is exact Canon text, marked
``counter_source: "canon"`` and never checked against the manuscript.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from ghostreader.canon import CanonState, format_canon_block, load_canon_state

logger = logging.getLogger(__name__)

CANON_SOURCE = "canon"

_CANON_PROMPT = """{genre_preamble}
{author_intent}
You are the Continuity Checker for a novel in progress. You get the STORY STATE
recorded before Chapter {n} (numbered entries such as [C2], [P1], [T3]) and the
full text of Chapter {n}.

Find places where Chapter {n} CONTRADICTS the recorded state. Report:
- A character acts against their recorded status: a dead character speaks or
  acts in the present (memories, ghosts, flashbacks and mentions are fine).
- An injury or physical condition is ignored: a character uses a limb recorded
  as broken, or shows no trace of a recent wound, with no healing time or
  treatment shown. Non-mention alone is not a contradiction; acting against
  the state is.
- An item appears where the state places it elsewhere, or is used after it was
  lost, destroyed or given away, with no recovery shown.
- Time runs backward or jumps against the recorded end time of the previous
  chapter without a scene break, flashback or stated time skip.
- A character knows a secret the state says they do not know, with no scene
  where they learn it.
- A fixed story fact or world rule is broken (names, relationships, places,
  rules of the world).
A chapter may change the state (a character dies, heals, moves, learns). Report
it only when the chapter gives no event that explains the change.

OUTPUT FORMAT: a JSON array. Each finding:
- "dimension": "consistency.plot_holes" | "consistency.timeline" |
  "consistency.character" | "consistency.unresolved"
- "severity": "concern" for a contradiction; "neutral" when unsure
- "summary": one line
- "evidence": "Ch {n}: '<verbatim passage from Chapter {n}>'" — copy the words
  exactly; they are checked against the text
- "canon_ref": the id of the state entry it contradicts, e.g. "P1"
- "chapter_ref": "{n}"
- "signal_kind" (optional): "fact_contradiction" | "wrong_place" | "other"
For a contradiction inside Chapter {n} itself, use "counter_evidence":
"Ch {n}: '<second verbatim passage>'" instead of "canon_ref".

Return [] when Chapter {n} is consistent with the state.
Return ONLY the JSON array, no markdown fencing or commentary.
"""


def _user_message(state: CanonState, chapter_n: int, title: str, content: str) -> str:
    return (
        f"## Story state before Chapter {chapter_n}\n{format_canon_block(state)}\n\n"
        f"## Chapter {chapter_n}: {title}\n{content}"
    )


def apply_canon_refs(
    findings: list[dict[str, Any]],
    refs: list[Any],
    state: CanonState,
    chapter_n: int,
) -> list[dict[str, Any]]:
    """Fill the Canon side of each finding from the cited entry id."""
    entries = state.by_id()
    out: list[dict[str, Any]] = []
    for f, ref in zip(findings, refs, strict=False):
        f = dict(f)
        rid = str(ref or "").strip().strip("[]").upper()
        if rid:
            entry = entries.get(rid)
            if entry is None:
                # Cited an id that is not in the state: no Canon side, so the
                # finding cannot be grounded.
                f["counter_evidence"] = ""
                f["canon_ref"] = {"id": rid, "kind": None, "chapter": None, "file": ""}
            else:
                f["counter_evidence"] = entry.as_counter_evidence()
                f["counter_source"] = CANON_SOURCE
                f["canon_ref"] = entry.as_ref()
                f["chapter_ref"] = (
                    f"{entry.chapter} vs {chapter_n}" if entry.chapter else f"Canon vs {chapter_n}"
                )
        out.append(f)
    out.extend(dict(f) for f in findings[len(refs) :])
    return out


def _parse(raw: str, state: CanonState, chapter_n: int) -> list[dict[str, Any]]:
    from ghostreader.agents.consistency_checker import _parse_findings
    from ghostreader.llm import extract_json_array

    findings = [dict(f) for f in _parse_findings(raw)]
    data = extract_json_array(raw.strip())
    refs = (
        [d.get("canon_ref") for d in data if isinstance(d, dict)] if isinstance(data, list) else []
    )
    return apply_canon_refs(findings, refs, state, chapter_n)


async def check_chapter_against_canon(
    *,
    chapter_n: int,
    title: str,
    content: str,
    state: CanonState,
    llm: BaseChatModel,
    genre: str | None = None,
    seed_meta: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """One LLM call: chapter prose vs Canon state. Returns finding dicts."""
    from ghostreader.agents.genre_prompts import get_genre_preamble
    from ghostreader.llm import message_text
    from ghostreader.seed import build_author_intent_block

    system = _CANON_PROMPT.format(
        genre_preamble=get_genre_preamble(genre),
        author_intent=build_author_intent_block(seed_meta or {}),
        n=chapter_n,
    )
    response = await llm.ainvoke(
        [
            SystemMessage(content=system),
            HumanMessage(content=_user_message(state, chapter_n, title, content)),
        ]
    )
    return _parse(message_text(response.content), state, chapter_n)


async def check_book_against_canon(
    chapters: list[dict[str, Any]],
    canon_dir: Path,
    llm: BaseChatModel,
    *,
    genre: str | None = None,
    seed_meta: dict[str, Any] | None = None,
    concurrency: int = 4,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Analyze: each chapter against Canon as of the chapter before it.

    Returns ``(findings, stats)``. A chapter whose reply does not parse is
    counted in ``stats["failed"]`` and adds no findings.
    """
    from ghostreader.companion.continuity import CONSISTENCY_PARSE_FAILED_DIM

    sem = asyncio.Semaphore(max(1, concurrency))
    stats = {"chapters": 0, "checkpoints": 0, "failed": 0, "skipped_empty": 0}

    async def one(ch: dict[str, Any]) -> list[dict[str, Any]]:
        n = int(ch.get("chapter_number") or 0)
        state = load_canon_state(canon_dir, n)
        if not state:
            stats["skipped_empty"] += 1
            return []
        stats["chapters"] += 1
        stats["checkpoints"] += int(state.from_checkpoint)
        async with sem:
            try:
                rows = await check_chapter_against_canon(
                    chapter_n=n,
                    title=str(ch.get("title") or f"Chapter {n}"),
                    content=str(ch.get("content") or ""),
                    state=state,
                    llm=llm,
                    genre=genre,
                    seed_meta=seed_meta,
                )
            except Exception as exc:  # noqa: BLE001 — one chapter must not sink the book
                logger.warning("Canon check failed for chapter %s: %s", n, exc)
                stats["failed"] += 1
                return []
        if any(r.get("dimension") == CONSISTENCY_PARSE_FAILED_DIM for r in rows):
            stats["failed"] += 1
            return [r for r in rows if r.get("dimension") != CONSISTENCY_PARSE_FAILED_DIM]
        return rows

    results = await asyncio.gather(*(one(c) for c in chapters))
    return [f for rows in results for f in rows], stats


__all__ = [
    "CANON_SOURCE",
    "apply_canon_refs",
    "check_book_against_canon",
    "check_chapter_against_canon",
]
