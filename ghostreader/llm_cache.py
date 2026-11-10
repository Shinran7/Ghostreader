"""Content-addressed store for LLM results (#18).

A result is keyed on everything that shaped it: the input text hash, the
model, and a prompt version. A rerun with the same key reads the stored
value and makes no call. Corrupt or unreadable entries count as misses.
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def cache_key(*parts: object) -> str:
    """SHA-256 over the parts, in order (str() of each, NUL-separated)."""
    h = hashlib.sha256()
    for p in parts:
        h.update(str(p).encode("utf-8"))
        h.update(b"\0")
    return h.hexdigest()


def model_key(llm: Any, requested: str | None = None) -> str:
    """Stable model identifier for cache keys."""
    for attr in ("model_name", "model", "model_id"):
        v = getattr(llm, attr, None)
        if isinstance(v, str) and v:
            return v
    return requested or str(getattr(llm, "_llm_type", "") or type(llm).__name__)


class ResultCache:
    """JSON values under ``<root>/<kind>/<key>.json``.

    ``enabled=False`` (``--no-cache``) skips reads and writes. Counts hits
    and misses per kind for progress lines and tests.
    """

    def __init__(self, root: Path, *, enabled: bool = True) -> None:
        self.root = root
        self.enabled = enabled
        self.hits: dict[str, int] = {}
        self.misses: dict[str, int] = {}

    def _path(self, kind: str, key: str) -> Path:
        return self.root / kind / f"{key}.json"

    def get(self, kind: str, key: str) -> Any | None:
        value = None
        if self.enabled:
            try:
                value = json.loads(self._path(kind, key).read_text(encoding="utf-8"))["value"]
            except FileNotFoundError:
                value = None
            except (OSError, ValueError, KeyError, TypeError) as exc:
                logger.warning(
                    "Unreadable cache entry %s/%s (%s); treating as miss", kind, key, exc
                )
                value = None
        bucket = self.hits if value is not None else self.misses
        bucket[kind] = bucket.get(kind, 0) + 1
        return value

    def put(self, kind: str, key: str, value: Any) -> None:
        if not self.enabled or value is None:
            return
        path = self._path(kind, key)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps({"value": value}, ensure_ascii=False), encoding="utf-8")
            tmp.replace(path)
        except OSError as exc:  # a cache write never fails the run
            logger.warning("Could not write cache entry %s/%s (%s)", kind, key, exc)
