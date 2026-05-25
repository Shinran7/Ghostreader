"""LanceDB indexer — chunk, embed, and store manuscript data."""

from __future__ import annotations

from pathlib import Path

import lancedb
import pyarrow as pa

from ghostreader.ingestion import Chapter, SummaryHierarchy
from ghostreader.ingestion.chunking import TextChunk, chunk_text

# Default embedding dimension — placeholder for when a real embedding model
# is wired in. For now we use a simple hash-based stub so the pipeline is
# end-to-end testable without an API key.
_EMBED_DIM = 384

_CHUNKS_TABLE = "chunks"
_SUMMARIES_TABLE = "summaries"


def index_manuscript(
    chapters: list[Chapter],
    hierarchy: SummaryHierarchy,
    project_dir: Path,
    *,
    chunk_size: int = 1500,
    overlap: int = 200,
) -> tuple[int, Path]:
    """Chunk chapters, embed, and write to LanceDB.

    Returns (total_chunk_count, db_path).
    """
    db_path = project_dir / ".ghostreader" / "lancedb"
    db_path.mkdir(parents=True, exist_ok=True)

    db = lancedb.connect(str(db_path))

    # ── Chunk all chapters ──
    all_chunks = _build_chunks(chapters, chunk_size=chunk_size, overlap=overlap)

    # ── Write chunks table ──
    _write_chunks_table(db, all_chunks)

    # ── Write summaries table ──
    _write_summaries_table(db, hierarchy)

    return len(all_chunks), db_path


def _build_chunks(
    chapters: list[Chapter],
    *,
    chunk_size: int,
    overlap: int,
) -> list[TextChunk]:
    """Chunk every chapter and return flat list of TextChunk."""
    all_chunks: list[TextChunk] = []

    for chapter in chapters:
        raw_chunks = chunk_text(chapter.content, chunk_size=chunk_size, overlap=overlap)
        for idx, text in enumerate(raw_chunks):
            all_chunks.append(
                TextChunk(
                    text=text,
                    chapter_number=chapter.chapter_number,
                    chunk_index=idx,
                    source_path=str(chapter.source_path),
                )
            )

    return all_chunks


def _write_chunks_table(db: lancedb.DBConnection, chunks: list[TextChunk]) -> None:
    """Create or overwrite the chunks table in LanceDB."""
    if not chunks:
        return

    records = []
    for chunk in chunks:
        records.append(
            {
                "text": chunk.text,
                "chapter_number": chunk.chapter_number,
                "chunk_index": chunk.chunk_index,
                "source_path": chunk.source_path,
                "vector": _stub_embed(chunk.text),
            }
        )

    schema = pa.schema(
        [
            pa.field("text", pa.utf8()),
            pa.field("chapter_number", pa.int32()),
            pa.field("chunk_index", pa.int32()),
            pa.field("source_path", pa.utf8()),
            pa.field("vector", pa.list_(pa.float32(), _EMBED_DIM)),
        ]
    )

    if _CHUNKS_TABLE in db.table_names():
        db.drop_table(_CHUNKS_TABLE)
    db.create_table(_CHUNKS_TABLE, data=records, schema=schema)


def _write_summaries_table(
    db: lancedb.DBConnection, hierarchy: SummaryHierarchy
) -> None:
    """Create or overwrite the summaries table in LanceDB."""
    records = []

    for cs in hierarchy.chapter_summaries:
        records.append(
            {
                "level": "chapter",
                "identifier": f"chapter-{cs.chapter_number}",
                "title": cs.title,
                "summary": cs.summary,
                "vector": _stub_embed(cs.summary),
            }
        )

    for act in hierarchy.act_summaries:
        records.append(
            {
                "level": "act",
                "identifier": f"act-{act.act_number}",
                "title": f"Act {act.act_number} (ch {act.chapter_range[0]}-{act.chapter_range[1]})",
                "summary": act.summary,
                "vector": _stub_embed(act.summary),
            }
        )

    if hierarchy.global_summary:
        records.append(
            {
                "level": "global",
                "identifier": "global",
                "title": "Manuscript Summary",
                "summary": hierarchy.global_summary,
                "vector": _stub_embed(hierarchy.global_summary),
            }
        )

    if not records:
        return

    schema = pa.schema(
        [
            pa.field("level", pa.utf8()),
            pa.field("identifier", pa.utf8()),
            pa.field("title", pa.utf8()),
            pa.field("summary", pa.utf8()),
            pa.field("vector", pa.list_(pa.float32(), _EMBED_DIM)),
        ]
    )

    if _SUMMARIES_TABLE in db.table_names():
        db.drop_table(_SUMMARIES_TABLE)
    db.create_table(_SUMMARIES_TABLE, data=records, schema=schema)


def _stub_embed(text: str) -> list[float]:
    """Deterministic stub embedding for pipeline testing.

    Will be replaced with a real embedding model (e.g. sentence-transformers
    or OpenAI embeddings) when the embedding configuration is wired in.
    """
    import hashlib

    digest = hashlib.sha256(text.encode("utf-8")).digest()
    # Expand the 32-byte hash to fill _EMBED_DIM floats
    values: list[float] = []
    for i in range(_EMBED_DIM):
        byte_val = digest[i % len(digest)]
        values.append((byte_val / 255.0) * 2.0 - 1.0)  # normalize to [-1, 1]
    return values
