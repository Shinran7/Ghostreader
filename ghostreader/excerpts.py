"""Hit-weighted manuscript excerpts for analyze grounding.

Slice 2a: chapter-level allocation + chapter heads only.
Position/needle windows and overlap merge land in Slice 2b.
``window_chars`` is accepted for API stability but unused until 2b.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

_SEVERITY_WEIGHT = {"high": 3, "moderate": 2, "low": 1}


@dataclass(frozen=True)
class Hit:
    """A weighted locus for excerpt allocation.

    ``position`` is 0.0–1.0 within the chapter when known; ``None`` means
    chapter-level. Slice 2a aggregates by chapter only; positioned hits still
    contribute weight (XOR with chapter-level — see ``hits_from_repetition_data``).
    """

    chapter_number: int
    weight: float  # must be > 0
    position: float | None = None
    needle: str | None = None


def quote_from_text(term: str, text: str, *, max_len: int = 160) -> str | None:
    """Return one short verbatim span from *text* containing *term*, if any."""
    if not term or not text:
        return None
    match = re.search(rf"(?<!\w){re.escape(term)}(?!\w)", text, re.IGNORECASE)
    if match is None:
        return None
    sent_start = text.rfind(".", 0, match.start())
    sent_start = 0 if sent_start < 0 else sent_start + 1
    sent_end_candidates = [text.find(p, match.end()) for p in (".", "!", "?")]
    sent_ends = [i for i in sent_end_candidates if i != -1]
    sent_end = (min(sent_ends) + 1) if sent_ends else min(len(text), match.end() + 80)
    quote = text[sent_start:sent_end].strip()
    if len(quote) > max_len:
        local = match.start() - sent_start
        left = max(0, local - max_len // 3)
        quote = quote[left : left + max_len].strip()
    return quote or None


def row_weight(severity: str, count: int) -> float:
    """Severity × (1 + floor(log10(max(count, 1))))."""
    sev = _SEVERITY_WEIGHT.get(str(severity).lower(), 1)
    return float(sev * (1 + math.floor(math.log10(max(int(count), 1)))))


def hits_from_chapter_numbers(
    nums: Sequence[int], *, weight: float = 1.0
) -> list[Hit]:
    """One chapter-level hit per distinct chapter number."""
    if weight <= 0:
        return []
    out: list[Hit] = []
    seen: set[int] = set()
    for n in nums:
        c = int(n)
        if c in seen:
            continue
        seen.add(c)
        out.append(Hit(chapter_number=c, weight=float(weight)))
    return out


def hits_from_repetition_data(repetition_data: Sequence[Mapping[str, Any]]) -> list[Hit]:
    """Build hits from analyze ``repetition_data`` rows.

    XOR (no double-count): for each (row, chapter c) with weight ``w_row``:
    - If the row has one or more ``locations`` for c → emit only positioned
      hits (weight split evenly). Do not also emit a chapter-level hit.
    - Else → emit exactly one chapter-level hit (``position=None``,
      ``needle`` = phrase / first pattern example).

    Slice 2a callers aggregate by chapter; positions are reserved for 2b windows.
    """
    hits: list[Hit] = []
    for entry in repetition_data:
        chapters = entry.get("chapters") or []
        if not chapters:
            continue
        w_row = row_weight(str(entry.get("severity", "low")), int(entry.get("count", 1) or 1))
        if w_row <= 0:
            continue
        kind = entry.get("kind") or "phrase"
        needle: str | None = str(entry.get("phrase") or "") or None
        if kind == "sentence_pattern":
            examples = [
                str(ex).strip()
                for ex in (entry.get("examples") or [])
                if str(ex).strip()
            ]
            if examples:
                needle = examples[0][:80]
        locations = entry.get("locations") or []
        for raw_c in chapters:
            c = int(raw_c)
            locs_c = [
                loc
                for loc in locations
                if isinstance(loc, Mapping) and int(loc.get("chapter_number", -1)) == c
            ]
            if locs_c:
                w_each = w_row / len(locs_c)
                for loc in locs_c:
                    pos = loc.get("approximate_position")
                    position = float(pos) if pos is not None else None
                    hits.append(
                        Hit(
                            chapter_number=c,
                            weight=w_each,
                            position=position,
                            needle=needle,
                        )
                    )
            else:
                hits.append(
                    Hit(
                        chapter_number=c,
                        weight=w_row,
                        position=None,
                        needle=needle,
                    )
                )
    return hits


def _header(number: Any, title: str) -> str:
    return f"--- Chapter {number}: {title} ---\n"


def _largest_remainder(raw_shares: list[float], total: int) -> list[int]:
    """Hamilton / largest-remainder integer allocation summing to *total*."""
    if total <= 0 or not raw_shares:
        return [0] * len(raw_shares)
    floors = [int(math.floor(x)) for x in raw_shares]
    leftover = total - sum(floors)
    order = sorted(
        range(len(raw_shares)),
        key=lambda i: (floors[i] - raw_shares[i], i),  # most fractional first
    )
    for i in order:
        if leftover <= 0:
            break
        floors[i] += 1
        leftover -= 1
    return floors


def _aggregate_weights(hits: Sequence[Hit]) -> dict[int, float]:
    weights: dict[int, float] = {}
    for h in hits:
        if h.weight <= 0:
            continue
        weights[h.chapter_number] = weights.get(h.chapter_number, 0.0) + h.weight
    return weights


def _alloc_for_hits(
    chapter_weights: dict[int, float],
    *,
    content_budget: int,
    min_per_chapter: int,
) -> dict[int, int]:
    """Proportional content alloc for hit chapters (soft floor + remainder)."""
    ordered = sorted(chapter_weights.keys(), key=lambda c: (-chapter_weights[c], c))
    if not ordered or content_budget <= 0:
        return {}

    # Soft floor when budget allows; else include chapters in priority order.
    mins: dict[int, int] = {}
    remaining = content_budget
    for c in ordered:
        take = min(min_per_chapter, remaining)
        if take <= 0:
            break
        mins[c] = take
        remaining -= take

    if not mins:
        return {}

    selected = list(mins.keys())
    w_total = sum(chapter_weights[c] for c in selected)
    if remaining > 0 and w_total > 0:
        raw = [remaining * (chapter_weights[c] / w_total) for c in selected]
        extras = _largest_remainder(raw, remaining)
        return {c: mins[c] + extras[i] for i, c in enumerate(selected)}
    return dict(mins)


def build_hit_weighted_excerpts(
    chapters: Sequence[Mapping[str, Any]],
    hits: Sequence[Hit],
    *,
    total_budget: int,
    window_chars: int = 900,
    min_per_chapter: int = 400,
    legacy_per_chapter: int = 4000,
) -> str:
    """Allocate excerpt chars under a hard ceiling; emit chapter heads (Slice 2a).

    Ceiling = ``min(total_budget, legacy_per_chapter * N)`` (hard max, not a
    fill target). Headers count toward the ceiling. ``window_chars`` is unused
    until Slice 2b position windows.
    """
    del window_chars  # Slice 2b
    n = len(chapters)
    if n == 0 or total_budget <= 0:
        return ""

    by_num = {int(ch.get("chapter_number", 0)): ch for ch in chapters}
    effective_ceiling = min(int(total_budget), int(legacy_per_chapter) * n)
    if effective_ceiling <= 0:
        return ""

    weights = _aggregate_weights(hits)
    hit_chapters = {c for c in weights if c in by_num and weights[c] > 0}

    parts: list[str] = []
    used = 0

    def _emit(ch: Mapping[str, Any], content_chars: int) -> bool:
        nonlocal used
        if content_chars <= 0:
            return False
        number = ch.get("chapter_number", "?")
        title = str(ch.get("title") or f"Chapter {number}")
        header = _header(number, title)
        content = str(ch.get("content") or "")
        # Cap: alloc, half-ceiling, and content length.
        hard = min(
            content_chars,
            max(min_per_chapter, effective_ceiling // 2),
            len(content),
        )
        room = effective_ceiling - used - len(header)
        if room <= 0:
            return False
        take = min(hard, room)
        if take <= 0:
            return False
        block = f"{header}{content[:take]}"
        parts.append(block)
        used += len(block)
        return True

    if not hit_chapters:
        per = min(legacy_per_chapter, effective_ceiling // max(n, 1))
        for ch in chapters:
            if used >= effective_ceiling:
                break
            _emit(ch, per)
        return _join_under_ceiling(parts, effective_ceiling)

    # Headers/separators are trimmed at emit/join; ceiling is a hard max.
    alloc = _alloc_for_hits(
        {c: weights[c] for c in hit_chapters},
        content_budget=effective_ceiling,
        min_per_chapter=min_per_chapter,
    )
    ordered = sorted(alloc.keys(), key=lambda c: (-weights[c], c))
    for c in ordered:
        if used >= effective_ceiling:
            break
        _emit(by_num[c], alloc[c])

    return _join_under_ceiling(parts, effective_ceiling)


def _join_under_ceiling(parts: list[str], ceiling: int) -> str:
    """Join parts with blank lines without exceeding *ceiling*."""
    if not parts:
        return ""
    out = parts[0]
    for part in parts[1:]:
        sep = "\n\n"
        if len(out) + len(sep) + len(part) <= ceiling:
            out = f"{out}{sep}{part}"
            continue
        room = ceiling - len(out) - len(sep)
        if room <= 0:
            break
        out = f"{out}{sep}{part[:room]}"
        break
    return out[:ceiling]


__all__ = [
    "Hit",
    "build_hit_weighted_excerpts",
    "hits_from_chapter_numbers",
    "hits_from_repetition_data",
    "quote_from_text",
    "row_weight",
]
