"""Narrow LLM enrich for TypeSafe skeleton findings (quotes/summary only)."""

from __future__ import annotations

import json
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from ghostreader.graph import AgentFinding
from ghostreader.llm import message_text

_SIGNAL_KINDS = frozenset(
    {
        "fact_contradiction",
        "wrong_place",
        "tone_understatement",
        "other",
    }
)

_ENRICH_SYSTEM = """You enrich literary-analysis findings with grounded quotes.
Severity for each dimension is FIXED and must not be changed.
Return ONLY a JSON object mapping dimension id → object with keys:
  summary (str), evidence (str), chapter_ref (str)
Optionally include counter_evidence (str) when asked for consistency.
Evidence must be DIRECT quotes from the manuscript, chapter-prefixed
(e.g. "Ch 3: '…'"). No markdown fencing."""

_ENRICH_SYSTEM_CONTINUITY = """You enrich literary-analysis findings with grounded quotes.
Severity for each dimension is FIXED and must not be changed.
Return ONLY a JSON object mapping dimension id → object with keys:
  summary (str), evidence (str), chapter_ref (str), counter_evidence (str),
  signal_kind (str)
signal_kind must be one of:
  fact_contradiction — two stated facts conflict
  wrong_place — character/object cannot be where the text puts them
  tone_understatement — framing/tone understates prior events; presence OK
  other — does not fit above
Countdown / remaining-days guidance: if summarizing countdown issues, name
the non-monotonic pair explicitly (e.g. "Ch X: 24 → Ch Y: 25"). Do not list
later drops as proof of the same defect unless sheets show no elapsed time.
Later lower countdown values after plausible elapsed narrative time are not the same failure as the non-monotonic bump.
Evidence must be DIRECT quotes from the manuscript, chapter-prefixed
(e.g. "Ch 3: '…'"). No markdown fencing."""

_CONTINUITY_COUNTDOWN_ADDENDUM = (
    "Countdown guidance: name the non-monotonic pair explicitly "
    '(e.g. "Ch X: 24 → Ch Y: 25"). Do not list later drops as proof of the '
    "same defect unless sheets show no elapsed time. Later lower countdown "
    "values after plausible elapsed narrative time are not the same failure "
    "as the non-monotonic bump."
)


def normalize_signal_kind(raw: Any) -> str | None:
    """Map enrich/LLM signal_kind to the closed enum; unknown → ``other``."""
    if raw is None:
        return None
    text = str(raw).strip().lower()
    if not text:
        return None
    if text in _SIGNAL_KINDS:
        return text
    return "other"


