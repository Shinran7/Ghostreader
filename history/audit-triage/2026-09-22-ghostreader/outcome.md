# Ghostreader SLizard-Audit Triage Outcome

- Total findings: 14
- Verified bugs to fix: 2
- Reporting debt (SLizard noise / overstated): 12
- Wontfix candidates: 0
- Still pending: 0

## 1. BUGS WE NEED TO FIX

- **P1** `ghostreader/llm.py:94` — ghostreader/llm.py:88 — `extract_json_array` extracts nested array instead of root construct. Who is hurt: Pipeline components expecting root-level JSON. Failure: Slicing across brackets grabs an inner array from a top-level object, bypassing outermost structure validation. (confirmed-bug: extract_json_array first-[/last-] on prose-wrapped object returns nested list (e.g. items [1,2,3]); prose/consistency/narrative parsers consume that and can yield empty findings when items are non-dicts.)
- **P3** `ghostreader/agents/fact_extractor.py:55` — ghostreader/agents/fact_extractor.py:55 — Empty or minimal repair responses pass as successful fact sheets. Who is hurt: Continuity checkers and fact sheet consumers. Failure: Repaired JSON returning an empty object or minimal `{}` passes validation without `parse_failed`, populating empty lists and poisoning continuity checks. (confirmed-bug: _parse_fact_response('{}') builds empty ChapterFact with no parse_failed; count_parse_failed/abort_on_fact_parse_failure only key off that flag, so silent empty sheets can look clean.)

## 2. REPORTING DEBT (SLizard false / overstated)

### false-positive (6)
- `ghostreader/companion/continuity.py:76` — collect_info_findings/cited_chapters use .get() plus str(...) defaults; malformed chapter/evidence fields do not raise TypeError/AttributeError.
- `ghostreader/companion/brief.py:336` — info_continuity_findings are PrioritizedFinding via _rank_findings; _print_findings already renders brief.info_continuity_findings at line 339.
- `ghostreader/companion/continuity.py:112` — ensure_info_ratings returns dict maps; pipeline converts with _ratings_from_map before CompanionBrief, so brief_to_payload asdict sees DimensionRating instances.
- `ghostreader/companion/continuity.py:95` — Line 95 is severity != concern filter; no recursion and chapter citation parsing is finite regex findall/finditer.
- `ghostreader/companion/fact_memory.py:131` — FactRecord.fact is always a ChapterFact dict from from_dict; record.fact.get('parse_failed') cannot AttributeError on records returned by get().
- `ghostreader/companion/pipeline.py:501` — compute_verdict already accepts narrative_findings: list[PrioritizedFinding] | None = None; pipeline call at line 507 matches.

### overstated (3)
- `ghostreader/agents/fact_extractor.py:140` — extract_chapter_facts does exactly one repair ainvoke; extract_all_facts bounds concurrency with Semaphore(max_concurrent=10), not unbounded retries.
- `ghostreader/companion/craft.py:183` — assert typesafe_client is not None only when config typesafe_enabled; companion CLI pairs enabled=True with AsyncTypeSafeClient context, so default path does not trip it.
- `ghostreader/report/markdown_writer.py:118` — Warnings are rendered under Overview ### Pipeline warnings; executive_summary is separate LLM prose and is not a status bit that claims clean when warnings exist.

### appendix-noise (1)
- `ghostreader/companion/craft.py:33` — Truncated null-handling note on state.get('chapters', []); run_companion_craft always supplies chapters_to_dicts(focus_chapters).

### duplicate (1)
- `ghostreader/companion/continuity.py:80` — Same continuity soft-grounding helpers as 739a85b0e6a663e2; line 80 is the collect_info_findings signature, still defensive .get access.

### bad-anchor (1)
- `ghostreader/companion/pipeline.py:407` — Line 407 is include_info_dims=companion_info_dims; continuity findings are dict TypedDicts and partition_findings already uses .get.


## 3. WONTFIX CANDIDATES
