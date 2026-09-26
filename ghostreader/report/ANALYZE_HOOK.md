# Analyze JSON hook (0.2.0)

Autonomicon (and scripts) read analyze JSON from:

```text
ghostreader analyze … --format json
```

Stdout / the report file is one JSON object. Ignore unknown fields.

## Version fields

| Field | Meaning |
| --- | --- |
| `ghostreader_version` | **Analyze JSON contract** (`ANALYZE_JSON_VERSION`). Currently **`0.2.0`**. Bumps only when analyze payload shape changes. |
| `package_version` | Installed package version (`ghostreader.__version__`). For correlating which install produced the file. |

Do **not** assume `ghostreader_version` equals companion brief `ghostreader_version`, or equals `package_version`. Companion briefs stay on their own contract (today **`0.2.2`**). Package `__version__` is released separately and was **not** bumped with this contract wave.

## Contract shape (0.2.0)

Always present:

- `repetition_findings` — book-wide algorithmic rows (empty list OK). Prefer these for surgical avoid-lists. Soft `prose.repetition` in `prioritized_findings` remains the craft judgment note.
- `register_findings` — additive opening-window register / initiation rows (empty list OK). Emitted on **`standard` and `deep`** when `analyze_register_watch` is on; `quick` / kill-off → `[]`. Kinds: `unearned_jargon` \| `initiation_budget` only. Soft `prose.human_door` / `prose.jargon_earn` stay **companion-only** in v1 (stock analyze prose stays five-pack).
- `prioritized_findings` — ranked findings. Empty-evidence **strengths** are omitted after enrich (ratings may still show strength).
- Continuity findings may carry additive `signal_kind` when enrich provided it.

Repetition row notes vs companion: always `"focus_count": 0`; never `kind: dialogue_tag`; scope is whole-book chapter cardinality.

Markdown reports include a thin “Algorithmic repetition” subsection when rows are non-empty. JSON is the machine contract. `register_findings` is JSON-primary (no markdown subsection required in v1).

## Minimal version keys

```json
{
  "ghostreader_version": "0.2.0",
  "package_version": "0.1.0",
  "repetition_findings": [],
  "register_findings": []
}
```
