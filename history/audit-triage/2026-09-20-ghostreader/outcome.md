# Ghostreader SLizard-Audit Triage Outcome

- Total findings: 109
- Verified bugs to fix: 12
- Reporting debt (SLizard noise / overstated): 69
- Wontfix candidates: 28
- Still pending: 0

## 1. BUGS WE NEED TO FIX

- **P1** `ghostreader/ingestion/epub_loader.py:36` — ghostreader/ingestion/epub_loader.py:36 — Document iteration order defect. Who is hurt: readers/analysts. Failure: book.get_items_of_type(ITEM_DOCUMENT) reads manifest items rather than spine order, causing chapters to load out of order and corrupting continuity analysis. (confirmed-bug: Line 35 uses get_items_of_type (manifest self.items), not spine; repro with spine 1→2→3 but add-order 3,1,2 loaded chapter-3 text as Chapter 1.)
- **P1** `ghostreader/agents/fact_extractor.py:140` — ghostreader/agents/fact_extractor.py:140 — Empty fact sheet fallback masking errors. Who is hurt: Consistency checker and manuscript author. Failure: _parse_fact_response returns empty ChapterFact on parse error, causing consistency checker to report false negative 'no contradictions'. (likely-bug: Cited line 140 is format_fact_sheets; _parse_fact_response:83-91 returns an empty ChapterFact on JSON failure, so consistency can report no contradictions after a parse miss.)
- **P2** `ghostreader/typesafe/client.py:29` — ghostreader/typesafe/client.py:29 — Hardcoded user environment path. Who is hurt: Non-author users encountering missing typesafe_sdk. Failure: Error message prints a broken pip install command pointing to a non-existent author-specific local directory. (confirmed-bug: ensure_typesafe_sdk ImportError text hardcodes C:\Users\shinr\Projects\Ghostreader at L29-30)
- **P2** `ghostreader/ingestion/markdown_loader.py:81` — ghostreader/ingestion/markdown_loader.py:81 — Chapter number collision in directory loading. Who is hurt: callers loading mixed markdown directories. Failure: falling back to len(chapters) + 1 causes collisions or non-monotonic chapter numbers when named and unnamed files coexist. (likely-bug: Unmatched *.md files use len(chapters)+1; a name sorting before chapter-01.md (e.g. appendix.md) can both become chapter_number 1.)
- **P2** `ghostreader/analyzers/repetition_detector.py:214` — ghostreader/analyzers/repetition_detector.py:214 — Empty vocabulary handling. Who is hurt: downstream consumers of repetition metrics. Failure: when all words match stop words or chapters are empty, empty frequency lists are returned without notification or default metrics. (confirmed-bug: analyze_word_frequency L205-211: TfidfVectorizer.fit_transform raises ValueError on stopword-only docs; no guard.)
- **P2** `ghostreader/ingestion/indexer.py:133` — ghostreader/ingestion/indexer.py:133 — LanceDB table existence check incompatibility. Who is hurt: operators indexing manuscripts. Failure: querying db.list_tables() directly with 'in' fails or raises errors on differing LanceDB versions. (confirmed-bug: On lancedb 0.30.2, list_tables() returns ListTablesResponse; chunks in db.list_tables() is False even when tables=[chunks], so drop is skipped and recreate raises ValueError.)
- **P2** `ghostreader/commands/compare.py:72` — ghostreader/commands/compare.py:72 — Ignored cache flag. Who is hurt: Users passing --no-cache to compare. Failure: Comparison always loads cached analysis reports from disk, ignoring the --no-cache parameter. (confirmed-bug: run_compare accepts no_cache (L65) but always _load_report from cache.json; flag never consulted.)
- **P2** `ghostreader/agents/synthesis.py:232` — ghostreader/agents/synthesis.py:232 — Inconsistent finding count calculation. Who is hurt: End users reading JSON report outputs in standard LLM mode. Failure: Final report can report zero or inaccurate strengths_count and concerns_count despite existing findings. (confirmed-bug: LLM path: _parse_report fallback sets counts to 0 (L105-110); setdefault at L295-302 will not recompute from findings.)
- **P2** `scripts/audit-triage-split-defer-waves.py:18` — scripts/audit-triage-split-defer-waves.py:18 — Priority logic omission. Who is hurt: Reviewers triaging critical vulnerabilities. Failure: P0 findings bypass Wave 1 priority and fall into lower priority waves 2 or 4. (confirmed-bug: wave_for Wave 1 only checks sev in (P1, P2) at L18; P0 falls through to waves 2-4)
- **P2** `ghostreader/embed.py:78` — ghostreader/embed.py:78 — Hardcoded embedding dimension. Who is hurt: Users using OpenAIEmbedder with 3072-dimension models like text-embedding-3-large. Failure: embedder.dimension reports 1536, causing LanceDB vector table insertion or query crashes. (confirmed-bug: OpenAIEmbedder hardcodes self._dimension = 1536 for every model_name; text-embedding-3-large vectors are 3072 so schema/list size mismatches.)
- **P3** `ghostreader/commands/chat.py:69` — ghostreader/commands/chat.py:69 — Incompatible table listing API. Who is hurt: Interactive chat users. Failure: In newer LanceDB releases, db.list_tables() may return a collection object or namespaced table names, breaking string membership checks for the chunks table. (confirmed-bug: LanceDB 0.30.2 list_tables() returns ListTablesResponse; 'chunks' in response is False even when response.tables contains chunks, so chat always thinks the table is missing.)
- **P3** `ghostreader/commands/companion.py:89` — ghostreader/commands/companion.py:89 — Uncaught exceptions during report export. Who is hurt: CLI operators. Failure: errors raised during write_brief_files or export_brief_json escape the command handler with a traceback instead of exiting cleanly with status code 1. (likely-bug: try/except covers only run_companion_pipeline (89-131); write_brief_files/export_brief_json at 134-139 sit outside and can raise an uncaught traceback.)

