"""Heuristic voice-vs-card detector (no LLM).

Cousin of Autonomicon agents/voice_fidelity.attribute_quotes /
speaker_surface_metrics / find_voice_collapses — keep ±2 line same-line-first
behavior in sync. Ghostreader#11 / Autonomicon#264.

DELIBERATE DIVERGENCE: skip title tokens (Dr./Doctor/Captain/…) when building
the given-name alias so "Dr. Selah Abe" aliases to "selah", not "dr.".
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any

from ghostreader.analyzers.register_detector import strip_chapter_body
from ghostreader.companion.voice_card_constants import (
    COLLAPSE_AVG_WORDS_DELTA,
    COLLAPSE_CONTRACTION_DELTA,
    COLLAPSE_FRAGMENT_DELTA,
    COLLOQUIAL_CONTRACTION_MAX,
    COLLOQUIAL_CUES,
    FORMAL_CONTRACTION_MIN,
    FORMAL_CUES,
    FRAGMENTARY_CUES,
    FRAGMENTARY_RATE_NEAR_ZERO,
    MONOTONE_CUES,
    SERMON_AVG_WORDS_MAX,
    SERMON_CONTRACTION_MIN,
    SERMON_CUES,
    TERSE_AVG_WORDS_MIN,
    TERSE_CUES,
    TITLE_SKIP_TOKENS,
    VOICE_CARD_EXCERPT_MAX,
    VOICE_CARD_FINDINGS_CAP,
    VOICE_CARD_MIN_LINES,
)
from ghostreader.companion.voice_cards import VoiceCard

_QUOTE_RE = re.compile(r'\u201c([^\u201d]+)\u201d|"([^"]+)"')
_CONTRACTIONS = (
    "n't",
    "'ll",
    "'ve",
    "'re",
    "'d",
    "'m",
    "it's",
    "that's",
    "what's",
    "he's",
    "she's",
    "we're",
    "they're",
    "i'm",
    "i've",
    "i'll",
    "i'd",
)

_SEVERITY_RANK = {"high": 0, "moderate": 1, "low": 2}


def _is_title_token(token: str) -> bool:
    bare = token.strip().casefold().rstrip(".")
    if not bare:
        return False
    return bare in TITLE_SKIP_TOKENS or f"{bare}." in TITLE_SKIP_TOKENS


def given_name_alias(name: str) -> str | None:
    """First non-title Proper token, casefolded. None if none found."""
    if not name or not name.strip():
        return None
    for raw in name.split():
        tok = raw.strip(".,;:'\"“”")
        if not tok or _is_title_token(tok):
            continue
        if tok[0].isalpha() and tok[0].isupper():
            return tok.casefold()
    return None


def attribute_quotes(text: str, cast: list[tuple[str, str]]) -> dict[str, list[str]]:
    """Attribute quoted lines to nearest cast name (±2 lines).

    Cousin of Autonomicon voice_fidelity.attribute_quotes. Prefer same-line
    speaker tags; only then expand ±2. Form C bare quotes stay unattributed.
    """
    lines = text.split("\n")
    name_to_slug: dict[str, str] = {}
    for slug, name in cast:
        if not name:
            continue
        name_to_slug[name.casefold()] = slug
        alias = given_name_alias(name)
        if alias:
            name_to_slug[alias] = slug
    sorted_names = sorted(name_to_slug.items(), key=lambda x: -len(x[0]))

    out: dict[str, list[str]] = {}
    for line_idx, line in enumerate(lines):
        quotes = _QUOTE_RE.findall(line)
        if not quotes:
            continue
        dialogue_texts = [q[0] or q[1] for q in quotes if q[0] or q[1]]
        if not dialogue_texts:
            continue
        # Prefer same-line speaker tags; only then expand ±2 lines (avoids
        # adjacent-speaker theft when lines alternate tightly).
        contexts = [
            line.casefold(),
            " ".join(lines[max(0, line_idx - 2) : min(len(lines), line_idx + 3)]).casefold(),
        ]
        attributed = False
        for context in contexts:
            for name_lower, slug in sorted_names:
                if name_lower and name_lower in context:
                    out.setdefault(slug, []).extend(dialogue_texts)
                    attributed = True
                    break
            if attributed:
                break
    return out


def speaker_surface_metrics(quotes: list[str]) -> dict[str, float]:
    """Surface metrics for one speaker's quotes (always includes interruption_rate)."""
    if not quotes:
        return {
            "line_count": 0.0,
            "avg_words": 0.0,
            "contraction_rate": 0.0,
            "fragment_rate": 0.0,
            "interruption_rate": 0.0,
        }
    word_counts: list[int] = []
    contractions = 0
    fragments = 0
    interruptions = 0
    for q in quotes:
        words = re.findall(r"[A-Za-z']+", q)
        word_counts.append(len(words))
        lower = q.lower()
        if any(c in lower for c in _CONTRACTIONS):
            contractions += 1
        if 0 < len(words) <= 5:
            fragments += 1
        if "—" in q or "..." in q or "…" in q:
            interruptions += 1
    n = len(quotes)
    return {
        "line_count": float(n),
        "avg_words": sum(word_counts) / n,
        "contraction_rate": contractions / n,
        "fragment_rate": fragments / n,
        "interruption_rate": interruptions / n,
    }


