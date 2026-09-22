"""Companion craft-window selection and N-relevant repetition serialization."""

from __future__ import annotations

import re
from typing import Any

from ghostreader.analyzers import RepetitionReport
from ghostreader.ingestion import Chapter

_SEVERITY_RANK = {"high": 0, "moderate": 1, "low": 2}
_WS_RE = re.compile(r"\s+")


def select_craft_chapters(
    chapters: list[Chapter],
    *,
    focus_n: int,
    window: int,
) -> list[Chapter]:
    """Return chapters in (focus_n - window) … focus_n inclusive, sorted."""
    lo = focus_n - window
    by_num = {c.chapter_number: c for c in chapters}
    nums = sorted(n for n in by_num if lo <= n <= focus_n)
    # Always include focus N when present even if outside sparse gaps.
    if focus_n in by_num and focus_n not in nums:
        nums.append(focus_n)
        nums.sort()
    return [by_num[n] for n in nums]


def _count_in_text(term: str, text: str) -> int:
    """Case-insensitive whole-phrase occurrence count in *text*."""
    if not term or not text:
        return 0
    pattern = re.compile(rf"(?<!\w){re.escape(term)}(?!\w)", re.IGNORECASE)
    return len(pattern.findall(text))


def _normalized_key(phrase: str) -> str:
    return _WS_RE.sub(" ", phrase.strip().lower())


