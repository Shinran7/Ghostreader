"""Heuristic register / initiation-budget detector (no LLM).

Detects unexplained italic/coined and institutional hyphen terms in a
chapter opening window. Emits machine rows for companion/analyze export.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from ghostreader.companion.register_constants import (
    HYPHEN_DENYLIST,
    INITIATION_BUDGET_COINED_NOUNS,
    INITIATION_BUDGET_WINDOW_WORDS,
)

if TYPE_CHECKING:
    from ghostreader.ingestion import Chapter

# YAML frontmatter: opening --- … --- (optional BOM). Idempotent if absent.
_FRONTMATTER_RE = re.compile(
    r"\A\ufeff?\s*---\r?\n.*?\r?\n---\r?\n?",
    re.DOTALL,
)

# *italic* spans; optional trailing -compound (*bhandari*-chain → bhandari-chain).
_ITALIC_RE = re.compile(r"(?<!\*)\*([A-Za-z][A-Za-z0-9']*)\*(?:-([A-Za-z][A-Za-z0-9']*))?")

# Plain institutional hyphen compounds (lowercase-ish content words).
_HYPHEN_RE = re.compile(r"\b([A-Za-z]+(?:-[A-Za-z]+)+)\b")

_TEACH_IN_RE = re.compile(
    r"(?:"
    r"\b(?:was|were|is|are)\s+called\b"
    r"|\bknown\s+as\b"
    r"|\bmeans?\b"
    r"|\bnamed\b"
    r"|[\(\[][^)\]]{1,80}[\)\]]"
    r")",
    re.IGNORECASE,
)

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


@dataclass
class RegisterCandidate:
    """One coined / institutional term hit inside the opening window."""

    term: str
    normalized_key: str
    char_start: int
    char_end: int
    span_start_word: int
    span_end_word: int
    quote: str
    taught: bool = False


@dataclass
class RegisterFinding:
    """Raw machine finding before companion/analyze projection."""

    kind: str
    severity: str
    summary: str
    quote: str | None = None
    span_start_word: int | None = None
    span_end_word: int | None = None
    term: str | None = None
    window_words: int = INITIATION_BUDGET_WINDOW_WORDS
    coined_count: int | None = None
    budget: int | None = None
    chapter: int = 0
    normalized_key: str | None = None


@dataclass
class RegisterReport:
    """Detector output for one chapter opening."""

    findings: list[RegisterFinding] = field(default_factory=list)
    candidates: list[RegisterCandidate] = field(default_factory=list)
    window_word_count: int = 0
    unexplained_count: int = 0
    body: str = ""
    window_text: str = ""


def strip_chapter_body(content: str) -> str:
    """Return prose body after YAML frontmatter (--- … ---). Idempotent if none."""
    if not content:
        return ""
    match = _FRONTMATTER_RE.match(content)
    if match is None:
        return content
    return content[match.end() :]


def _whitespace_tokens(text: str) -> list[str]:
    return text.split()


def _char_to_word_index(text: str, char_pos: int) -> int:
    """Map a character offset in *text* to a 0-based whitespace-token index."""
    if char_pos <= 0:
        return 0
    prefix = text[:char_pos]
    # Tokens fully before char_pos; if mid-token, still that token index.
    tokens_before = len(prefix.split())
    if prefix and not prefix[-1].isspace() and tokens_before > 0:
        return tokens_before - 1
    return tokens_before


def _quote_around(text: str, start: int, end: int, *, max_len: int = 160) -> str:
    sent_start = text.rfind(".", 0, start)
    sent_start = 0 if sent_start < 0 else sent_start + 1
    ends = [i for i in (text.find(p, end) for p in (".", "!", "?")) if i != -1]
    sent_end = (min(ends) + 1) if ends else min(len(text), end + 80)
    quote = text[sent_start:sent_end].strip()
    if len(quote) > max_len:
        local = start - sent_start
        left = max(0, local - max_len // 3)
        quote = quote[left : left + max_len].strip()
    return quote or text[start:end]


def _sentence_spans(text: str) -> list[tuple[int, int]]:
    if not text.strip():
        return []
    spans: list[tuple[int, int]] = []
    pos = 0
    for part in _SENTENCE_SPLIT_RE.split(text):
        if not part:
            continue
        start = text.find(part, pos)
        if start < 0:
            start = pos
        end = start + len(part)
        spans.append((start, end))
        pos = end
    return spans or [(0, len(text))]


def _is_taught(term: str, window_text: str, char_start: int) -> bool:
    """Cheap teach-in: gloss / called / means / parenthetical within ±2 sentences."""
    spans = _sentence_spans(window_text)
    if not spans:
        return False
    idx = 0
    for i, (s, e) in enumerate(spans):
        if s <= char_start < e:
            idx = i
            break
        if char_start < s:
            idx = i
            break
        idx = i
    lo = max(0, idx - 2)
    hi = min(len(spans), idx + 3)
    neighborhood = window_text[spans[lo][0] : spans[hi - 1][1]]
    # Term must appear near a teach-in cue in the neighborhood.
    if not re.search(rf"(?i)(?<!\w){re.escape(term)}(?!\w)", neighborhood):
        return False
    return _TEACH_IN_RE.search(neighborhood) is not None


def _normalized_key(term: str) -> str:
    return re.sub(r"\s+", " ", term.strip().lower())


def _collect_candidates(window_text: str) -> list[RegisterCandidate]:
    """Italic + institutional hyphen candidates; no Title Case places."""
    hits: dict[str, RegisterCandidate] = {}

    def _consider(term: str, start: int, end: int) -> None:
        clean = term.strip(".,;:!?\"'")
        if not clean or "-" in clean and _normalized_key(clean) in HYPHEN_DENYLIST:
            return
        key = _normalized_key(clean)
        if key in HYPHEN_DENYLIST:
            return
        # Skip pure Title-Case multiword places (no hyphen / not italic path).
        if " " in clean:
            return
        if key in hits:
            return
        w0 = _char_to_word_index(window_text, start)
        w1 = _char_to_word_index(window_text, max(start, end - 1)) + 1
        hits[key] = RegisterCandidate(
            term=clean,
            normalized_key=key,
            char_start=start,
            char_end=end,
            span_start_word=w0,
            span_end_word=w1,
            quote=_quote_around(window_text, start, end),
            taught=_is_taught(clean, window_text, start),
        )

    for m in _ITALIC_RE.finditer(window_text):
        base = m.group(1)
        tail = m.group(2)
        term = f"{base}-{tail}" if tail else base
        _consider(term, m.start(), m.end())

    for m in _HYPHEN_RE.finditer(window_text):
        term = m.group(1)
        key = _normalized_key(term)
        if key in HYPHEN_DENYLIST:
            continue
        # Avoid double-counting italic+hyphen already recorded.
        if key in hits:
            continue
        # Skip Title-Case-looking place compounds (Ashfall-Stair) in v1.
        if term[0].isupper() and any(p[:1].isupper() for p in term.split("-")[1:]):
            continue
        _consider(term, m.start(), m.end())

    return sorted(hits.values(), key=lambda c: c.char_start)


def _budget_severity(overrun: int) -> str:
    if overrun >= 2:
        return "high"
    if overrun >= 1:
        return "moderate"
    return "low"


def _jargon_severity(rank: int, unexplained_count: int) -> str:
    if unexplained_count >= INITIATION_BUDGET_COINED_NOUNS + 2 and rank < 3:
        return "high"
    if rank < 5:
        return "moderate"
    return "low"


def _opening_window_text(body: str, window_n: int) -> tuple[str, list[str]]:
    """Return (prefix of *body* covering first *window_n* tokens, those tokens)."""
    tokens = _whitespace_tokens(body)
    window_tokens = tokens[: max(0, window_n)]
    if not window_tokens:
        return "", []
    search_from = 0
    consumed = 0
    for tok in window_tokens:
        idx = body.find(tok, search_from)
        if idx < 0:
            break
        consumed = idx + len(tok)
        search_from = consumed
    return (body[:consumed] if consumed else " ".join(window_tokens)), window_tokens


def detect_register(
    content: str,
    *,
    chapter_number: int = 0,
    window_words: int = INITIATION_BUDGET_WINDOW_WORDS,
    budget: int = INITIATION_BUDGET_COINED_NOUNS,
) -> RegisterReport:
    """Run opening-window register heuristic on chapter *content* (may include YAML)."""
    body = strip_chapter_body(content)
    window_n = max(0, int(window_words))
    window_text, window_tokens = _opening_window_text(body, window_n)
    if not window_tokens:
        return RegisterReport(body=body, window_text="")

    candidates = _collect_candidates(window_text)
    unexplained = [c for c in candidates if not c.taught]
    findings: list[RegisterFinding] = []

    unexplained_count = len(unexplained)
    if unexplained_count > budget:
        overrun = unexplained_count - budget
        top_terms = ", ".join(c.term for c in unexplained[:6])
        findings.append(
            RegisterFinding(
                kind="initiation_budget",
                severity=_budget_severity(overrun),
                summary=(
                    f"{unexplained_count} unexplained coined/institutional nouns "
                    f"in first {window_n} words (budget {budget})"
                    + (f": {top_terms}" if top_terms else ".")
                ),
                quote=unexplained[0].quote if unexplained else window_text[:160],
                span_start_word=0,
                span_end_word=min(window_n, len(window_tokens)),
                term=None,
                window_words=window_n,
                coined_count=unexplained_count,
                budget=budget,
                chapter=chapter_number,
                normalized_key=f"initiation_budget:{chapter_number}",
            )
        )

    for rank, cand in enumerate(unexplained):
        findings.append(
            RegisterFinding(
                kind="unearned_jargon",
                severity=_jargon_severity(rank, unexplained_count),
                summary=f"Coined/institutional term appears before teach-in: {cand.term}",
                quote=cand.quote,
                span_start_word=cand.span_start_word,
                span_end_word=cand.span_end_word,
                term=cand.term,
                window_words=window_n,
                coined_count=None,
                budget=None,
                chapter=chapter_number,
                normalized_key=cand.normalized_key,
            )
        )

    return RegisterReport(
        findings=findings,
        candidates=candidates,
        window_word_count=len(window_tokens),
        unexplained_count=unexplained_count,
        body=body,
        window_text=window_text,
    )


def detect_register_for_chapter(chapter: Chapter) -> RegisterReport:
    """Run detector on a loaded ``Chapter`` (content may include YAML frontmatter)."""
    return detect_register(
        chapter.content,
        chapter_number=chapter.chapter_number,
    )


__all__ = [
    "RegisterCandidate",
    "RegisterFinding",
    "RegisterReport",
    "detect_register",
    "detect_register_for_chapter",
    "strip_chapter_body",
]
