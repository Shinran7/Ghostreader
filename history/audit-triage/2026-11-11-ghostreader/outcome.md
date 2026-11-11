# SLizard Self-Audit Triage Outcome

- Total findings: 22
- Verified bugs to fix: 3
- Reporting debt: 17
- Wontfix candidates: 19
- Still pending: 0

## 1. BUGS WE NEED TO FIX

- **P2** `ghostreader/cache.py:49` — ghostreader/cache.py:49–55 — Wrong report loaded. Users comparing manuscripts are hurt: a legacy cache can supply a per-chapter result as the full report, leaving scorecard data missing or invalid. (likely-bug: cache.py:48-53 returns results[-1] from the legacy per-chapter entries layout. Commit b2de792 shows those entries held one chapter's agent result, not a synthesis report, so compare._extract_ratings (compare.py:116-130) finds no dimension_ratings and prints all '-' instead of saying there is no report. This happens only for state dirs left by older versions.)
- **P3** `ghostreader/canon.py:237` — ghostreader/canon.py:237-255 — Time-inaccurate secret state. Authors may receive false continuity findings or miss real secret-knowledge contradictions when an earlier chapter is checked against a later reveal state. (likely-bug: canon.py:237-255 _plot filters secrets only by planted_chapter < N, then prints the current state and knowers. With live Canon (no checkpoint, canon.py:94-98), a reveal recorded after chapter N leaks into the state for chapter N. Unlike cast deaths (canon.py:162-164), it does not check state_since_chapter >= N.)
- **P3** `ghostreader/cli.py:405` — ghostreader/cli.py:727–744 — Invalid numeric config input crashes the CLI. Users setting per-job temperature or max_tokens to an invalid number receive an unhandled ValueError instead of a reported configuration error. (confirmed-bug: cli.py:738-741 runs float(value)/int(value) on per-job temperature/max_tokens with no try/except, and cli.py:756-759 does the same for top-level keys. 'ghostreader config set craft.temperature abc' raises an uncaught ValueError traceback instead of a clean error. Config is not written.)

## 2. POOR REPORTING IN SLIZARD

### false-positive (10)
- `ghostreader/ingestion/summarizer.py:106` — summarizer.py:102-104: '... if act_ranges else []' sends an empty act_ranges to _group_into_acts. _group_by_ranges also drops empty groups (summarizer.py:266), so act_chapters[0] at line ~118 always has an element.
- `ghostreader/canon_audit.py:333` — _drift_match (canon_audit.py:294-303) is only called with names from names_in, which yields names of 2 or more capitalized words (canon_audit.py:111-130), so a[0] and b[0] always exist. The cast loop at canon_audit.py:338-346 guards with 'if tokens'. _anchor is unused, and audit_canon also catches errors per part (canon_audit.py:382-385).
- `ghostreader/canon_audit.py:267` — _timeline returns early when len(stamps) < 3 (canon_audit.py:260-261), so len(values) >= 3 at the division on canon_audit.py:267. Empty timestamps count as blank, not as zero length.
- `ghostreader/excerpts.py:284` — excerpts.py:284-294: the loop keeps adding windows while the merged length fits alloc_c. It breaks only when chosen already fills alloc_c, or after truncating to exactly alloc_c, so no budget is left over.
- `ghostreader/report/check_homes.py:56` — check_homes.py:55-61 clamps every count with max(0, ...), so counts cannot go negative. The only caller, drop_report_dimensions (check_homes.py:69), builds gone as a unique subset of prioritized_findings, so the counts are not undercounted either.
- `ghostreader/companion/pipeline.py:219` — pipeline.py:244 passes through=N-1; for N=1, through=0 makes _coverage range(1,1) empty and _timeline/_names_vs_prose filter to nothing (canon_audit.py:152-180,254-260,338). load_canon_state(canon,1) correctly has no entries before ch1, and pipeline.py:264-268 falls back to fact sheets with a warning, which is the intended behavior.
- `ghostreader/agents/canon_consistency.py:68` — canon_consistency.py:101-107: refs are built from the same extract_json_array output with the same isinstance(d, dict) filter that consistency_checker._parse_findings uses (consistency_checker.py:166-168), so findings and refs stay one-to-one. Invalid non-dict entries are skipped on both sides.
- `ghostreader/agents/consistency_checker.py:563` — demote_ungrounded_concerns only checks the manuscript evidence field (grounding.py:39-40,454), never counter_evidence. quotes.py:343 skips the lookup when canon_counter() is true (quotes.py:318-322, counter_source='canon' set at canon_consistency.py:91), so Canon counter-evidence is never treated as a manuscript quote.
- `ghostreader/companion/pipeline.py:14` — run_companion_pipeline (pipeline.py:306+) puts genre and the others after a bare '*', where keyword-only args without defaults are legal. ast.parse of the file succeeds.
- `ghostreader/usage.py:84` — usage.py:66-93: a child task inherits a copy of the context, so it keeps the tracker of the run that spawned it. Its usage is credited to that earlier run, which is the correct attribution. start_usage in a later run only rebinds that run's own context.

### speculative (7)
- `ghostreader/quotes.py:348` — The real anchor is ingestion/indexer.py:226-248, not quotes.py:348. The stamp lives inside db_path and is written only after index_manuscript completes (indexer.py:245-247), so deleting the db also deletes the stamp. A stale match needs a crashed rebuild followed by reverting to exactly the old content, or hand-deleting tables while keeping the stamp.
- `ghostreader/cache.py:20` — cache.py:20-55: last-report.json is per state dir and is the first file tried. A wrong-run result needs last-report.json to be unreadable and a legacy cache.json to also exist, and a corrupt file yields None, not corrupted output. The real legacy-shape problem is tracked separately in 0db3df07c7b60ec3.
- `ghostreader/canon_audit.py:382` — _coverage uses range(1, through+1) (canon_audit.py:166), matching the 1-based chapter-*.md convention that discovery also assumes ('missing chapter file(s) in 1..N'). The companion caller passes through explicitly (pipeline.py:244). An empty chapter map means there is nothing to cover.
- `ghostreader/graph/workflow.py:122` — workflow.py:87-140 only builds a standard LangGraph StateGraph with no custom task management. Cancellation propagates through the ainvoke coroutines, and no caller in the repo cancels or abandons a run partway.
- `ghostreader/ingestion/summarizer.py:146` — split_chunks (summarizer.py:141-165) would loop forever with chunk_chars<=0, but the only production caller (cli.py:341) never passes chunk_chars, so it uses DEFAULT_CHUNK_CHARS. No config exposes it.
- `ghostreader/report/markdown_writer.py:193` — markdown_writer.py:234 does prefer phrase over lemma and normalized_key, but thrash producers set phrase only for phrase-kind rows (thrash_detector.py:867-878) and leave lemma rows with an empty phrase, which falls through. Nothing emits a whitespace-only phrase.
- `ghostreader/agents/prose_analyst.py:120` — per_chapter comes from excerpts.py:37-40 chapter_chars(), which only returns STANDARD_CHAPTER_CHARS=4000 or DEEP_CHAPTER_CHARS=16000 (excerpts.py:33-34), so scale = per_chapter // 4000 at prose_analyst.py:121 is never 0; no config produces a sub-4000 cap.


## 3. WONTFIX CANDIDATES

- `ghostreader/quotes.py:348` — The real anchor is ingestion/indexer.py:226-248, not quotes.py:348. The stamp lives inside db_path and is written only a
- `ghostreader/cache.py:20` — cache.py:20-55: last-report.json is per state dir and is the first file tried. A wrong-run result needs last-report.json
- `ghostreader/ingestion/summarizer.py:106` — summarizer.py:102-104: '... if act_ranges else []' sends an empty act_ranges to _group_into_acts. _group_by_ranges also 
- `ghostreader/canon_audit.py:333` — _drift_match (canon_audit.py:294-303) is only called with names from names_in, which yields names of 2 or more capitaliz
- `ghostreader/canon_audit.py:382` — _coverage uses range(1, through+1) (canon_audit.py:166), matching the 1-based chapter-*.md convention that discovery als
- `ghostreader/graph/workflow.py:122` — workflow.py:87-140 only builds a standard LangGraph StateGraph with no custom task management. Cancellation propagates t
- `ghostreader/canon_audit.py:267` — _timeline returns early when len(stamps) < 3 (canon_audit.py:260-261), so len(values) >= 3 at the division on canon_audi
- `ghostreader/excerpts.py:284` — excerpts.py:284-294: the loop keeps adding windows while the merged length fits alloc_c. It breaks only when chosen alre
- `ghostreader/ingestion/summarizer.py:146` — split_chunks (summarizer.py:141-165) would loop forever with chunk_chars<=0, but the only production caller (cli.py:341)
- `ghostreader/report/markdown_writer.py:193` — markdown_writer.py:234 does prefer phrase over lemma and normalized_key, but thrash producers set phrase only for phrase
- `ghostreader/companion/shape.py:151` — shape.py:127-133: unquoted rows are allowed only for BOOK_KINDS (book-level single-track/flat-escalation), and the key (
- `ghostreader/report/check_homes.py:56` — check_homes.py:55-61 clamps every count with max(0, ...), so counts cannot go negative. The only caller, drop_report_dim
- `ghostreader/agents/prose_analyst.py:120` — per_chapter comes from excerpts.py:37-40 chapter_chars(), which only returns STANDARD_CHAPTER_CHARS=4000 or DEEP_CHAPTER
- `ghostreader/companion/pipeline.py:219` — pipeline.py:244 passes through=N-1; for N=1, through=0 makes _coverage range(1,1) empty and _timeline/_names_vs_prose fi
- `ghostreader/agents/canon_consistency.py:68` — canon_consistency.py:101-107: refs are built from the same extract_json_array output with the same isinstance(d, dict) f
- `ghostreader/agents/consistency_checker.py:563` — demote_ungrounded_concerns only checks the manuscript evidence field (grounding.py:39-40,454), never counter_evidence. q
- `ghostreader/llm.py:255` — llm.py:251-256: 'except OSError: pass' wraps a best-effort write to the once-per-day probe-cache file. Losing it only me
- `ghostreader/companion/pipeline.py:14` — run_companion_pipeline (pipeline.py:306+) puts genre and the others after a bare '*', where keyword-only args without de
- `ghostreader/usage.py:84` — usage.py:66-93: a child task inherits a copy of the context, so it keeps the tracker of the run that spawned it. Its usa