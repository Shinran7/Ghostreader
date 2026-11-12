"""Dialogue shape: tennis volleys, missing long speeches, too-fluent speech (#21).

Deterministic, no LLM. Reads double-quoted speech (straight or curly) per
paragraph. One paragraph with speech is one turn (the usual prose convention:
a new speaker starts a new paragraph).

Thresholds come from a 2026-11-12 baseline of ten public-domain novels
(Austen, Doyle, Christie, Twain, Fitzgerald, Barrie) against recent
Autonomicon stories:

- Hesitant turns (trailing off, broken-off lines, fillers, hedges): human
  chapters rarely fall under 5%; Autonomicon chapters sit at 0-4%.
- Turns of 40+ spoken words: most human chapters 5-25%; tennis-heavy
  Autonomicon chapters 0-3%.
- Volleys of 10+ short turns occur in human books (cross-examination, Peter
  Pan) but are rare; one Autonomicon chapter ran 23.

Rows are watch signals, not defects: a single volley or a terse chapter can be
the right call. The pattern across chapters is what matters.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any

# Speech inside double quotes. An unclosed quote runs to the paragraph end
# (multi-paragraph speeches leave the closing quote off until the last one).
_QUOTE = re.compile(r"[\"\u201c]([^\"\u201c\u201d]*)[\"\u201d]?")
_WORD = re.compile(r"[A-Za-z0-9]+(?:['\u2019][A-Za-z]+)*")

SHORT_TURN_WORDS = 12
LONG_TURN_WORDS = 40
# Narration longer than this ends a volley; shorter beats sit inside it.
VOLLEY_BREAK_WORDS = 30
VOLLEY_MIN_TURNS = 10
VOLLEY_HIGH_TURNS = 16
# Below this share of 40+ word turns, a volley counts as replacing long speech.
STARVED_LONG_SHARE = 0.03
# Chapter-level rows need enough speech to mean anything.
MIN_TURNS_FOR_CHAPTER_ROWS = 25
FLUENT_MODERATE_SHARE = 0.05
FLUENT_HIGH_SHARE = 0.02

HESITATION_MARKERS: dict[str, re.Pattern[str]] = {
    "broken_off": re.compile(r"\u2014|--|\u2013"),
    "trailing_off": re.compile(r"\.\.\.|\u2026|\. \. \."),
    "filler": re.compile(
        r"\b(?:um+|uh+|er+|erm|hmm+|(?<!as )well|I mean|you know|sort of|kind of|"
        r"or something|or whatever|I dunno|look,|listen,|oh)\b",
        re.IGNORECASE,
    ),
    "hedge": re.compile(
        r"\b(?:maybe|perhaps|I guess|I think|I suppose|probably|I'm not sure|"
        r"I don't know|not sure|might|seems?|I believe)\b",
        re.IGNORECASE,
    ),
    "restart": re.compile(r"\b(\w{1,6})[-\u2014]\s?\1\b", re.IGNORECASE),
}


@dataclass
class Turn:
    """One paragraph that carries speech."""

    paragraph: int
    spoken: str
    spoken_words: int
    hesitations: list[str] = field(default_factory=list)


@dataclass
class DialogueShapeStats:
    """Per-chapter dialogue measurements."""

    chapter: int
    turns: int = 0
    words: int = 0
    spoken_words: int = 0
    dialogue_share: float = 0.0
    short_turn_share: float = 0.0
    long_turn_share: float = 0.0
    hesitant_turn_share: float = 0.0
    hesitation_counts: dict[str, int] = field(default_factory=dict)
    longest_turn_words: int = 0
    longest_volley: int = 0


@dataclass
class DialogueShapeFinding:
    """One watch row."""

    kind: str  # volley | no_long_speech | fluent_speech
    severity: str  # high | moderate | low
    chapter: int
    summary: str
    quote: str = ""
    turns: int = 0
    start_paragraph: int = 0
    metric: float = 0.0


@dataclass
class DialogueShapeReport:
    stats: DialogueShapeStats
    findings: list[DialogueShapeFinding] = field(default_factory=list)


def _strip_front_matter(text: str) -> str:
    if text.startswith("---"):
        parts = text.split("\n---", 1)
        if len(parts) == 2:
            return parts[1].split("\n", 1)[1] if "\n" in parts[1] else ""
    return text


def split_paragraphs(text: str) -> list[str]:
    """Blank-line paragraphs, whitespace collapsed; headings and rules dropped."""
    text = _strip_front_matter(text.replace("\r\n", "\n"))
    out: list[str] = []
    for raw in re.split(r"\n\s*\n", text):
        para = re.sub(r"\s+", " ", raw).strip()
        if not para or para.startswith("#") or set(para) <= set("*-_ "):
            continue
        out.append(para)
    return out


def word_count(text: str) -> int:
    return len(_WORD.findall(text))


def extract_turns(paragraphs: list[str]) -> list[Turn | None]:
    """One entry per paragraph: a Turn, or None for pure narration."""
    out: list[Turn | None] = []
    for i, para in enumerate(paragraphs):
        spans = [s.strip() for s in _QUOTE.findall(para) if s.strip()]
        if not spans:
            out.append(None)
            continue
        spoken = " ".join(spans)
        hes = [name for name, pat in HESITATION_MARKERS.items() if pat.search(spoken)]
        out.append(Turn(i, spoken, word_count(spoken), hes))
    return out


def _volleys(paragraphs: list[str], turns: list[Turn | None]) -> list[list[Turn]]:
    """Runs of consecutive short turns; short narration beats stay inside."""
    runs: list[list[Turn]] = []
    cur: list[Turn] = []
    for para, turn in zip(paragraphs, turns, strict=True):
        if turn is None:
            if word_count(para) > VOLLEY_BREAK_WORDS:
                if cur:
                    runs.append(cur)
                cur = []
            continue
        if turn.spoken_words <= SHORT_TURN_WORDS:
            cur.append(turn)
        else:
            if cur:
                runs.append(cur)
            cur = []
    if cur:
        runs.append(cur)
    return runs


def _clip(text: str, limit: int = 60) -> str:
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "\u2026"


def detect_dialogue_shape(text: str, *, chapter_number: int = 1) -> DialogueShapeReport:
    """Measure one chapter and emit watch rows."""
    paragraphs = split_paragraphs(text)
    turn_slots = extract_turns(paragraphs)
    turns = [t for t in turn_slots if t is not None]
    stats = DialogueShapeStats(chapter=chapter_number)
    stats.words = sum(word_count(p) for p in paragraphs)
    report = DialogueShapeReport(stats=stats)
    if not turns:
        return report

    n = len(turns)
    stats.turns = n
    stats.spoken_words = sum(t.spoken_words for t in turns)
    stats.dialogue_share = round(stats.spoken_words / max(stats.words, 1), 3)
    stats.short_turn_share = round(sum(t.spoken_words <= SHORT_TURN_WORDS for t in turns) / n, 3)
    stats.long_turn_share = round(sum(t.spoken_words >= LONG_TURN_WORDS for t in turns) / n, 3)
    hesitant = sum(1 for t in turns if t.hesitations)
    stats.hesitant_turn_share = round(hesitant / n, 3)
    stats.hesitation_counts = {
        name: sum(1 for t in turns if name in t.hesitations) for name in HESITATION_MARKERS
    }
    stats.longest_turn_words = max(t.spoken_words for t in turns)
    volleys = _volleys(paragraphs, turn_slots)
    stats.longest_volley = max((len(v) for v in volleys), default=0)

    # Human books volley too (cross-examination, children's books), so a volley
    # alone is low. It rises only when the chapter also starves long speech:
    # the tennis match standing in for an extended answer.
    starved = stats.long_turn_share < STARVED_LONG_SHARE
    for run in volleys:
        if len(run) < VOLLEY_MIN_TURNS:
            continue
        if not starved:
            sev = "low"
        else:
            sev = "high" if len(run) >= VOLLEY_HIGH_TURNS else "moderate"
        long_pct = round(stats.long_turn_share * 100)
        few = "None" if long_pct == 0 else f"Only {long_pct}%"
        why = (
            f" {few} of this chapter's turns run {LONG_TURN_WORDS}+ words, so the "
            "volley may be standing in for a longer answer."
            if starved
            else ""
        )
        report.findings.append(
            DialogueShapeFinding(
                kind="volley",
                severity=sev,
                chapter=chapter_number,
                summary=(
                    f"{len(run)} one-line turns in a row (each {SHORT_TURN_WORDS} spoken words "
                    "or fewer). Check that this is a deliberate rapid exchange, not a "
                    "tennis match." + why
                ),
                quote=" / ".join(_clip(t.spoken) for t in run[:4]),
                turns=len(run),
                start_paragraph=run[0].paragraph + 1,
                metric=float(len(run)),
            )
        )

    if n < MIN_TURNS_FOR_CHAPTER_ROWS:
        return report

    if stats.longest_turn_words < LONG_TURN_WORDS:
        report.findings.append(
            DialogueShapeFinding(
                kind="no_long_speech",
                severity="moderate",
                chapter=chapter_number,
                summary=(
                    f"{n} spoken turns and none runs {LONG_TURN_WORDS}+ words (longest "
                    f"{stats.longest_turn_words}). Most human chapters with this much talk "
                    "give someone room for an extended answer, story, or argument."
                ),
                turns=n,
                metric=float(stats.longest_turn_words),
            )
        )

    share = stats.hesitant_turn_share
    if share < FLUENT_MODERATE_SHARE:
        sev = "high" if share < FLUENT_HIGH_SHARE else "moderate"
        report.findings.append(
            DialogueShapeFinding(
                kind="fluent_speech",
                severity=sev,
                chapter=chapter_number,
                summary=(
                    f"Only {hesitant} of {n} spoken turns hesitate ({round(share * 100)}%): "
                    "no trailing off, broken-off lines, fillers, or hedges. Human novels run "
                    "about 15 to 35%. Speech this clean reads as scripted certainty."
                ),
                turns=n,
                metric=share,
            )
        )
    return report


_SEVERITY_RANK = {"high": 0, "moderate": 1, "low": 2}
_KIND_RANK = {"volley": 0, "no_long_speech": 1, "fluent_speech": 2}


def finding_to_dict(finding: DialogueShapeFinding) -> dict[str, Any]:
    row = asdict(finding)
    row["message"] = finding.summary
    return row


def sort_findings(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        rows,
        key=lambda r: (
            _SEVERITY_RANK.get(str(r.get("severity")), 9),
            _KIND_RANK.get(str(r.get("kind")), 9),
            -float(r.get("metric") or 0) if r.get("kind") == "volley" else 0.0,
            int(r.get("chapter") or 0),
        ),
    )


__all__ = [
    "DialogueShapeFinding",
    "DialogueShapeReport",
    "DialogueShapeStats",
    "HESITATION_MARKERS",
    "detect_dialogue_shape",
    "extract_turns",
    "finding_to_dict",
    "sort_findings",
    "split_paragraphs",
]