def _strip_fence(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [ln for ln in lines if not ln.strip().startswith("```")]
        text = "\n".join(lines)
    return text.strip()


def _parse_enrich_map(raw: str) -> dict[str, dict[str, Any]]:
    text = _strip_fence(raw)
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return {
                str(k): v for k, v in data.items() if isinstance(v, dict)
            }
    except (json.JSONDecodeError, TypeError):
        pass
    return {}


async def enrich_findings_batch(
    llm: BaseChatModel,
    findings: list[AgentFinding],
    dimensions: list[str],
    *,
    context_block: str,
    include_counter_evidence: bool = False,
    ask_signal_kind: bool = False,
) -> tuple[list[AgentFinding], dict[str, str | None], int]:
    """One LLM call to enrich selected dimensions. Severity stays immutable.

    Returns (updated findings, enrich_raw map, parse_failure_count).
    """
    if not dimensions:
        return findings, {}, 0

    by_dim = {f.get("dimension"): f for f in findings}
    lines = []
    for dim in dimensions:
        f = by_dim.get(dim)
        if f is None:
            continue
        lines.append(
            f"- {dim}: severity={f.get('severity')} "
            f"(immutable); current summary={f.get('summary', '')}"
        )

    continuity = include_counter_evidence or ask_signal_kind
    if continuity and ask_signal_kind:
        fields = (
            "summary, evidence, counter_evidence, chapter_ref, signal_kind"
        )
        system = _ENRICH_SYSTEM_CONTINUITY
    elif include_counter_evidence:
        fields = "summary, evidence, chapter_ref, counter_evidence"
        system = _ENRICH_SYSTEM
    else:
        fields = "summary, evidence, chapter_ref"
        system = _ENRICH_SYSTEM

    user = (
        f"Enrich these dimensions with quotes. Fields per dimension: {fields}.\n"
        f"Do not change severity.\n"
    )
    if ask_signal_kind:
        user += (
            "Include signal_kind for each dimension "
            "(fact_contradiction|wrong_place|tone_understatement|other).\n"
            f"{_CONTINUITY_COUNTDOWN_ADDENDUM}\n"
        )
    user += (
        f"\n## Dimensions\n" + "\n".join(lines) + "\n\n"
        f"## Context\n{context_block}"
    )

    response = await llm.ainvoke(
        [SystemMessage(content=system), HumanMessage(content=user)]
    )
    raw_text = message_text(response.content)
    parsed = _parse_enrich_map(raw_text)
    enrich_raw: dict[str, str | None] = {d: None for d in dimensions}
    failures = 0

    updated: list[AgentFinding] = []
    for f in findings:
        dim = f.get("dimension", "")
        if dim not in dimensions:
            updated.append(f)
            continue
        entry = parsed.get(dim)
        if entry is None:
            failures += 1
            enrich_raw[dim] = None
            updated.append(f)
            continue
        enrich_raw[dim] = raw_text
        new_f: AgentFinding = dict(f)  # type: ignore[assignment]
        if entry.get("summary"):
            new_f["summary"] = str(entry["summary"])
        if entry.get("evidence") is not None:
            new_f["evidence"] = str(entry.get("evidence", ""))
        if entry.get("chapter_ref") is not None:
            new_f["chapter_ref"] = str(entry.get("chapter_ref", ""))
        if include_counter_evidence and entry.get("counter_evidence") is not None:
            new_f["counter_evidence"] = str(entry.get("counter_evidence", ""))
        if ask_signal_kind and entry.get("signal_kind") is not None:
            kind = normalize_signal_kind(entry.get("signal_kind"))
            if kind is not None:
                new_f["signal_kind"] = kind
        # severity intentionally untouched
        updated.append(new_f)

    # If batch parse wholly failed, mark all dims as failure once
    if not parsed and dimensions:
        failures = len(dimensions)
        for d in dimensions:
            enrich_raw[d] = None

    return updated, enrich_raw, failures


_TIEBREAK_SYSTEM = """You decide whether a mid-confidence consistency gate reflects
a real contradiction in the manuscript/fact sheets.
Return ONLY a JSON object mapping dimension id → either:
  {"contradiction": false}
or
  {"contradiction": true, "summary": str, "evidence": str,
   "counter_evidence": str, "chapter_ref": str}
Evidence must be direct quotes, chapter-prefixed. No markdown fencing."""

_TIEBREAK_SYSTEM_SIGNAL = """You decide whether a mid-confidence consistency gate reflects
a real contradiction in the manuscript/fact sheets.
Return ONLY a JSON object mapping dimension id → either:
  {"contradiction": false}
or
  {"contradiction": true, "summary": str, "evidence": str,
   "counter_evidence": str, "chapter_ref": str, "signal_kind": str}
signal_kind must be one of: fact_contradiction, wrong_place,
tone_understatement, other.
Countdown guidance: name the non-monotonic pair explicitly when relevant.
Later lower countdown values after plausible elapsed narrative time are not the same failure as the non-monotonic bump.
Evidence must be direct quotes, chapter-prefixed. No markdown fencing."""


async def consistency_tiebreak_batch(
    llm: BaseChatModel,
    dimensions: list[str],
    *,
    context_block: str,
    ask_signal_kind: bool = False,
) -> tuple[list[AgentFinding], dict[str, dict[str, str]], dict[str, str | None], int]:
    """LLM tie-break for mid-band Noul dims. Returns findings, ratings, raw, failures."""
    findings: list[AgentFinding] = []
    ratings: dict[str, dict[str, str]] = {}
    enrich_raw: dict[str, str | None] = {}
    failures = 0

    if not dimensions:
        return findings, ratings, enrich_raw, failures

    user = (
        "For each dimension, decide if there is a real contradiction.\n"
    )
    if ask_signal_kind:
        user += (
            "When contradiction is true, include signal_kind "
            "(fact_contradiction|wrong_place|tone_understatement|other).\n"
            f"{_CONTINUITY_COUNTDOWN_ADDENDUM}\n"
        )
    user += (
        "\n## Dimensions\n" + "\n".join(f"- {d}" for d in dimensions) + "\n\n"
        f"## Context\n{context_block}"
    )

    system = _TIEBREAK_SYSTEM_SIGNAL if ask_signal_kind else _TIEBREAK_SYSTEM
    response = await llm.ainvoke(
        [SystemMessage(content=system), HumanMessage(content=user)]
    )
    raw_text = message_text(response.content)
    parsed = _parse_enrich_map(raw_text)

    for dim in dimensions:
        entry = parsed.get(dim)
        enrich_raw[dim] = raw_text if entry else None
        if entry is None:
            failures += 1
            ratings[dim] = {
                "severity": "neutral",
                "note": "No contradiction detected",
            }
            continue
        if entry.get("contradiction") in (True, "true", "True", 1):
            finding: AgentFinding = {
                "dimension": dim,
                "severity": "concern",
                "summary": str(entry.get("summary", f"{dim}: contradiction")),
                "evidence": str(entry.get("evidence", "")),
                "counter_evidence": str(entry.get("counter_evidence", "")),
                "chapter_ref": str(entry.get("chapter_ref", "")),
                "_certainty": 0.5,  # type: ignore[typeddict-unknown-key]
            }
            if ask_signal_kind and entry.get("signal_kind") is not None:
                kind = normalize_signal_kind(entry.get("signal_kind"))
                if kind is not None:
                    finding["signal_kind"] = kind
            findings.append(finding)
            ratings[dim] = {
                "severity": "concern",
                "note": finding["summary"],
            }
        else:
            ratings[dim] = {
                "severity": "neutral",
                "note": "No contradiction detected",
            }

    if not parsed:
        failures = len(dimensions)
        for dim in dimensions:
            ratings[dim] = {
                "severity": "neutral",
                "note": "No contradiction detected",
            }
            enrich_raw[dim] = None

    return findings, ratings, enrich_raw, failures
