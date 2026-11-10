"""Chapter content hashing shared by the result caches (#18).

The analyze summary cache (``ghostreader.llm_cache``) and the fact store
(``ghostreader.companion.fact_memory``) key chapters on this hash.
"""

from __future__ import annotations

import hashlib


def chapter_content_hash(content: str) -> str:
    """SHA-256 hex digest of chapter text."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


__all__ = ["chapter_content_hash"]
