# Analyze JSON hook (0.2.1)

Autonomicon (and scripts) read analyze JSON from:

```text
ghostreader analyze … --format json
```

Stdout / the report file is one JSON object. Ignore unknown fields.

## Version fields

| Field | Meaning |
| --- | --- |
| `ghostreader_version` | **Analyze JSON contract** (`ANALYZE_JSON_VERSION`). Currently **`0.2.1`**. Bumps only when analyze payload shape changes. |
| `package_version` | Installed package version (`ghostreader.__version__`). For correlating which install produced the file. |

Do **not** assume `ghostreader_version` equals companion brief `ghostreader_version`, or equals `package_version`. Companion briefs stay on their own contract (today **`0.2.2`**). Package `__version__` is released separately and was **not** bumped with this contract wave.

## Contract shape (0.2.1)

Always present:

- `repetition_findings` — book-wide algorithmic rows (empty list OK). Prefer these for surgical avoid-lists. Soft `prose.repetition` in `prioritized_findings` remains the craft judgment note.
- `register_findings` — additive opening-window register / initiation rows (empty list OK). Emitted on **`standard` and `deep`** when `analyze_register_watch` is on; `quick` / kill-off → `[]`. Kinds: `unearned_jargon` \| `initiation_budget` only. Soft `prose.human_door` / `prose.jargon_earn` stay **companion-only** in v1 (stock analyze prose stays five-pack).
- `thrash_findings` — additive reader-visible thrash rows (empty list OK). Emitted on **`standard` and `deep`** when `analyze_thrash_watch` is on; `quick` / kill-off → `[]`. Kinds: `within_scene` \| `chapter_rare` \| `phrase` \| `dialogue_tag` \| `common_word` \| `cross_chapter`. Machine rows are the v1 action surface for Autonomicon end-of-book cleanup. Soft `prose.uncommon_thrash` is **deferred** (not shipped in v1). Do not overload `prose.vocabulary` / `prose.repetition` for Zipf/#355 thrash. Do not overload `repetition_findings` for literary carpet.
- `prioritized_findings` — ranked findings. Empty-evidence **strengths** are omitted after enrich (ratings may still show strength).
- Continuity findings may carry additive `signal_kind` when enrich provided it.

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
  "ghostreader_version": "0.2.1",
  "package_version": "0.1.0",
  "repetition_findings": [],
  "register_findings": [],
  "thrash_findings": []
}
```
