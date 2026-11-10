"""Fetch verbatim quotes for continuity concerns whose quotes did not verify (#17).

The companion continuity pass often works from fact sheets, so its evidence is
a paraphrase. Before such a concern can gate, one bounded LLM call per concern
asks for the exact supporting passages from the cited chapters' full text.
The returned quotes are verified again; a concern stays unverified (and so
ungrounded) when the model finds no support or invents the quotes.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from ghostreader.companion.continuity import COMPANION_GATE_DIMS, cited_chapters
from ghostreader.llm import extract_json_object, message_text
from ghostreader.quotes import QuoteIndex, canon_counter, verify_finding

logger = logging.getLogger(__name__)

MAX_CHAPTERS_PER_CALL = 3

_SYSTEM = """You check a continuity claim against the manuscript text you are given.
Copy the exact words from the text. Do not paraphrase, fix, or shorten inside
a quote. Return ONLY a JSON object:
  {"supported": bool,
   "evidence": "Ch N: '<verbatim passage, one sentence or less>'",
   "counter_evidence": "Ch M: '<verbatim passage that conflicts with it>'"}
Use "" for counter_evidence when the claim has only one side (for example an
unresolved thread). Use "supported": false, with empty strings, when the text
does not show the issue. No markdown fencing."""


def _user_message(finding: dict[str, Any], texts: Sequence[tuple[int, str]]) -> str:
    chapters = "\n\n".join(f"--- Chapter {n} ---\n{t}" for n, t in texts)
    return (
        f"Claim: {finding.get('summary') or ''}\n"
        f"Evidence as stated: {finding.get('evidence') or ''}\n"
        f"Counter-evidence as stated: {finding.get('counter_evidence') or ''}\n\n"
        f"## Manuscript\n{chapters}"
    )


def needs_recovery(finding: dict[str, Any]) -> bool:
    return (
        not canon_counter(finding)
        and finding.get("dimension") in COMPANION_GATE_DIMS
        and finding.get("severity") == "concern"
        and finding.get("quote_verified") is False
    )


def needs_recovery_any_consistency(finding: dict[str, Any]) -> bool:
    """Analyze: every consistency concern, not only the companion gate dims."""
    return (
        not canon_counter(finding)
        and str(finding.get("dimension") or "").startswith("consistency.")
        and finding.get("severity") == "concern"
        and finding.get("quote_verified") is False
    )


async def recover_continuity_quotes(
    findings: list[dict[str, Any]],
    index: QuoteIndex,
    llm: BaseChatModel,
    *,
    chapter_n: int | None,
    max_calls: int = 5,
    select: Callable[[dict[str, Any]], bool] = needs_recovery,
) -> tuple[list[dict[str, Any]], int, int]:
    """Return ``(findings, recovered_count, calls_made)``.

    ``chapter_n`` is the companion focus chapter (always sent first); analyze
    passes ``None`` and sends the cited chapters only.
    """
    out: list[dict[str, Any]] = []
    recovered = 0
    calls = 0
    for f in findings:
        if calls >= max_calls or not select(f):
            out.append(f)
            continue
        cited = [c for c in sorted(cited_chapters(f)) if index.text(c) is not None]
        if chapter_n is not None:
            if chapter_n not in cited and index.text(chapter_n) is not None:
                cited = [chapter_n, *cited]
            # Keep chapter N, then the nearest cited chapters.
            focus = chapter_n
            cited = sorted(cited, key=lambda c: (c != focus, abs(focus - c)))
        texts = [(c, index.text(c) or "") for c in cited[:MAX_CHAPTERS_PER_CALL]]
        if not texts:
            out.append(f)
            continue
        calls += 1
        try:
            response = await llm.ainvoke(
                [SystemMessage(content=_SYSTEM), HumanMessage(content=_user_message(f, texts))]
            )
            data = extract_json_object(message_text(response.content)) or {}
        except Exception as exc:  # noqa: BLE001
            logger.warning("quote recovery failed: %s", exc)
            out.append(f)
            continue
        if not data.get("supported") or not str(data.get("evidence") or "").strip():
            out.append(f)
            continue
        candidate = dict(f)
        candidate["evidence_claim"] = f.get("evidence") or ""
        candidate["counter_evidence_claim"] = f.get("counter_evidence") or ""
        candidate["evidence"] = str(data.get("evidence") or "")
        candidate["counter_evidence"] = str(data.get("counter_evidence") or "")
        checked = verify_finding(
            candidate, index, prefer=[c for c, _ in texts], demote=False
        )
        if checked.get("quote_verified"):
            checked["quote_recovered"] = True
            recovered += 1
            out.append(checked)
        else:
            out.append(f)
    return out, recovered, calls


__all__ = [
    "needs_recovery",
    "needs_recovery_any_consistency",
    "recover_continuity_quotes",
]
