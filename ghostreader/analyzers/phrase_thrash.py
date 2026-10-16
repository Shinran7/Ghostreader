"""Literary multi-word phrase thrash (#10 / compose Autonomicon #355).

Adjacent 2–3 content grams; fuse ≥2; SI/procedural numeric+unit grams demoted.
"""

from __future__ import annotations

import re
from collections import Counter

from ghostreader.analyzers.common_word_thrash import SI_UNIT_LEMMAS
from ghostreader.analyzers.register_detector import strip_chapter_body
from ghostreader.analyzers.thrash_detector import ThrashFinding
from ghostreader.excerpts import quote_from_text

_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z\-']*")
PHRASE_THRASH_FUSE = 2

_STOPWORDS = frozenset(
    {
        "a",
        "an",
        "the",
        "and",
        "or",
        "but",
        "if",
        "as",
        "at",
        "by",
        "for",
        "from",
        "in",
        "into",
        "of",
        "on",
        "onto",
        "to",
        "with",
        "without",
        "about",
        "over",
        "under",
        "up",
        "down",
        "out",
        "off",
        "than",
        "then",
        "that",
        "this",
        "these",
        "those",
        "there",
        "here",
        "when",
        "where",
        "while",
        "who",
        "what",
        "which",
        "how",
        "why",
        "not",
        "no",
        "nor",
        "so",
        "too",
        "very",
        "just",
        "only",
        "also",
        "even",
        "still",
        "he",
        "she",
        "it",
        "they",
        "them",
        "his",
        "her",
        "their",
        "its",
        "him",
        "me",
        "my",
        "we",
        "us",
        "our",
        "you",
        "your",
        "i",
        "am",
        "is",
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
        "could",
        "should",
        "may",
        "might",
        "must",
        "can",
        "said",
        "says",
        "asked",
        "muttered",
    }
)

# Spelled number / quantity tokens for procedural SI gram rejector (KD-8 / KD-16).
_NUMBER_WORDS = frozenset(
    {
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
        "eleven",
        "twelve",
        "thirteen",
        "fourteen",
        "fifteen",
        "sixteen",
        "seventeen",
        "eighteen",
        "nineteen",
        "twenty",
        "thirty",
        "forty",
        "fifty",
        "sixty",
        "seventy",
        "eighty",
        "ninety",
        "hundred",
        "thousand",
    }
)


def _norm_token(tok: str) -> str:
    low = tok.lower().replace("-", "")
    if low.endswith("'s"):
        return low[:-2]
    if len(low) > 3 and low.endswith("s") and not low.endswith("ss"):
        return low[:-1]
    return low


def _content_tokens(text: str) -> list[tuple[str, int, int, str]]:
    """Return (norm, start, end, surface) for tokens."""
    out: list[tuple[str, int, int, str]] = []
    for m in _TOKEN_RE.finditer(text or ""):
        surface = m.group(0)
        norm = _norm_token(surface)
        if not norm:
            continue
        out.append((norm, m.start(), m.end(), surface))
    return out


def _is_procedural_si_gram(norms: list[str]) -> bool:
    """True when gram is numeric/quantity + SI/time unit shaped (KD-8)."""
    if len(norms) < 2:
        return False
    # Both tokens numeric+unit shaped, or first number-like and last a unit.
    unitish = SI_UNIT_LEMMAS | {"pace", "paces"}
    if norms[-1] in unitish and (
        norms[0] in _NUMBER_WORDS or norms[0].isdigit() or norms[0] in unitish
    ):
        return True
    return all(t in _NUMBER_WORDS or t in unitish or t.isdigit() for t in norms)


def _candidate_ngrams(
    tokens: list[tuple[str, int, int, str]],
) -> list[tuple[str, int, str]]:
    """Adjacent 2–3-grams → (phrase, start, first_surface)."""
    phrases: list[tuple[str, int, str]] = []
    n = len(tokens)
    for i in range(n):
        for width in (2, 3):
            if i + width > n:
                continue
            window = tokens[i : i + width]
            adjacent = True
            for a, b in zip(window, window[1:], strict=False):
                gap = b[1] - a[2]
                if gap > 2:
                    adjacent = False
                    break
            if not adjacent:
                continue
            norms = [t[0] for t in window]
            if any(len(t) < 3 for t in norms):
                continue
            if norms[0] in _STOPWORDS or norms[-1] in _STOPWORDS:
                continue
            if any(t in _STOPWORDS for t in norms):
                continue
            if _is_procedural_si_gram(norms):
                continue
            phrase = " ".join(norms)
            phrases.append((phrase, window[0][1], window[0][3]))
    return phrases


def _severity(count: int) -> str:
    if count >= 4:
        return "high"
    if count >= 2:
        return "moderate"
    return "low"


def _quote(body: str, token: str) -> str | None:
    q = quote_from_text(token, body)
    if q:
        return q
    idx = body.lower().find(token.lower())
    if idx < 0:
        return None
    left = max(0, idx - 40)
    return body[left : left + 160].strip() or None


def detect_phrase_thrash(
    content: str,
    *,
    chapter_number: int,
    fuse: int = PHRASE_THRASH_FUSE,
) -> list[ThrashFinding]:
    """Adjacent literary 2–3-grams repeated ≥fuse (kind=phrase; lemma=None)."""
    body = strip_chapter_body(content or "")
    if not body.strip():
        return []
    grams = _candidate_ngrams(_content_tokens(body))
    if not grams:
        return []
    counts: Counter[str] = Counter(p for p, _start, _surf in grams)
    first_hit: dict[str, tuple[int, str]] = {}
    for phrase, start, surface in grams:
        if phrase not in first_hit:
            first_hit[phrase] = (start, surface)

    need = max(1, int(fuse))
    findings: list[ThrashFinding] = []
    for phrase, n in counts.items():
        if n < need:
            continue
        _start, foothold = first_hit[phrase]
        findings.append(
            ThrashFinding(
                kind="phrase",
                lemma=None,
                phrase=phrase,
                severity=_severity(n),
                count=n,
                chapters=[chapter_number],
                chapter=chapter_number,
                scene_index=None,
                quote=_quote(body, foothold),
                normalized_key=phrase,
                foothold_token=foothold,
                later_surfaces=[],
            )
        )
    findings.sort(key=lambda f: (-f.count, f.phrase or ""))
    return findings


__all__ = ["PHRASE_THRASH_FUSE", "detect_phrase_thrash"]