## 2. REPORTING DEBT (SLizard false / overstated)

### overstated (24)
- `ghostreader/cache.py:228` — Line 228 is load_checkpoint; save keeps prior started_at (or now). Empty started_at only if old/corrupt file lacked it — metadata niggle, not a security failure.
- `ghostreader/agents/synthesis.py:188` — Line 188 is parse_ratings_from_raw; the 2000-char trim is only in _parse_report's JSON-failure fallback (line 106), not silent success-path truncation.
- `ghostreader/agents/prose_analyst.py:105` — Line 105 is a default dimension on successful parse; the prose.general synthetic finding at 117-126 is an intentional unstructured fallback, not a hidden crash.
- `ghostreader/report/markdown_writer.py:51` — Line 51 is a docstring; _slugify leaves ?*, but manuscript_name comes from Path stems already OS-safe on Windows, so the OSError path is not realistic here.
- `ghostreader/ingestion/summarizer.py:64` — Cited line 64 is ActSummary wiring; chapter.content[:12_000] at 83 is an intentional token-limit cap, not a pipeline-breaking defect.
- `ghostreader/companion/continuity.py:40` — involves_N at 40; cited_chapters uses bare digits only on chapter_ref, and Ch/Chapter prefixes on evidence/counter_evidence — years in prose do not become chapter ids.
- `scripts/audit-triage-merge.py:66` — else appends defer into reporting (L83-84), but Phase 2b must clear defer before merge so path is protocol-gated
- `ghostreader/agents/consistency_checker.py:55` — Grounding rule is LLM prompt (L35-38); L146-154 fallback only on parse failure, not a quote-path contradiction.
- `scripts/audit-triage-ingest.py:171` — join_rows omits auditCommit (L166-180) but export still reads summary.json auditCommit before unknown
- `ghostreader/companion/typesafe_consistency.py:105` — by_dim last-wins is real, but consistency_from_nouls emits one finding per dimension before that loop; mid-band findings append afterward.
- `ghostreader/seed.py:58` — load_seed_meta catches YAMLError/OSError at L46-47 and returns {} by docstring design; L58 is _KNOWN_FIELDS not the handler
- `scripts/audit-triage-merge.py:62` — fix-before-wontfix at L77 is documented exclusive membership (L68); inconsistent verifier pair is the root
- `ghostreader/ingestion/indexer.py:99` — Drop-then-create is non-atomic, but manuscript source remains; today drop often never runs because list_tables membership is broken.
- `scripts/audit-triage-export-buckets.py:32` — bucket_map six verdict buckets vs outcome.md four sections are intentional different aggregations, not a broken classifier
- `ghostreader/ingestion/__init__.py:92` — _MIN_SCENE_CHARS=200 intentionally drops frontmatter-sized blocks; whole-chapter scenes still form when content is long enough without ---.
- `ghostreader/agents/consistency_checker.py:131` — AgentFinding omits _certainty by design; adapters set it with type:ignore and prioritize_findings strips it intentionally.
- `ghostreader/companion/continuity.py:92` — partition_findings only routes concern gate-dims; weak grounding goes to ungrounded (L96-101).
- `ghostreader/cache.py:246` — Line 246 only loads CheckpointData; get_resume_point can ignore checkpoint results without a cache hash, but save_checkpoint/get_resume_point are unused by the analyze CLI.
- `ghostreader/companion/brief.py:92` — Line 92 is generated_at serialization; exact severity=='concern' lives in compute_verdict (59-62) with no case-fold, but no concrete malformed-severity failure path is shown.
- `ghostreader/companion/pipeline.py:234` — assert typesafe_client is at line 301 inside typesafe_enabled; companion CLI only enables TypeSafe inside AsyncTypeSafeClient, so AssertionError is an internal misuse path, and line 234 is unrelated.
- `ghostreader/companion/pipeline.py:480` — ensure_facts has no degraded fallback, but commands/companion.py catches Exception and returns 1; abort-without-partial-facts is accepted fail-closed behavior, not a silent break.
- `ghostreader/ingestion/chunking.py:65` — _split_long_paragraph applies character overlap within oversized paragraphs (100-111); after that path, overlap is not seeded into the next paragraph buffer — niche quality limit, not a crash.
- `ghostreader/report/rewrites.py:55` — Empty LLM alternatives are skipped (91-92) without backfilling beyond the pre-sliced eligible[:max_rewrites] set — fewer suggestions, not incorrect ones.
- `ghostreader/typesafe/routing.py:29` — needs_choice_enrich only special-cases concern (routing.py:32-34); other severities correctly use confidence_floor.

