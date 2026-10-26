"""Voice-vs-card watch constants (#11).

Cousin of Autonomicon voice_fidelity floors / cue families — do not import
across repos. Caps and cue lexicons live here so detector + companion share
one source.
"""

from __future__ import annotations

VOICE_CARD_FINDINGS_CAP = 15
VOICE_CARD_MIN_LINES = 4
VOICE_CARD_EXCERPT_MAX = 120

# Skip these when building the given-name alias (KD-7 / titled-name fix).
# Match with and without a trailing period.
TITLE_SKIP_TOKENS = frozenset(
    {
        "dr",
        "dr.",
        "doctor",
        "mr",
        "mr.",
        "mrs",
        "mrs.",
        "ms",
        "ms.",
        "miss",
        "captain",
        "capt",
        "capt.",
        "sir",
        "dame",
        "prof",
        "prof.",
        "professor",
    }
)

# Cue families (§5.2). Stems matched casefold as substrings in card text.
TERSE_CUES = frozenset({"terse", "clipped", "short", "laconic", "curt"})
FORMAL_CUES = frozenset({"formal", "precise", "clinical", "articulate", "complex", "syntactically"})
COLLOQUIAL_CUES = frozenset({"colloquial", "slang", "casual", "contractions"})
FRAGMENTARY_CUES = frozenset({"fragmentary", "interrupted", "trailing"})
# Long register — split from monotone/radio (polarity lock).
SERMON_CUES = frozenset({"sermon", "cadence", "liturgy", "oratorical"})
# Short/flat → same fire rule as terse when no long-register neighbor.
MONOTONE_CUES = frozenset({"monotone", "radio"})
# Soft-dim primary; heuristic may no-op.
SOFT_DIM_PRIMARY_CUES = frozenset(
    {
        "deadpan",
        "dry",
        "biting",
        "sarcasm",
        "dialect",
        "endearment",
        "oath",
    }
)
# Bare stems: soft-dim only unless a disambiguating neighbor is present.
AMBIGUOUS_SOFT_ONLY_CUES = frozenset({"measured", "protocol"})

# Collapse pairwise absolute deltas (Autonomicon find_voice_collapses).
COLLAPSE_AVG_WORDS_DELTA = 2.0
COLLAPSE_CONTRACTION_DELTA = 0.10
COLLAPSE_FRAGMENT_DELTA = 0.10

# Mismatch fire thresholds.
TERSE_AVG_WORDS_MIN = 12.0
SERMON_AVG_WORDS_MAX = 4.0
SERMON_CONTRACTION_MIN = 0.40
FORMAL_CONTRACTION_MIN = 0.35
COLLOQUIAL_CONTRACTION_MAX = 0.05
FRAGMENTARY_RATE_NEAR_ZERO = 0.05

__all__ = [
    "AMBIGUOUS_SOFT_ONLY_CUES",
    "COLLAPSE_AVG_WORDS_DELTA",
    "COLLAPSE_CONTRACTION_DELTA",
    "COLLAPSE_FRAGMENT_DELTA",
    "COLLOQUIAL_CONTRACTION_MAX",
    "COLLOQUIAL_CUES",
    "FORMAL_CONTRACTION_MIN",
    "FORMAL_CUES",
    "FRAGMENTARY_CUES",
    "FRAGMENTARY_RATE_NEAR_ZERO",
    "MONOTONE_CUES",
    "SERMON_AVG_WORDS_MAX",
    "SERMON_CONTRACTION_MIN",
    "SERMON_CUES",
    "SOFT_DIM_PRIMARY_CUES",
    "TERSE_AVG_WORDS_MIN",
    "TERSE_CUES",
    "TITLE_SKIP_TOKENS",
    "VOICE_CARD_EXCERPT_MAX",
    "VOICE_CARD_FINDINGS_CAP",
    "VOICE_CARD_MIN_LINES",
]
