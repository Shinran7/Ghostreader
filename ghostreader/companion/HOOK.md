# Companion JSON hook (0.2.10)

Autonomicon calls:

```text
ghostreader companion chapter-NNN.md --format json
```

Stdout is one JSON object. Stderr is progress only. Ignore unknown fields.

`ghostreader_version` on this payload is **`0.2.10`**. It is the **companion brief contract**, not the install version and not the analyze contract.

| Field | Meaning |
| --- | --- |
| `ghostreader_version` | Companion JSON contract (**`0.2.10`**). Independent of analyze JSON (`0.2.6`) and of package `__version__`. |
| `package_version` | Installed package version (`ghostreader.__version__`). Additive; ignore if unused. **No** brief contract bump for this field. |

Do **not** assume companion and analyze `ghostreader_version` strings match. Correlate installs with `package_version` on both surfaces. See `ghostreader/report/ANALYZE_HOOK.md` for analyze.

## Shared continuity judgment text (no contract bump)

Companion gate Nouls reuse analyze `_CONSISTENCY_INSTRUCTIONS` (`plot_holes` /
`character` / `timeline` / `unresolved`). Prompt precision for impossibility vs
tone, location ownership (no double-fire), and non-monotonic countdown rules
tightens companion progressive-gate judgment text when those shared instructions
change. Judgment wording only; **no** extra `GHOSTREADER_VERSION` bump for that
side effect beyond the current contract.

## Verdict rules

| Band | Flips `verdict` to `watch`? | Exit `2` (`--fail-on-continuity`)? |
| --- | --- | --- |
| Gate continuity (`character` / `timeline` / `plot_holes`) | Yes | Yes (continuity concerns only) |
| Craft (incl. soft `prose.human_door` / `prose.jargon_earn` / `prose.earth_anachronism` / optional `prose.voice_card`) | Yes | No |
| Info continuity (`foreshadowing` / `unresolved`) | **Never** alone | No |
| Light narrative (`pacing` / `character_arcs`) | Only when narrative is **on** and the finding is **grounded to chapter N** | No |
| Machine `register_findings` alone | **No** | No |
| Machine `voice_card_findings` alone | **No** | No |

A continuity pass that could not be checked (`continuity_status: "failed"`) also flips `watch` and adds `"continuity"` to `verdict_drivers`. Under `--fail-on-continuity` it exits `2`, as a gate concern does.

`info` never flips ship by itself. Soft craft can. Narrative flips only when enabled and grounded. Algorithmic `register_findings` and `voice_card_findings` never flip `watch` or exit `2` by themselves.

`verdict_drivers` lists which bands caused `watch`: `"continuity"`, `"craft"`, `"narrative"`. Prefer this (and the finding arrays) over guessing from `verdict` alone. Soft register / voice-card concerns stay under **`"craft"`** (no `"register"` or `"voice_card"` driver in v1).

Soft LLM `craft_findings` stay human-facing. Machine-actionable cross-chapter repetition for avoid/governor promotion lives in **`repetition_findings`** (algorithmic; empty list OK). Machine register / initiation rows live in **`register_findings`** (algorithmic; empty list OK; **JSON-primary** — markdown/terminal may omit machine rows in v1). Machine voice-vs-card rows live in **`voice_card_findings`** (algorithmic; empty list OK; **JSON-primary**).

## Config knobs

