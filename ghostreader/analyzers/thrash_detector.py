"""Zipf-aligned uncommon-noun thrash detector for analyze (8c6c4513 / #285).

Machine findings only in v1 — within_scene and cross_chapter kinds.
Soft prose.uncommon_thrash is deferred (KD-4).

Zipf sync obligation (KD-5): when Autonomicon
`src/autonomicon/data/en_zipf_small.json` changes, update the sibling copy
`ghostreader/data/en_zipf_small.json` in the same closeout window. Keep both
files strict JSON (no comments). Threshold 4.0 and COMMON_ENGLISH membership
must stay aligned with Autonomicon `polish_uncommon_noun_thrash`. Document
sync in non-JSON seats only (this docstring, `ghostreader/data/README.md`,
Autonomicon `docs/plans/pointer-8c6c4513-zipf-sync.md`).
"""

from __future__ import annotations

import json
import logging
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from ghostreader.analyzers.register_detector import strip_chapter_body
from ghostreader.excerpts import quote_from_text

logger = logging.getLogger(__name__)

DEFAULT_ZIPF_THRESHOLD = 4.0
_WITHIN_SCENE_CAP_PER_CHAPTER = 12
_HOUSE_SCENE_SEP = "\n\n---\n\n"
_HOUSE_SCENE_FALLBACK_RE = re.compile(r"\n---\n")
_BLANK_SCENE_RE = re.compile(r"\n\s*\n+")
_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z\-']*")

_ZIPF_PATH = Path(__file__).resolve().parent.parent / "data" / "en_zipf_small.json"

# Exact port of Autonomicon polish_uncommon_noun_thrash._COMMON_ENGLISH (KD-5 §5).
COMMON_ENGLISH = frozenset(
    {
        "a",
        "about",
        "above",
        "across",
        "actually",
        "after",
        "again",
        "air",
        "all",
        "almost",
        "along",
        "already",
        "also",
        "although",
        "am",
        "among",
        "an",
        "and",
        "animal",
        "animals",
        "another",
        "answered",
        "any",
        "anyone",
        "are",
        "arm",
        "arms",
        "as",
        "asked",
        "at",
        "back",
        "bad",
        "bag",
        "base",
        "bay",
        "be",
        "became",
        "because",
        "become",
        "been",
        "before",
        "being",
        "between",
        "big",
        "bird",
        "birds",
        "blood",
        "body",
        "bone",
        "boot",
        "boots",
        "both",
        "box",
        "boy",
        "bridge",
        "but",
        "button",
        "by",
        "cable",
        "came",
        "camp",
        "can",
        "carefully",
        "cargo",
        "cat",
        "cats",
        "chair",
        "child",
        "children",
        "city",
        "closed",
        "cloud",
        "clouds",
        "coat",
        "cold",
        "control",
        "corridor",
        "could",
        "crew",
        "dark",
        "data",
        "day",
        "deck",
        "degree",
        "degrees",
        "device",
        "did",
        "do",
        "does",
        "dog",
        "dogs",
        "door",
        "down",
        "during",
        "each",
        "eight",
        "either",
        "empty",
        "end",
        "engine",
        "enough",
        "even",
        "eventually",
        "every",
        "everything",
        "eye",
        "eyes",
        "face",
        "false",
        "far",
        "feel",
        "feet",
        "felt",
        "few",
        "field",
        "fields",
        "finally",
        "find",
        "fire",
        "first",
        "five",
        "floor",
        "foot",
        "for",
        "found",
        "four",
        "from",
        "full",
        "gave",
        "get",
        "girl",
        "give",
        "glass",
        "glove",
        "gloves",
        "good",
        "got",
        "grass",
        "great",
        "ground",
        "group",
        "had",
        "hair",
        "hall",
        "hand",
        "hands",
        "hard",
        "has",
        "have",
        "he",
        "head",
        "heat",
        "helmet",
        "her",
        "here",
        "hers",
        "high",
        "hill",
        "hills",
        "him",
        "his",
        "hold",
        "home",
        "hour",
        "hours",
        "house",
        "how",
        "however",
        "i",
        "ice",
        "if",
        "immediately",
        "in",
        "instead",
        "into",
        "is",
        "it",
        "its",
        "just",
        "keep",
        "kept",
        "knew",
        "know",
        "lab",
        "large",
        "last",
        "leaf",
        "least",
        "leave",
        "leaves",
        "left",
        "leg",
        "legs",
        "less",
        "let",
        "life",
        "light",
        "like",
        "line",
        "lines",
        "little",
        "load",
        "long",
        "look",
        "looked",
        "low",
        "machine",
        "made",
        "make",
        "man",
        "many",
        "mask",
        "may",
        "maybe",
        "me",
        "men",
        "metal",
        "might",
        "mine",
        "minute",
        "minutes",
        "moment",
        "month",
        "months",
        "moon",
        "more",
        "morning",
        "most",
        "motor",
        "mountain",
        "mountains",
        "mouth",
        "much",
        "must",
        "my",
        "name",
        "names",
        "near",
        "need",
        "needed",
        "neither",
        "new",
        "next",
        "night",
        "nine",
        "no",
        "nor",
        "not",
        "nothing",
        "ocean",
        "of",
        "off",
        "office",
        "old",
        "on",
        "once",
        "one",
        "only",
        "onto",
        "open",
        "or",
        "other",
        "our",
        "ours",
        "out",
        "over",
        "own",
        "pack",
        "panel",
        "part",
        "party",
        "path",
        "people",
        "perhaps",
        "person",
        "place",
        "planet",
        "planets",
        "power",
        "pressure",
        "put",
        "quickly",
        "quietly",
        "quite",
        "rather",
        "really",
        "replied",
        "right",
        "river",
        "road",
        "rock",
        "room",
        "said",
        "same",
        "saw",
        "says",
        "screen",
        "sea",
        "second",
        "seconds",
        "see",
        "seem",
        "seemed",
        "set",
        "seven",
        "several",
        "shall",
        "she",
        "ship",
        "short",
        "should",
        "side",
        "signal",
        "since",
        "six",
        "skin",
        "sky",
        "slowly",
        "small",
        "snow",
        "so",
        "soft",
        "some",
        "someone",
        "something",
        "sound",
        "space",
        "star",
        "stars",
        "station",
        "step",
        "steps",
        "still",
        "stone",
        "street",
        "such",
        "suddenly",
        "suit",
        "sun",
        "switch",
        "system",
        "table",
        "take",
        "team",
        "teeth",
        "temperature",
        "ten",
        "than",
        "that",
        "the",
        "their",
        "theirs",
        "them",
        "then",
        "there",
        "therefore",
        "these",
        "they",
        "thing",
        "things",
        "think",
        "this",
        "those",
        "though",
        "thought",
        "three",
        "through",
        "time",
        "to",
        "told",
        "too",
        "took",
        "tool",
        "toward",
        "towards",
        "tree",
        "trees",
        "tried",
        "true",
        "try",
        "tunnel",
        "twice",
        "two",
        "under",
        "unless",
        "unlike",
        "until",
        "up",
        "upon",
        "us",
        "very",
        "voice",
        "wall",
        "want",
        "wanted",
        "was",
        "water",
        "way",
        "we",
        "week",
        "weeks",
        "went",
        "were",
        "what",
        "when",
        "where",
        "whether",
        "which",
        "while",
        "who",
        "whom",
        "whose",
        "why",
        "will",
        "wind",
        "window",
        "wire",
        "with",
        "within",
        "without",
        "woman",
        "women",
        "word",
        "words",
        "work",
        "world",
        "would",
        "year",
        "years",
        "yes",
        "you",
        "your",
        "yours",
    }
)


