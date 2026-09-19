"""Narrow LLM enrich for TypeSafe skeleton findings (quotes/summary only)."""

from __future__ import annotations

import json
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from ghostreader.graph import AgentFinding

_ENRICH_SYSTEM = """You enrich literary-analysis findings with grounded quotes.
Severity for each dimension is FIXED and must not be changed.
Return ONLY a JSON object mapping dimension id → object with keys:
  summary (str), evidence (str), chapter_ref (str)
Optionally include counter_evidence (str) when asked for consistency.
Evidence must be DIRECT quotes from the manuscript, chapter-prefixed
(e.g. "Ch 3: '…'"). No markdown fencing."""


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

    fields = "summary, evidence, chapter_ref"
    if include_counter_evidence:
        fields += ", counter_evidence"

    user = (
        f"Enrich these dimensions with quotes. Fields per dimension: {fields}.\n"
        f"Do not change severity.\n\n"
        f"## Dimensions\n" + "\n".join(lines) + "\n\n"
        f"## Context\n{context_block}"
    )

    response = await llm.ainvoke(
        [SystemMessage(content=_ENRICH_SYSTEM), HumanMessage(content=user)]
    )
    raw_text = str(response.content).strip()
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


async def consistency_tiebreak_batch(
    llm: BaseChatModel,
    dimensions: list[str],
    *,
    context_block: str,
) -> tuple[list[AgentFinding], dict[str, dict[str, str]], dict[str, str | None], int]:
    """LLM tie-break for mid-band Noul dims. Returns findings, ratings, raw, failures."""
    findings: list[AgentFinding] = []
    ratings: dict[str, dict[str, str]] = {}
    enrich_raw: dict[str, str | None] = {}
    failures = 0

    if not dimensions:
        return findings, ratings, enrich_raw, failures

    user = (
        "For each dimension, decide if there is a real contradiction.\n\n"
        f"## Dimensions\n" + "\n".join(f"- {d}" for d in dimensions) + "\n\n"
        f"## Context\n{context_block}"
    )

    response = await llm.ainvoke(
        [SystemMessage(content=_TIEBREAK_SYSTEM), HumanMessage(content=user)]
    )
    raw_text = str(response.content).strip()
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
