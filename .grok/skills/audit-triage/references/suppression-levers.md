# Suppression levers (Ghostreader consumer)

Pick the lever matching the bucket outcome.

## Bucket 1–2 (bugs)

Fix in `ghostreader/` (or real production `site/`). No suppression — ship code + tests.

**Hygiene:** read `implementation-hygiene.md`.

## Bucket 3 (reporting debt)

| Pattern | Lever |
|---------|-------|
| SLizard over-fires on style / heuristics | `.slizard/suppressions.yml` and/or note for upstream SLizard |
| Bad anchor / wrong line | reporting debt — do not change product code to appease anchor |
| Systemic duplicate cluster | One suppress or one clustered issue; not N copy-paste tickets |
| Severity inflation | Treat as overstated; suppress or demote in disposition notes |

## Bucket 4 (appendix noise)

Bulk suppress or ignore test-quality appendix rows. Prefer a single suppression
pattern for `tests/**` noise when re-audit thrash is high.

## Bucket 5 (wontfix)

Accepted risk. Record in `.slizard/suppressions.yml` when re-audit would re-emit
the same finding. Commit the file — `.slizard/suppressions.yml` is a tracked
carve-out; SLizard reads it from the default branch.

Example sketch (confirm schema against SLizard `docs/repo-suppressions.md`):

```yaml
# .slizard/suppressions.yml
schemaVersion: 1
suppressions:
  - findingId: "a1b2c3d4e5f60718"
    reason: "accepted residual risk — operator script only"
    addedBy: "audit-triage"
    addedAt: "2026-09-15"
```

## Bucket 6 (defer)

Must be empty after Phase 2b. Do not suppress defer rows — resolve them.

## Not available on consumer

- `training/self-labels.json` / `markWontFix` — SLizard **self-audit** only
- SLizard `src/analysis/validators/*` knobs — fix upstream in SLizard if validator is wrong