def _quote_from_text(term: str, text: str, *, max_len: int = 160) -> str | None:
    """Return one short verbatim span from *text* containing *term*, if any."""
    if not term or not text:
        return None
    match = re.search(rf"(?<!\w){re.escape(term)}(?!\w)", text, re.IGNORECASE)
    if match is None:
        return None
    # Prefer the sentence that contains the match.
    sent_start = text.rfind(".", 0, match.start())
    sent_start = 0 if sent_start < 0 else sent_start + 1
    sent_end_candidates = [
        text.find(p, match.end()) for p in (".", "!", "?")
    ]
    sent_ends = [i for i in sent_end_candidates if i != -1]
    sent_end = (min(sent_ends) + 1) if sent_ends else min(len(text), match.end() + 80)
    quote = text[sent_start:sent_end].strip()
    if len(quote) > max_len:
        # Center on the match inside the sentence.
        local = match.start() - sent_start
        left = max(0, local - max_len // 3)
        quote = quote[left : left + max_len].strip()
    return quote or None


def _word_severity(tfidf_score: float) -> str:
    if tfidf_score > 0.3:
        return "high"
    if tfidf_score > 0.15:
        return "moderate"
    return "low"


def _phrase_severity(count: int) -> str:
    if count >= 10:
        return "high"
    if count >= 5:
        return "moderate"
    return "low"


def _tag_severity(count: int) -> str:
    if count >= 10:
        return "high"
    if count >= 5:
        return "moderate"
    return "low"


def _pattern_severity(similarity_score: float) -> str:
    if similarity_score >= 0.9:
        return "high"
    if similarity_score >= 0.75:
        return "moderate"
    return "low"


def companion_repetition_to_dicts(
    report: RepetitionReport,
    *,
    focus_n: int,
    focus_chapter: Chapter | None = None,
    max_entries: int = 25,
) -> list[dict[str, Any]]:
    """Serialize N-relevant repetition for companion prose + brief export.

    Each entry includes ``kind``, ``scope``, ``severity``, optional
    ``focus_count``, ``quote``, and ``normalized_key``. Dialogue-tag
    ``phrase`` is the lemma only (no ``[dialogue tag]`` prefix).
    """
    focus_text = focus_chapter.content if focus_chapter is not None else ""
    entries: list[dict[str, Any]] = []

    for wf in report.word_frequencies:
        chapters = sorted({loc.chapter_number for loc in wf.locations})
        if focus_n not in chapters:
            continue
        scope = "cross_chapter" if any(c != focus_n for c in chapters) else "local"
        entries.append(
            {
                "phrase": wf.term,
                "kind": "word",
                "count": wf.count,
                "chapters": chapters,
                "severity": _word_severity(wf.tfidf_score),
                "scope": scope,
                "focus_count": _count_in_text(wf.term, focus_text),
                "quote": _quote_from_text(wf.term, focus_text),
                "normalized_key": _normalized_key(wf.term),
            }
        )

    for rp in report.repeated_phrases:
        chapters = sorted({loc.chapter_number for loc in rp.locations})
        if focus_n not in chapters:
            continue
        scope = "cross_chapter" if any(c != focus_n for c in chapters) else "local"
        entries.append(
            {
                "phrase": rp.phrase,
                "kind": "phrase",
                "count": rp.count,
                "chapters": chapters,
                "severity": _phrase_severity(rp.count),
                "scope": scope,
                "focus_count": _count_in_text(rp.phrase, focus_text),
                "quote": _quote_from_text(rp.phrase, focus_text),
                "normalized_key": _normalized_key(rp.phrase),
            }
        )

    for tag in report.dialogue_tags:
        focus_count = int(tag.chapter_counts.get(focus_n, 0) or 0)
        if focus_count <= 0:
            continue
        chapters = sorted(tag.chapter_counts)
        scope = (
            "cross_chapter"
            if any(c != focus_n and tag.chapter_counts.get(c, 0) > 0 for c in chapters)
            else "local"
        )
        lemma = tag.tag
        entries.append(
            {
                "phrase": lemma,
                "kind": "dialogue_tag",
                "count": tag.count,
                "chapters": chapters,
                "severity": _tag_severity(tag.count),
                "scope": scope,
                "focus_count": focus_count,
                "quote": _quote_from_text(lemma, focus_text),
                "normalized_key": _normalized_key(lemma),
            }
        )

    for pattern in report.sentence_patterns:
        if pattern.chapter_number != focus_n:
            continue
        phrase = pattern.description or pattern.pattern_type
        example = pattern.examples[0].strip() if pattern.examples else None
        entries.append(
            {
                "phrase": phrase,
                "kind": "sentence_pattern",
                "count": max(len(pattern.examples), 1),
                "chapters": [pattern.chapter_number],
                "severity": _pattern_severity(pattern.similarity_score),
                "scope": "local",
                "pattern_type": pattern.pattern_type,
                "quote": example,
                "normalized_key": _normalized_key(phrase),
            }
        )

    def _sort_key(e: dict[str, Any]) -> tuple[int, int, int]:
        sev = _SEVERITY_RANK.get(str(e.get("severity") or "low"), 99)
        count = -int(e.get("count") or 0)
        scope_rank = 0 if e.get("scope") == "cross_chapter" else 1
        return (sev, count, scope_rank)

    entries.sort(key=_sort_key)
    return entries[:max_entries]


def repetition_findings_for_brief(
    dicts: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Project companion repetition dicts into Autonomicon ``repetition_findings`` rows."""
    out: list[dict[str, Any]] = []
    for entry in dicts:
        phrase = str(entry.get("phrase") or "")
        kind = str(entry.get("kind") or "phrase")
        chapters = [int(c) for c in (entry.get("chapters") or [])]
        row: dict[str, Any] = {
            "phrase": phrase,
            "kind": kind,
            "count": int(entry.get("count") or 0),
            "focus_count": int(entry.get("focus_count") or 0),
            "chapters": chapters,
            "scope": str(entry.get("scope") or "local"),
            "severity": str(entry.get("severity") or "low"),
            "quote": entry.get("quote"),
            "normalized_key": entry.get("normalized_key")
            if entry.get("normalized_key") is not None
            else (_normalized_key(phrase) if phrase else None),
        }
        # Sentence patterns omit focus_count in detector mapping; brief still
        # wants an int — keep 0 when absent.
        if kind == "sentence_pattern" and "focus_count" not in entry:
            row["focus_count"] = 0
        out.append(row)
    return out


def companion_format_repetition_data(dicts: list[dict[str, Any]]) -> str:
    """Format companion repetition entries including scope / focus_count."""
    if not dicts:
        return "No significant repetition patterns detected."

    lines = ["Algorithmically-detected repetition patterns:"]
    for entry in dicts:
        phrase = entry.get("phrase", "")
        kind = entry.get("kind")
        display = (
            f"[dialogue tag] {phrase}" if kind == "dialogue_tag" else phrase
        )
        count = entry.get("count", 0)
        chapters = entry.get("chapters", [])
        severity = entry.get("severity", "low")
        scope = entry.get("scope", "local")
        ch_str = ", ".join(str(c) for c in chapters)
        parts = [
            f'  - "{display}" × {count} occurrences '
            f"(chapters: {ch_str}, severity: {severity}, scope: {scope}"
        ]
        if "focus_count" in entry:
            parts.append(f", in N: {entry['focus_count']}")
        parts.append(")")
        lines.append("".join(parts))
    return "\n".join(lines)


__all__ = [
    "companion_format_repetition_data",
    "companion_repetition_to_dicts",
    "repetition_findings_for_brief",
    "select_craft_chapters",
]