_zipf_scores: dict[str, float] | None = None
_zipf_load_attempted = False
_zipf_active = False
_zipf_logged = False
_zipf_path_override: Path | None = None


@dataclass
class ThrashFinding:
    """One uncommon-noun thrash row before analyze JSON projection."""

    kind: str  # within_scene | cross_chapter
    lemma: str
    severity: str  # high | moderate | low
    count: int
    chapters: list[int] = field(default_factory=list)
    chapter: int | None = None
    scene_index: int | None = None
    quote: str | None = None
    normalized_key: str = ""
    foothold_token: str | None = None
    later_surfaces: list[str] = field(default_factory=list)


def _zipf_path() -> Path:
    return _zipf_path_override if _zipf_path_override is not None else _ZIPF_PATH


def reset_zipf_cache_for_tests(*, path: Path | None = None) -> None:
    """Test helper: clear Zipf cache; optional path override (None restores default)."""
    global _zipf_scores, _zipf_load_attempted, _zipf_active, _zipf_logged
    global _zipf_path_override
    _zipf_scores = None
    _zipf_load_attempted = False
    _zipf_active = False
    _zipf_logged = False
    _zipf_path_override = path


def ensure_zipf_loaded() -> dict[str, float]:
    """Load vendored Zipf scores; missing/unreadable → fail-soft empty."""
    global _zipf_scores, _zipf_load_attempted, _zipf_active, _zipf_logged
    if _zipf_load_attempted and _zipf_scores is not None:
        return _zipf_scores
    _zipf_load_attempted = True
    path = _zipf_path()
    if not path.is_file():
        _zipf_scores = {}
        _zipf_active = False
        if not _zipf_logged:
            logger.warning(
                "thrash_detector: Zipf vendor missing at %s; fail-soft (no thrash fire)",
                path,
            )
            _zipf_logged = True
        return _zipf_scores
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        scores: dict[str, float] = {}
        if isinstance(raw, dict):
            for key, val in raw.items():
                try:
                    scores[str(key).lower()] = float(val)
                except (TypeError, ValueError):
                    continue
        _zipf_scores = scores
        _zipf_active = bool(scores)
        if not _zipf_logged:
            logger.info(
                "thrash_detector: Zipf vendor active (%d lemmas) from %s",
                len(scores),
                path.name,
            )
            _zipf_logged = True
    except Exception:  # noqa: BLE001
        _zipf_scores = {}
        _zipf_active = False
        if not _zipf_logged:
            logger.warning(
                "thrash_detector: Zipf vendor load failed; fail-soft (no thrash fire)",
                exc_info=True,
            )
            _zipf_logged = True
    return _zipf_scores or {}


