"""Seed.yaml discovery and parsing for manuscript metadata.

Reads the Autonomicon-format seed.yaml to extract author-stated intent
that calibrates analysis agents. Only the ``meta`` block is consumed.

Precedence: CLI flags > seed.yaml > defaults.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


def find_seed_yaml(manuscript_path: Path) -> Path | None:
    """Walk up from *manuscript_path* looking for ``seed.yaml``.

    Checks the manuscript directory itself, then each parent. Returns
    the first ``seed.yaml`` found, or ``None``.
    """
    current = manuscript_path.resolve()
    if current.is_file():
        current = current.parent
    for directory in [current, *current.parents]:
        candidate = directory / "seed.yaml"
        if candidate.is_file():
            return candidate
    return None


def load_seed_meta(manuscript_path: Path) -> dict[str, Any]:
    """Load the ``meta`` block from the nearest ``seed.yaml``.

    Returns an empty dict if no seed.yaml exists or the meta block is
    missing/invalid.
    """
    seed_path = find_seed_yaml(manuscript_path)
    if seed_path is None:
        return {}

    try:
        with open(seed_path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except (yaml.YAMLError, OSError):
        return {}

    if not isinstance(data, dict):
        return {}

    meta = data.get("meta", {})
    return meta if isinstance(meta, dict) else {}


# ── Fields the agents understand ─────────────────────────────────────

_KNOWN_FIELDS: dict[str, str] = {
    "genre": "Genre",
    "target_chapters": "Target chapter count",
    "target_chapter_length": "Target chapter length (words)",
    "arc_archetype": "Arc archetype",
    "dialogue_density": "Intended dialogue density",
    "content_rating": "Content rating",
    "reading_level": "Reading level",
    "story_epoch": "Story epoch / era",
    "time_units": "Time units",
}


def build_author_intent_block(seed_meta: dict[str, Any]) -> str:
    """Format seed meta into a context block for agent system prompts.

    Returns an empty string when there is no actionable metadata,
    so callers can safely concatenate without extra whitespace.
    """
    if not seed_meta:
        return ""

    lines: list[str] = []
    for key, label in _KNOWN_FIELDS.items():
        value = seed_meta.get(key)
        if value is not None:
            lines.append(f"- {label}: {value}")

    if not lines:
        return ""

    header = (
        "AUTHOR-STATED INTENT (from seed.yaml):\n"
        "The author provided the following metadata about this manuscript. "
        "Use it to calibrate your evaluation — do not penalize intentional "
        "choices that align with these stated goals.\n"
    )
    return header + "\n".join(lines)


__all__ = [
    "build_author_intent_block",
    "find_seed_yaml",
    "load_seed_meta",
]
