# GhostReader data

## `en_zipf_small.json`

Vendored Zipf frequency subset for uncommon-noun thrash (`thrash_detector`, `#285` / `8c6c4513`).

**Source of truth:** Autonomicon `src/autonomicon/data/en_zipf_small.json`.

**Sync:** when the Autonomicon SoT changes, update this copy in the same closeout window. Keep **strict JSON only** (no comments inside the file). Threshold `4.0` and `COMMON_ENGLISH` membership live in `ghostreader/analyzers/thrash_detector.py` and must stay aligned with Autonomicon `polish_uncommon_noun_thrash`.

See also Autonomicon `docs/plans/pointer-8c6c4513-zipf-sync.md`.
