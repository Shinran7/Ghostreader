"""Adapt TypeSafe answers into AgentFinding / dimension_ratings."""

from __future__ import annotations

import json
from typing import Any

from ghostreader.graph import AgentFinding
from ghostreader.typesafe.questions import (
    CONSISTENCY_DIMENSIONS,
    NARRATIVE_DIMENSIONS,
    PROSE_DIMENSIONS,
    SEVERITY_CRITERIA,
)
from ghostreader.typesafe.routing import noul_band, prioritization_sort_key

_VALID_SEVERITIES = frozenset({"strength", "neutral", "concern"})
_NO_CONTRADICTION_NOTE = "No contradiction detected"


def _template_summary(dimension: str, severity: str, *, low_confidence: bool = False) -> str:
    label = SEVERITY_CRITERIA.get(severity, severity)
    base = f"{dimension}: {label}"
    if low_confidence:
        return f"{base} (low confidence)"
    return base


def serialize_choice_answers(response: Any) -> dict[str, Any]:
    """Serialize Choice answers for raw_response debug blobs."""
    out: dict[str, Any] = {}
    choices = getattr(response, "choices", {}) or {}
    for qid, ans in choices.items():
        out[qid] = {
            "type": "choice",
            "choice": getattr(ans, "choice", None),
            "confidence": getattr(ans, "confidence", None),
            "probabilities": dict(getattr(ans, "probabilities", {}) or {}),
        }
    return out


def serialize_noul_answers(response: Any) -> dict[str, Any]:
    """Serialize Noul answers for raw_response debug blobs."""
    out: dict[str, Any] = {}
    nouls = getattr(response, "nouls", {}) or {}
    for qid, ans in nouls.items():
        out[qid] = {
            "type": "noul",
            "noul": getattr(ans, "noul", None),
        }
    return out


def choice_to_finding(
    dimension: str,
    answer: Any,
    *,
    confidence_floor: float = 0.55,
) -> AgentFinding:
    """Build one skeleton finding from a Choice answer."""
    raw_choice = str(getattr(answer, "choice", "neutral") or "neutral")
    severity = raw_choice if raw_choice in _VALID_SEVERITIES else "neutral"
    confidence = float(getattr(answer, "confidence", 0.0) or 0.0)
    low = confidence < confidence_floor
    finding: AgentFinding = {
        "dimension": dimension,
        "severity": severity,
        "summary": _template_summary(dimension, severity, low_confidence=low),
        "evidence": "",
        "chapter_ref": "",
        "_certainty": confidence,  # type: ignore[typeddict-unknown-key]
    }
    return finding


def choices_to_findings(
    response: Any,
    dimensions: tuple[str, ...],
    *,
    confidence_floor: float = 0.55,
) -> tuple[list[AgentFinding], dict[str, dict[str, str]]]:
    """Map Choice answers → findings + dimension_ratings for *dimensions*."""
    choices = getattr(response, "choices", {}) or {}
    findings: list[AgentFinding] = []
    ratings: dict[str, dict[str, str]] = {}
    for dim in dimensions:
        ans = choices.get(dim)
        if ans is None:
            ratings[dim] = {"severity": "neutral", "note": "No TypeSafe answer"}
            continue
        finding = choice_to_finding(dim, ans, confidence_floor=confidence_floor)
        findings.append(finding)
        ratings[dim] = {
            "severity": finding["severity"],
            "note": finding.get("summary", ""),
        }
    return findings, ratings


