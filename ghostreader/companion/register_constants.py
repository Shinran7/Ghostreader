"""Register / initiation-budget constants for companion + analyze (#7).

S7 / Ghostreader#7 — keep Autonomicon + GhostReader numbers identical.
Cousin of Autonomicon craft_register_constants.py — do not import across repos.
"""

from __future__ import annotations

# Twin of Autonomicon INITIATION_BUDGET_* — keep in sync.
INITIATION_BUDGET_COINED_NOUNS = 3
INITIATION_BUDGET_WINDOW_WORDS = 300
REGISTER_FINDINGS_CAP = 15

# English hyphen compounds that are not institutional jargon (extend as needed).
HYPHEN_DENYLIST = frozenset(
    {
        "cold-forged",  # Shatterbound ch1 literal; English compound, not jargon
        "well-known",
        "well-worn",
        "long-term",
        "short-term",
        "two-turn",
        "half-bell",
        "slag-hills",
        "felt-lined",
        "middle-aged",
        "half-syllable",
        "soot-wet",
    }
)

__all__ = [
    "HYPHEN_DENYLIST",
    "INITIATION_BUDGET_COINED_NOUNS",
    "INITIATION_BUDGET_WINDOW_WORDS",
    "REGISTER_FINDINGS_CAP",
]