def cards_eligible_for_contrast(card_a: str, card_b: str) -> bool:
    a = (card_a or "").casefold().strip()
    b = (card_b or "").casefold().strip()
    if not a or not b:
        return False
    return a != b


def _card_cue_blob(card: VoiceCard) -> str:
    parts = [card.dialogue_voice, *card.voice_wildcards]
    return " ".join(parts).casefold()


def _stem_present(blob: str, stem: str) -> bool:
    """True when *stem* appears as a substring word-ish hit in *blob*."""
    if not stem:
        return False
    # Substring match is enough for v1 cue lexicon (design §5.2).
    return stem in blob


def active_cue_families(card: VoiceCard) -> set[str]:
    """Return heuristic cue family ids present on the card (polarity-aware)."""
    blob = _card_cue_blob(card)
    if not blob.strip():
        return set()

    families: set[str] = set()

    if any(_stem_present(blob, s) for s in TERSE_CUES):
        families.add("terse")
    if any(_stem_present(blob, s) for s in FORMAL_CUES):
        families.add("formal")
    if any(_stem_present(blob, s) for s in COLLOQUIAL_CUES):
        families.add("colloquial")
    if any(_stem_present(blob, s) for s in FRAGMENTARY_CUES):
        families.add("fragmentary")

    has_sermon = any(_stem_present(blob, s) for s in SERMON_CUES)
    has_monotone = any(_stem_present(blob, s) for s in MONOTONE_CUES)

    if has_sermon:
        families.add("sermon")
    # monotone/radio → terse fire only when no long-register neighbor.
    if has_monotone and not has_sermon:
        families.add("monotone")

    # Bare measured/protocol never add a family alone (soft-dim primary).
    # Disambiguating neighbors already covered via sermon/monotone stems above.
    return families


def _cue_misses(families: set[str], metrics: dict[str, float], *, min_lines: int) -> list[str]:
    """Return family ids whose speech metrics conflict with the card cue."""
    line_count = float(metrics.get("line_count", 0))
    if line_count < min_lines:
        return []

    avg_words = float(metrics.get("avg_words", 0))
    contraction = float(metrics.get("contraction_rate", 0))
    fragment = float(metrics.get("fragment_rate", 0))
    interruption = float(metrics.get("interruption_rate", 0))
    misses: list[str] = []

    # Terse + monotone share the long-speech fire rule.
    if ("terse" in families or "monotone" in families) and avg_words >= TERSE_AVG_WORDS_MIN:
        misses.append("terse" if "terse" in families else "monotone")

    if "formal" in families and contraction >= FORMAL_CONTRACTION_MIN:
        misses.append("formal")

    if "colloquial" in families and contraction <= COLLOQUIAL_CONTRACTION_MAX:
        misses.append("colloquial")

    if "fragmentary" in families and (
        fragment <= FRAGMENTARY_RATE_NEAR_ZERO and interruption <= FRAGMENTARY_RATE_NEAR_ZERO
    ):
        misses.append("fragmentary")

    if "sermon" in families and (
        avg_words <= SERMON_AVG_WORDS_MAX or contraction >= SERMON_CONTRACTION_MIN
    ):
        misses.append("sermon")

    return misses


def _truncate_excerpt(text: str, *, max_len: int = VOICE_CARD_EXCERPT_MAX) -> str:
    clean = re.sub(r"\s+", " ", (text or "").strip())
    if len(clean) <= max_len:
        return clean
    return clean[: max_len - 1].rstrip() + "…"


def _metrics_payload(metrics: dict[str, float]) -> dict[str, float]:
    return {
        "line_count": float(metrics.get("line_count", 0)),
        "avg_words": float(metrics.get("avg_words", 0)),
        "contraction_rate": float(metrics.get("contraction_rate", 0)),
        "fragment_rate": float(metrics.get("fragment_rate", 0)),
        "interruption_rate": float(metrics.get("interruption_rate", 0)),
    }


def _prefer_quote(quotes: list[str]) -> str | None:
    if not quotes:
        return None
    # Prefer latest attributed span (chapters processed in order).
    return quotes[-1]


def _mismatch_summary(slug: str, misses: list[str], card_excerpt: str) -> str:
    miss_label = ", ".join(misses)
    cue_bit = f" vs card cue '{card_excerpt}'" if card_excerpt else ""
    return f"{slug} attributed speech mismatches cue families [{miss_label}]{cue_bit}."


def _collapse_summary(slug_a: str, slug_b: str) -> str:
    return (
        f"{slug_a} and {slug_b} attributed speech look surface-similar "
        "despite distinct dialogue_voice cards."
    )


