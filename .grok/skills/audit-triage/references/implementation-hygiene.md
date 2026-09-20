# Implementation hygiene (Ghostreader)

When triage exports bucket **1** (confirmed bugs) or **2** (likely bugs) into
GitHub issues, each fix commit must ship **code + tests** where the path is
product code. ⊗ Land "fixes" that only silence SLizard without changing behavior
when the claim was true.

## Classify the touched path first

| Path pattern | What it is | Unit tests | Notes |
|--------------|------------|------------|-------|
| `ghostreader/agents/**` | Analysis agents (prose/narrative/consistency/…) | `tests/test_agents.py`, nearest tests | Prefer focused unit tests |
| `ghostreader/companion/**` | Progressive companion pipeline | `tests/test_companion_*.py` | Continuity-first surface |
| `ghostreader/typesafe/**` | TypeSafe judgment helpers | `tests/test_typesafe.py` | |
| `ghostreader/graph/**` | LangGraph workflow / state | `tests/test_graph.py` | |
| `ghostreader/cli.py`, `commands/**` | CLI surface | `tests/test_cli.py`, companion CLI tests | |
| `ghostreader/ingestion/**`, `analyzers/**`, `report/**` | Ingest / detect / report | matching `tests/test_*.py` | |
| `.ghostreader/**` | Local per-story state | n/a | Out of product-fix scope |
| `scripts/**` | Operator CLI / diagnostics | optional | Often wontfix rather than fix |
| `tests/**` | Test tree | n/a | Usually appendix-noise, not product fix |

## Issue / ticket acceptance criteria

### Bucket 1 (confirmed bug)

1. **Code fix** with findingId or `file:line` in commit message.
2. **Test** — new or extended case that would fail on pre-fix code (when path is product).
3. Scoped `pytest` green on touched tests.

### Bucket 2 (likely bug)

Same as bucket 1 when promoting to fix; otherwise a short verification note in
the issue that closes the row as overstated/wontfix with evidence.

### Bucket 3 (reporting debt)

- Prefer suppressions / upstream SLizard — not product "fixes" for pure FP.
- If a Ghostreader pattern change is intentional, treat as a real refactor with tests.

### Bucket 4–6

No product tests — suppress / defer workflows only (6 must be empty at export).

## Pre-close verification

```text
pytest <touched-test-files> -q --tb=short
```

⊗ Close implementation issues without linked commits that include tests when the
path requires them.
