# Verdict taxonomy

Every finding gets exactly one verdict and one bucket.

## Verdicts

| Verdict | Bucket | Meaning |
|---------|--------|---------|
| confirmed-bug | fix | Code read proves defect; ship fix in Ghostreader |
| likely-bug | fix / defer | Plausible; fix or short follow-up |
| false-positive | reporting | Claim does not hold on inspection |
| overstated | reporting | Real niggle, wrong severity or framing, **and** production harm is negligible. Intentional fail-soft / gates that can still hurt users on the default product path → `likely-bug`, not overstated |
| speculative | reporting | Hypothetical; no concrete failure path |
| bad-anchor | reporting | Wrong line/symbol; undermines trust |
| duplicate | reporting | Systemic cluster / also-at sibling |
| appendix-noise | reporting | Test-quality appendix hygiene |
| wontfix | wontfix | Valid observation; accepted risk |
| defer | defer | Needs runtime / external verification |

## Six export buckets

1. `1-confirmed-bugs-to-fix` — verdict `confirmed-bug`
2. `2-likely-bugs` — verdict `likely-bug`
3. `3-reporting-debt` — false-positive, overstated, speculative, bad-anchor, duplicate
4. `4-appendix-noise` — verdict `appendix-noise`
5. `5-wontfix` — verdict `wontfix` OR bucket `wontfix` (includes ruled pre-pass)
6. `6-defer` — verdict `defer` (must be empty after Phase 2b)
