"""Verify that LLM finding quotes exist in the manuscript, and locate them (#17).

An invented quote is worse than no finding. Every LLM finding's ``evidence``
(and ``counter_evidence``) is checked against the chapter text:

1. exact substring,
2. normalized (curly quotes, dashes, whitespace, case, markdown emphasis),
3. fuzzy (token-window similarity >= ``FUZZY_THRESHOLD``, quotes of 5+ words).

Evidence strings follow the prompt convention ``Ch 3: 'quoted words'``. Several
chapter-prefixed quotes may appear in one string, and ``...`` marks elisions.
Every quoted part must match for the field to count as verified.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass
from difflib import SequenceMatcher
from typing import Any, Literal

MatchKind = Literal["exact", "normalized", "fuzzy"]

FUZZY_THRESHOLD = 0.9
MIN_WORDS = 3
FUZZY_MIN_WORDS = 5

_KIND_RANK = {"exact": 0, "normalized": 1, "fuzzy": 2}

_CH_SPLIT = re.compile(
    r"(?:^|(?<=[\s;,.\n]))(?:Ch(?:apters?|s)?\.?|Chapter)\s*(\d+)\s*(?:[:—–]|-\s)\s*",
    re.IGNORECASE,
)
_ELLIPSIS = re.compile(r"\s*(?:\[\s*(?:\.\s*){3}\]|\.{3,}|…)\s*")
_EDGE = "'\"‘’“”`*_ \t\n,;:"
_TRANSLATE = str.maketrans(
    {
        "‘": "'",
        "’": "'",
        "‚": "'",
        "‛": "'",
        "′": "'",
        "“": '"',
        "”": '"',
        "„": '"',
        "″": '"',
        "—": "-",
        "–": "-",
        "‒": "-",
        "‑": "-",
        "‐": "-",
        " ": " ",
    }
)
_DROP = set("*_`")
_WORD = re.compile(r"[a-z0-9']+")
_TRAILING_JOIN = re.compile(r"\s+(?:and|vs\.?|versus|while|but|or)\s*$", re.IGNORECASE)


@dataclass(frozen=True)
class QuoteLocation:
    chapter: int
    paragraph: int
    line: int
    char_start: int
    char_end: int
    match: MatchKind

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class _Text:
    number: int
    raw: str
    norm: str
    index: tuple[int, ...]  # norm position -> raw position
    words: tuple[str, ...]
    word_starts: tuple[int, ...]  # norm offsets of each word


def _normalize(text: str) -> tuple[str, list[int]]:
    """Lowercase, fold quotes/dashes, collapse whitespace, drop emphasis marks.

    Returns the normalized string and a map from each normalized char to its
    raw offset, so matches can be reported in raw coordinates.
    """
    out: list[str] = []
    index: list[int] = []
    prev_space = True
    for i, ch in enumerate(text):
        if ch in _DROP:
            continue
        c = ch.translate(_TRANSLATE).lower()
        if c == "…":
            for _ in range(3):
                out.append(".")
                index.append(i)
            prev_space = False
            continue
        if c.isspace():
            if prev_space:
                continue
            out.append(" ")
            index.append(i)
            prev_space = True
            continue
        out.append(c)
        index.append(i)
        prev_space = False
    if out and out[-1] == " ":
        out.pop()
        index.pop()
    return "".join(out), index


def _prepare(number: int, raw: str) -> _Text:
    norm, index = _normalize(raw)
    words: list[str] = []
    starts: list[int] = []
    for m in _WORD.finditer(norm):
        words.append(m.group(0))
        starts.append(m.start())
    return _Text(number, raw, norm, tuple(index), tuple(words), tuple(starts))


def _chapter_items(chapters: Iterable[Any]) -> list[tuple[int, str]]:
    items: list[tuple[int, str]] = []
    for ch in chapters:
        if isinstance(ch, Mapping):
            num, content = ch.get("chapter_number"), ch.get("content")
        else:
            num, content = getattr(ch, "chapter_number", None), getattr(ch, "content", None)
        if num is None or not content:
            continue
        items.append((int(num), str(content)))
    return items


class QuoteIndex:
    """Normalized chapter texts, built once per run."""

    def __init__(self, chapters: Iterable[Any]) -> None:
        self._texts = {n: _prepare(n, raw) for n, raw in _chapter_items(chapters)}

    def __bool__(self) -> bool:
        return bool(self._texts)

    @property
    def chapter_numbers(self) -> list[int]:
        return sorted(self._texts)

    def text(self, number: int) -> str | None:
        t = self._texts.get(number)
        return t.raw if t else None

    def _order(self, prefer: Sequence[int]) -> list[_Text]:
        seen: set[int] = set()
        out: list[_Text] = []
        for n in [*prefer, *sorted(self._texts)]:
            if n in self._texts and n not in seen:
                seen.add(n)
                out.append(self._texts[n])
        return out

    def locate(
        self, quote: str, *, prefer: Sequence[int] = (), min_words: int = MIN_WORDS
    ) -> QuoteLocation | None:
        """Find one quote part. Cited chapters (``prefer``) are searched first."""
        q = quote.strip(_EDGE)
        qnorm, _ = _normalize(q)
        qwords = _WORD.findall(qnorm)
        if not qwords or len(qwords) < min_words:
            return None
        order = self._order(prefer)
        for t in order:
            pos = t.raw.find(q)
            if pos != -1:
                return _location(t, pos, pos + len(q), "exact")
        for t in order:
            pos = t.norm.find(qnorm)
            if pos != -1:
                start = t.index[pos]
                end = t.index[pos + len(qnorm) - 1] + 1
                return _location(t, start, end, "normalized")
        if len(qwords) < FUZZY_MIN_WORDS:
            return None
        best: tuple[float, _Text, int, int] | None = None
        for t in order:
            hit = _fuzzy(t, qwords)
            if hit and (best is None or hit[0] > best[0]):
                best = (hit[0], t, hit[1], hit[2])
            if best and best[0] >= 0.98:
                break
        if best is None:
            return None
        _, t, w0, w1 = best
        start = t.index[t.word_starts[w0]]
        last = t.word_starts[w1 - 1] + len(t.words[w1 - 1]) - 1
        return _location(t, start, t.index[last] + 1, "fuzzy")


def _fuzzy(t: _Text, qwords: list[str]) -> tuple[float, int, int] | None:
    n = len(qwords)
    if len(t.words) < n - 1:
        return None
    target = " ".join(qwords)
    qset = set(qwords)
    need = max(1, int(len(qset) * 0.6))
    best: tuple[float, int, int] | None = None
    for size in (n, n - 1, n + 1):
        if size < 1 or size > len(t.words):
            continue
        for w0 in range(len(t.words) - size + 1):
            window = t.words[w0 : w0 + size]
            if len(qset.intersection(window)) < need:
                continue
            sm = SequenceMatcher(None, target, " ".join(window), autojunk=False)
            if sm.real_quick_ratio() < FUZZY_THRESHOLD or sm.quick_ratio() < FUZZY_THRESHOLD:
                continue
            r = sm.ratio()
            if r >= FUZZY_THRESHOLD and (best is None or r > best[0]):
                best = (r, w0, w0 + size)
    return best


def _location(t: _Text, start: int, end: int, kind: MatchKind) -> QuoteLocation:
    before = t.raw[:start]
    paragraph = len(re.findall(r"\n[ \t]*\n+", before)) + 1
    line = before.count("\n") + 1
    return QuoteLocation(t.number, paragraph, line, start, end, kind)


def quote_parts(text: str) -> list[tuple[int | None, str]]:
    """Split an evidence string into ``(cited_chapter, quote_part)`` pairs."""
    text = (text or "").strip()
    if not text:
        return []
    pieces: list[tuple[int | None, str]] = []
    matches = list(_CH_SPLIT.finditer(text))
    if not matches:
        pieces.append((None, text))
    else:
        head = text[: matches[0].start()].strip(_EDGE)
        if head:
            pieces.append((None, head))
        for i, m in enumerate(matches):
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            pieces.append((int(m.group(1)), text[m.end() : end]))
    out: list[tuple[int | None, str]] = []
    for ch, piece in pieces:
        piece = _TRAILING_JOIN.sub("", piece.strip().rstrip(";,"))
        for part in _ELLIPSIS.split(piece):
            part = part.strip(_EDGE)
            if part:
                out.append((ch, part))
    return out


@dataclass(frozen=True)
class FieldCheck:
    verified: bool
    location: QuoteLocation | None
    match: MatchKind | None


def check_field(
    index: QuoteIndex, text: str, *, prefer: Sequence[int] = ()
) -> FieldCheck:
    """Verify every quote part in one evidence field."""
    parts = quote_parts(text)
    if not parts:
        return FieldCheck(False, None, None)
    # At least one part must be a real quote (MIN_WORDS); short elided
    # fragments ("... slow paths") may then match with fewer words.
    sizes = [len(_WORD.findall(_normalize(p)[0])) for _, p in parts]
    if max(sizes) < MIN_WORDS:
        return FieldCheck(False, None, None)
    first: QuoteLocation | None = None
    worst: MatchKind = "exact"
    for ch, part in parts:
        pref = [ch, *prefer] if ch is not None else list(prefer)
        loc = index.locate(part, prefer=pref, min_words=1 if len(parts) > 1 else MIN_WORDS)
        if loc is None:
            return FieldCheck(False, None, None)
        if first is None:
            first = loc
        if _KIND_RANK[loc.match] > _KIND_RANK[worst]:
            worst = loc.match
    return FieldCheck(True, first, worst)


def finding_id(finding: Mapping[str, Any]) -> str:
    """Stable id: dimension + quote span (or normalized evidence)."""
    dim = str(finding.get("dimension") or "")
    loc = finding.get("location")
    if isinstance(loc, Mapping) and loc.get("chapter") is not None:
        key = f"{dim}|{loc.get('chapter')}|{loc.get('char_start')}|{loc.get('char_end')}"
    else:
        ev, _ = _normalize(str(finding.get("evidence") or ""))
        key = f"{dim}|{finding.get('chapter_ref') or ''}|{ev}"
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]


UNVERIFIED_PREFIX = "Unverified quote"
# Dimensions whose evidence is often counts or word lists from algorithmic data,
# not passages: tagged, never demoted or dropped.
QUOTE_EXEMPT_DIMS = frozenset({"prose.repetition"})


def quote_required(finding: Mapping[str, Any]) -> bool:
    return str(finding.get("dimension") or "") not in QUOTE_EXEMPT_DIMS


def canon_counter(finding: Mapping[str, Any]) -> bool:
    """True when ``counter_evidence`` is a Canon entry, not a manuscript quote (#16)."""
    return finding.get("counter_source") == "canon" or str(
        finding.get("counter_evidence") or ""
    ).startswith("Canon ")


def verify_finding(
    finding: Mapping[str, Any],
    index: QuoteIndex,
    *,
    prefer: Sequence[int] = (),
    demote: bool = True,
) -> dict[str, Any]:
    """Return a copy with ``quote_verified``, ``location`` and ``id`` set.

    ``quote_verified`` is true only when ``evidence`` verifies and, when
    present, ``counter_evidence`` verifies too (a Canon entry as counter
    evidence is exact by construction and is not looked up). When ``demote`` is set, an
    unverified ``concern`` becomes ``neutral`` with an ``Unverified quote``
    summary prefix, so it cannot gate or rank as a concern.
    """
    out = dict(finding)
    ev = check_field(index, str(out.get("evidence") or ""), prefer=prefer)
    counter_text = str(out.get("counter_evidence") or "").strip()
    counter_ok = True
    counter_loc: QuoteLocation | None = None
    if counter_text and not canon_counter(out):
        cc = check_field(index, counter_text, prefer=prefer)
        counter_ok = cc.verified
        counter_loc = cc.location
    verified = ev.verified and counter_ok
    out["quote_verified"] = verified
    out["location"] = ev.location.as_dict() if ev.location else None
    if counter_loc is not None:
        out["counter_location"] = counter_loc.as_dict()
    if not verified and demote and out.get("severity") == "concern" and quote_required(out):
        out["severity"] = "neutral"
        summary = str(out.get("summary") or "").strip()
        out["summary"] = f"{UNVERIFIED_PREFIX}: {summary}" if summary else UNVERIFIED_PREFIX
    out["id"] = finding_id(out)
    return out


def verify_findings(
    findings: Iterable[Mapping[str, Any]],
    index: QuoteIndex,
    *,
    prefer_fn: Any = None,
    demote: bool = True,
) -> tuple[list[dict[str, Any]], int]:
    """Verify many findings. Returns ``(findings, demoted_concern_count)``.

    Strengths and neutrals are tagged but never changed.
    """
    out: list[dict[str, Any]] = []
    demoted = 0
    for f in findings:
        prefer = prefer_fn(f) if prefer_fn else ()
        v = verify_finding(f, index, prefer=sorted(prefer), demote=demote)
        if f.get("severity") == "concern" and v.get("severity") != "concern":
            demoted += 1
        out.append(v)
    return out, demoted


__all__ = [
    "QUOTE_EXEMPT_DIMS",
    "canon_counter",
    "quote_required",
    "FUZZY_THRESHOLD",
    "UNVERIFIED_PREFIX",
    "FieldCheck",
    "QuoteIndex",
    "QuoteLocation",
    "check_field",
    "finding_id",
    "quote_parts",
    "verify_finding",
    "verify_findings",
]