def consistency_from_nouls(
    response: Any,
    *,
    positive_threshold: float = 0.65,
) -> tuple[list[AgentFinding], dict[str, dict[str, str]], list[str], list[str]]:
    """Map Noul gates → findings, ratings, enrich dims, mid-band dims.

    Clear-negative → rating ``neutral`` (no finding).
    Positive → concern finding (enrich later).
    Mid → listed for LLM tie-break (no finding yet).
    """
    nouls = getattr(response, "nouls", {}) or {}
    findings: list[AgentFinding] = []
    ratings: dict[str, dict[str, str]] = {}
    enrich_dims: list[str] = []
    mid_dims: list[str] = []

    for dim in CONSISTENCY_DIMENSIONS:
        ans = nouls.get(dim)
        if ans is None:
            ratings[dim] = {"severity": "neutral", "note": _NO_CONTRADICTION_NOTE}
            continue
        value = float(getattr(ans, "noul", 0.0) or 0.0)
        band = noul_band(value, positive_threshold=positive_threshold)
        if band == "positive":
            finding: AgentFinding = {
                "dimension": dim,
                "severity": "concern",
                "summary": _template_summary(dim, "concern"),
                "evidence": "",
                "counter_evidence": "",
                "chapter_ref": "",
                "_certainty": value,  # type: ignore[typeddict-unknown-key]
            }
            findings.append(finding)
            ratings[dim] = {"severity": "concern", "note": finding["summary"]}
            enrich_dims.append(dim)
        elif band == "mid":
            mid_dims.append(dim)
            # Rating filled after tie-break; provisional neutral until then.
            ratings[dim] = {
                "severity": "neutral",
                "note": "Pending LLM tie-break",
            }
        else:
            ratings[dim] = {
                "severity": "neutral",
                "note": _NO_CONTRADICTION_NOTE,
            }

    return findings, ratings, enrich_dims, mid_dims


def ratings_from_findings(
    findings: list[AgentFinding],
    dimensions: tuple[str, ...],
) -> dict[str, dict[str, str]]:
    """Build dimension_ratings from findings (first hit wins per dim)."""
    by_dim = {f.get("dimension"): f for f in findings if f.get("dimension")}
    ratings: dict[str, dict[str, str]] = {}
    for dim in dimensions:
        f = by_dim.get(dim)
        if f is None:
            ratings[dim] = {"severity": "neutral", "note": ""}
        else:
            ratings[dim] = {
                "severity": str(f.get("severity", "neutral")),
                "note": str(f.get("summary", "")),
            }
    return ratings


def prioritize_findings(findings: list[AgentFinding]) -> list[dict[str, Any]]:
    """Sort findings and assign rank; strip internal ``_certainty``."""
    sorted_findings = sorted(findings, key=prioritization_sort_key)
    out: list[dict[str, Any]] = []
    for i, f in enumerate(sorted_findings, 1):
        item = {
            "rank": i,
            "dimension": f.get("dimension", ""),
            "severity": f.get("severity", "neutral"),
            "summary": f.get("summary", ""),
            "evidence": f.get("evidence", ""),
            "counter_evidence": f.get("counter_evidence", ""),
            "chapter_ref": f.get("chapter_ref", ""),
        }
        kind = f.get("signal_kind")
        if kind:
            item["signal_kind"] = str(kind)
        out.append(item)
    return out


def merge_dimension_ratings(
    *rating_maps: dict[str, dict[str, str]] | None,
) -> dict[str, dict[str, str]]:
    """Merge rating maps left-to-right (later keys overwrite)."""
    merged: dict[str, dict[str, str]] = {}
    for m in rating_maps:
        if m:
            merged.update(m)
    return merged


def parse_ratings_from_raw(raw_response: str) -> dict[str, dict[str, str]]:
    """Extract dimension_ratings from a TypeSafe agent raw_response JSON blob."""
    try:
        data = json.loads(raw_response)
    except (json.JSONDecodeError, TypeError):
        return {}
    if not isinstance(data, dict):
        return {}
    ratings = data.get("dimension_ratings", {})
    if not isinstance(ratings, dict):
        return {}
    out: dict[str, dict[str, str]] = {}
    for dim, info in ratings.items():
        if isinstance(info, dict):
            out[str(dim)] = {
                "severity": str(info.get("severity", "neutral")),
                "note": str(info.get("note", "")),
            }
    return out


def build_typesafe_raw_response(
    *,
    answers: dict[str, Any],
    dimension_ratings: dict[str, dict[str, str]],
    enrich_raw: dict[str, Any] | None = None,
    stats: dict[str, Any] | None = None,
) -> str:
    """JSON debug blob for AgentOutput.raw_response on TypeSafe paths."""
    payload = {
        "typesafe_answers": answers,
        "dimension_ratings": dimension_ratings,
        "enrich_raw": enrich_raw or {},
        "stats": stats or {},
    }
    return json.dumps(payload)


# Re-export dimension tuples for synthesis convenience
ALL_CHOICE_DIMENSIONS = PROSE_DIMENSIONS + NARRATIVE_DIMENSIONS
