"""Hit-weighted manuscript excerpts for analyze grounding.

Allocate by chapter weight under a hard ceiling, then emit merged windows
centered on hit positions / needles (with optional head pad within alloc).
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
    chapter-level (locate via ``needle`` when placing windows).
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


def _needle_match(needle: str, text: str) -> re.Match[str] | None:
    """First case-insensitive whole-phrase match (same spirit as quote_from_text)."""
    if not needle or not text:
        return None
    return re.search(rf"(?<!\w){re.escape(needle)}(?!\w)", text, re.IGNORECASE)


def _centered_window(center: int, length: int, window_chars: int) -> tuple[int, int]:
    """Window around *center* using the design half-split formula."""
    half = window_chars // 2
    start = max(0, center - half)
    end = min(length, center + window_chars - half)
    if start >= end:
        return (0, 0)
    return (start, end)


def _window_for_hit(
    content: str, hit: Hit, window_chars: int
) -> tuple[int, int] | None:
    """Return ``[start, end)`` for a hit, or None if no placeable window."""
    n = len(content)
    if n == 0 or window_chars <= 0:
        return None
    if hit.position is not None:
        center = int(float(hit.position) * n)
        center = max(0, min(n, center))
        start, end = _centered_window(center, n, window_chars)
        return (start, end) if end > start else None
    if hit.needle:
        match = _needle_match(hit.needle, content)
        if match is None:
            return None
        center = (match.start() + match.end()) // 2
        start, end = _centered_window(center, n, window_chars)
        return (start, end) if end > start else None
    return None


def _merge_intervals(intervals: Sequence[tuple[int, int]]) -> list[tuple[int, int]]:
    """Union overlapping or adjacent ``[start, end)`` intervals."""
    if not intervals:
        return []
    ordered = sorted((s, e) for s, e in intervals if e > s)
    if not ordered:
        return []
    merged: list[list[int]] = [[ordered[0][0], ordered[0][1]]]
    for s, e in ordered[1:]:
        if s <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], e)
        else:
            merged.append([s, e])
    return [(s, e) for s, e in merged]


def _interval_length(intervals: Sequence[tuple[int, int]]) -> int:
    return sum(e - s for s, e in intervals)


def _truncate_intervals(
    intervals: Sequence[tuple[int, int]], budget: int
) -> list[tuple[int, int]]:
    """Keep intervals in order until *budget* chars; truncate the last."""
    if budget <= 0:
        return []
    out: list[tuple[int, int]] = []
    remaining = budget
    for s, e in intervals:
        if remaining <= 0:
            break
        length = e - s
        if length <= remaining:
            out.append((s, e))
            remaining -= length
        else:
            out.append((s, s + remaining))
            remaining = 0
    return out


def _select_intervals_by_priority(
    weighted: Sequence[tuple[int, int, float]], alloc_c: int
) -> list[tuple[int, int]]:
    """Keep higher-weight windows first until *alloc_c*; truncate the last."""
    if alloc_c <= 0 or not weighted:
        return []
    ordered = sorted(weighted, key=lambda t: (-t[2], t[0], t[1]))
    chosen: list[tuple[int, int]] = []
    for start, end, _w in ordered:
        trial = _merge_intervals([*chosen, (start, end)])
        if _interval_length(trial) <= alloc_c:
            chosen = trial
            continue
        if _interval_length(chosen) >= alloc_c:
            break
        chosen = _truncate_intervals(
            _merge_intervals([*chosen, (start, end)]), alloc_c
        )
        break
    return chosen


def _head_pad_intervals(
    intervals: list[tuple[int, int]], alloc_c: int, content_len: int
) -> list[tuple[int, int]]:
    """Extend the first window toward chapter start up to *alloc_c*."""
    if alloc_c <= 0 or content_len <= 0:
        return []
    if not intervals:
        return [(0, min(alloc_c, content_len))]
    total = _interval_length(intervals)
    if total >= alloc_c:
        return intervals
    need = alloc_c - total
    first_s, first_e = intervals[0]
    extend = min(need, first_s)
    if extend <= 0:
        return intervals
    padded = [(first_s - extend, first_e), *intervals[1:]]
    return _merge_intervals(padded)


def _windows_for_chapter(
    content: str,
    chapter_hits: Sequence[Hit],
    *,
    window_chars: int,
    alloc_c: int,
) -> list[tuple[int, int]]:
    """Place, merge, priority-trim, and optionally head-pad windows."""
    if alloc_c <= 0 or not content:
        return []

    weighted: list[tuple[int, int, float]] = []
    for hit in chapter_hits:
        if hit.weight <= 0:
            continue
        span = _window_for_hit(content, hit, window_chars)
        if span is None:
            continue
        start, end = span
        weighted.append((start, end, hit.weight))

    if not weighted:
        # No placeable window (missing needle, etc.) — head within alloc.
        return [(0, min(alloc_c, len(content)))]

    merged = _merge_intervals([(s, e) for s, e, _ in weighted])
    if _interval_length(merged) > alloc_c:
        merged = _select_intervals_by_priority(weighted, alloc_c)
    else:
        merged = list(merged)

    return _head_pad_intervals(merged, alloc_c, len(content))


def _body_from_intervals(content: str, intervals: Sequence[tuple[int, int]]) -> str:
    return "".join(content[s:e] for s, e in intervals)


def build_hit_weighted_excerpts(
    chapters: Sequence[Mapping[str, Any]],
    hits: Sequence[Hit],
    *,
    total_budget: int,
    window_chars: int = 900,
    min_per_chapter: int = 400,
    legacy_per_chapter: int = 4000,
) -> str:
    """Allocate excerpt chars under a hard ceiling; emit merged hit windows.

    Ceiling = ``min(total_budget, legacy_per_chapter * N)`` (hard max, not a
    fill target). Headers count toward the ceiling. Windows center on
    ``position`` / ``needle``; overlaps are unioned; short chapters may
    head-pad within ``alloc_c`` only.
    """
    n = len(chapters)
    if n == 0 or total_budget <= 0:
        return ""

    by_num = {int(ch.get("chapter_number", 0)): ch for ch in chapters}
    effective_ceiling = min(int(total_budget), int(legacy_per_chapter) * n)
    if effective_ceiling <= 0:
        return ""

    weights = _aggregate_weights(hits)
    hits_by_chapter: dict[int, list[Hit]] = {}
    for h in hits:
        if h.weight <= 0:
            continue
        hits_by_chapter.setdefault(h.chapter_number, []).append(h)

    hit_chapters = {c for c in weights if c in by_num and weights[c] > 0}

    parts: list[str] = []
    used = 0

    def _emit_head(ch: Mapping[str, Any], content_chars: int) -> bool:
        """Zero-hit / legacy path: chapter head only."""
        nonlocal used
        if content_chars <= 0:
            return False
        number = ch.get("chapter_number", "?")
        title = str(ch.get("title") or f"Chapter {number}")
        header = _header(number, title)
        content = str(ch.get("content") or "")
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

    def _emit_windows(ch: Mapping[str, Any], content_chars: int, c: int) -> bool:
        nonlocal used
        if content_chars <= 0:
            return False
        number = ch.get("chapter_number", "?")
        title = str(ch.get("title") or f"Chapter {number}")
        header = _header(number, title)
        content = str(ch.get("content") or "")
        hard = min(
            content_chars,
            max(min_per_chapter, effective_ceiling // 2),
            len(content),
        )
        room = effective_ceiling - used - len(header)
        if room <= 0:
            return False
        alloc_c = min(hard, room)
        if alloc_c <= 0:
            return False
        intervals = _windows_for_chapter(
            content,
            hits_by_chapter.get(c, []),
            window_chars=window_chars,
            alloc_c=alloc_c,
        )
        body = _body_from_intervals(content, intervals)
        if not body:
            return False
        # Final clamp if body somehow overshoots room.
        body = body[:room]
        block = f"{header}{body}"
        parts.append(block)
        used += len(block)
        return True

    if not hit_chapters:
        per = min(legacy_per_chapter, effective_ceiling // max(n, 1))
        for ch in chapters:
            if used >= effective_ceiling:
                break
            _emit_head(ch, per)
        return _join_under_ceiling(parts, effective_ceiling)

    alloc = _alloc_for_hits(
        {c: weights[c] for c in hit_chapters},
        content_budget=effective_ceiling,
        min_per_chapter=min_per_chapter,
    )
    ordered = sorted(alloc.keys(), key=lambda c: (-weights[c], c))
    for c in ordered:
        if used >= effective_ceiling:
            break
        _emit_windows(by_num[c], alloc[c], c)

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
