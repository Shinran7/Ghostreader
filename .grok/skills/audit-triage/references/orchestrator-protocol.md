# Orchestrator protocol (Ghostreader)

## Id

`YYYY-MM-DD-Ghostreader` e.g. `2026-07-24-Ghostreader`

Suffix `-diff` when the run is an explicit second-pass diff export only.

## Audit inputs

SLizard audit against Ghostreader produces:

- `Ghostreader-audit.new.md` — findings on changed files only (**default ingest**)
- `Ghostreader-audit.md` — full repo snapshot; not for ingest

**Default triage:** ingest `.new.md`, run verify + defer resolution, export buckets,
open fix issues from buckets 1–2 when operator asks.

Commit hash resolution order (ingest):

1. `--commit` flag
2. report line `current audit commit: <hash>`
3. `.slizard/audit-run-manifest.json` → `commitHash`
4. `git rev-parse --short=8 HEAD`

## Phase 0 — Ingest

```text
python scripts/audit-triage-ingest.py
# or
python scripts/audit-triage-ingest.py --report C:\Users\shinr\Projects\Ghostreader-audit.new.md --id 2026-07-24-Ghostreader
```

Writes:

- `ledger.json` — all findings (markdown findingIds by default)
- `batches/batch-NNN.json` — pending findings, ~20 each
- `summary.json` — counts after rule pre-pass

## Phase 1 — Rule pre-pass (automatic)

Ingest marks obvious rows without Meeseeks:

- `tests/**`, `test_*.py` → appendix-noise
- `capped: test-quality`, lint appendix → appendix-noise
- `capped: cli-script-context`, scripts hygiene clusters → wontfix
- SHA-1 crypto fear on non-crypto IDs → false-positive
- fly.*/docker-compose P3 → wontfix

## Phase 2 — Verify (parallel Mr. Meeseeks)

Dispatch one Meeseeks per batch file. Template: `verifier-prompt.md`.

Write results to `results/result-batch-NNN.json`.

⊗ Skip reading source → invalid verdict.


## Phase 2a — Zero-fix second-pass (mandatory tripwire)

After Phase 2 results are on disk, before Phase 2b/3:

1. Tally fix-bucket rows (`confirmed-bug` / `likely-bug`) and pending severity mix from `batches/` + `results/`.
2. **Tripwire:** fix count is **0** AND the pending/verified bag has **any P1** or **≥5 P2** → run an adversarial second-pass on the full pending set (or all Phase 2 rows).
3. Second-pass prompt: `verifier-prompt.md` § Adversarial second-pass. Preserve first-pass results under `results-first-pass/`; write new results into `results/` (and optionally `second-pass/`).
4. Re-tally. Proceed to 2b/3 with the second-pass verdicts.

⊗ Merge/export a non-trivial P1/P2 bag as 0 bugs without running this tripwire.
⊗ Skip the tripwire when the bag is only scripts CLI / appendix / P3-only.

Operator may also say **second-pass** / **hostile re-check** to force 2a even when the tripwire is quiet.

## Phase 2b — Defer resolution (mandatory when defer > 0)

See `defer-resolution.md`. Summary:

```text
python scripts/audit-triage-split-defer-waves.py --dir <triage-dir>
# dispatch one Meeseeks per defer-waves/wave-N.json
python scripts/audit-triage-merge-defer-resolution.py --dir <triage-dir>
```

Ledger must have **zero** `defer` verdicts before Phase 3.

## Phase 3 — Merge

```text
python scripts/audit-triage-merge.py --dir <triage-dir>
```

Produces `outcome.md` (human) and updates `ledger.json`.

## Phase 4 — Export for issues

```text
python scripts/audit-triage-export-buckets.py --dir <triage-dir> --id <id>
```

Copies six bucket JSON files to `history/audit-triage/<id>/buckets/`.

## Phase 5 — Apply suppressions

Operator-approved rows from buckets 4+5 (and pure FP in 3) →
`.slizard/suppressions.yml` per `suppression-levers.md`.

## Phase 6 — Graduate to GitHub (operator-requested)

See `issue-graduation.md`. Run `scripts/audit-triage-create-issues.py` after
export is on disk. ⊗ Without explicit operator consent.
