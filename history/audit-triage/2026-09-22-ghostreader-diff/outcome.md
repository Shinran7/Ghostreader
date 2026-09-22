# Ghostreader SLizard-Audit Triage Outcome

- Total findings: 7
- Verified bugs to fix: 1
- Reporting debt (SLizard noise / overstated): 6
- Wontfix candidates: 0
- Still pending: 0

## 1. BUGS WE NEED TO FIX

- **P1** `ghostreader/agents/consistency_checker.py:148` — ghostreader/agents/consistency_checker.py:148 — Silent parse skip. Who is hurt: callers expecting full dimension coverage. Failure: _parse_findings silently drops non-dict items, yielding a partial finding list and missing ratings for chapters emitting malformed items. (likely-bug: Re-read _parse_findings 143-160: non-dict items are continue-skipped then return out. Docstring promises fallback, but a non-empty all-non-dict array returns [] and never hits the unstructured fallback (162-169). Code-default typesafe_enabled=false uses this LLM/scene parse path, so malformed arrays can zero out consistency findings.)

## 2. REPORTING DEBT (SLizard false / overstated)

### false-positive (3)
- `ghostreader/typesafe/enrich.py:222` — Re-read consistency_tiebreak_batch 272-280: signal_kind is stored on findings only; ratings stay severity/note by schema. demote_tone_plot_holes reads finding.signal_kind and updates rating severity/note. prioritize_findings/report JSON keep signal_kind on findings — classification is not lost.
- `ghostreader/agents/prose_analyst.py:282` — Re-read apply_repetition_evidence_policy: _update_rating runs on enrich-success (334-342), detector fallback (357-361), and demote (373). prose_analyst 282-293 passes ratings and assigns ratings_out. Notes stay synced with rewritten summaries on the typesafe path.
- `ghostreader/agents/consistency_checker.py:392` — Re-read scene path 499-506: demote_* update finding severities without ratings=; AgentOutput has no ratings blob. Typesafe path 406-417 does pass ratings. Synthesis LLM path formats demoted findings; no stale rating severity left in product output.

### appendix-noise (1)
- `ghostreader/typesafe/grounding.py:97` — Re-read grounding.py:97 — state.get("scene_facts", []) is a normal safe default; truncated null-handling advisory with no failure path.

### bad-anchor (1)
- `ghostreader/agents/fact_extractor.py:187` — Re-read fact_extractor.py:170-191 — _is_empty_fact_payload has one docstring only; line 187 is _parse_fact_response's real docstring. No discarded bare triple-quoted expression exists at the cited site.

### overstated (1)
- `ghostreader/typesafe/grounding.py:428` — Re-read demote_tone_plot_holes 414-423: last write to ratings[PLOT_HOLES_DIM]['note'] is real, but ratings are one slot per dimension by contract and each finding keeps its own summary. Typesafe path normally emits one plot_holes finding, so production harm is negligible.


## 3. WONTFIX CANDIDATES
