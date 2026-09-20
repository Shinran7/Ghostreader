# Verifier Mr. Meeseeks prompt template (Ghostreader)

Task `description`: `Mr. Meeseeks — audit verify <batch>`. See `.grok/mr-meeseeks-dispatch.md`.

Replace `<BATCH_PATH>` and `<REPO_ROOT>` (default `C:\Users\shinr\Projects\Ghostreader`).

```text
MR. MEESEEKS REPORT-BACK (mandatory):
You are Mr. Meeseeks. Your final message MUST begin with exactly:
I'm Mr. Meeseeks, look at me!
Then a blank line, then your JSON array.

Audit verifier for Ghostreader at <REPO_ROOT>.

Read batch file: <BATCH_PATH>

For EACH finding:
1. Read source at filePath:line (±30 lines)
2. Return verdict + bucket + one-line evidence citing what you saw

Verdicts: confirmed-bug, likely-bug, false-positive, overstated, speculative,
wontfix, bad-anchor, defer, appendix-noise, duplicate

Buckets: fix, reporting, wontfix, defer

Return ONLY JSON array:
{"findingId":"...","verdict":"...","bucket":"...","evidence":"..."}

Rules:
- P1/P2 production (`ghostreader/**`, user-facing `.ghostreader/** (local state; usually out of scope)`) needs code proof for confirmed-bug
- scripts/* CLI / diagnostic findings → often wontfix unless pipeline/server-path bug
- Marker coupling / maintainability nits → overstated unless broken today
- Test appendix / tests/** P3 → appendix-noise unless real test defect named
- Prompt/template / craft-style claims need concrete failure path, not taste alone
```

Write output to `results/result-batch-NNN.json` matching batch number (orchestrator may write from agent JSON).

## Defer resolver variant

When running Phase 2b, use the prompt in `defer-resolution.md` instead. Defer resolvers must never return `defer`.