def zipf_path_active() -> bool:
    """True when vendored Zipf subset loaded successfully."""
    ensure_zipf_loaded()
    return _zipf_active


def lemma(token: str) -> str:
    """Port of Autonomicon _lemma (lower; strip 's; simple trailing s/not ss)."""
    low = token.lower()
    if low.endswith("'s"):
        return low[:-2]
    if len(low) > 3 and low.endswith("s") and not low.endswith("ss"):
        return low[:-1]
    return low


def is_uncommon(
    lemma_str: str,
    scores: dict[str, float] | None = None,
    *,
    threshold: float = DEFAULT_ZIPF_THRESHOLD,
) -> bool:
    """Uncommonness: COMMON_ENGLISH pre-filter, then Zipf < threshold.

    Missing lemma from small vendor → not uncommon (KD-5 §3).
    Empty/missing vendor scores → not uncommon (fail-soft; KD-5 §4).
    """
    if lemma_str in COMMON_ENGLISH or len(lemma_str) < 3:
        return False
    use_scores = scores if scores is not None else ensure_zipf_loaded()
    if not use_scores:
        return False
    if lemma_str in use_scores:
        return float(use_scores[lemma_str]) < threshold
    return False


def _split_scenes(body: str) -> list[str]:
    """KD-6: prefer house --- when present; else blank-line paragraphs."""
    text = body or ""
    if not text.strip():
        return []
    if _HOUSE_SCENE_SEP in text:
        return [p for p in text.split(_HOUSE_SCENE_SEP) if p.strip()]
    parts = _HOUSE_SCENE_FALLBACK_RE.split(text)
    if len(parts) > 1:
        return [p for p in parts if p.strip()]
    return [p for p in _BLANK_SCENE_RE.split(text) if p.strip()]


def _severity_for_count(count: int) -> str:
    if count >= 4:
        return "high"
    if count >= 2:
        return "moderate"
    return "low"


def _iter_candidate_tokens(
    scene: str,
    *,
    scores: dict[str, float],
    threshold: float = DEFAULT_ZIPF_THRESHOLD,
) -> list[tuple[str, str, int, int]]:
    """Yield (lemma, surface, start, end); proper-name skip spirit (KD-5 §7)."""
    out: list[tuple[str, str, int, int]] = []
    tokens = list(_TOKEN_RE.finditer(scene))
    for i, m in enumerate(tokens):
        tok = m.group(0)
        start = m.start()
        end = m.end()
        if tok[:1].isupper() and not tok.isupper():
            prefix = scene[:start].rstrip()
            mid_sentence = bool(prefix) and prefix[-1] not in ".!?\n"
            nxt = tokens[i + 1].group(0) if i + 1 < len(tokens) else ""
            multi_proper = bool(nxt) and nxt[:1].isupper() and not nxt.isupper()
            if mid_sentence or multi_proper:
                continue
        lem = lemma(tok)
        if not is_uncommon(lem, scores, threshold=threshold):
            continue
        out.append((lem, tok, start, end))
    return out


def _quote_for_scene(scene: str, token: str) -> str | None:
    q = quote_from_text(token, scene)
    if q:
        return q
    # Fallback: first 160 chars around first token occurrence.
    idx = scene.lower().find(token.lower())
    if idx < 0:
        return None
    left = max(0, idx - 40)
    return scene[left : left + 160].strip() or None


