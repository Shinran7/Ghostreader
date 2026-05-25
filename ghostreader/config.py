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

    model: str | None = None
    embedding_model: str = "all-MiniLM-L6-v2"
    temperature: float | None = None
    max_tokens: int | None = None
    genre: str | None = None
    depth: Literal["quick", "standard", "deep"] = "standard"
    format: Literal["markdown", "json"] = "markdown"

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
            f"# LLM model (required). e.g. gpt-4o, claude-sonnet-4-20250514, grok-beta, ollama:llama3, gemini-2.5-pro",
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
        ]

        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

        return path