### false-positive (23)
- `ghostreader/typesafe/questions.py:102` — Line 102 is instruction prose; consistency_questions() correctly returns {dim: Noul(...)} matching the TypeSafe SDK question shape.
- `scripts/audit-triage-merge.py:104` — outcome.md explicitly lists 'Still pending: {len(pending)}' (lines 96-97); incomplete work is disclosed, not presented as final.
- `ghostreader/agents/synthesis.py:310` — Line 310 is synthesis_node's signature; TypeSafe path setdefaults missing consistency dims (210-214), and total_findings 0 is correct when agents returned no findings.
- `ghostreader/ingestion/epub_loader.py:48` — Line 48 constructs Chapter; _local_tag strips {ns} prefixes and _extract_xhtml_title returns titles from xmlns XHTML.
- `ghostreader/companion/typesafe_consistency.py:58` — AnalysisState nests AnalysisConfig under config; pipeline builds config with typesafe_noul_positive_threshold before run_companion_consistency.
- `scripts/audit-triage-ingest.py:240` — verdict None on build is expected; rule_classify then batch_entries keeps only verdict is None (L516-524)
- `scripts/audit-triage-ingest.py:530` — category substring miss still takes candidates[0] (L161-162); hasMarkdown False only when no key candidates
- `scripts/audit-triage-ingest.py:380` — _is_security_priority returns None on purpose so P0/P1 security stay pending for Meeseeks (L361-362)
- `ghostreader/companion/pipeline.py:283` — L283 is prose_state; rate at L341-345 uses concern-only partition totals, so neutrals never enter the denominator.
- `scripts/audit-triage-merge-defer-resolution.py:116` — return 1 if remaining defer (L124) correctly fails when resolution left verdict=defer; protocol requires zero defer
- `ghostreader/analyzers/repetition_detector.py:240` — total_word_count uses .split() at L179; hyphenated words and contractions stay one token, not inflated as claimed.
- `ghostreader/companion/typesafe_consistency.py:48` — Prefix mutates ts_state from build_consistency_state (new dict/strings), not AnalysisState scene_facts or chapters.
- `ghostreader/graph/__init__.py:55` — AnalysisState is total=False; synthesis uses state.get and _format_agent_findings(None) -> No output available without KeyError.
- `ghostreader/graph/workflow.py:105` — Line 105 returns synthesis; quick mode intentionally skips narrative/consistency and synthesis already tolerates missing outputs.
- `scripts/audit-triage-export-buckets.py:73` — commit resolves --commit then summary.json auditCommit then ledger[0]; unknown only if all missing (L76-87)
- `scripts/audit-triage-ingest.py:198` — infer_section returns Findings with or without docker-compose.yml; rule uses docker-compose substring so .yaml matches
- `ghostreader/report/rewrites.py:62` — generate_rewrites keeps input order after evidence filter then slices (66-67); CLI passes report.prioritized_findings already ranked.
- `ghostreader/report/rewrites.py:68` — Line 68 is eligible[:max_rewrites]; rationale uses PrioritizedFinding str fields (severity/dimension/summary), so literal None formatting is not reachable on the typed path.
- `ghostreader/typesafe/enrich.py:140` — consistency_tiebreak_batch increments failures for each missing dim (enrich.py:164-166); partial maps are counted.
- `ghostreader/typesafe/enrich.py:177` — if not parsed (enrich.py:192) only runs on empty map; partial successes are not wiped. Line 177 is finding evidence, not override.
- `ghostreader/typesafe/state_builders.py:54` — Early fact_sheets return is intentional; consumers use in/get checks (consistency_checker.py:276-281) — no KeyError path.
- `ghostreader/agents/consistency_checker.py:196` — Line 196 is _parse_findings in the unstructured path; scene_facts fallback at 354-355 is documented intentional design, and cli.py sets initial_state['scene_facts'] correctly.
- `ghostreader/paths.py:112` — Line 112 is chapter slug nesting; _resolve_project_root intentionally walks manuscript/CWD then package_project_root for Autonomicon foreign-CWD hooks.

