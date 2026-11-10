# Analyze JSON hook (0.2.5)

Autonomicon (and scripts) read analyze JSON from:

```text
ghostreader analyze … --format json
```

Stdout is exactly one JSON object. Progress, warnings and "Report saved"
lines go to stderr (fixed in #18; before that they shared stdout). Add
`--json-out PATH` to also write the same JSON to a file; that works with any
`--format`. `--output` is still a copy of the Markdown report. Ignore unknown
fields.

Reruns are cached by content hash (#18). Chapter fact sheets share the
companion fact store (`state/stories/<story>/`); chapter, act and global
summaries sit under `state/llm-cache/`, keyed on the input text, model and
prompt version. An unchanged book makes no fact or summary calls; an edited
chapter re-runs its own facts and summary, its act and the global summary.
Analysis agents still run each time. `--no-cache` skips cache reads and
writes. The last report is kept once at `state/last-report.json` (read by
`compare` and `chat`), and the summaries at `state/summaries.json`.

Analyze no longer builds the LanceDB index; only `chat` uses it. `chat`
builds it on first use, and rebuilds it when the chapter text, summaries or
embedding model change. LanceDB and local embeddings (torch) are the optional
`chat` extra (`uv sync --extra chat`, or `pip install 'ghostreader[chat]'`;
`dev` includes it). Companion and analyze do not need them.

## Version fields

| Field | Meaning |
| --- | --- |
| `ghostreader_version` | **Analyze JSON contract** (`ANALYZE_JSON_VERSION`). Currently **`0.2.5`**. Bumps only when analyze payload shape changes. |
| `package_version` | Installed package version (`ghostreader.__version__`). For correlating which install produced the file. |

Do **not** assume `ghostreader_version` equals companion brief `ghostreader_version`, or equals `package_version`. Companion briefs stay on their own contract (today **`0.2.8`**). Package `__version__` is released separately and was **not** bumped with this contract wave.

## Contract shape (0.2.5)

Always present:

- `repetition_findings` — book-wide algorithmic rows (empty list OK). Prefer these for surgical avoid-lists. Soft `prose.repetition` in `prioritized_findings` remains the craft judgment note.
- `register_findings` — additive opening-window register / initiation rows (empty list OK). Emitted on **`standard` and `deep`** when `analyze_register_watch` is on; `quick` / kill-off → `[]`. Kinds: `unearned_jargon` \| `initiation_budget` only. Soft `prose.human_door` / `prose.jargon_earn` stay **companion-only** in v1 (stock analyze prose stays five-pack).
- `thrash_findings` — additive reader-visible thrash rows (empty list OK). Emitted on **`standard` and `deep`** when `analyze_thrash_watch` is on; `quick` / kill-off → `[]`. Kinds: `within_scene` \| `chapter_rare` \| `phrase` \| `dialogue_tag` \| `common_word` \| `cross_chapter`. Machine rows are the v1 action surface for Autonomicon end-of-book cleanup. Soft `prose.uncommon_thrash` is **deferred** (not shipped in v1). Do not overload `prose.vocabulary` / `prose.repetition` for Zipf/#355 thrash. Do not overload `repetition_findings` for literary carpet. Optional `analyze_thrash_load_bearing` in `config.yaml` raises the common-word bar for listed motif lemmas (empty = ordinary thresholds).
- `prioritized_findings` — ranked findings. Empty-evidence **strengths** are omitted after enrich (ratings may still show strength).
- Continuity findings may carry additive `signal_kind` when enrich provided it.
- `unverified_findings` — concerns whose quotes are not in the manuscript
  (empty list OK). They are removed from `prioritized_findings` and from the
  `overview` counts; `prioritized_findings` is re-ranked.
- `quote_stats` — `{verified, unverified, dropped, recovered, recovery_calls}`
  (`{}` when `quote_verification: false`).

### Since 0.2.5: usage and per-job models (#19)

- `usage` — `{llm_calls, input_tokens, output_tokens, total_tokens, by_model}`
  for this run; same shape as the companion brief (`companion/HOOK.md`,
  Since 0.2.8). Cached facts and summaries make no calls, so reruns show
  fewer.
- Per-job models in `config.yaml` (`facts`, `continuity`, `craft`,
  `narrative`, `synthesis`, `rewrite_writer`). `--show-rewrites` uses only
  `rewrite_writer`; with no `rewrite_writer.model` it skips rewrites and adds
  a warning.
- The JSON probe result is cached per model per day in the analyze state
  directory (`json-probe.json`). `--no-cache` probes again.
- `check_homes` — `{gce_in_pipeline, dropped_dimensions, thrash_within_scene,
  dropped_findings, deduped: {thrash_phrase_rows, prose_repetition_findings}}`.
  One home per check: with `gce_in_pipeline: true`, `prose.rhythm`,
  `prose.vocabulary` and `prose.earth_anachronism` are removed from
  `prioritized_findings`, `dimension_ratings` and `unverified_findings`, and
  `within_scene` thrash rows are left out (they still feed `cross_chapter`).
  Per-check flags in `config.yaml` override (`null` = follow
  `gce_in_pipeline`). Default: nothing dropped.
- Repetition dedupe (always on): a `phrase` thrash row that repeats a
  `repetition_findings` phrase is dropped, and a `prose.repetition` concern
  that names a machine row's phrase or word is dropped from
  `prioritized_findings` (re-ranked). Machine rows win.

### Since 0.2.4: Canon audit (#16)

- `canon_findings` — deterministic Canon audit rows over the whole book (empty
  list OK). Empty when continuity did not use Canon. Same row shape and kinds
  as the companion brief (see `companion/HOOK.md`, Since 0.2.7). Rows never
  enter `prioritized_findings` or ratings.
- Book-wide CLI: `ghostreader canon-audit <story-or-stories-dir>` (`--json`, `--out`).

### Since 0.2.3: Canon continuity (#16)

When Autonomicon Canon sits beside the chapters, the consistency pass checks
each chapter's prose against Canon as of the chapter before it (one LLM call
per chapter, 4 at a time) in place of the fact-sheet ask, with or without
TypeSafe. Chapters with no Canon entries before them are skipped.

- `continuity_source` — the continuity state of record: `"canon"` when
  Autonomicon Canon (`canon/` beside the chapters, or
  `checkpoints/chapter-NNN/canon/` when present) was loaded and chapter prose
  was checked against it; `"facts"` when Ghostreader fact sheets were used;
  `""` when continuity did not run.
- `canon_stats` — `{chapters, checkpoints, failed, skipped_empty}` (chapter counts); `{}` unless `continuity_source` is
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

### Since 0.2.2: quote verification (#17)

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
- Consistency concerns that do not verify (fact-sheet paraphrase when
  TypeSafe is off) first get one LLM quote fetch each, capped by
  `quote_recovery_max` (default 5 per run). Recovered rows carry
  `quote_recovered: true` and the original text in `evidence_claim` /
  `counter_evidence_claim`. Strengths and neutrals are tagged, never removed.
- Markdown: verified quotes show `(Ch N, line L)`; an "Unverified Findings"
  section lists dropped concerns.

Repetition row notes vs companion: always `"focus_count": 0`; never `kind: dialogue_tag`; scope is whole-book chapter cardinality. Fancy dialogue-tag carpet lives under `thrash_findings` (`kind=dialogue_tag`), never bare `said`.

Markdown reports include a thin “Algorithmic repetition” subsection when rows are non-empty. JSON is the machine contract. Since #18 the Markdown report also has short Register, Word thrash and Canon audit sections (30 rows each; the rest are in the JSON). JSON stays the full contract.

### `thrash_findings` row shape

| Field | Notes |
| --- | --- |
| `kind` | `within_scene` \| `chapter_rare` \| `phrase` \| `dialogue_tag` \| `common_word` \| `cross_chapter` |
| `lemma` | Normalized single-token lemma; **`null` when `kind=phrase`** |
| `phrase` | Normalized multi-word phrase when `kind=phrase`; else `null` |
| `count` | Hit count (local or rolled) |
| `chapters` | Chapter numbers involved |
| `chapter` | Primary chapter for chapter-scoped kinds; null for `cross_chapter` |
| `scene_index` | 0-based scene within chapter when known |
| `severity` | `high` / `moderate` / `low` — rare kinds: high ≥4, moderate ≥2; `common_word`: high ≥8, moderate ≥6 |
| `quote` | Verbatim span for surgical search; for `cross_chapter`, from the densest chapter then worst scene |
| `normalized_key` | Lemma or phrase key |
| `foothold_token` | First surface form (keep this) |
| `later_surfaces` | Later surface forms to vary (optional empty for common/phrase/dialogue_tag) |

**Noise floor:** never crown bare `said` / `says` / `say` or mid-sentence proper names as primary thrash. Fancy tags skip `common_word` (one smell, one seat). Cap default 40 across all kinds. Sort: severity → kind priority (`within_scene` → `chapter_rare` → `phrase` → `dialogue_tag` → `common_word` → `cross_chapter`) → −count → key.

Consumers that do not know `thrash_findings` or unknown kinds ignore them. Missing key ≡ `[]`.

## Minimal version keys

```json
{
  "ghostreader_version": "0.2.5",
  "package_version": "0.1.0",
  "repetition_findings": [],
  "register_findings": [],
  "thrash_findings": []
}
```
