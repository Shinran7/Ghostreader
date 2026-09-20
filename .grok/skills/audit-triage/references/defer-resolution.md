# Phase 2b — Defer resolution (Ghostreader)

Defer is not a final outcome. It means the initial verifier could not decide. Run this phase **after Phase 2 (verify)** and **before Phase 3 (merge/export)** so the ledger has zero `defer` rows when artifacts ship.

⊗ Export `outcome.md` or bucket JSON with pending defer without running Phase 2b.

## When to run

Skip when ingest + rule pre-pass + Phase 2 produced zero defer rows.

Otherwise split remaining defer rows into waves, dispatch verifier Mr. Meeseeks, merge results back into `ledger.json`.

## Wave assignment

Use `scripts/audit-triage-split-defer-waves.py --dir <triage-dir>` (same `wave_for` rules):

| Wave | Scope | Default disposition |
|------|-------|---------------------|
| 1 | P1/P2 defer | Promote real defects to fix; Dockerfile/CI/reproducibility → wontfix or reporting unless server path breaks |
| 2 | Production `ghostreader/` / `site/` P3 | Product paths → fix or likely-bug; style heuristics → reporting or wontfix |
| 3 | Validators & heuristics | (rare on Ghostreader consumer) FP-ish language → reporting or wontfix |
| 4 | Scripts & infra | Default wontfix for one-off/dev scripts and fly.* P3; promote only on critical automation path |

## Dispatch

One Meeseeks per wave file under `<triage-dir>/defer-waves/wave-N.json`.

Prompt variant (defer resolver — **must pick a final verdict**, never `defer`):

```text
Audit defer resolver for Ghostreader at <REPO_ROOT>.

Read wave file: <WAVE_PATH>

These findings were deferred in the first pass. You MUST resolve each to a final verdict.

For EACH finding:
1. Read source at filePath:line (±30 lines)
2. Pick finalVerdict + finalBucket + one-line evidence
3. Set recommendedIssue to null (orchestrator maps buckets to GH later)

Final verdicts: confirmed-bug, likely-bug, false-positive, overstated, speculative,
wontfix, bad-anchor, appendix-noise, duplicate

Final buckets: fix, reporting, wontfix

Return ONLY JSON array:
{"findingId":"...","finalVerdict":"...","finalBucket":"...","evidence":"...","recommendedIssue":null}

Rules:
- ⊗ Return defer — pick the best available final disposition
- P1/P2 production needs code proof for confirmed-bug
- scripts/* CLI findings → often wontfix unless server-path bug
- Test appendix P3 → appendix-noise unless real test defect named
```

Write output to `<triage-dir>/defer-waves/result-wave-N.json`.

## Merge back

```text
python scripts/audit-triage-merge-defer-resolution.py --dir <triage-dir>
```

Updates `ledger.json` in place. Exits non-zero if any defer rows remain or wave results are incomplete.

Produces `<triage-dir>/defer-resolution-summary.json` with counts by final verdict/bucket.

## Issue model

Defer resolution is **internal plumbing**, not operator-facing. Do not open a separate "deferred findings" GitHub issue when the skill runs end-to-end.

Promoted fix-track rows land in export buckets 1–2; reporting in bucket 3; wontfix in 5. Bucket `6-defer` should be empty (or omitted) in the final export.
