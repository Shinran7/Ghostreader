# Phase 6 — Graduate to GitHub issues (Ghostreader)

Run **only when the operator uses an action verb** (`open issues`, `create tickets`, `per bucket`, `graduate to GH`). Triage ends at Phase 4 export; issue creation is a separate handoff.

## Preconditions

- Phase 4 export exists under `history/audit-triage/<id>/`
- `outcome.md` and `buckets/*.json` are committed or will land with the work
- Operator approved issue creation for this triage id

## Bucket → issue map

| Bucket file | Default title prefix | Action | Hygiene block |
|-------------|---------------------|--------|---------------|
| `1-confirmed-bugs-to-fix` | Ghostreader audit triage: confirmed bugs to fix (N) | Ship code fixes | Yes — see `implementation-hygiene.md` |
| `2-likely-bugs` | Ghostreader audit triage: likely bugs (N) | Fix or short-verify | Yes |
| `3-reporting-debt` | Ghostreader audit triage: reporting debt (N) | Suppress / upstream SLizard | Optional |
| `4-appendix-noise` | Ghostreader audit triage: test appendix noise (N) | Bulk suppress | No |
| `5-wontfix` | Ghostreader audit triage: wontfix candidates (N) | Accepted risk suppress | No |
| `6-defer` | — | **Skip** — defer must be empty at export | — |

**Skip rules**

- ⊗ Open an issue when bucket count is **0**
- ~ On small runs, operator may merge buckets 1+2 into one fix issue
- Cluster systemic duplicate-pattern rows into **one** issue, not one per file

## Issue body template

Write body to `.tmp/issue-<bucket-file>.md` (never inline `gh --body` on Windows).

```markdown
## Context

Ghostreader SLizard-audit triage on commit `<auditCommit>` (<active> active in report; <ledger> in ledger).
Orchestrated via `.grok/skills/audit-triage/`. Export id: `<triage-id>`.

## Bucket

- **<bucket-file>** — N findings
- **Action:** <one-line action from table>

## Artifacts

- Machine ledger: `history/audit-triage/<id>/buckets/<bucket-file>.json`
- Human synthesis: `history/audit-triage/<id>/outcome.md`
- Export README: `history/audit-triage/<id>/README.md`

## Acceptance

- All N rows in this bucket addressed per action above
- Cross-link commits to this issue

## Implementation hygiene

(buckets 1–2 — copy from implementation-hygiene.md issue checklist)
```

## gh command

Preferred: canonical script (reads bucket counts, skips empty):

```text
python scripts/audit-triage-create-issues.py --id <triage-id> --commit <prefix> --report-active N --ledger-total M --dry-run
python scripts/audit-triage-create-issues.py --id <triage-id> --commit <prefix> --report-active N --ledger-total M
```

Manual fallback:

```text
gh issue create --title "<title>" --body-file .tmp/issue-<bucket-file>.md
```

Record created numbers in `.tmp/issue-ids-<triage-id>.json`.

## Closure patterns

| Bucket | Typical close |
|--------|----------------|
| 1–2 | Fix commits + pytest; close with summary |
| 3 | Suppressions and/or upstream SLizard note |
| 4–5 | Suppressions entries or explicit wontfix disposition in issue |

## Canonical script

`scripts/audit-triage-create-issues.py` reads export `buckets/*.json` counts and emits issues. Override `--id` and `--commit` for each run.
