"""Common-word carpet + fancy dialogue-tag thrash (#10 / compose Autonomicon #355).

Common-word thresholds lock to Autonomicon S4 (KD-5). Fancy tags are a
separate ``dialogue_tag`` seat (KD-7); bare ``said`` never emits.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict

from ghostreader.analyzers.register_detector import strip_chapter_body
from ghostreader.analyzers.repetition_detector import _DIALOGUE_VERBS
from ghostreader.analyzers.thrash_detector import (
    ThrashFinding,
    is_uncommon,
    lemma,
)
from ghostreader.excerpts import quote_from_text

_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z\-']*")

# Autonomicon S4 thresholds (KD-5).
COMMON_OVERUSE_ABS = 6
COMMON_OVERUSE_PER_1000 = 1.2
LOAD_BEARING_ABS = 10
LOAD_BEARING_PER_1000 = 1.8
_RATE_MIN_WORDS = 1000
_RATE_MIN_COUNT = 4

# Fancy dialogue-tag fuse (KD-7); quieter than Autonomicon demote-at-2.
DIALOGUE_TAG_FUSE = 3

_BARE_ATTRIBUTION = frozenset({"said", "asked", "replied", "answered"})
# Exact frozenset lock: GR _DIALOGUE_VERBS canonicals minus bare attribution.
FANCY_DIALOGUE_TAG_LEMMAS: frozenset[str] = frozenset(_DIALOGUE_VERBS.values()) - _BARE_ATTRIBUTION

# Never emit as thrash (KD-6).
_SAID_FAMILY = frozenset({"said", "says", "say"})

# Reader structural exempt (KD-6): frequency-exempt spirit + high-noise leftovers.
READER_EXEMPT_WORDS: frozenset[str] = frozenset(
    {
        "a",
        "an",
        "the",
        "and",
        "but",
        "or",
        "nor",
        "for",
        "yet",
        "so",
        "is",
        "am",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "have",
        "has",
        "had",
        "do",
        "does",
        "did",
        "will",
        "would",
        "shall",
        "should",
        "can",
        "could",
        "may",
        "might",
        "must",
        "i",
        "me",
        "my",
        "we",
        "our",
        "you",
        "your",
        "he",
        "him",
        "his",
        "she",
        "her",
        "they",
        "them",
        "their",
        "it",
        "its",
        "this",
        "that",
        "these",
        "those",
        "what",
        "which",
        "who",
        "whom",
        "whose",
        "of",
        "in",
        "to",
        "on",
        "at",
        "by",
        "from",
        "with",
        "into",
        "about",
        "between",
        "through",
        "without",
        "against",
        "under",
        "over",
        "than",
        "then",
        "more",
        "most",
        "only",
        "just",
        "even",
        "also",
        "still",
        "very",
        "down",
        "back",
        "away",
        "out",
        "off",
        "up",
        "not",
        "no",
        "if",
        "as",
        "like",
        "said",
        "says",
        "say",
        # High-noise leftovers (KD-6).
        "across",
        "before",
        "already",
        "where",
        "while",
        "onto",
        "after",
        "again",
        "once",
        "upon",
        "within",
        "one",
        "two",
        "three",
        "four",
        "five",
        "six",
        "seven",
        "eight",
        "nine",
        "ten",
        "minute",
        "minutes",
        "hour",
        "hours",
        "second",
        "seconds",
    }
)

# Local SI length/time units (KD-16) — no Autonomicon import.
SI_UNIT_LEMMAS: frozenset[str] = frozenset(
    {
        "meter",
        "meters",
        "metre",
        "metres",
        "kilometer",
        "kilometers",
        "kilometre",
        "kilometres",
        "centimeter",
        "centimeters",
        "centimetre",
        "centimetres",
        "millimeter",
        "millimeters",
        "millimetre",
        "millimetres",
        "inch",
        "inches",
        "foot",
        "feet",
        "yard",
        "yards",
        "mile",
        "miles",
        "km",
        "cm",
        "mm",
        "minute",
        "minutes",
        "hour",
        "hours",
        "second",
        "seconds",
    }
)


def _severity_common(count: int) -> str:
    if count >= 8:
        return "high"
    if count >= 6:
        return "moderate"
    return "low"


def _severity_dialogue(count: int) -> str:
    if count >= 4:
        return "high"
    if count >= 2:
        return "moderate"
    return "low"


def _over_threshold(
    count: int,
    per_1000: float,
    *,
    load_bearing: bool,
    word_n: int,
) -> bool:
    abs_t = LOAD_BEARING_ABS if load_bearing else COMMON_OVERUSE_ABS
    rate_t = LOAD_BEARING_PER_1000 if load_bearing else COMMON_OVERUSE_PER_1000
    if count >= abs_t:
        return True
    return word_n >= _RATE_MIN_WORDS and count >= _RATE_MIN_COUNT and per_1000 >= rate_t


def _iter_content_hits(text: str) -> list[tuple[str, str, int, int]]:
    """Yield (lemma, surface, start, end); skip mid-sentence proper names."""
    out: list[tuple[str, str, int, int]] = []
    tokens = list(_TOKEN_RE.finditer(text))
    for i, m in enumerate(tokens):
        tok = m.group(0)
        start = m.start()
        end = m.end()
        if tok[:1].isupper() and not tok.isupper():
            prefix = text[:start].rstrip()
            mid_sentence = bool(prefix) and prefix[-1] not in ".!?\n"
            nxt = tokens[i + 1].group(0) if i + 1 < len(tokens) else ""
            multi_proper = bool(nxt) and nxt[:1].isupper() and not nxt.isupper()
            if mid_sentence or multi_proper:
                continue
        out.append((lemma(tok), tok, start, end))
    return out


def _quote(body: str, token: str) -> str | None:
    q = quote_from_text(token, body)
    if q:
        return q
    idx = body.lower().find(token.lower())
    if idx < 0:
        return None
    left = max(0, idx - 40)
    return body[left : left + 160].strip() or None


def detect_common_word_thrash(
    content: str,
    *,
    chapter_number: int,
    load_bearing: set[str] | frozenset[str] | None = None,
) -> list[ThrashFinding]:
    """Common-word carpet (kind=common_word). Skip Zipf-uncommon + fancy tags."""
    body = strip_chapter_body(content or "")
    if not body.strip():
        return []
    hits = _iter_content_hits(body)
    if not hits:
        return []
    word_n = max(len(hits), 1)
    counts: Counter[str] = Counter()
    surfaces: dict[str, list[str]] = defaultdict(list)
    for lem, tok, _s, _e in hits:
        counts[lem] += 1
        surfaces[lem].append(tok)

    lb = {lemma(str(x)) for x in (load_bearing or []) if str(x).strip()}
    findings: list[ThrashFinding] = []
    for lem, n in counts.items():
        if len(lem) < 3:
            continue
        if lem in READER_EXEMPT_WORDS or lem in SI_UNIT_LEMMAS:
            continue
        if lem in _SAID_FAMILY:
            continue
        if lem in FANCY_DIALOGUE_TAG_LEMMAS:
            continue  # dialogue_tag owns these (KD-5 / KD-7)
        if is_uncommon(lem):
            continue
        is_lb = lem in lb
        per_1000 = (n * 1000.0) / word_n
        if not _over_threshold(n, per_1000, load_bearing=is_lb, word_n=word_n):
            continue
        foothold = surfaces[lem][0]
        findings.append(
            ThrashFinding(
                kind="common_word",
                lemma=lem,
                severity=_severity_common(n),
                count=n,
                chapters=[chapter_number],
                chapter=chapter_number,
                scene_index=None,
                quote=_quote(body, foothold),
                normalized_key=lem,
                foothold_token=foothold,
                later_surfaces=[],
            )
        )
    findings.sort(key=lambda f: (-f.count, f.lemma))
    return findings


def _canonical_dialogue_lemma(surface: str) -> str | None:
    """Map surface to fancy dialogue canonical, or None if not fancy."""
    raw = surface.lower()
    mapped = _DIALOGUE_VERBS.get(raw)
    if mapped is None:
        mapped = _DIALOGUE_VERBS.get(lemma(surface))
    if mapped is None:
        return None
    if mapped in _BARE_ATTRIBUTION or mapped in _SAID_FAMILY:
        return None
    if mapped not in FANCY_DIALOGUE_TAG_LEMMAS:
        return None
    return mapped


def detect_dialogue_tag_thrash(
    content: str,
    *,
    chapter_number: int,
    fuse: int = DIALOGUE_TAG_FUSE,
) -> list[ThrashFinding]:
    """Fancy dialogue-tag carpet (kind=dialogue_tag). Never bare said."""
    body = strip_chapter_body(content or "")
    if not body.strip():
        return []
    by_canon: dict[str, list[str]] = defaultdict(list)
    for m in _TOKEN_RE.finditer(body):
        tok = m.group(0)
        canon = _canonical_dialogue_lemma(tok)
        if canon is None:
            continue
        by_canon[canon].append(tok)

    findings: list[ThrashFinding] = []
    need = max(1, int(fuse))
    for canon, surfaces in by_canon.items():
        n = len(surfaces)
        if n < need:
            continue
        foothold = surfaces[0]
        findings.append(
            ThrashFinding(
                kind="dialogue_tag",
                lemma=canon,
                severity=_severity_dialogue(n),
                count=n,
                chapters=[chapter_number],
                chapter=chapter_number,
                scene_index=None,
                quote=_quote(body, foothold),
                normalized_key=canon,
                foothold_token=foothold,
                later_surfaces=[],
            )
        )
    findings.sort(key=lambda f: (-f.count, f.lemma))
    return findings


__all__ = [
    "COMMON_OVERUSE_ABS",
    "DIALOGUE_TAG_FUSE",
    "FANCY_DIALOGUE_TAG_LEMMAS",
    "READER_EXEMPT_WORDS",
    "SI_UNIT_LEMMAS",
    "detect_common_word_thrash",
    "detect_dialogue_tag_thrash",
]
