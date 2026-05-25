"""Configuration model for Ghostreader.

Resolution order:
    1. Global config  (~/.config/ghostreader/config.yaml  or  %APPDATA%\\ghostreader\\config.yaml)
    2. Project override  (ghostreader.yaml found walking up from the manuscript)
    3. CLI flags  (applied by callers after loading)
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel

from ghostreader.paths import find_project_override, global_config_path


class GhostreaderConfig(BaseModel):
    """Ghostreader configuration."""

    default_model: str = "grok-beta"
    embedding_model: str = "all-MiniLM-L6-v2"
    genre: str | None = None
    depth: Literal["quick", "standard", "deep"] = "standard"
    model_preference_order: list[str] = ["grok-beta", "gemini-2.5-pro"]
    format: Literal["markdown", "json"] = "markdown"

    @classmethod
    def load(cls, manuscript_path: Path | None = None) -> GhostreaderConfig:
        """Load config: global defaults → project override → return merged."""
        data: dict = {}

        # 1. Global config
        gcp = global_config_path()
        if gcp.exists():
            with open(gcp, encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}

        # 2. Project-level override (ghostreader.yaml)
        if manuscript_path is not None:
            override_path = find_project_override(manuscript_path)
            if override_path is not None:
                with open(override_path, encoding="utf-8") as f:
                    override = yaml.safe_load(f) or {}
                data.update(override)

        return cls(**data)

    def save_global(self) -> Path:
        """Write config to the global config.yaml. Returns the path written."""
        path = global_config_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            yaml.dump(
                self.model_dump(exclude_none=True),
                f,
                default_flow_style=False,
                sort_keys=False,
            )
        return path

    def save_project(self, directory: Path) -> Path:
        """Write config to a project-level ghostreader.yaml override."""
        config_path = directory / "ghostreader.yaml"
        with open(config_path, "w", encoding="utf-8") as f:
            yaml.dump(
                self.model_dump(exclude_none=True),
                f,
                default_flow_style=False,
                sort_keys=False,
            )
        return config_path
