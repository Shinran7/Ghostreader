"""Tests for LanceDB table-name helpers."""

from __future__ import annotations

from types import SimpleNamespace

from ghostreader.lancedb_util import has_table, list_table_names


class TestListTableNames:
    def test_plain_list(self) -> None:
        db = SimpleNamespace(list_tables=lambda: ["chunks", "summaries"])
        assert list_table_names(db) == ["chunks", "summaries"]
        assert has_table(db, "chunks") is True
        assert has_table(db, "missing") is False

    def test_list_tables_response_shape(self) -> None:
        """LanceDB 0.30+ returns an object with .tables, not a raw list."""
        response = SimpleNamespace(tables=["chunks", "summaries"])
        db = SimpleNamespace(list_tables=lambda: response)
        assert list_table_names(db) == ["chunks", "summaries"]
        assert has_table(db, "chunks") is True
        assert has_table(db, "summaries") is True
