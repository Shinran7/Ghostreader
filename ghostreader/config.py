"""Configuration model for Ghostreader.

Resolution order:
    1. config.yaml at the project root (found by walking up from CWD
       or the manuscript path)
    2. CLI flags (applied by callers after loading)
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel

from ghostreader.paths import config_path as _find_config_path


class GhostreaderConfig(BaseModel):
    """Ghostreader configuration."""

    model: str | None = "gemini-3.8-flash"
    embedding_model: str = "all-MiniLM-L6-v2"
    temperature: float | None = None
    max_tokens: int | None = None
    genre: str | None = None
    depth: Literal["quick", "standard", "deep"] = "standard"
    format: Literal["markdown", "json"] = "markdown"
    typesafe_enabled: bool = False
    typesafe_confidence_floor: float = 0.55
    typesafe_noul_positive_threshold: float = 0.65
    companion_prior: Literal["full", "rolling"] = "full"
    companion_rolling_min_chapters: int = 15
    companion_fact_chars_budget: int = 48000
    # Prior chapters (excluding N) included in companion repetition detection.
    companion_craft_window: int = 5
    # Master kill switch for cross-chapter craft (false = N-only).
    companion_cross_chapter_craft: bool = True
    # Ask/store foreshadowing + unresolved as watch-only (never flip verdict alone).
    companion_info_dims: bool = True
    # Light narrative (pacing + character arcs). Default on; set false to disable.
    companion_light_narrative: bool = True
    # Preflight: ask the chat model for {"ok": true} before expensive work.
    # Catches provider content-shape / JSON breakage after model switches.
    llm_json_probe: bool = True
    # Abort analyze/companion (exit 1) when any chapter fact sheet fails JSON parse.
    # Continuity on empty sheets looks "clean" and must not be trusted.
    abort_on_fact_parse_failure: bool = True
    # Analyze repetition feed caps (always on; not gated by analyze_grounding_hardening).
    analyze_repetition_words: int = 50
    analyze_repetition_phrases: int = 40
    analyze_repetition_patterns: int = 20
    # Hit-weighted excerpt ceiling (headers included). Used when hardening is on.
    analyze_excerpt_total_budget: int = 100000
    analyze_excerpt_window_chars: int = 900
    analyze_excerpt_min_per_chapter: int = 400
    # Continuity enrich/tie-break combined ceiling (sheets + manuscript).
    analyze_continuity_enrich_total_budget: int = 120000
    # Master switch for hit-weighted excerpts + empty-evidence policies.
    # Does NOT gate analyze_repetition_* caps / kind / pattern examples.
    analyze_grounding_hardening: bool = True
    # Ask/parse continuity signal_kind; demote tone_understatement plot_holes.
    analyze_continuity_signal_kind: bool = True
    # Max algorithmic repetition_findings rows in analyze JSON (always on).
    analyze_repetition_findings_cap: int = 40
    # Include TypeSafe strengths in Choice enrich batch (analyze only).
    analyze_enrich_strengths: bool = True
    # Drop empty-evidence strengths from prioritized findings after synthesis.
    analyze_omit_empty_strengths: bool = True

    @classmethod
    def load(cls, manuscript_path: Path | None = None) -> GhostreaderConfig:
        """Load config from the project-root ``config.yaml``."""
        cfg_path = _find_config_path(manuscript_path)
        if cfg_path is not None and cfg_path.exists():
            with open(cfg_path, encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            return cls(**data)
        return cls()

    def save(self, directory: Path) -> Path:
        """Write config to ``config.yaml`` in *directory*.

        All fields are written so the user can see every available setting.
        Uses a hand-written template so inline comments are preserved.
        """
        path = directory / "config.yaml"
        path.parent.mkdir(parents=True, exist_ok=True)

        def _fmt(val: object) -> str:
            if val is None:
                return "null"
            if isinstance(val, bool):
                return str(val).lower()
            return str(val)

        lines = [
            # LLM model (required). Examples: gemini-3.8-flash,
            # accounts/fireworks/models/minimax-m3, gpt-4o, ollama:llama3
            "# LLM model (required). e.g. gemini-3.8-flash, "
            "accounts/fireworks/models/minimax-m3, gpt-4o, ollama:llama3",
            f"model: {_fmt(self.model)}",
            f"",
            f"# Embedding model for vector search. Default: all-MiniLM-L6-v2 (local, no API key)",
            f"embedding_model: {_fmt(self.embedding_model)}",
            f"",
            f"# Temperature for LLM generation. null = provider default (typically 0.7-1.0)",
            f"temperature: {_fmt(self.temperature)}",
            f"",
            f"# Max tokens for LLM responses. null = provider default",
            f"max_tokens: {_fmt(self.max_tokens)}",
            f"",
            f"# Genre lens for analysis prompts. null = genre-agnostic analysis",
            f"# Options: literary, fantasy, thriller, romance, sci-fi, mystery, horror, etc.",
            f"genre: {_fmt(self.genre)}",
            f"",
            f"# Analysis depth: quick, standard, or deep",
            f"depth: {_fmt(self.depth)}",
            f"",
            f"# Output format: markdown or json",
            f"format: {_fmt(self.format)}",
            f"",
            f"# Use TypeSafe.ai (Jev) for judgment severities/gates. Needs TYPESAFE_API_KEY.",
            f"typesafe_enabled: {_fmt(self.typesafe_enabled)}",
            f"",
            f"# Below this Choice confidence, enrich with LLM quotes (severity stays TypeSafe).",
            f"typesafe_confidence_floor: {_fmt(self.typesafe_confidence_floor)}",
            f"",
            f"# Consistency Noul at or above this → concern + enrich. Mid-band always LLM tie-break.",
            f"typesafe_noul_positive_threshold: {_fmt(self.typesafe_noul_positive_threshold)}",
            f"",
            f"# Companion prior facts: full (1…N) or rolling (last K on budget/config).",
            f"companion_prior: {_fmt(self.companion_prior)}",
            f"",
            f"# When rolling engages, keep at least this many recent chapters.",
            f"companion_rolling_min_chapters: {_fmt(self.companion_rolling_min_chapters)}",
            f"",
            f"# Auto-roll when formatted fact sheets exceed this many characters.",
            f"companion_fact_chars_budget: {_fmt(self.companion_fact_chars_budget)}",
            f"",
            f"# Prior chapters (excluding N) included in companion repetition detection.",
            f"companion_craft_window: {_fmt(self.companion_craft_window)}",
            f"",
            f"# Master kill switch for cross-chapter craft (false = N-only, v1 behavior).",
            f"companion_cross_chapter_craft: {_fmt(self.companion_cross_chapter_craft)}",
            f"",
            f"# Ask foreshadowing/unresolved as watch-only (never flip verdict alone).",
            f"companion_info_dims: {_fmt(self.companion_info_dims)}",
            f"",
            f"# Light narrative pacing + character arcs (default on; false = kill switch).",
            f"companion_light_narrative: {_fmt(self.companion_light_narrative)}",
            f"",
            f"# Probe chat model JSON contract at analyze/companion start (model-switch guard).",
            f"llm_json_probe: {_fmt(self.llm_json_probe)}",
            f"",
            f"# Abort when fact-extraction JSON parse fails (empty sheets poison continuity).",
            f"abort_on_fact_parse_failure: {_fmt(self.abort_on_fact_parse_failure)}",
            f"",
            f"# Analyze repetition feed: max word / phrase / sentence-pattern rows.",
            f"# Always applied (not gated by analyze_grounding_hardening).",
            f"analyze_repetition_words: {_fmt(self.analyze_repetition_words)}",
            f"analyze_repetition_phrases: {_fmt(self.analyze_repetition_phrases)}",
            f"analyze_repetition_patterns: {_fmt(self.analyze_repetition_patterns)}",
            f"",
            f"# Hit-weighted manuscript excerpt ceiling (chars, headers included).",
            f"analyze_excerpt_total_budget: {_fmt(self.analyze_excerpt_total_budget)}",
            f"analyze_excerpt_window_chars: {_fmt(self.analyze_excerpt_window_chars)}",
            f"analyze_excerpt_min_per_chapter: {_fmt(self.analyze_excerpt_min_per_chapter)}",
            f"",
            f"# Continuity enrich/tie-break combined ceiling (sheets + manuscript).",
            f"analyze_continuity_enrich_total_budget: {_fmt(self.analyze_continuity_enrich_total_budget)}",
            f"",
            f"# Hit-weighted excerpts + empty-evidence retry/fallback/demotion.",
            f"# false restores legacy flat excerpts and skips those policies.",
            f"# Does NOT revert analyze_repetition_* caps or kind/pattern examples.",
            f"analyze_grounding_hardening: {_fmt(self.analyze_grounding_hardening)}",
            f"",
            f"# Continuity enrich signal_kind + tone_understatement plot_holes demotion.",
            f"# false skips asking/parsing signal_kind and the tone demotion.",
            f"analyze_continuity_signal_kind: {_fmt(self.analyze_continuity_signal_kind)}",
            f"",
            f"# Max algorithmic repetition_findings rows in analyze JSON export.",
            f"analyze_repetition_findings_cap: {_fmt(self.analyze_repetition_findings_cap)}",
            f"",
            f"# Enrich TypeSafe strength findings in the Choice enrich batch.",
            f"# false keeps high-conf strengths as template stubs (companion-like).",
            f"analyze_enrich_strengths: {_fmt(self.analyze_enrich_strengths)}",
            f"",
            f"# Drop empty-evidence strengths from findings lists after prioritize.",
            f"# Dimension ratings still show strength; TypeSafe-off summary prose unchanged.",
            f"analyze_omit_empty_strengths: {_fmt(self.analyze_omit_empty_strengths)}",
            f"",
        ]

        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

        return path
