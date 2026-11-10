"""Audit Autonomicon Canon: Canon against itself and against the prose (#16).

Deterministic checks, no LLM. Each row is a machine-actionable ``canon_findings``
entry for Autonomicon (and a test harness for its Updater). Rows never gate a
verdict.

Row shape::

    {kind, severity, file, entity, chapter, summary, detail}

``severity`` is ``"concern"`` when Canon is wrong (it disagrees with itself or
with the prose) and ``"info"`` when Canon is only thin (an empty file, a
chapter not recorded, a vague field).
"""

from __future__ import annotations

import json
import re
from collections import Counter
from collections.abc import Mapping
from pathlib import Path
from typing import Any

# Files the Updater is expected to fill for every story with chapters.
EXPECTED_FILES = (
    "style/physical-state.json",
    "style/story-timeline.json",
    "style/chapter-ending-states.json",
    "style/chapter-locations.json",
    "style/key-facts.json",
    "plot/unresolved-seeds.json",
    "plot/secrets-registry.json",
)

# Files with one row per chapter (chapter key, rows path inside the file).
PER_CHAPTER = (
    ("style/chapter-ending-states.json", None),
    ("style/chapter-locations.json", None),
    ("style/story-timeline.json", "chapter_timestamps"),
)

KINDS = (
    "missing_file",
    "empty_file",
    "chapter_not_recorded",
    "death_chapter_missing",
    "seen_after_death",
    "seed_resolved_when_planted",
    "seed_resolved_before_planted",
    "timeline_vague",
    "name_drift",
    "character_not_in_prose",
)

_TITLE = r"(?:St|Saint|Mt|Mount|Ft|Fort|Lake|Dr|Mr|Mrs|Ms)\.?"
# A capitalized word that is not an abbreviated title ("St." starts a name;
# it does not continue "At").
_CAP = r"(?!(?:St|Mt|Ft|Dr|Mr|Mrs|Ms)\.)[A-Z][A-Za-z'’\-]+"
_JOIN = rf"(?:\s+(?:(?:of|the|de|la)\s+){{0,2}}{_CAP})"
_NAME = re.compile(rf"\b(?:{_TITLE}\s+{_CAP}{_JOIN}*|{_CAP}{_JOIN}+)")
_HONORIFIC = {"father", "mother", "sister", "brother", "dr", "mr", "mrs", "ms", "detective"}
_STOP = {"The", "A", "An", "In", "At", "On", "Of", "And", "But", "When", "Then", "Story", "Genre"}
_TITLES = {"st", "st.", "saint", "mt", "mt.", "mount", "lake", "fort", "ft", "ft."}


def _row(kind: str, severity: str, file: str, summary: str, **kw: Any) -> dict[str, Any]:
    return {
        "kind": kind,
        "severity": severity,
        "file": file,
        "entity": kw.get("entity"),
        "chapter": kw.get("chapter"),
        "summary": summary,
        "detail": kw.get("detail", ""),
    }


def _int(v: Any) -> int | None:
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _load(canon: Path, rel: str) -> tuple[bool, Any]:
    p = canon / rel
    if not p.is_file():
        return False, None
    try:
        return True, json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return True, None


def _rows(data: Any, key: str | None = None) -> list[dict[str, Any]]:
    if key and isinstance(data, dict):
        data = data.get(key)
    return [r for r in data if isinstance(r, dict)] if isinstance(data, list) else []


def _norm(text: str) -> str:
    text = text.replace("’", "'").replace("‘", "'")
    return re.sub(r"\s+", " ", text).lower()


def _bare(name: str) -> str:
    return re.sub(r"'s$", "", _norm(name).strip())


def names_in(text: str, common: set[str] | frozenset[str] = frozenset()) -> list[str]:
    """Multi-word proper names in ``text`` ("St. Mary's", "Harbor Street").

    A possessive ends a name ("Cole's Syrian" -> "Cole"). Leading words in
    ``common`` (words the prose also uses in lower case, such as a
    sentence-initial "Your") are dropped. Names left with one word are skipped.
    """
    out = []
    for m in _NAME.finditer(text.replace("’", "'")):
        words: list[str] = []
        for w in m.group(0).split():
            words.append(w)
            if w.endswith("'s"):
                words[-1] = w[:-2]
                break
        while words and (words[0] in _STOP or words[0].lower() in common):
            words = words[1:]
        if len(words) >= 2:
            out.append(" ".join(words))
    return out


def common_words(text: str) -> set[str]:
    """Words the text uses in lower case (so not only as names)."""
    return set(re.findall(r"\b[a-z][a-z'\-]+\b", text.replace("’", "'")))


def _characters(canon: Path) -> list[dict[str, Any]]:
    d = canon / "characters"
    out = []
    for p in sorted(d.glob("*.json")) if d.is_dir() else []:
        try:
            r = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(r, dict) and r.get("name"):
            r.setdefault("slug", p.stem)
            out.append(r)
    return out


