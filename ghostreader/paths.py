"""Path resolution for Ghostreader config and per-manuscript state.

Global config:
    Windows:  %APPDATA%\\ghostreader\\config.yaml
    Other:    ~/.config/ghostreader/config.yaml

Per-manuscript state (cache, LanceDB index, checkpoints):
    <global_config_dir>/cache/<sha256(resolved_path)[:16]>/

A ``source.txt`` breadcrumb inside each state dir records the original
manuscript path for discoverability.
"""

from __future__ import annotations

import hashlib
import os
import platform
from pathlib import Path


def global_config_dir() -> Path:
    """Return the platform-appropriate global config directory."""
    if platform.system() == "Windows":
        base = os.environ.get("APPDATA")
        if base:
            return Path(base) / "ghostreader"
    return Path.home() / ".config" / "ghostreader"


def global_config_path() -> Path:
    """Return the path to the global ``config.yaml``."""
    return global_config_dir() / "config.yaml"


def state_dir_for(manuscript_path: Path) -> Path:
    """Return the per-manuscript state directory, creating it if needed.

    The directory is keyed by a truncated SHA-256 of the resolved
    manuscript path.  A ``source.txt`` breadcrumb is written so the
    user can discover which manuscript a state dir belongs to.
    """
    resolved = str(manuscript_path.resolve())
    path_hash = hashlib.sha256(resolved.encode("utf-8")).hexdigest()[:16]
    state = global_config_dir() / "cache" / path_hash
    state.mkdir(parents=True, exist_ok=True)

    breadcrumb = state / "source.txt"
    if not breadcrumb.exists():
        breadcrumb.write_text(resolved, encoding="utf-8")

    return state


def find_project_override(start: Path) -> Path | None:
    """Walk up from *start* looking for a ``ghostreader.yaml`` override.

    Returns the path to the YAML file, or ``None`` if not found.
    """
    current = start.resolve()
    if current.is_file():
        current = current.parent
    for directory in [current, *current.parents]:
        candidate = directory / "ghostreader.yaml"
        if candidate.is_file():
            return candidate
    return None


__all__ = [
    "find_project_override",
    "global_config_dir",
    "global_config_path",
    "state_dir_for",
]
