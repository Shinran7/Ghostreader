# Ghostreader SLizard-Audit Triage Outcome

- Total findings: 7
- Verified bugs to fix: 0
- Reporting debt (SLizard noise / overstated): 5
- Wontfix candidates: 2
- Still pending: 0

## 1. BUGS WE NEED TO FIX


## 2. REPORTING DEBT (SLizard false / overstated)

### overstated (3)
- `ghostreader/embed.py:109` — Known OpenAI models use _OPENAI_DIMS with no probe (tested); unknown-model probe can raise on auth/network, which is intentional fail-closed for bad config, not a P1 safe-property crash.
- `ghostreader/analyzers/repetition_detector.py:215` — ValueError catch is the empty-vocabulary guard after strip/empty-doc checks; vectorizer params are hardcoded so non-vocab ValueErrors are not a shown failure path.
- `ghostreader/agents/synthesis.py:297` — Unconditional strengths/concerns recompute from findings is the intentional fix for setdefault+fallback zeros; casing drift is hypothetical against lowercase prompt/TypedDict values.

### duplicate (1)
- `ghostreader/embed.py:115` — Line 115 is def embed (already guards empty vectors); probe[0] IndexError is the same unknown-model path as 5e5755ca392fd020.

### false-positive (1)
- `ghostreader/agents/fact_extractor.py:148` — format_fact_sheets emits PARSE_FAILED: ... do not treat as contradiction-free for LLM consumers; parse_failed flag is set on the TypedDict for code paths.


## 3. WONTFIX CANDIDATES

- `ghostreader/ingestion/indexer.py:106` — has_table then drop/create is single-CLI overwrite; concurrent indexers on one LanceDB are outside Ghostreader product u
- `ghostreader/commands/compare.py:71` — CLI intentionally SystemExit(1) with a clear --no-cache message; tests/test_compare.py asserts that exit.