# Canon audit

214 stories with Canon and chapters. 212 have at least one finding.

| Kind | Severity | Stories | Rows |
| --- | --- | --- | --- |
| `missing_file` | info | 211 of 214 | 610 |
| `empty_file` | info | 14 of 214 | 16 |
| `chapter_not_recorded` | info | 9 of 214 | 13 |
| `death_chapter_missing` | concern | 14 of 214 | 15 |
| `seen_after_death` | concern | 7 of 214 | 15 |
| `seed_resolved_when_planted` | concern | 77 of 214 | 100 |
| `timeline_vague` | info | 6 of 214 | 6 |
| `name_drift` | concern | 2 of 214 | 2 |
| `character_not_in_prose` | concern | 7 of 214 | 10 |

## `missing_file`

- `plot/secrets-registry.json`: 211 stories
- `style/physical-state.json`: 153 stories
- `style/story-timeline.json`: 150 stories
- `style/chapter-ending-states.json`: 59 stories
- `style/chapter-locations.json`: 37 stories
- autonomicon: style/physical-state.json is missing
- autonomicon: style/story-timeline.json is missing
- autonomicon: style/chapter-ending-states.json is missing
- autonomicon: style/chapter-locations.json is missing
- autonomicon: plot/secrets-registry.json is missing
- … 605 more

## `empty_file`

- `style/physical-state.json`: 14 stories
- `plot/unresolved-seeds.json`: 2 stories
- bay-four-v1: style/physical-state.json is empty
- bay-four-v10: style/physical-state.json is empty
- bay-four-v11: style/physical-state.json is empty
- bay-four-v12: style/physical-state.json is empty
- bay-four-v2: style/physical-state.json is empty
- … 11 more

## `chapter_not_recorded`

- `style/chapter-locations.json`: 6 stories
- `style/chapter-ending-states.json`: 4 stories
- `style/story-timeline.json`: 3 stories
- parasentience-v2: style/chapter-ending-states.json has no row for chapter(s) 3
- parasentience-v2: style/chapter-locations.json has no row for chapter(s) 3
- the-echo-ward: style/chapter-ending-states.json has no row for chapter(s) 8
- the-echo-ward: style/chapter-locations.json has no row for chapter(s) 8
- the-indigo-anomaly-v2: style/chapter-ending-states.json has no row for chapter(s) 5
- … 8 more

## `death_chapter_missing`

- midnight-ride-share-matrix-b: Dwayne Pell is deceased but died_chapter is 0
- midnight-ride-share-matrix-c: Dominic Albayrak is deceased but died_chapter is 0
- midnight-ride-share-matrix-c: Wendell Bryce is deceased but died_chapter is 0
- midnight-ride-share-published: Alan Fernandez is deceased but died_chapter is 0
- the-echo-ward: Vesper Lynch is deceased but died_chapter is 0
- … 10 more

## `seen_after_death`

- the-cascade-codex: Jordan Hale died in chapter 15 but was last seen in chapter 17
- the-cascade-codex: Prof. Victor Blanchard died in chapter 15 but was last seen in chapter 17
- the-cascade-codex-published: Maya Ruiz died in chapter 6 but was last seen in chapter 13
- the-echo-ward-published: Amanda Cheney died in chapter 9 but was last seen in chapter 24
- the-echo-ward-published: Ellis Tanaka died in chapter 8 but was last seen in chapter 22
- … 10 more

## `seed_resolved_when_planted`

- bay-four: Critical seed 'pete-grief-impact' is planted and resolved in chapter 1
- bay-four-v1: Critical seed 'pete-decision' is planted and resolved in chapter 1
- bay-four-v12: Critical seed 'pete-decision' is planted and resolved in chapter 1
- bay-four-v2: Critical seed 'developer-closure-impact' is planted and resolved in chapter 1
- bay-four-v3: Critical seed 'pete-grief-impact' is planted and resolved in chapter 1
- … 95 more

## `timeline_vague`

- bay-four: Timeline narrative_time does not tell chapters apart (7 of 7 chapters say 'Late August')
- bay-four-v10: Timeline narrative_time does not tell chapters apart (5 of 5 chapters say 'Late August')
- bay-four-v11: Timeline narrative_time does not tell chapters apart (5 of 5 chapters say 'Late August')
- bay-four-v12: Timeline narrative_time does not tell chapters apart (5 of 5 chapters say 'Late August')
- bay-four-v5: Timeline narrative_time does not tell chapters apart (5 of 5 chapters say 'Late August')
- … 1 more

## `name_drift`

- bay-four-v3: Key facts say 'Morales Auto Body'; the prose says 'Luis Auto Body'
- three-liars-at-a-funeral: Key facts say 'St. Augustine'; the prose says 'St. Mary'

## `character_not_in_prose`

- midnight-ride-share: Ferrin (introduced chapter 4) is never named in the prose
- the-cartographer-s-stand-v1: Józef Barański (introduced chapter 1) is never named in the prose
- the-farther-shore: Trenton Ines Barrow (introduced chapter 1) is never named in the prose
- the-quiet-archive: Ruth Calloway (introduced chapter 3) is never named in the prose
- the-quiet-archive: Tavi (introduced chapter 3) is never named in the prose
- … 5 more