### bad-anchor (16)
- `ghostreader/agents/consistency_checker.py:220` — Line 220 is grounding text inside _SCENE_CONSISTENCY_PROMPT; ask() runs later at 268 after build_consistency_state().
- `ghostreader/agents/consistency_checker.py:280` — Line 280 builds the summary/manuscript context string; no AssertionError or TypesafeConfigError there (assert is at 349).
- `ghostreader/agents/consistency_checker.py:312` — Line 312 assigns noul_tie_breaks; the typesafe_client assert lives at scene_consistency_checker_node:349, and CLI injects the client when typesafe_enabled.
- `ghostreader/analyzers/repetition_detector.py:480` — L480 is _locate_term loop; one optional adverb is _DIALOGUE_TAG_RE at L135 (heuristic limit).
- `ghostreader/analyzers/repetition_detector.py:312` — L312 ends analyze_sentence_patterns; dialogue verbs/regex live at L61-136 and analyze_dialogue_tags L422+.
- `ghostreader/graph/workflow.py:92` — workflow.py:92 is depth routing, not client plumbing; assert typesafe_client is intentional when typesafe_enabled.
- `ghostreader/cli.py:434` — L434 is chat docstring; config_set L532 maps false via membership check to False correctly.
- `ghostreader/companion/pipeline.py:316` — Line 316 extracts continuity findings; progress persists only at update_progress_after_run (~384) after a successful brief.
- `ghostreader/embed.py:62` — Line 62 is SentenceTransformer construction; stub fallback lives in _make_st_embedder and logs a warning (default MiniLM and stub both 384-dim).
- `ghostreader/agents/consistency_checker.py:178` — L178 is hierarchy_block; jev-latest is ask() default in typesafe/client.py:56, separate from chat config.model.
- `ghostreader/agents/synthesis.py:370` — synthesis.py ends at L324; _merge_typesafe_stats at L131 defaults zeros when raw stats missing.
- `ghostreader/ingestion/epub_loader.py:74` — Line 74 is _element_text recursion on parsed XML; crude regex strip is only the ParseError fallback at _crude_strip.
- `ghostreader/graph/workflow.py:148` — workflow.py:148 wires conditional edges; ask() is in typesafe/client.py and only prechecks SDK/API key via TypesafeConfigError.
- `ghostreader/cli.py:312` — Anchors 215/312 are seed/rewrite code; chapter_facts are produced by extract_all_facts and optionally stored as scene_facts at 287-288 with no shown KeyError path.
- `ghostreader/graph/__init__.py:111` — Line 111 is hierarchy act_summaries serialization; repetition_report_to_dicts (122+) reads typed RepetitionReport attributes from the analyze path.
- `ghostreader/typesafe/adapters.py:162` — Line 162 is ratings_from_findings; noul bands are handled exhaustively at adapters.py:124-149 via noul_band().

### speculative (5)
- `ghostreader/companion/typesafe_consistency.py:70` — Lines 68-73 prepend bias; build_consistency_state always sets fact_sheets or manuscript, so the else branch that sets fact_sheets=prefix alone is a defensive dead path.
- `ghostreader/report/__init__.py:77` — f.get(rank, i+1) can yield None if rank is null, but dataclass accepts it and renderers print #None rather than crash; no producer emits null rank.
- `scripts/audit-triage-merge-defer-resolution.py:97` — deferRemaining recounts ledger verdict==defer after writes (L103-107); inaccurate counts need an unshown inconsistent mutate path
- `ghostreader/commands/chat.py:192` — Embed call is at line 182 (_embedder.embed([query])[0]); current Embedder implementations return one vector per input, and line 192 is only text append.
- `ghostreader/typesafe/enrich.py:160` — Prompt requires JSON bool; check at enrich.py:171 accepts True/true/True/1 — non-contract strings are hypothetical.