def _coverage(canon: Path, through: int) -> list[dict[str, Any]]:
    rows = []
    for rel in EXPECTED_FILES:
        present, data = _load(canon, rel)
        if not present:
            rows.append(_row("missing_file", "info", rel, f"{rel} is missing"))
        elif data in (None, [], {}) or (
            isinstance(data, dict) and not any(v not in (None, [], {}, "") for v in data.values())
        ):
            rows.append(_row("empty_file", "info", rel, f"{rel} is empty"))
    for rel, key in PER_CHAPTER:
        present, data = _load(canon, rel)
        if not present:
            continue
        have = {_int(r.get("chapter")) for r in _rows(data, key)}
        missing = [c for c in range(1, through + 1) if c not in have]
        if missing:
            rows.append(
                _row(
                    "chapter_not_recorded",
                    "info",
                    rel,
                    f"{rel} has no row for chapter(s) {_span(missing)}",
                    chapter=missing[-1],
                    detail=",".join(str(c) for c in missing),
                )
            )
    return rows


def _span(nums: list[int]) -> str:
    return ", ".join(str(n) for n in nums[:8]) + (" …" if len(nums) > 8 else "")


def _cast(chars: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for c in chars:
        file = f"characters/{c['slug']}.json"
        if str(c.get("status") or "") != "deceased":
            continue
        died = _int(c.get("died_chapter"))
        if not died:
            rows.append(
                _row(
                    "death_chapter_missing",
                    "concern",
                    file,
                    f"{c['name']} is deceased but died_chapter is {c.get('died_chapter')!r}",
                    entity=c["slug"],
                )
            )
            continue
        seen = _int(c.get("last_seen_chapter"))
        if seen and seen > died:
            rows.append(
                _row(
                    "seen_after_death",
                    "concern",
                    file,
                    f"{c['name']} died in chapter {died} but was last seen in chapter {seen}",
                    entity=c["slug"],
                    chapter=seen,
                )
            )
    return rows


def _seeds(canon: Path) -> list[dict[str, Any]]:
    rel = "plot/unresolved-seeds.json"
    rows = []
    for s in _rows(_load(canon, rel)[1]):
        planted, resolved = _int(s.get("planted_in_chapter")), _int(s.get("resolved_in_chapter"))
        if planted is None or resolved is None:
            continue
        slug = s.get("slug")
        if resolved < planted:
            rows.append(
                _row(
                    "seed_resolved_before_planted",
                    "concern",
                    rel,
                    f"Seed {slug!r} resolved in chapter {resolved}, before it was planted "
                    f"(chapter {planted})",
                    entity=slug,
                    chapter=resolved,
                )
            )
        elif resolved == planted and str(s.get("priority") or "") == "critical":
            rows.append(
                _row(
                    "seed_resolved_when_planted",
                    "concern",
                    rel,
                    f"Critical seed {slug!r} is planted and resolved in chapter {planted}",
                    entity=slug,
                    chapter=planted,
                    detail=str(s.get("description") or "")[:200],
                )
            )
    return rows


def _timeline(canon: Path, through: int) -> list[dict[str, Any]]:
    rel = "style/story-timeline.json"
    stamps = [
        r
        for r in _rows(_load(canon, rel)[1], "chapter_timestamps")
        if (_int(r.get("chapter")) or 0) <= through
    ]
    if len(stamps) < 3:
        return []
    rows = []
    for field in ("narrative_time", "end_time"):
        values = [str(r.get(field) or "").strip() for r in stamps]
        common, n = Counter(v for v in values if v).most_common(1)[0] if any(values) else ("", 0)
        blank = values.count("")
        if blank == len(values) or n == len(values) or (n + blank) / len(values) >= 0.75:
            detail = f"{n} of {len(values)} chapters say {common!r}" if common else "all blank"
            if blank and common:
                detail += f"; {blank} blank"
            rows.append(
                _row(
                    "timeline_vague",
                    "info",
                    rel,
                    f"Timeline {field} does not tell chapters apart ({detail})",
                    entity=field,
                    detail=detail,
                )
            )
    return rows


def _anchor(name: str) -> tuple[str, str]:
    words = _bare(name).split()
    return words[0], words[-1]


def _prose(chapters: Mapping[int, str], upto: int | None = None) -> str:
    return _norm(" ".join(t for n, t in sorted(chapters.items()) if upto is None or n <= upto))


def _drift_match(canon_name: str, prose_name: str) -> bool:
    """Same-shape names that differ: likely one entity renamed."""
    a, b = _bare(canon_name).split(), _bare(prose_name).split()
    if a == b:
        return False
    if a[0] in _TITLES and a[0] == b[0]:
        return True  # St. Augustine's / St. Mary's
    # Morales Auto Body / Luis Auto Body. Shared surnames alone are usually
    # relatives (Lila Cole / Siena Cole), not drift.
    return len(a) >= 3 and len(b) >= 3 and a[-2:] == b[-2:]


def _names_vs_prose(canon: Path, chapters: Mapping[int, str], through: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    prose = _prose(chapters)
    raw = " ".join(chapters.values())
    common = common_words(raw)
    prose_names = {_bare(n): n for n in names_in(raw, common)}

    rel = "style/key-facts.json"
    facts = _load(canon, rel)[1]
    seen: set[str] = set()
    for fact in facts if isinstance(facts, list) else []:
        text = fact if isinstance(fact, str) else str((fact or {}).get("fact") or "")
        body = text.split(":", 1)[1] if ":" in text[:40] else text
        for name in names_in(body, common):
            b = _bare(name)
            if b in seen or re.search(rf"\b{re.escape(b)}\b", prose):
                continue
            seen.add(b)
            others = [orig for pb, orig in prose_names.items() if _drift_match(name, orig)]
            if len(others) == 1:
                rows.append(
                    _row(
                        "name_drift",
                        "concern",
                        rel,
                        f"Key facts say {name!r}; the prose says {others[0]!r}",
                        entity=name,
                        detail=text[:200],
                    )
                )

    for c in _characters(canon):
        intro = _int(c.get("introduced_chapter"))
        if intro is None or intro > through or intro not in chapters:
            continue
        tokens = [
            t
            for t in re.findall(r"[A-Za-z'’\-]{3,}", str(c["name"]))
            if t.lower() not in _HONORIFIC
        ]
        if tokens and not any(
            re.search(rf"\b{re.escape(_norm(t))}\b", _prose(chapters)) for t in tokens
        ):
            rows.append(
                _row(
                    "character_not_in_prose",
                    "concern",
                    f"characters/{c['slug']}.json",
                    f"{c['name']} (introduced chapter {intro}) is never named in the prose",
                    entity=c["slug"],
                    chapter=intro,
                )
            )
    return rows


def audit_canon(
    canon_dir: Path,
    chapters: Mapping[int, str],
    *,
    through: int | None = None,
) -> list[dict[str, Any]]:
    """All Canon checks. ``through`` = last chapter Canon should cover.

    ``chapters`` maps chapter number to prose (chapters the caller has).
    ``through`` defaults to the highest chapter number.
    """
    last = through if through is not None else max(chapters, default=0)
    rows: list[dict[str, Any]] = []
    for part in (
        lambda: _coverage(canon_dir, last),
        lambda: _cast(_characters(canon_dir)),
        lambda: _seeds(canon_dir),
        lambda: _timeline(canon_dir, last),
        lambda: _names_vs_prose(canon_dir, chapters, last),
    ):
        try:
            rows.extend(part())
        except Exception:  # noqa: BLE001 — Canon shape varies; never sink the run
            continue
    return rows


def load_story_chapters(chapters_dir: Path) -> dict[int, str]:
    out: dict[int, str] = {}
    for p in sorted(chapters_dir.glob("chapter-*.md")):
        m = re.search(r"(\d+)", p.stem)
        if m:
            out[int(m.group(1))] = p.read_text(encoding="utf-8", errors="replace")
    return out


def audit_story(story: Path) -> dict[str, Any] | None:
    """Audit ``story/canon`` against ``story/chapters``; None when either is absent."""
    canon, chapters_dir = story / "canon", story / "chapters"
    if not canon.is_dir() or not chapters_dir.is_dir():
        return None
    chapters = load_story_chapters(chapters_dir)
    if not chapters:
        return None
    return {
        "story": story.name,
        "chapters": len(chapters),
        "findings": audit_canon(canon, chapters),
    }


def audit_stories(stories_dir: Path) -> list[dict[str, Any]]:
    """Audit each story directory under ``stories_dir``."""
    results = (audit_story(p) for p in sorted(stories_dir.iterdir()) if p.is_dir())
    return [r for r in results if r is not None]


def render_audit_markdown(results: list[dict[str, Any]], *, examples: int = 5) -> str:
    """Summary by kind (stories affected, rows) plus a few examples each."""
    n = len(results)
    by_kind: dict[str, list[tuple[str, dict[str, Any]]]] = {}
    for r in results:
        for f in r["findings"]:
            by_kind.setdefault(f["kind"], []).append((r["story"], f))
    lines = [
        "# Canon audit",
        "",
        f"{n} stories with Canon and chapters. "
        f"{sum(1 for r in results if r['findings'])} have at least one finding.",
        "",
        "| Kind | Severity | Stories | Rows |",
        "| --- | --- | --- | --- |",
    ]
    for kind in KINDS:
        rows = by_kind.get(kind, [])
        if rows:
            stories = len({s for s, _ in rows})
            lines.append(
                f"| `{kind}` | {rows[0][1]['severity']} | {stories} of {n} | {len(rows)} |"
            )
    for kind in KINDS:
        rows = by_kind.get(kind, [])
        if not rows:
            continue
        lines += ["", f"## `{kind}`", ""]
        if kind in ("missing_file", "empty_file", "chapter_not_recorded"):
            files = Counter(f["file"] for _, f in rows)
            lines += [f"- `{file}`: {c} stories" for file, c in files.most_common()]
        for story, f in rows[:examples]:
            lines.append(f"- {story}: {f['summary']}")
        if len(rows) > examples:
            lines.append(f"- … {len(rows) - examples} more")
    return "\n".join(lines) + "\n"


__all__ = [
    "EXPECTED_FILES",
    "KINDS",
    "audit_canon",
    "audit_stories",
    "audit_story",
    "load_story_chapters",
    "names_in",
    "render_audit_markdown",
]
