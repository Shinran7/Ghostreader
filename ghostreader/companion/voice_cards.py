"""Canon character card IO for voice-vs-card watch (#11).

Owns discovery + parse under story_dir/canon/characters. Detector and
analyze export import from here — do not re-home load_voice_cards under
analyzers/. Fail-soft: missing/unreadable → [].
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

_LOG = logging.getLogger(__name__)

_CARD_GLOBS = ("*.json", "*.yaml", "*.yml")


@dataclass(frozen=True)
class VoiceCard:
    """One canon character card with dialogue_voice for contrast."""

    slug: str
    name: str
    dialogue_voice: str
    voice_wildcards: list[str] = field(default_factory=list)
    weight: str | None = None


def find_canon_characters_dir(story_dir: Path) -> Path | None:
    """Return story_dir/canon/characters if it is a directory; else None."""
    if story_dir is None:
        return None
    try:
        candidate = Path(story_dir) / "canon" / "characters"
    except (TypeError, ValueError):
        return None
    if candidate.is_dir():
        return candidate
    return None


def _as_str_list(raw: Any) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        text = raw.strip()
        return [text] if text else []
    if isinstance(raw, list):
        out: list[str] = []
        for item in raw:
            if item is None:
                continue
            text = str(item).strip()
            if text:
                out.append(text)
        return out
    return []


def _parse_card_payload(data: dict[str, Any], *, fallback_slug: str) -> VoiceCard | None:
    """Build a VoiceCard from a parsed mapping. Skip empty dialogue_voice."""
    dialogue = data.get("dialogue_voice")
    if dialogue is None:
        return None
    dialogue_voice = str(dialogue).strip()
    if not dialogue_voice:
        return None

    slug_raw = data.get("slug")
    slug = str(slug_raw).strip() if slug_raw else fallback_slug
    if not slug:
        slug = fallback_slug
    if not slug:
        return None

    name_raw = data.get("name")
    name = str(name_raw).strip() if name_raw else slug

    weight_raw = data.get("weight")
    weight = None if weight_raw is None or weight_raw == "" else str(weight_raw).strip() or None

    return VoiceCard(
        slug=slug,
        name=name,
        dialogue_voice=dialogue_voice,
        voice_wildcards=_as_str_list(data.get("voice_wildcards")),
        weight=weight,
    )


def _load_one_card(path: Path) -> VoiceCard | None:
    suffix = path.suffix.lower()
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        _LOG.debug("voice_cards: skip unreadable %s (%s)", path, exc)
        return None

    try:
        data = json.loads(text) if suffix == ".json" else yaml.safe_load(text)
    except (json.JSONDecodeError, yaml.YAMLError, OSError) as exc:
        _LOG.debug("voice_cards: skip parse failure %s (%s)", path, exc)
        return None

    if not isinstance(data, dict):
        return None
    return _parse_card_payload(data, fallback_slug=path.stem)


def load_voice_cards(story_dir: Path) -> list[VoiceCard]:
    """Load *.json / *.yaml / *.yml under canon/characters. Fail-soft → []."""
    characters_dir = find_canon_characters_dir(story_dir)
    if characters_dir is None:
        return []

    cards: list[VoiceCard] = []
    seen_slugs: set[str] = set()
    paths: list[Path] = []
    for pattern in _CARD_GLOBS:
        paths.extend(sorted(characters_dir.glob(pattern)))

    for path in paths:
        if not path.is_file():
            continue
        card = _load_one_card(path)
        if card is None:
            continue
        if card.slug in seen_slugs:
            continue
        seen_slugs.add(card.slug)
        cards.append(card)
    return cards


__all__ = [
    "VoiceCard",
    "find_canon_characters_dir",
    "load_voice_cards",
]