### duplicate (1)
- `ghostreader/ingestion/indexer.py:84` — Schema already uses embedder.dimension at create_table; real dim lie is the OpenAIEmbedder 1536 hardcode sibling finding.


## 3. WONTFIX CANDIDATES

- `scripts/audit-triage-merge.py:17` — scripts/audit-triage-merge.py:17 json.loads can raise; operator triage script, accepted fail-loud risk.
- `scripts/audit-triage-merge-defer-resolution.py:106` — --export-history intentionally writes only 6-defer-resolved.json for the defer-resolution step, not a full bucket export
- `scripts/audit-triage-merge.py:41` — scripts/audit-triage-merge.py:44-45 read ledger/results without exists check; diagnostic script, not product path.
- `scripts/audit-triage-create-issues.py:145` — scripts/audit-triage-create-issues.py:174-175 takes the URL tail without isdigit(); operator triage helper, not product 
- `scripts/audit-triage-ingest.py:52` — Markdown finding_id() hashes path/line/message; self-labels keep lab IDs by design. Ghostreader ingest defaults to markd
- `scripts/audit-triage-ingest.py:20` — FINDING_RE at line 23 (cite ~20) skips non-matching lines; accepted ingest contract for known audit markdown shape.
- `ghostreader/agents/synthesis.py:85` — L85 formats findings; _collect_all_findings aggregates agents without dedup by design.
- `scripts/audit-triage-ingest.py:345` — CLI report clock / generatedAt — accepted operational non-determinism
- `ghostreader/ingestion/epub_loader.py:102` — _extract_xhtml_title prefers first title then h1/h2; heuristic nav misfires are accepted EPUB risk, not a clear defect.
- `scripts/audit-triage-export-buckets.py:70` — default export_id is YYYY-MM-DD-ghostreader at L68; --id override exists; same-id overwrite is accepted CLI default
- `ghostreader/companion/brief.py:46` — compute_verdict L55-63 returns ship when no concern severities; empty lists mean clean, not unanalyzed.
- `ghostreader/companion/fact_memory.py:186` — ensure_facts L180 gather fails fast on LLM error; no partial overwrite/KeyError path without return_exceptions.
- `ghostreader/companion/progress.py:132` — progress.py:130-137 intentionally uses max so rewrites do not lower last_chapter_companioned; docstring states that cont
- `ghostreader/ingestion/markdown_loader.py:70` — Filename chapter-NNN numbering is intentional for companion/analyze paths; loader never reads chapter numbers from headi
- `scripts/audit-triage-create-issues.py:74` — note_file read_text(utf-8) at L94 fail-loud on bad encoding; operator script, L74 is argparse not the read
- `scripts/audit-triage-merge-defer-resolution.py:55` — exit 1 on unresolved defer (L74-78) is required fail-closed Phase 2b gate, not missing transactionality
- `scripts/audit-triage-merge-defer-resolution.py:48` — no result-wave-*.json returns 1 at L62-64; correct fail-closed when merge inputs are absent
- `ghostreader/companion/fact_memory.py:173` — _save_manifest L97-104 is non-atomic local state; single-operator companion, accepted race risk.
- `scripts/audit-triage-merge.py:23` — normalize_bucket maps infra/maintainability to reporting (L21-26); defensive coerce of unknown labels
- `ghostreader/agents/fact_extractor.py:93` — fact_extractor.py:130 gather fails fast on task error; does not silently drop facts.
- `scripts/audit-triage-merge.py:130` — CLI report clock / generatedAt — accepted operational non-determinism
- `scripts/audit-triage-split-defer-waves.py:39` — return 2 at L46 is intentional catch-all default wave for leftovers after P1/P2/scripts/heuristic rules
- `ghostreader/companion/brief.py:188` — Markdown writer always appends the Ship checklist (212-218) after verdict text; checklist wording covers address-or-acce
- `ghostreader/companion/discovery.py:120` — Sweep focus defaults to max(files) with gap warnings (127-137); chapter_override can retarget — intentional latest-chapt
- `ghostreader/companion/pipeline.py:428` — _run_llm_consistency builds ratings only for COMPANION_GATE_DIMS (153-161) while returning full findings; non-gate dims 
- `ghostreader/llm.py:215` — get_llm prints a yellow warning then returns _stub_chat_model() (265-271); TypeSafe analyze/companion CLI paths reject s
- `ghostreader/report/rewrites.py:84` — rewrites.py:87-89 intentionally continues on LLM Exception; tests/test_rewrites.py asserts [] on broken LLM.
- `ghostreader/report/markdown_writer.py:92` — group_findings_by_dimension splits on first dot by design so consistency.* maps to the Consistency label; markdown_write