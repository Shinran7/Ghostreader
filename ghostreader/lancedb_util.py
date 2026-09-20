"""LanceDB helpers that tolerate API shape differences across versions."""

from __future__ import annotations

from typing import Any


def list_table_names(db: Any) -> list[str]:
    """Return table names from ``db.list_tables()``.

    LanceDB 0.30+ returns ``ListTablesResponse`` (with a ``.tables`` attribute)
    instead of a plain ``list``; ``name in db.list_tables()`` is therefore False
    even when the table exists.
    """
    result = db.list_tables()
    tables = getattr(result, "tables", result)
    return [str(name) for name in tables]


def has_table(db: Any, name: str) -> bool:
    """Return True if *name* is among the DB's tables."""
    return name in list_table_names(db)


__all__ = ["has_table", "list_table_names"]
