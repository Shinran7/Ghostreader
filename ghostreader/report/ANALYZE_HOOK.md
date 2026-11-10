# Analyze JSON hook (0.2.4)

Autonomicon (and scripts) read analyze JSON from:

```text
ghostreader analyze … --format json
```

Stdout / the report file is one JSON object. Ignore unknown fields.

## Version fields

| Field | Meaning |
| --- | --- |
| `ghostreader_version` | **Analyze JSON contract** (`ANALYZE_JSON_VERSION`). Currently **`0.2.4`**. Bumps only when analyze payload shape changes. |
| `package_version` | Installed package version (`ghostreader.__version__`). For correlating which install produced the file. |

Do **not** assume `ghostreader_version` equals companion brief `ghostreader_version`, or equals `package_version`. Companion briefs stay on their own contract (today **`0.2.7`**). Package `__version__` is released separately and was **not** bumped with this contract wave.

## Contract shape (0.2.4)

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

Markdown reports include a thin “Algorithmic repetition” subsection when rows are non-empty. JSON is the machine contract. `register_findings` and `thrash_findings` are JSON-primary (no markdown subsection required in v1).

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
  "ghostreader_version": "0.2.4",
  "package_version": "0.1.0",
  "repetition_findings": [],
  "register_findings": [],
  "thrash_findings": []
}
```