def detect_thrash_in_chapter(
    content: str,
    *,
    chapter_number: int,
    threshold: float = DEFAULT_ZIPF_THRESHOLD,
    cap_per_chapter: int = _WITHIN_SCENE_CAP_PER_CHAPTER,
) -> list[ThrashFinding]:
    """Emit within_scene findings for one chapter (count ≥ 2 uncommon lemmas)."""
    body = strip_chapter_body(content or "")
    if not body.strip():
        return []
    scores = ensure_zipf_loaded()
    findings: list[ThrashFinding] = []
    for scene_idx, scene in enumerate(_split_scenes(body)):
        by_lemma: dict[str, list[tuple[str, int, int]]] = defaultdict(list)
        for lem, tok, start, end in _iter_candidate_tokens(
            scene, scores=scores, threshold=threshold
        ):
            by_lemma[lem].append((tok, start, end))
        for lem, occurrences in by_lemma.items():
            if len(occurrences) < 2:
                continue
            surfaces = [tok for tok, _, _ in occurrences]
            later = list(dict.fromkeys(surfaces[1:]))
            foothold = surfaces[0]
            findings.append(
                ThrashFinding(
                    kind="within_scene",
                    lemma=lem,
                    severity=_severity_for_count(len(occurrences)),
                    count=len(occurrences),
                    chapters=[chapter_number],
                    chapter=chapter_number,
                    scene_index=scene_idx,
                    quote=_quote_for_scene(scene, foothold),
                    normalized_key=lem,
                    foothold_token=foothold,
                    later_surfaces=later,
                )
            )
    findings.sort(key=lambda f: (-f.count, f.lemma, f.scene_index or 0))
    return findings[: max(0, int(cap_per_chapter))]


def aggregate_cross_chapter(
    within: list[ThrashFinding],
) -> list[ThrashFinding]:
    """Roll up lemmas thrashing in ≥2 chapters (KD-19 quote selection)."""
    # lemma -> chapter -> best within_scene row (max count; ties lowest scene_index)
    best: dict[str, dict[int, ThrashFinding]] = defaultdict(dict)
    for row in within:
        if row.kind != "within_scene":
            continue
        ch = int(row.chapter or 0)
        lem = row.lemma
        prev = best[lem].get(ch)
        if prev is None:
            best[lem][ch] = row
            continue
        if (
            row.count > prev.count
            or row.count == prev.count
            and (row.scene_index or 0) < (prev.scene_index or 0)
        ):
            best[lem][ch] = row

    out: list[ThrashFinding] = []
    for lem, by_ch in best.items():
        if len(by_ch) < 2:
            continue
        chapters = sorted(by_ch.keys())
        total = sum(r.count for r in by_ch.values())
        # KD-19: chapter with max within-scene count; ties → lowest chapter number
        pick_ch = min(chapters, key=lambda c: (-by_ch[c].count, c))
        picked = by_ch[pick_ch]
        out.append(
            ThrashFinding(
                kind="cross_chapter",
                lemma=lem,
                severity=_severity_for_count(total),
                count=total,
                chapters=chapters,
                chapter=None,
                scene_index=picked.scene_index,
                quote=picked.quote,
                normalized_key=lem,
                foothold_token=picked.foothold_token,
                later_surfaces=list(picked.later_surfaces),
            )
        )
    out.sort(key=lambda f: (-f.count, f.lemma))
    return out


def detect_thrash(
    chapters: list[tuple[int, str]],
    *,
    threshold: float = DEFAULT_ZIPF_THRESHOLD,
    cap_per_chapter: int = _WITHIN_SCENE_CAP_PER_CHAPTER,
) -> list[ThrashFinding]:
    """Book-level: within_scene per chapter + cross_chapter rollup."""
    within: list[ThrashFinding] = []
    for chapter_number, content in chapters:
        within.extend(
            detect_thrash_in_chapter(
                content,
                chapter_number=chapter_number,
                threshold=threshold,
                cap_per_chapter=cap_per_chapter,
            )
        )
    cross = aggregate_cross_chapter(within)
    return within + cross


def finding_to_dict(finding: ThrashFinding) -> dict:
    """Project a ThrashFinding to analyze JSON row shape."""
    return {
        "kind": finding.kind,
        "lemma": finding.lemma,
        "severity": finding.severity,
        "count": finding.count,
        "chapters": list(finding.chapters),
        "chapter": finding.chapter,
        "scene_index": finding.scene_index,
        "quote": finding.quote,
        "normalized_key": finding.normalized_key or finding.lemma,
        "foothold_token": finding.foothold_token,
        "later_surfaces": list(finding.later_surfaces),
    }


__all__ = [
    "COMMON_ENGLISH",
    "DEFAULT_ZIPF_THRESHOLD",
    "ThrashFinding",
    "aggregate_cross_chapter",
    "detect_thrash",
    "detect_thrash_in_chapter",
    "ensure_zipf_loaded",
    "finding_to_dict",
    "is_uncommon",
    "lemma",
    "reset_zipf_cache_for_tests",
    "zipf_path_active",
]
