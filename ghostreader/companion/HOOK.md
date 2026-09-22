# Companion JSON hook (0.2.0)

Autonomicon calls:

```text
ghostreader companion chapter-NNN.md --format json
```

Stdout is one JSON object. Stderr is progress only. Ignore unknown fields.

`ghostreader_version` on this payload is **`0.2.0`**. It is independent of package `__version__` and of analyze JSON export (those may stay `0.1.0`).

## Verdict rules

| Band | Flips `verdict` to `watch`? | Exit `2` (`--fail-on-continuity`)? |
| --- | --- | --- |
| Gate continuity (`character` / `timeline` / `plot_holes`) | Yes | Yes (continuity concerns only) |
| Craft | Yes | No |
| Info continuity (`foreshadowing` / `unresolved`) | **Never** alone | No |
| Light narrative (`pacing` / `character_arcs`) | Only when narrative is **on** and the finding is **grounded to chapter N** | No |

`info` never flips ship by itself. Craft can. Narrative flips only when enabled and grounded.

`verdict_drivers` lists which bands caused `watch`: `"continuity"`, `"craft"`, `"narrative"`. Prefer this (and the finding arrays) over guessing from `verdict` alone.

## Config knobs

| Knob | Default | Role |
| --- | --- | --- |
| `companion_craft_window` | `5` | Prior chapters in repetition window (plus N) |
| `companion_cross_chapter_craft` | `true` | `false` = N-only craft (v1 behavior) |
| `companion_info_dims` | `true` | Ask/store foreshadowing + unresolved (watch-only) |
| `companion_light_narrative` | **`true`** | Pacing + character arcs; set `false` to roll back |

Steady state is narrative **on**. Kill switch remains for rollback.

## Additive 0.2.0 fields

Always present from Slice 1 onward (empty lists until filled):

- `craft_window_chapters` — chapters passed to the repetition detector
- `info_continuity_findings` / `info_continuity_ratings` — watch-only; never gate alone
- `narrative_findings` / `narrative_ratings` — empty when narrative off or skipped
- `verdict_drivers` — which bands flipped watch

Older keys keep their names and meaning for Autonomicon parsers.

## Minimal example payload

Shape Autonomicon should accept (unknown keys ignored):

```json
{
  "ghostreader_version": "0.2.0",
  "mode": "progressive",
  "generated_at": "2026-09-22T12:00:00+00:00",
  "manuscript_name": "the-jailer-s-wound",
  "story_slug": "the-jailer-s-wound",
  "chapter_number": 18,
  "chapters_considered": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18],
  "facts_reused": 17,
  "facts_extracted": 1,
  "verdict": "ship",
  "chapter_note": "Chapter 18 clears continuity and craft.",
  "continuity_findings": [],
  "preexisting_continuity_findings": [],
  "ungrounded_continuity_findings": [],
  "craft_findings": [],
  "continuity_ratings": [],
  "craft_ratings": [],
  "craft_window_chapters": [13, 14, 15, 16, 17, 18],
  "info_continuity_findings": [],
  "info_continuity_ratings": [
    {"dimension": "consistency.foreshadowing", "severity": "neutral", "note": ""},
    {"dimension": "consistency.unresolved", "severity": "neutral", "note": ""}
  ],
  "narrative_findings": [],
  "narrative_ratings": [
    {"dimension": "narrative.pacing", "severity": "neutral", "note": ""},
    {"dimension": "narrative.character_arcs", "severity": "neutral", "note": ""}
  ],
  "verdict_drivers": [],
  "warnings": [],
  "ungrounded_count": 0,
  "typesafe_enabled": true
}
```

When narrative is on and a grounded pacing concern lands, expect `verdict: "watch"`, a non-empty `narrative_findings`, and `"narrative"` inside `verdict_drivers`. Watch rate may rise vs narrative-off even when continuity and craft are clean.

## Autonomicon smoke checklist

Ghostreader cannot run Autonomicon smoke from this workspace. Operators should A/B in Autonomicon with narrative **on** (package default):

1. Point Autonomicon at Ghostreader `master` with `companion_light_narrative: true` (default).
2. Run companion on a mid/late chapter (e.g. `chapter-018.md`) with `--format json`.
3. Confirm stdout parses; `ghostreader_version` is `0.2.0`; additive keys exist.
4. Confirm info-only concerns leave `verdict` as `ship` (or leave drivers without inventing `"info"`).
5. Force a grounded narrative concern (or compare a known soft chapter) and confirm `verdict_drivers` includes `"narrative"` without exit `2`.
6. Rollback check: set `companion_light_narrative: false` and confirm narrative arrays empty / no narrative driver.

Repeat a short A/B with TypeSafe on and off if both paths matter for the hook.