| Knob | Default | Role |
| --- | --- | --- |
| `companion_craft_window` | `5` | Prior chapters in repetition window (plus N) |
| `companion_cross_chapter_craft` | `true` | `false` = N-only craft (v1 behavior) |
| `companion_info_dims` | `true` | Ask/store foreshadowing + unresolved (watch-only) |
| `companion_light_narrative` | **`true`** | Pacing + character arcs; set `false` to roll back |
| `companion_register_watch` | **`true`** | Heuristic `register_findings` + soft register dims; `false` → `[]` + stock five prose dims |
| `companion_voice_card_watch` | **`true`** | Heuristic `voice_card_findings` + soft `prose.voice_card` (when wired); `false` → `[]` + no soft voice-card dim |
| `quote_verification` | **`true`** | Check finding quotes against the text (#17); `false` = off |
| `continuity_canon` | **`true`** | Check chapter prose against Autonomicon Canon when `canon/` is present (#16); `false` = fact sheets |
| `quote_recovery_max` | `5` | Max LLM calls per run to fetch verbatim quotes for unverified continuity concerns; `0` = none |

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

### Since 0.2.2

- `register_findings` — algorithmic opening-window register rows (cap 15). **JSON-primary** (always on the payload; markdown/terminal need not render machine rows in v1). Empty when craft/register is skipped (`--continuity-only` / kill switch) or nothing fired. Kinds are only `unearned_jargon` \| `initiation_budget` — **no** `missing_human_door` or Earth-anachronism machine rows (human door is soft `prose.human_door`; Earth timeline/culture is soft `prose.earth_anachronism` craft only). Soft craft dims `prose.human_door` / `prose.jargon_earn` / `prose.earth_anachronism` may also appear under `craft_findings` / `craft_ratings`. Soft-only dims do **not** bump the contract by themselves.

| Field | Type | Notes |
| --- | --- | --- |
| `kind` | `unearned_jargon` \| `initiation_budget` | Detector bucket |
| `severity` | `high` \| `moderate` \| `low` | Machine bands |
| `summary` | string | One-line human summary |
| `quote` | string \| null | Verbatim span (preferred; required spirit for `high`) |
| `span_start_word` | int \| null | 0-based word offset over **stripped** body tokens |
| `span_end_word` | int \| null | Exclusive end word offset |
| `term` | string \| null | Coined/institutional term when `kind=unearned_jargon` |
| `window_words` | int | Window used (default 300) |
| `coined_count` | int \| null | Unexplained count for `initiation_budget` |
| `budget` | int \| null | Allowed unexplained count (default 3) |
| `chapter` | int | Focus chapter number |
| `normalized_key` | string \| null | Lowercased collapsed key for Autonomicon dedup |

### Since 0.2.10

- `dialogue_findings` for the focus chapter (empty list OK; missing ≡ `[]`).
  Never flips the verdict. Kill switch: `companion_dialogue_watch: false`.

Dialogue shape rows (#21). No LLM. Thresholds come from ten public-domain
novels. Rows are watch signals, never defects on their own.

| Field | Type | Notes |
| --- | --- | --- |
| `kind` | string | `volley` \| `no_long_speech` \| `fluent_speech` \| `tennis_habit` \| `tennis_return` \| `quip_humor` \| `announced_levity` |
| `severity` | string | `high` \| `moderate` \| `low` |
| `chapter` | int | Chapter number |
| `summary` / `message` | string | Plain-language note (same text) |
| `quote` | string | Volley: first four turns; returns, quips, laughs: the lines |
| `turns` | int | Volley length, or spoken turns in the chapter |
| `start_paragraph` | int | Volley only: 1-based paragraph where it starts |
| `metric` | float | Volley length, longest turn words, or hesitant share |
| `form` | string | `tennis_return` only: `recast` \| `x_not_y` |

- `volley`: 10+ turns in a row of 12 spoken words or fewer. `low` unless
  under 3% of the chapter's turns run 40+ words; then `moderate`, or `high`
  at 16+ turns.
- `no_long_speech`: 25+ turns and none runs 40+ words.
- `fluent_speech`: 25+ turns and under 5% hesitate (trailing off, broken-off
  lines, fillers, hedges); `high` under 2%. Human novels run 15 to 35%.
- `tennis_habit` / `tennis_return` (LLM judge): a statement, then a reply that
  recasts it to deny it ("Sentiment." / "Logistics.") or corrects it with
  "X, not Y". Human novels: about 0.2% of exchanges; Autonomicon about 3%.
  `tennis_habit` per chapter at 2+ returns and 2% (`high` at 3.5%); up to five
  `tennis_return` rows (`low`) carry the quotes. Companion runs it on the focus
  chapter (`companion_dialogue_judge`, one call per 60 exchanges); analyze does
  not; `ghostreader dialogue --judge` runs it on every chapter.
- `quip_humor` / `announced_levity` (LLM comedy judge, one call per ~1,100-word
  scene): sorts each comic moment by source: situation, character, verbal
  (quips), or announced (narration says people laugh with no funny cause).
  `quip_humor` per chapter at 4+ comic moments when under 25% come from
  situation or character (`high` under 10%); quotes are sample quips. Comic
  human novels: 33 to 84%; Autonomicon: 0 to 19%. Up to three
  `announced_levity` rows (`low`) per chapter. Companion runs it on the focus
  chapter (`companion_comedy_judge`); `ghostreader dialogue --comedy` runs it on
  every chapter.
- Standalone: `ghostreader dialogue <story dir or file> [--json] [--judge]
  [--comedy]` prints the per-chapter table and every row.

### Since 0.2.9

Anti-tidy narrative shape (#8; Autonomicon #268 S4).

- `shape_findings` — watch rows for tidy narrative-shape craft patterns in
  the focus chapter (empty list OK; missing ≡ `[]`). **Progressive mode
  only**; sweep and `--continuity-only` emit `[]`. One LLM call (the
  `narrative` job model). Never flips the verdict, never gates, never feeds
  craft ratings. Craft framing only, never a claim about authorship.
- Kinds: `anti_tidy_theme_announce` \| `anti_tidy_dialogue_philosophy` \|
  `anti_tidy_moral_tidy` \| `anti_tidy_single_track` \|
  `anti_tidy_flat_escalation`. The last two are book-level and asked only
  once three chapters come before the focus chapter.
- Kill switch: `companion_shape_watch: false` in `config.yaml`.

| Field | Type | Notes |
| --- | --- | --- |
| `kind` | string | One of the five kinds |
| `severity` | string | `watch` (v1 only) |
| `chapter` | int | Focus chapter number |
| `quote` | string | Verbatim span from the focus chapter; may be `""` for the two book-level kinds only. A row whose quote is not in the chapter is dropped. |
| `message` | string | What happens in this chapter |
| `summary` | string | Same text as `message` (the Autonomicon ledger reads `summary`) |
| `suggested_fix` | string | One short fix |
| `location` | object \| null | Same shape as finding `location` (`null` with an empty quote) |
| `id` | string | Stable 12-character id |

At most 3 rows per chapter.

### Since 0.2.8

Cost and input (#19).

- `usage` — `{llm_calls, input_tokens, output_tokens, total_tokens, by_model}`
  for this run. `by_model` maps a model name to `{calls, input_tokens,
  output_tokens, total_tokens}`. Providers that report no token counts add
  calls but zero tokens. The JSON probe counts as a call when it runs.
- `chapter_note` is now `""` with `--format json` unless you pass `--note`.
  This saves one LLM call per chapter. The key is still present. Terminal
  output always writes the note.
- The JSON probe result is cached per model per day in
  `state/stories/<story>/json-probe.json`. A model that passed today is not
  probed again. Failures are never cached.
- Craft and narrative now read the whole focus chapter (head and tail past
  60,000 characters), not a short excerpt.
- Per-job models: `facts`, `continuity`, `craft`, `narrative` and `synthesis`
  in `config.yaml` can each name a model. A job with no model uses the main
  model. The probe runs on each distinct model.
- `check_homes` — `{dropped_dimensions: [...]}`. One home per check: with
  `gce_in_pipeline: true` in `config.yaml` (or `companion --gce-in-pipeline`
  for one run), `prose.rhythm`,
  `prose.vocabulary` and `prose.earth_anachronism` are left to
  GhostCopyeditor. They are removed from `craft_findings` and
  `craft_ratings` and cannot drive the verdict. Per-check flags
  (`prose_rhythm`, `prose_vocabulary`, `earth_anachronism`; `null` = follow
  `gce_in_pipeline`) override. Default: nothing dropped. `human_door`,
  `jargon_earn` and `voice_card` ratings always stay.

### Since 0.2.7

Canon audit (#16 Phase 2). A deterministic check of Autonomicon Canon against
itself and the chapter prose. No LLM call.

- `canon_findings` — list of machine rows (empty list OK). Empty when there is
  no Canon, in sweep mode, with `--craft-only`, or with `continuity_canon: false`.
  Rows **never** flip the verdict. They report on the Updater's output, not on
  the chapter.
- The audit covers chapters **before N** (the Updater may not have run on N).
- Row shape: `{kind, severity, file, entity, chapter, summary, detail}`.
  `file` is relative to the canon dir; `entity`, `chapter` and `detail` may be
  `null`/empty.
- `severity` is `"concern"` or `"info"`.
- Kinds:

| Kind | Severity | Meaning |
| --- | --- | --- |
| `missing_file` | info | An expected Canon file is absent |
| `empty_file` | info | File present but empty or unreadable |
| `chapter_not_recorded` | info | A per-chapter file skips chapters (`detail` lists them) |
| `death_chapter_missing` | concern | Deceased character with no `died_chapter` |
| `seen_after_death` | concern | `last_seen_chapter` after `died_chapter` |
| `seed_resolved_when_planted` | concern | Critical seed resolved in its planting chapter |
| `seed_resolved_before_planted` | concern | Seed resolved before it was planted |
| `timeline_vague` | info | Most chapter timestamps are blank or identical |
| `name_drift` | concern | A key-fact name is absent from the prose; one similar name is present |
| `character_not_in_prose` | concern | A character's name never appears in the chapters |

- The same audit runs book-wide as `ghostreader canon-audit <story-or-stories-dir>`
  (Markdown, or `--json`).

### Since 0.2.6

Canon continuity (#16). In progressive mode, when Autonomicon Canon sits
beside the chapters, gate continuity checks chapter N's prose against Canon as
of chapter N−1 (one LLM call) in place of the fact-sheet ask, with or without
TypeSafe. Sweep mode stays on fact sheets.

- `continuity_source` — the continuity state of record: `"canon"` when
  Autonomicon Canon (`canon/` beside the chapters, or
  `checkpoints/chapter-NNN/canon/` when present) was loaded and chapter prose
  was checked against it; `"facts"` when Ghostreader fact sheets were used;
  `""` when continuity did not run.
- `canon_stats` — `{entries, from_checkpoint}` (`from_checkpoint` is `0`/`1`); `{}` unless `continuity_source` is
  `"canon"`.
- Canon continuity rows carry `counter_source: "canon"` and `canon_ref`
  `{id, kind, chapter, file}` naming the Canon entry they contradict
  (`file` is relative to the canon dir). `counter_evidence` is that entry's
  text, `"Canon Ch K (kind): …"`; it is exact by construction and is not
  checked against the manuscript. `chapter_ref` is `"K vs N"`. A row that cites
  an id not in the state has empty `counter_evidence` and `canon_ref.kind:
  null`, and does not gate.
- Canon is read only for chapters before N. Live Canon is filtered by chapter;
  a deceased character whose `died_chapter` is N or later reads as active.
- Kill switch: `continuity_canon: false` in `config.yaml` (fact sheets only).
- Fact-sheet parse failures no longer force `continuity_status: "failed"`
  or `watch` when `continuity_source` is `"canon"`: fact sheets are not the
  state of record then. A Canon folder with no entries before N warns and
  falls back to `"facts"`.

### Since 0.2.5

Quote verification (#17). Finding quotes are checked against the chapter text.

- Every LLM finding row (`prioritized_findings`, `continuity_findings`, and the
  other finding lists) may carry:
  - `id` — stable 12-character id from dimension plus quote position (or the
    normalized evidence when the quote is not found). Use it for dedup and
    "already fixed" tracking across runs.
  - `quote_verified` — `true` when `evidence` (and `counter_evidence`, when
    present) is in the manuscript; `false` when not; `null` when not checked
    (algorithmic rows, `quote_verification: false`).
  - `location` / `counter_location` — `{chapter, paragraph, line, char_start,
    char_end, match}` for the first verified quote part. `line` and
    `paragraph` are 1-based within the chapter text; `char_*` are offsets into
    it. `match` is `exact` \| `normalized` (quote marks, dashes, spacing) \|
    `fuzzy` (≥0.9 token similarity, ≥5 words).
- `prose.repetition` rows are exempt: their evidence is often counts, not
  passages. They are tagged but never demoted or dropped.
- `quote_stats` — `{verified, unverified, demoted, recovered, recovery_calls}`
  (recovery keys appear only when recovery ran; `{}` when verification is off or nothing was checked).
- Craft and narrative concerns whose quotes are not found become `neutral`
  with an `Unverified quote: ` summary prefix.
- Continuity concerns keep their severity. When their quotes do not verify
  (fact-sheet paraphrase), one LLM call per concern (cap `quote_recovery_max`,
  default 5) asks for the verbatim passages from up to three cited chapters.
  Recovered rows replace `evidence` / `counter_evidence` with the verified
  quotes, keep the originals in `evidence_claim` / `counter_evidence_claim`,
  and set `quote_recovered: true`. Still-unverified concerns never gate: they
  count as ungrounded (or preexisting).
- Kill switch: `quote_verification: false` in `config.yaml`.

### Since 0.2.4

- `continuity_status` — `"ok"` \| `"failed"` \| `"skipped"`. `failed` means continuity was **not** checked: the consistency model returned no structured findings, or fact extraction failed for one or more chapters. `skipped` means `--craft-only`. Before 0.2.4 a parse failure produced an empty gate and could ship. Treat `failed` as blocking.
- Exit codes under `--fail-on-continuity`: `2` when a gate concern lands **or** `continuity_status` is `failed` (fact-parse poisoning now exits `2`, not `1`). Without the flag, fact-parse poisoning still exits `1` when `abort_on_fact_parse_failure` is true.
- Gate grounding changes (no new fields):
  - A same-chapter contradiction now gates: chapter N is the only cited chapter, and `evidence` and `counter_evidence` are two different quotes. Identical quotes stay ungrounded.
  - `chapter_ref` sub-locators (`scene 3`, `line 40`, `para 2`, `p. 7`) no longer count as chapters. `Ch. 12` and `Chapters 3 and 7` parse.
  - Tone-understatement `plot_holes` concerns and empty-evidence concerns are demoted before the gate, as in analyze.

### Since 0.2.3

- `voice_card_findings` — algorithmic book-so-far voice-vs-card rows (cap 15). **JSON-primary** (always on the payload; markdown/terminal need not render machine rows in v1). Empty when craft/voice-card watch is skipped (`--continuity-only` / kill switch), cards are missing, speakers are below `min_lines`, or nothing fired. Kinds are only `card_mismatch` \| `card_collapse`. Machine rows **alone** never flip `watch` or exit `2`. Soft `prose.voice_card` (when enabled) stays under craft / `"craft"` drivers.

| Field | Type | Notes |
| --- | --- | --- |
| `kind` | `card_mismatch` \| `card_collapse` | Detector bucket |
| `severity` | `high` \| `moderate` \| `low` | Machine bands |
| `summary` | string | One-line human summary |
| `speaker` | string | Primary **card slug** (collapse: slug_a) |
| `speaker_b` | string \| null | Collapse partner **card slug**; null on mismatch |
| `quote` | string \| null | One verbatim attributed span |
| `card_excerpt` | string \| null | Truncated `dialogue_voice` (≤120 chars) |
| `metrics` | object \| null | `{line_count, avg_words, contraction_rate, fragment_rate, interruption_rate}` when attached |
| `chapters` | int[] | Chapters where this speaker’s quotes were found |
| `chapter` | int | Focus chapter N (brief `chapter_number`) |
| `normalized_key` | string \| null | e.g. `card_mismatch:slug` or `card_collapse:slug_a\|slug_b` (pair **sorted**) |

### Additive (no contract bump)

- `package_version` — install version string. Same meaning as on analyze JSON.

Older keys keep their names and meaning for Autonomicon parsers.

## Minimal example payload

Shape Autonomicon should accept (unknown keys ignored):

```json
{
  "ghostreader_version": "0.2.10",
  "package_version": "0.1.0",
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
  "register_findings": [],
  "voice_card_findings": [],
  "warnings": [],
  "continuity_status": "ok",
  "ungrounded_count": 0,
  "typesafe_enabled": true
}
```

When narrative is on and a grounded pacing concern lands, expect `verdict: "watch"`, a non-empty `narrative_findings`, and `"narrative"` inside `verdict_drivers`. Watch rate may rise vs narrative-off even when continuity and craft are clean.

## Autonomicon smoke checklist

Ghostreader cannot run Autonomicon smoke from this workspace. Operators should A/B in Autonomicon with narrative **on** (package default):

1. Point Autonomicon at Ghostreader `master` with `companion_light_narrative: true` (default).
2. Run companion on a mid/late chapter (e.g. `chapter-018.md`) with `--format json`.
3. Confirm stdout parses; `ghostreader_version` is `0.2.10`; `continuity_status` is `ok`; additive keys exist including `repetition_findings`, `register_findings`, `voice_card_findings`, `shape_findings`, `dialogue_findings`, and `package_version`.
4. Confirm info-only concerns leave `verdict` as `ship` (or leave drivers without inventing `"info"`).
5. Force a grounded narrative concern (or compare a known soft chapter) and confirm `verdict_drivers` includes `"narrative"` without exit `2`.
6. Rollback check: set `companion_light_narrative: false` and confirm narrative arrays empty / no narrative driver.
7. Confirm cross-chapter phrase rows in `repetition_findings` carry `kind`, `scope`, `chapters`, `focus_count` (empty list is fine).
8. Confirm `register_findings` is always present (empty OK) and kinds are only `unearned_jargon` / `initiation_budget`.
9. Confirm `voice_card_findings` is always present (empty OK) and kinds are only `card_mismatch` / `card_collapse`; machine rows alone do not flip `watch`.

Repeat a short A/B with TypeSafe on and off if both paths matter for the hook.