def detect_voice_card_issues(
    chapters: Sequence[tuple[int, str]],
    cards: Sequence[VoiceCard],
    *,
    focus_chapter: int = 0,
    min_lines: int = VOICE_CARD_MIN_LINES,
    max_entries: int = VOICE_CARD_FINDINGS_CAP,
) -> list[dict[str, Any]]:
    """Attribute quotes across chapters, emit card_mismatch / card_collapse rows.

    *chapters* is ``(chapter_number, content)`` pairs (content may include YAML
    frontmatter). Empty *cards* → ``[]``. Speakers below *min_lines* emit no row.
    """
    if not cards:
        return []

    cast = [(c.slug, c.name) for c in cards]
    cards_by_slug = {c.slug: c for c in cards}
    dialogue_by_slug = {c.slug: c.dialogue_voice for c in cards}

    attributed: dict[str, list[str]] = {}
    chapters_spoken: dict[str, list[int]] = {}

    for ch_num, content in chapters:
        body = strip_chapter_body(content or "")
        if not body.strip():
            continue
        for slug, quotes in attribute_quotes(body, cast).items():
            if not quotes:
                continue
            attributed.setdefault(slug, []).extend(quotes)
            spoken = chapters_spoken.setdefault(slug, [])
            if ch_num not in spoken:
                spoken.append(ch_num)

    metrics_by_slug = {slug: speaker_surface_metrics(quotes) for slug, quotes in attributed.items()}

    findings: list[dict[str, Any]] = []

    # --- card_mismatch (cue heuristic) ---
    for slug, metrics in metrics_by_slug.items():
        card = cards_by_slug.get(slug)
        if card is None:
            continue
        if float(metrics.get("line_count", 0)) < min_lines:
            continue
        families = active_cue_families(card)
        misses = _cue_misses(families, metrics, min_lines=min_lines)
        if not misses:
            continue
        excerpt = _truncate_excerpt(card.dialogue_voice)
        severity = "high" if len(misses) >= 2 else "moderate"
        findings.append(
            {
                "kind": "card_mismatch",
                "severity": severity,
                "summary": _mismatch_summary(slug, misses, excerpt),
                "speaker": slug,
                "speaker_b": None,
                "quote": _prefer_quote(attributed.get(slug, [])),
                "card_excerpt": excerpt or None,
                "metrics": _metrics_payload(metrics),
                "chapters": list(chapters_spoken.get(slug, [])),
                "chapter": focus_chapter,
                "normalized_key": f"card_mismatch:{slug}",
            }
        )

    # --- card_collapse (pairwise deltas) ---
    slugs = sorted(metrics_by_slug)
    for i, slug_a in enumerate(slugs):
        for slug_b in slugs[i + 1 :]:
            m_a = metrics_by_slug[slug_a]
            m_b = metrics_by_slug[slug_b]
            if float(m_a.get("line_count", 0)) < min_lines:
                continue
            if float(m_b.get("line_count", 0)) < min_lines:
                continue
            card_a = dialogue_by_slug.get(slug_a, "")
            card_b = dialogue_by_slug.get(slug_b, "")
            if not cards_eligible_for_contrast(card_a, card_b):
                continue
            if abs(float(m_a.get("avg_words", 0)) - float(m_b.get("avg_words", 0))) > (
                COLLAPSE_AVG_WORDS_DELTA
            ):
                continue
            if (
                abs(float(m_a.get("contraction_rate", 0)) - float(m_b.get("contraction_rate", 0)))
                > COLLAPSE_CONTRACTION_DELTA
            ):
                continue
            if (
                abs(float(m_a.get("fragment_rate", 0)) - float(m_b.get("fragment_rate", 0)))
                > COLLAPSE_FRAGMENT_DELTA
            ):
                continue

            pair_key = "|".join(sorted((slug_a, slug_b)))
            chans = sorted(
                set(chapters_spoken.get(slug_a, [])) | set(chapters_spoken.get(slug_b, []))
            )
            findings.append(
                {
                    "kind": "card_collapse",
                    "severity": "moderate",
                    "summary": _collapse_summary(slug_a, slug_b),
                    "speaker": slug_a,
                    "speaker_b": slug_b,
                    "quote": _prefer_quote(attributed.get(slug_a, [])),
                    "card_excerpt": _truncate_excerpt(card_a) or None,
                    "metrics": _metrics_payload(m_a),
                    "chapters": chans,
                    "chapter": focus_chapter,
                    "normalized_key": f"card_collapse:{pair_key}",
                }
            )

    def _sort_key(row: dict[str, Any]) -> tuple[int, int, str]:
        sev = _SEVERITY_RANK.get(str(row.get("severity", "")), 99)
        kind_rank = 0 if row.get("kind") == "card_collapse" else 1
        return (kind_rank, sev, str(row.get("normalized_key") or ""))

    findings.sort(key=_sort_key)
    limit = max(0, int(max_entries))
    return findings[:limit]


__all__ = [
    "active_cue_families",
    "attribute_quotes",
    "cards_eligible_for_contrast",
    "detect_voice_card_issues",
    "given_name_alias",
    "speaker_surface_metrics",
]
