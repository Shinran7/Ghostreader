# Companion JSON hook (0.2.1)

Autonomicon calls:

```text
ghostreader companion chapter-NNN.md --format json
```

Stdout is one JSON object. Stderr is progress only. Ignore unknown fields.

`ghostreader_version` on this payload is **`0.2.1`**. It is independent of package `__version__` and of analyze JSON export (those may stay `0.1.0`).

## Shared continuity judgment text (no contract bump)

Companion gate Nouls reuse analyze `_CONSISTENCY_INSTRUCTIONS` (`plot_holes` /
`character` / `timeline` / `unresolved`). Prompt precision for impossibility vs
tone, location ownership (no double-fire), and non-monotonic countdown rules
tightens companion progressive-gate judgment text when those shared instructions
change. **Brief contract stays `0.2.1`** — judgment wording only; no
`GHOSTREADER_VERSION` bump for this side effect.

## Verdict rules

| Band | Flips `verdict` to `watch`? | Exit `2` (`--fail-on-continuity`)? |
| --- | --- | --- |
| Gate continuity (`character` / `timeline` / `plot_holes`) | Yes | Yes (continuity concerns only) |
| Craft | Yes | No |
| Info continuity (`foreshadowing` / `unresolved`) | **Never** alone | No |
| Light narrative (`pacing` / `character_arcs`) | Only when narrative is **on** and the finding is **grounded to chapter N** | No |

`info` never flips ship by itself. Craft can. Narrative flips only when enabled and grounded.

`verdict_drivers` lists which bands caused `watch`: `"continuity"`, `"craft"`, `"narrative"`. Prefer this (and the finding arrays) over guessing from `verdict` alone.

Soft LLM `craft_findings` stay human-facing. Machine-actionable cross-chapter repetition for avoid/governor promotion lives in **`repetition_findings`** (algorithmic; empty list OK).

## Config knobs

| Knob | Default | Role |
| --- | --- | --- |
| `companion_craft_window` | `5` | Prior chapters in repetition window (plus N) |
| `companion_cross_chapter_craft` | `true` | `false` = N-only craft (v1 behavior) |
| `companion_info_dims` | `true` | Ask/store foreshadowing + unresolved (watch-only) |
| `companion_light_narrative` | **`true`** | Pacing + character arcs; set `false` to roll back |

Steady state is narrative **on**. Kill switch remains for rollback.

## Additive fields

### Since 0.2.0

Always present (empty lists until filled):

- `craft_window_chapters` — chapters passed to the repetition detector
- `info_continuity_findings` / `info_continuity_ratings` — watch-only; never gate alone
- `narrative_findings` / `narrative_ratings` — empty when narrative off or skipped
- `verdict_drivers` — which bands flipped watch

### Since 0.2.1

- `repetition_findings` — algorithmic craft-window rows from `companion_repetition_to_dicts` (cap 25). Always present; empty when craft is skipped (`--continuity-only`) or nothing N-relevant was found.

| Field | Type | Notes |
| --- | --- | --- |
| `phrase` | string | Exact/near-exact text. Dialogue tags are the lemma only (e.g. `said`), not a `[dialogue tag]` prefix |
| `kind` | `word` \| `phrase` \| `dialogue_tag` \| `sentence_pattern` | Detector bucket |
| `count` | int | Hits in craft window |
| `focus_count` | int | Hits in chapter N (`0` for sentence patterns) |
| `chapters` | int[] | Chapters that contain it |
| `scope` | `cross_chapter` \| `local` | Same rule as craft-window serialization |
| `severity` | `high` \| `moderate` \| `low` | Existing detector bands |
| `quote` | string \| null | One short verbatim span from N when available |
| `normalized_key` | string \| null | Lowercased, collapsed whitespace (Autonomicon dedup key) |

Older keys keep their names and meaning for Autonomicon parsers.

## Minimal example payload

Shape Autonomicon should accept (unknown keys ignored):

```json
{
  "ghostreader_version": "0.2.1",
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
  "repetition_findings": [
    {
      "phrase": "cold iron",
      "kind": "phrase",
      "count": 6,
      "focus_count": 2,
      "chapters": [16, 18],
      "scope": "cross_chapter",
      "severity": "moderate",
      "quote": "The cold iron bit his palm.",
      "normalized_key": "cold iron"
    }
  ],
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
3. Confirm stdout parses; `ghostreader_version` is `0.2.1`; additive keys exist including `repetition_findings`.
4. Confirm info-only concerns leave `verdict` as `ship` (or leave drivers without inventing `"info"`).
5. Force a grounded narrative concern (or compare a known soft chapter) and confirm `verdict_drivers` includes `"narrative"` without exit `2`.
6. Rollback check: set `companion_light_narrative: false` and confirm narrative arrays empty / no narrative driver.
7. Confirm cross-chapter phrase rows in `repetition_findings` carry `kind`, `scope`, `chapters`, `focus_count` (empty list is fine).

Repeat a short A/B with TypeSafe on and off if both paths matter for the hook.
