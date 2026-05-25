"""LanceDB indexer — chunk, embed, and store manuscript data."""

from __future__ import annotations

from pathlib import Path

import lancedb
import pyarrow as pa

from ghostreader.embed import Embedder, StubEmbedder, get_embedder
from ghostreader.ingestion import Chapter, SummaryHierarchy
from ghostreader.ingestion.chunking import TextChunk, chunk_text

_CHUNKS_TABLE = "chunks"
_SUMMARIES_TABLE = "summaries"


def index_manuscript(
    chapters: list[Chapter],
    hierarchy: SummaryHierarchy,
    state_dir: Path,
    *,
    chunk_size: int = 1500,
    overlap: int = 200,
    embedding_model: str = "stub",
) -> tuple[int, Path]:
    """Chunk chapters, embed, and write to LanceDB.

    Returns (total_chunk_count, db_path).
    """
    db_path = state_dir / "lancedb"
    db_path.mkdir(parents=True, exist_ok=True)

    db = lancedb.connect(str(db_path))
    embedder = get_embedder(embedding_model)

    # ── Chunk all chapters ──
    all_chunks = _build_chunks(chapters, chunk_size=chunk_size, overlap=overlap)

    # ── Write chunks table ──
    _write_chunks_table(db, all_chunks, embedder)

    # ── Write summaries table ──
    _write_summaries_table(db, hierarchy, embedder)

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


def _write_chunks_table(
    db: lancedb.DBConnection, chunks: list[TextChunk], embedder: Embedder
) -> None:
    """Create or overwrite the chunks table in LanceDB."""
    if not chunks:
        return

    texts = [chunk.text for chunk in chunks]
    vectors = embedder.embed(texts)

    records = []
    for chunk, vec in zip(chunks, vectors):
        records.append(
            {
                "text": chunk.text,
                "chapter_number": chunk.chapter_number,
                "chunk_index": chunk.chunk_index,
                "source_path": chunk.source_path,
                "vector": vec,
            }
        )

    schema = pa.schema(
        [
            pa.field("text", pa.utf8()),
            pa.field("chapter_number", pa.int32()),
            pa.field("chunk_index", pa.int32()),
            pa.field("source_path", pa.utf8()),
            pa.field("vector", pa.list_(pa.float32(), embedder.dimension)),
        ]
    )

    if _CHUNKS_TABLE in db.list_tables():
        db.drop_table(_CHUNKS_TABLE)
    db.create_table(_CHUNKS_TABLE, data=records, schema=schema)


def _write_summaries_table(
    db: lancedb.DBConnection, hierarchy: SummaryHierarchy, embedder: Embedder
) -> None:
    """Create or overwrite the summaries table in LanceDB."""
    summary_texts: list[str] = []
    meta: list[dict] = []

    for cs in hierarchy.chapter_summaries:
        summary_texts.append(cs.summary)
        meta.append({
            "level": "chapter",
            "identifier": f"chapter-{cs.chapter_number}",
            "title": cs.title,
            "summary": cs.summary,
        })

    for act in hierarchy.act_summaries:
        summary_texts.append(act.summary)
        meta.append({
            "level": "act",
            "identifier": f"act-{act.act_number}",
            "title": f"Act {act.act_number} (ch {act.chapter_range[0]}-{act.chapter_range[1]})",
            "summary": act.summary,
        })

    if hierarchy.global_summary:
        summary_texts.append(hierarchy.global_summary)
        meta.append({
            "level": "global",
            "identifier": "global",
            "title": "Manuscript Summary",
            "summary": hierarchy.global_summary,
        })

    if not meta:
        return

    vectors = embedder.embed(summary_texts)
    records = [{**m, "vector": v} for m, v in zip(meta, vectors)]

    schema = pa.schema(
        [
            pa.field("level", pa.utf8()),
            pa.field("identifier", pa.utf8()),
            pa.field("title", pa.utf8()),
            pa.field("summary", pa.utf8()),
            pa.field("vector", pa.list_(pa.float32(), embedder.dimension)),
        ]
    )

    if _SUMMARIES_TABLE in db.list_tables():
        db.drop_table(_SUMMARIES_TABLE)
    db.create_table(_SUMMARIES_TABLE, data=records, schema=schema)
