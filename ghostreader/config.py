"""Configuration model for Ghostreader projects."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel


class GhostreaderConfig(BaseModel):
    """Project-level configuration stored in config.yaml."""

    default_model: str = "grok-beta"
    genre: str | None = None
    depth: Literal["quick", "standard", "deep"] = "standard"
    model_preference_order: list[str] = ["grok-beta", "gemini-2.5-pro"]
    format: Literal["markdown", "json"] = "markdown"

    @classmethod
    def load(cls, project_dir: Path) -> GhostreaderConfig:
        """Load config from a project's config.yaml, falling back to defaults."""
        config_path = project_dir / "config.yaml"
        if config_path.exists():
            with open(config_path, encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            return cls(**data)
        return cls()

    def save(self, project_dir: Path) -> Path:
        """Write config to the project's config.yaml. Returns the path written."""
        config_path = project_dir / "config.yaml"
        with open(config_path, "w", encoding="utf-8") as f:
            yaml.dump(
                self.model_dump(exclude_none=True),
                f,
                default_flow_style=False,
                sort_keys=False,
            )
        return config_path
