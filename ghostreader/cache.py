"""Chapter content hashing and the last-report file (#18).

The analyze summary cache (``ghostreader.llm_cache``) and the fact store
(``ghostreader.companion.fact_memory``) key chapters on this hash.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def chapter_content_hash(content: str) -> str:
    """SHA-256 hex digest of chapter text."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


# ── Last analyze report (#18) ────────────────────────────────────────

LAST_REPORT = "last-report.json"


def save_last_report(state_dir: Path, report: dict[str, Any]) -> Path:
    """Write the final analyze report once, to ``<state>/last-report.json``."""
    state_dir.mkdir(parents=True, exist_ok=True)
    path = state_dir / LAST_REPORT
    path.write_text(json.dumps(report, ensure_ascii=False, default=str), encoding="utf-8")
    return path


def load_last_report(state_dir: Path) -> dict[str, Any] | None:
    """The last analyze report: ``last-report.json``, else legacy ``cache.json``.

    Legacy ``cache.json`` held either ``{"final_report": …}`` or the old
    per-chapter ``{"entries": [{"result": …}]}`` layout.
    """
    for name in (LAST_REPORT, "cache.json"):
        try:
            data = json.loads((state_dir / name).read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue
        if not isinstance(data, dict):
            continue
        if isinstance(data.get("final_report"), dict):
            return data["final_report"]
        entries = data.get("entries")
        if isinstance(entries, list):
            results = [e.get("result") for e in entries if isinstance(e, dict)]
            results = [r for r in results if isinstance(r, dict)]
            if results:
                return results[-1]
            continue
        return data
    return None


__all__ = ["chapter_content_hash", "load_last_report", "save_last_report"]
