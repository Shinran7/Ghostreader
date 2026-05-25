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
        """Write config to ``config.yaml`` in *directory*."""
        path = directory / "config.yaml"
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            yaml.dump(
                self.model_dump(exclude_none=True),
                f,
                default_flow_style=False,
                sort_keys=False,
            )
        return path
