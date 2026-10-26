"""Companion projection for voice-vs-card heuristic findings (#11)."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from ghostreader.analyzers.voice_card_detector import detect_voice_card_issues
from ghostreader.companion.voice_card_constants import VOICE_CARD_FINDINGS_CAP
from ghostreader.companion.voice_cards import VoiceCard

_SEVERITY_RANK = {"high": 0, "moderate": 1, "low": 2}
_ALLOWED_KINDS = frozenset({"card_mismatch", "card_collapse"})
_ALLOWED_SEVERITIES = frozenset({"high", "moderate", "low"})


def voice_card_finding_to_dict(row: dict[str, Any]) -> dict[str, Any]:
    """Normalize one detector/export row for brief payload."""
    kind_raw = str(row.get("kind") or "")
    kind = kind_raw if kind_raw in _ALLOWED_KINDS else "card_mismatch"
    sev_raw = str(row.get("severity") or "")
    severity = sev_raw if sev_raw in _ALLOWED_SEVERITIES else "low"

    speaker = str(row.get("speaker") or "")
    speaker_b_raw = row.get("speaker_b")
    speaker_b = str(speaker_b_raw) if speaker_b_raw else None

    metrics_raw = row.get("metrics")
    metrics: dict[str, float] | None
    if isinstance(metrics_raw, dict):
        metrics = {
            "line_count": float(metrics_raw.get("line_count", 0)),
            "avg_words": float(metrics_raw.get("avg_words", 0)),
            "contraction_rate": float(metrics_raw.get("contraction_rate", 0)),
            "fragment_rate": float(metrics_raw.get("fragment_rate", 0)),
            "interruption_rate": float(metrics_raw.get("interruption_rate", 0)),
        }
    else:
        metrics = None

    chapters_raw = row.get("chapters") or []
    chapters = [int(c) for c in chapters_raw] if isinstance(chapters_raw, list) else []

    quote = row.get("quote")
    card_excerpt = row.get("card_excerpt")
    normalized_key = row.get("normalized_key")

    return {
        "kind": kind,
        "severity": severity,
        "summary": str(row.get("summary") or ""),
        "speaker": speaker,
        "speaker_b": speaker_b,
        "quote": str(quote) if quote else None,
        "card_excerpt": str(card_excerpt) if card_excerpt else None,
        "metrics": metrics,
        "chapters": chapters,
        "chapter": int(row.get("chapter") or 0),
        "normalized_key": str(normalized_key) if normalized_key else None,
    }


def companion_voice_card_to_dicts(
    rows: Sequence[dict[str, Any]],
    *,
    max_entries: int = VOICE_CARD_FINDINGS_CAP,
) -> list[dict[str, Any]]:
    """Cap and sort voice-card findings for companion brief export."""

    def _sort_key(row: dict[str, Any]) -> tuple[int, int, str]:
        sev = _SEVERITY_RANK.get(str(row.get("severity", "")), 99)
        kind_rank = 0 if row.get("kind") == "card_collapse" else 1
        return (kind_rank, sev, str(row.get("normalized_key") or ""))

    normalized = [voice_card_finding_to_dict(r) for r in rows]
    normalized.sort(key=_sort_key)
    limit = max(0, int(max_entries))
    return normalized[:limit]


def voice_card_findings_for_chapters(
    chapters: Sequence[tuple[int, str]],
    cards: Sequence[VoiceCard],
    *,
    focus_n: int = 0,
    max_entries: int = VOICE_CARD_FINDINGS_CAP,
) -> list[dict[str, Any]]:
    """Detect + project voice-card rows across loaded chapters (1…N)."""
    rows = detect_voice_card_issues(
        chapters,
        cards,
        focus_chapter=focus_n,
        max_entries=max_entries,
    )
    return companion_voice_card_to_dicts(rows, max_entries=max_entries)


def _scope_label(chapters: list[int], focus_chapter: int) -> str:
    """Label prior vs focus evidence for soft-dim bias (§4.2)."""
    if not chapters:
        return "prior — context only"
    has_focus = focus_chapter in chapters
    has_prior = any(c != focus_chapter for c in chapters)
    if has_focus and has_prior:
        return "prior+focus"
    if has_focus:
        return "focus"
    return "prior — context only"


def voice_card_block(
    findings: list[dict[str, Any]],
    *,
    chapter_number: int,
) -> str:
    """Format heuristic voice-card rows as craft-prompt bias (like register_block)."""
    header = "## Voice-vs-card heuristic"
    if not findings:
        return (
            f"{header}\n"
            "No voice/card machine rows for book-so-far attributed speech "
            "(missing cards, below min_lines, or no cue/collapse hits)."
        )

    lines = [
        header,
        "Algorithmically-detected voice/card signals (book-so-far machine rows):",
    ]
    for entry in findings:
        kind = entry.get("kind", "")
        severity = entry.get("severity", "low")
        speaker = entry.get("speaker") or ""
        speaker_b = entry.get("speaker_b")
        chapters = entry.get("chapters") or []
        if not isinstance(chapters, list):
            chapters = []
        scope = _scope_label([int(c) for c in chapters], chapter_number)
        speaker_bit = f" speaker={speaker}" if speaker else ""
        partner_bit = f" speaker_b={speaker_b}" if speaker_b else ""
        ch_bit = f" chapters={chapters}" if chapters else ""
        lines.append(f"  - [{kind}/{severity}]{speaker_bit}{partner_bit}{ch_bit} ({scope})")
    lines.append(
        f"Focus-chapter {chapter_number} quotes are in the manuscript excerpt; "
        "do not re-litigate prior-only evidence as a new N concern without N text."
    )
    return "\n".join(line for line in lines if line is not None and line != "")


__all__ = [
    "companion_voice_card_to_dicts",
    "voice_card_block",
    "voice_card_finding_to_dict",
    "voice_card_findings_for_chapters",
]
