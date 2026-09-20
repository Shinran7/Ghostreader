---
name: audit-triage
description: >-
  Triage long SLizard audit reports for Ghostreader with parallel verifier
  Mr. Meeseeks. Classifies findings into six buckets (confirmed fix, likely bug,
  reporting debt, appendix noise, wontfix, defer), ingests ghostreader-audit.new.md
  (markdown-first), and emits outcome.md plus per-bucket JSON. Use for "audit
  triage", "triage audit report", "review audit findings", "process audit", or
  "ghostreader audit review". Do NOT trigger on SLizard self-audit (use SLizard's
  own audit-triage skill), Autonomicon audits (use Autonomicon's copy), or
  Ghostwriter audits (use Ghostwriter's copy). Requires repo Ghostreader at
  C:\Users\shinr\Projects\Ghostreader.
---

# Audit Triage (Ghostreader)

Orchestrate verification of a SLizard **consumer** audit markdown report using
batched Mr. Meeseeks. Produce two operator-facing lists: **bugs to fix in
Ghostreader** and **reporting debt** (SLizard over-fire / noise), plus
wontfix/defer disposition batches.

**Port of:** Autonomicon `.grok/skills/audit-triage` (itself a consumer adaptation
of SLizard's skill) — same six-bucket flow; markdown ingest by default (no
`training/self-labels.json`); suppressions via `.slizard/suppressions.yml`;
pytest hygiene.

**References:** `references/verdict-taxonomy.md`, `references/orchestrator-protocol.md`,
`references/defer-resolution.md`, `references/suppression-levers.md`,
`references/implementation-hygiene.md`, `references/issue-graduation.md`,
`references/verifier-prompt.md`

## Audit report pair

SLizard `task audit` against this repo writes **two** markdown reports (often
kept next to the Projects root, not inside git):

| File | Scope |
|------|--------|
| `ghostreader-audit.md` | **Full** — repo-wide active findings; archival skim only |
| `ghostreader-audit.new.md` | **Diff / new** — findings on files changed since prior audit; **default triage ingest** |

Default paths on this machine:

- `C:\Users\shinr\Projects\ghostreader-audit.new.md` (**ingest this**)
- `C:\Users\shinr\Projects\ghostreader-audit.md` (full snapshot — do not ingest for triage)

Naming rule: insert `.new` before the final extension. On a no-op incremental
run the CLI may omit `.new.md`.

⊗ Ingest the full report for triage — large wontfix/appendix replay wastes tokens.

## Prerequisites

- Ghostreader repo at `C:\Users\shinr\Projects\Ghostreader`
- Diff report path (default above)
- Optional: `.slizard/audit-run-manifest.json` for commit hash when the report
  Summary omits `current audit commit`
- Scripts under `scripts/audit-triage-*.py`

⊗ Require SLizard `training/self-labels.json` — that is self-audit only. Ghostreader
defaults to **markdown findingIds** from ingest.

## Six output buckets

| Bucket | Verdict filter | Action |
|--------|----------------|--------|
| 1 confirmed-bugs-to-fix | `confirmed-bug` | Ship code fixes in Ghostreader |
| 2 likely-bugs | `likely-bug` | Fix or short verification pass |
| 3 reporting-debt | `false-positive`, `overstated`, `speculative`, `bad-anchor`, `duplicate` | Suppress or upstream SLizard feedback |
| 4 appendix-noise | `appendix-noise` | Bulk suppress / ignore test-quality noise |
| 5 wontfix | `wontfix` or bucket `wontfix` | Accepted risk → `.slizard/suppressions.yml` |
| 6 defer | `defer` | **Transient only** — Phase 2b must clear before export |

## Orchestrator workflow

| Phase | Command / action | Output |
|-------|------------------|--------|
| 0 Ingest | `python scripts/audit-triage-ingest.py --report <md> [--commit <prefix>]` | `.tmp/audit-triage/<id>/ledger.json`, `batches/batch-*.json` |
| 1 Rule pre-pass | (inside ingest) | appendix-noise, obvious wontfix auto-classified |
| 2 Verify | Dispatch Meeseeks per `references/verifier-prompt.md` (~20 findings/batch, parallel) | `results/result-batch-*.json` |
| 2b Defer resolve | Split defer → wave Meeseeks per `references/defer-resolution.md`; merge | `defer-waves/result-wave-*.json`, updated `ledger.json` |
| 3 Merge | `python scripts/audit-triage-merge.py --dir <triage-dir>` | `outcome.md`, updated `ledger.json` |
| 4 Export | `python scripts/audit-triage-export-buckets.py --dir <triage-dir> --id <id>` | `history/audit-triage/<id>/buckets/*.json` |
| 5 Apply | Operator approves suppressions for buckets 4–5 → `.slizard/suppressions.yml` | suppressions committed (carve-out from `.slizard/` ignore) |
| 6 Graduate | Operator says **open issues** / **per bucket** → `scripts/audit-triage-create-issues.py` | GitHub issues #N per non-empty bucket |

**Artifact root:** `.tmp/audit-triage/<YYYY-MM-DD>-ghostreader/` (scratch, gitignored).
Committed exports live under `history/audit-triage/<id>/` for issue linking.

**Default ingest:**

```powershell
python scripts/audit-triage-ingest.py
# or explicit:
python scripts/audit-triage-ingest.py --report C:\Users\shinr\Projects\ghostreader-audit.new.md --id 2026-09-19-ghostreader
```

## Iron laws

1. **Read source before verdict** — verifiers must read `filePath:line` ±30 lines.
2. **Markers are hints** — `gated-assumed`, `reanchored`, `systemic`, `corroborated` are not ground truth.
3. **CLI / scripts context → often wontfix** — `scripts/**` and one-off diagnostics are accepted risk unless proven exploitable on the product path (`ghostreader/**` package code, especially `cli.py`, `companion/`, `agents/`, `typesafe/`).
4. **Test appendix → appendix-noise** — `tests/**`, `test_*.py`; default unless message names a real test defect.
5. **No pending defer at export** — run Phase 2b before merge/export; ⊗ ship bucket 6 with rows still `defer`.
6. **Scratch only** — ⊗ `git add` under `.tmp/audit-triage/` except exported `history/audit-triage/` copies.
7. **Suppressions must land on git** — after Phase 5, commit `.slizard/suppressions.yml` (tracked carve-out). SLizard reads it from the default branch.
8. **Cluster systemic duplicates** — one issue / one suppress for a repeated pattern, not one ticket per file.

## Sub-agent dispatch

Read `references/orchestrator-protocol.md`. Summary:

- Priority queue: Security-Sensitive → production P1 → P2 → P3 → scripts → defer-heavy P3
- Group by file when batching
- Each Meeseeks returns JSON array: `{findingId, verdict, bucket, evidence}`
- Orchestrator writes `results/result-batch-NNN.json`; never patch ledger by hand without evidence
- Use `.grok/mr-meeseeks-dispatch.md` report-back opener when present

## Suppression levers (after triage)

Read `references/suppression-levers.md`:

- **Product bugs (1–2)** — fix in `ghostreader/` + pytest regression
- **Reporting debt (3)** — `.slizard/suppressions.yml` and/or upstream SLizard validator feedback (do not "fix" Ghostreader for pure FP)
- **Appendix / wontfix (4–5)** — bulk suppressions entries
- **Defer (6)** — must be empty after Phase 2b

## Skill conflicts

| User says | Use | Not |
|-----------|-----|-----|
| audit triage / process audit report (Ghostreader) | this skill | SLizard self-audit triage |
| Autonomicon audit triage | Autonomicon `.grok/skills/audit-triage` | this skill |
| Ghostwriter audit triage | Ghostwriter `.grok/skills/audit-triage` | this skill |
| SLizard **self**-audit triage | SLizard `.grok/skills/audit-triage` | this skill |
| diagnose PR / why did slizard miss | SLizard `slizard-dx` | this skill |
| mark wontfix on **SLizard self** finding | SLizard `wontfix` skill | this skill (consumer uses suppressions.yml) |

## Graduation to GitHub (Phase 6)

⊗ Auto-create issues at end of triage — requires explicit operator action verb
(`open issues`, `create tickets`, `per bucket`).

Read `references/issue-graduation.md`. Summary:

1. Commit (or stage) `history/audit-triage/<id>/` export first so issue links resolve.
2. Run `python scripts/audit-triage-create-issues.py --id <id> --commit <prefix>` — skips empty buckets.
3. Record issue numbers in `.tmp/issue-ids-<id>.json`.
4. Close buckets 1–2 with fix commits + tests; bucket 3 via suppressions/upstream; 4–5 via suppressions.

## Graduation to implementation

Confirmed bucket 1 items → normal fix commits or scoped vBRIEF. Link triage artifact:

`history/audit-triage/<id>/buckets/1-confirmed-bugs-to-fix.json`

**Before opening fix issues:** read `references/implementation-hygiene.md`.
Each implementation issue body must list acceptance criteria: code fix, **regression
test** (path-dependent), scoped pytest green.
