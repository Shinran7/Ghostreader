"""Read Autonomicon Canon as the continuity state of record (#16).

Autonomicon's Updater writes ``stories/<slug>/canon/`` after each chapter and
snapshots it to ``checkpoints/chapter-NNN/canon/`` (state through chapter
N-1). This module loads that state as of a chapter and formats it as a
compact block of numbered entries. A continuity finding cites an entry id,
and code fills the Canon side of the finding from the entry, so the Canon
text is exact.

Read-only. Missing files, empty files and unknown fields are tolerated.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Caps keep the block near ~12k characters on long books.
_MAX_CAST = 40
_MAX_PHYSICAL = 60
_MAX_RECENT = 3
_MAX_SECRETS = 20
_MAX_SEEDS = 25
_MAX_FACTS = 40
_MAX_RULES = 15
_TEXT_CAP = 240


@dataclass
class CanonEntry:
    """One citable Canon fact."""

    id: str
    kind: str
    text: str
    chapter: int | None = None
    file: str = ""

    def as_ref(self) -> dict[str, Any]:
        return {"id": self.id, "kind": self.kind, "chapter": self.chapter, "file": self.file}

    def as_counter_evidence(self) -> str:
        where = f"Ch {self.chapter} " if self.chapter else ""
        return f"Canon {where}({self.kind}): {self.text}"


@dataclass
class CanonState:
    """Canon as of the start of ``chapter_n``."""

    chapter_n: int
    source_dir: Path
    from_checkpoint: bool
    entries: list[CanonEntry] = field(default_factory=list)
    files_loaded: list[str] = field(default_factory=list)

    def by_id(self) -> dict[str, CanonEntry]:
        return {e.id: e for e in self.entries}

    def __bool__(self) -> bool:
        return bool(self.entries)


def _int(v: Any) -> int | None:
    try:
        n = int(v)
    except (TypeError, ValueError):
        return None
    return n if n > 0 else None


def _clip(text: Any, cap: int = _TEXT_CAP) -> str:
    s = " ".join(str(text or "").split())
    return s if len(s) <= cap else s[: cap - 1].rstrip() + "…"


def find_canon_dir(*candidates: Path | None) -> Path | None:
    """First ``canon/`` dir at or beside any candidate (story dir or chapters dir)."""
    for c in candidates:
        if c is None:
            continue
        c = Path(c)
        for d in (c / "canon", c.parent / "canon"):
            if d.is_dir() and any(d.iterdir()):
                return d
    return None


def _source_for(canon_dir: Path, chapter_n: int) -> tuple[Path, bool]:
    cp = canon_dir.parent / "checkpoints" / f"chapter-{chapter_n:03d}" / "canon"
    if cp.is_dir() and any(cp.rglob("*.json")):
        return cp, True
    return canon_dir, False


def _read(root: Path, rel: str, loaded: list[str]) -> Any:
    p = root / rel
    if not p.is_file():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        logger.warning("Canon: cannot read %s: %s", p, exc)
        return None
    loaded.append(rel)
    return data


def _rows(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, list):
        return [r for r in data if isinstance(r, dict)]
    return []


class _Builder:
    def __init__(self, chapter_n: int) -> None:
        self.n = chapter_n
        self.entries: list[CanonEntry] = []
        self._counts: dict[str, int] = {}

    def before(self, ch: Any) -> bool:
        c = _int(ch)
        return c is None or c < self.n

    def add(self, prefix: str, kind: str, text: str, chapter: Any, file: str) -> None:
        if not text.strip():
            return
        k = self._counts.get(prefix, 0) + 1
        self._counts[prefix] = k
        self.entries.append(
            CanonEntry(
                id=f"{prefix}{k}", kind=kind, text=_clip(text), chapter=_int(chapter), file=file
            )
        )


def _cast(b: _Builder, root: Path, loaded: list[str]) -> None:
    chars_dir = root / "characters"
    if not chars_dir.is_dir():
        return
    rows: list[dict[str, Any]] = []
    for p in sorted(chars_dir.glob("*.json")):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(d, dict) and d.get("name"):
            rows.append(d)
    if rows:
        loaded.append("characters/")
    rows = [r for r in rows if b.before(r.get("introduced_chapter"))]
    weight = {"protagonist": 0, "primary": 0, "major": 1, "secondary": 2, "background": 3}
    rows.sort(key=lambda r: (weight.get(str(r.get("weight") or ""), 2), str(r.get("name"))))
    for r in rows[:_MAX_CAST]:
        status = str(r.get("status") or "")
        died = _int(r.get("died_chapter"))
        if status == "deceased":
            if died and died >= b.n:
                status = "active"  # live Canon: dies in this chapter or later
            elif died:
                status = f"deceased since Ch {died}"
            else:
                status = "deceased (death chapter not recorded; may be this chapter)"
        parts = [f"{r.get('name')}"]
        if r.get("role"):
            parts[0] += f" ({r.get('role')})"
        parts.append(f"status {status or 'unknown'}")
        if r.get("pronouns"):
            parts.append(f"pronouns {r.get('pronouns')}")
        last = _int(r.get("last_seen_chapter"))
        if last and last < b.n and r.get("last_seen_location"):
            seen = f"last seen Ch {last} at {r.get('last_seen_location')}"
            if r.get("last_seen_time"):
                seen += f", {r.get('last_seen_time')}"
            parts.append(seen)
        if r.get("physical_description"):
            parts.append(f"looks: {_clip(r.get('physical_description'), 120)}")
        chapter = died if status.startswith("deceased since") else _int(r.get("introduced_chapter"))
        b.add("C", "character", "; ".join(parts), chapter, f"characters/{r.get('slug') or ''}.json")


def _physical(b: _Builder, root: Path, loaded: list[str]) -> None:
    rows = [
        r
        for r in _rows(_read(root, "style/physical-state.json", loaded))
        if b.before(r.get("chapter"))
    ]
    latest: dict[tuple[str, str], dict[str, Any]] = {}
    for r in sorted(rows, key=lambda r: _int(r.get("chapter")) or 0):
        latest[(str(r.get("entity")), str(r.get("attribute")))] = r
    kept = sorted(latest.values(), key=lambda r: -(_int(r.get("chapter")) or 0))[:_MAX_PHYSICAL]
    for r in sorted(kept, key=lambda r: (str(r.get("entity")), str(r.get("attribute")))):
        attr = str(r.get("attribute") or "")
        kind = (
            "item location"
            if attr.startswith(("object_locations", "possessions"))
            else "physical state"
        )
        text = f"{r.get('entity')} — {attr}: {r.get('value')}"
        if r.get("progression") and r.get("progression") != "stable":
            text += f" ({r.get('progression')})"
        b.add("P", kind, text, r.get("chapter"), "style/physical-state.json")


def _recent(b: _Builder, root: Path, loaded: list[str]) -> None:
    ends = [
        r
        for r in _rows(_read(root, "style/chapter-ending-states.json", loaded))
        if b.before(r.get("chapter"))
    ]
    for r in sorted(ends, key=lambda r: _int(r.get("chapter")) or 0)[-_MAX_RECENT:]:
        b.add(
            "E",
            "chapter ending",
            str(r.get("ending_state") or ""),
            r.get("chapter"),
            "style/chapter-ending-states.json",
        )
    tl = _read(root, "style/story-timeline.json", loaded)
    stamps = _rows(tl.get("chapter_timestamps")) if isinstance(tl, dict) else []
    stamps = [r for r in stamps if b.before(r.get("chapter"))]
    for r in sorted(stamps, key=lambda r: _int(r.get("chapter")) or 0)[-_MAX_RECENT:]:
        text = f"starts {r.get('narrative_time') or '?'}; ends {r.get('end_time') or '?'}"
        if r.get("elapsed"):
            text += f"; elapsed {r.get('elapsed')}"
        b.add("T", "timeline", text, r.get("chapter"), "style/story-timeline.json")
    if isinstance(tl, dict):
        for d in _rows(tl.get("deadlines"))[:5]:
            b.add(
                "T",
                "deadline",
                "; ".join(f"{k} {v}" for k, v in d.items() if v not in (None, "")),
                None,
                "style/story-timeline.json",
            )
    locs = [
        r
        for r in _rows(_read(root, "style/chapter-locations.json", loaded))
        if b.before(r.get("chapter"))
    ]
    for r in sorted(locs, key=lambda r: _int(r.get("chapter")) or 0)[-_MAX_RECENT:]:
        settings = r.get("settings") or []
        if isinstance(settings, list) and settings:
            b.add(
                "L",
                "settings",
                ", ".join(str(s) for s in settings),
                r.get("chapter"),
                "style/chapter-locations.json",
            )


def _secret_state_before(r: dict[str, Any], n: int) -> tuple[str, int] | None:
    """State and its chapter as of chapter *n*, from ``state_history`` (#602)."""
    history = r.get("state_history")
    if not isinstance(history, list):
        return None
    prior = [
        (c, str(h.get("state") or "?"))
        for h in history
        if isinstance(h, dict) and (c := _int(h.get("chapter"))) is not None and c < n
    ]
    if not prior:
        return None
    chapter, state = sorted(prior, key=lambda p: p[0])[-1]
    return state, chapter


def _knowers_before(r: dict[str, Any], n: int, *, undated_ok: bool) -> tuple[list[str], bool]:
    """Knowers who knew before chapter *n*, and whether undated ones were dropped."""
    knowers = r.get("knowers")
    if not isinstance(knowers, list):
        return [], False
    dated = r.get("knower_since")
    dated = dated if isinstance(dated, dict) else {}
    names: list[str] = []
    dropped = False
    for k in knowers:
        slug = str(k.get("slug") if isinstance(k, dict) else k)
        learned = _int(dated.get(slug))
        if learned is not None:
            if learned < n:
                names.append(slug)
        elif undated_ok:
            names.append(slug)
        else:
            dropped = True
    return names, dropped


def _plot(b: _Builder, root: Path, loaded: list[str]) -> None:
    secrets = [
        r
        for r in _rows(_read(root, "plot/secrets-registry.json", loaded))
        if b.before(r.get("planted_chapter"))
    ]
    for r in secrets[:_MAX_SECRETS]:
        since = _int(r.get("state_since_chapter"))
        changed_later = since is not None and since >= b.n
        asof = _secret_state_before(r, b.n)
        chapter: Any
        if asof is not None:
            # Autonomicon #602 records every state change with its chapter.
            state, chapter = asof
        elif changed_later:
            # Live Canon holds only the latest state. It changed in this
            # chapter or later, so only the first reveal is known for N.
            revealed = _int(r.get("first_revealed_chapter"))
            if revealed is not None and revealed < b.n:
                state = f"revealed since Ch {revealed}"
            else:
                state = "hidden"
                revealed = None
            chapter = revealed or r.get("planted_chapter")
        else:
            state = r.get("state") or "?"
            chapter = since or r.get("planted_chapter")
        # Knowers without a recorded chapter are only trusted while the
        # state has not changed since N; dated knowers (#602) are filtered.
        names, undated_dropped = _knowers_before(r, b.n, undated_ok=not changed_later)
        if names:
            tail = f"state {state}; known by {', '.join(names)}"
        elif undated_dropped or changed_later:
            tail = f"state {state}; knowers before Ch {b.n} not recorded"
        else:
            tail = f"state {state}; known by no one recorded"
        text = (
            f"{r.get('name') or r.get('slug')}: {_clip(r.get('description_summary'), 140)}; {tail}"
        )
        b.add("S", "secret", text, chapter, "plot/secrets-registry.json")
    seeds = _rows(_read(root, "plot/unresolved-seeds.json", loaded))
    open_seeds = [
        r
        for r in seeds
        if b.before(r.get("planted_in_chapter"))
        and (_int(r.get("resolved_in_chapter")) or b.n) >= b.n
    ]
    for r in open_seeds[:_MAX_SEEDS]:
        text = f"{_clip(r.get('description'), 180)} (open; {r.get('priority') or 'normal'})"
        b.add("O", "open seed", text, r.get("planted_in_chapter"), "plot/unresolved-seeds.json")


def _fixed(b: _Builder, root: Path, loaded: list[str]) -> None:
    facts = _read(root, "style/key-facts.json", loaded)
    if isinstance(facts, list):
        for f in facts[:_MAX_FACTS]:
            text = (
                f
                if isinstance(f, str)
                else (f.get("fact") or f.get("text") or "")
                if isinstance(f, dict)
                else ""
            )
            b.add("K", "key fact", str(text), None, "style/key-facts.json")
    for r in _rows(_read(root, "world/physics-rules.json", loaded))[:_MAX_RULES]:
        b.add(
            "R",
            "world rule",
            str(r.get("description") or r.get("name") or ""),
            None,
            "world/physics-rules.json",
        )


def load_canon_state(canon_dir: Path, chapter_n: int) -> CanonState:
    """Canon as of the start of ``chapter_n`` (entries from chapters < N only)."""
    root, from_cp = _source_for(canon_dir, chapter_n)
    b = _Builder(chapter_n)
    loaded: list[str] = []
    for part in (_cast, _physical, _recent, _plot, _fixed):
        try:
            part(b, root, loaded)
        except Exception as exc:  # noqa: BLE001 — fail soft per section
            logger.warning("Canon: %s failed for %s: %s", part.__name__, root, exc)
    return CanonState(
        chapter_n=chapter_n,
        source_dir=root,
        from_checkpoint=from_cp,
        entries=b.entries,
        files_loaded=loaded,
    )


_SECTIONS = [
    ("C", "Cast"),
    ("P", "Physical state and item locations (latest per attribute)"),
    ("E", "Where the last chapters ended"),
    ("T", "Timeline"),
    ("L", "Recent settings"),
    ("S", "Secrets (who knows what)"),
    ("O", "Open seeds (set up, not yet paid off)"),
    ("K", "Fixed story facts"),
    ("R", "World rules"),
]


def format_canon_block(state: CanonState) -> str:
    """Compact, id-tagged block for the continuity prompt."""
    out: list[str] = []
    for prefix, title in _SECTIONS:
        rows = [e for e in state.entries if e.id.startswith(prefix) and e.id[1:].isdigit()]
        if not rows:
            continue
        out.append(f"### {title}")
        for e in rows:
            where = f" (Ch {e.chapter})" if e.chapter else ""
            out.append(f"[{e.id}]{where} {e.text}")
        out.append("")
    return "\n".join(out).strip()


__all__ = [
    "CanonEntry",
    "CanonState",
    "find_canon_dir",
    "format_canon_block",
    "load_canon_state",
]
