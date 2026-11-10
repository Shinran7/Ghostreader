"""LanceDB indexer — chunk, embed, and store manuscript data."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import lancedb
import pyarrow as pa

from ghostreader.embed import Embedder, StubEmbedder, get_embedder
from ghostreader.ingestion import ActSummary, Chapter, ChapterSummary, SummaryHierarchy
from ghostreader.ingestion.chunking import TextChunk, chunk_text
from ghostreader.lancedb_util import has_table

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

    if has_table(db, _CHUNKS_TABLE):
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
        meta.append(
            {
                "level": "chapter",
                "identifier": f"chapter-{cs.chapter_number}",
                "title": cs.title,
                "summary": cs.summary,
            }
        )

    for act in hierarchy.act_summaries:
        summary_texts.append(act.summary)
        meta.append(
            {
                "level": "act",
                "identifier": f"act-{act.act_number}",
                "title": f"Act {act.act_number} (ch {act.chapter_range[0]}-{act.chapter_range[1]})",
                "summary": act.summary,
            }
        )

    if hierarchy.global_summary:
        summary_texts.append(hierarchy.global_summary)
        meta.append(
            {
                "level": "global",
                "identifier": "global",
                "title": "Manuscript Summary",
                "summary": hierarchy.global_summary,
            }
        )

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

    if has_table(db, _SUMMARIES_TABLE):
        db.drop_table(_SUMMARIES_TABLE)
    db.create_table(_SUMMARIES_TABLE, data=records, schema=schema)


# ── Chat-only index, built on demand (#18) ───────────────────────────
# Analysis never retrieves from the index; only ``chat`` does. Analyze
# saves its summaries; chat builds the index when it is missing or stale.

_STAMP_FILE = "stamp.json"
SUMMARIES_FILE = "summaries.json"


def save_summaries(state_dir: Path, hierarchy: SummaryHierarchy) -> Path:
    """Keep the summary hierarchy so chat can index it without LLM calls."""
    state_dir.mkdir(parents=True, exist_ok=True)
    path = state_dir / SUMMARIES_FILE
    path.write_text(json.dumps(asdict(hierarchy), ensure_ascii=False), encoding="utf-8")
    return path


def load_summaries(state_dir: Path) -> SummaryHierarchy:
    """Saved summaries, or an empty hierarchy when absent or unreadable."""
    try:
        raw = json.loads((state_dir / SUMMARIES_FILE).read_text(encoding="utf-8"))
        return SummaryHierarchy(
            chapter_summaries=[ChapterSummary(**c) for c in raw.get("chapter_summaries", [])],
            act_summaries=[
                ActSummary(
                    act_number=a["act_number"],
                    chapter_range=(a["chapter_range"][0], a["chapter_range"][1]),
                    summary=a["summary"],
                )
                for a in raw.get("act_summaries", [])
            ],
            global_summary=str(raw.get("global_summary", "")),
        )
    except (OSError, ValueError, KeyError, TypeError, IndexError, AttributeError):
        return SummaryHierarchy()


def index_stamp(chapters: list[Chapter], hierarchy: SummaryHierarchy, embedding_model: str) -> str:
    """Key over everything the index holds: chapter text, summaries, embedder."""
    from ghostreader.cache import chapter_content_hash
    from ghostreader.llm_cache import cache_key

    return cache_key(
        embedding_model,
        *(f"{c.chapter_number}:{chapter_content_hash(c.content)}" for c in chapters),
        json.dumps(asdict(hierarchy), sort_keys=True),
    )


def ensure_index(
    chapters: list[Chapter],
    hierarchy: SummaryHierarchy,
    state_dir: Path,
    *,
    embedding_model: str = "stub",
) -> tuple[bool, Path]:
    """Build the index unless its stamp matches. Returns (rebuilt, db_path)."""
    db_path = state_dir / "lancedb"
    stamp = index_stamp(chapters, hierarchy, embedding_model)
    try:
        if json.loads((db_path / _STAMP_FILE).read_text(encoding="utf-8"))["stamp"] == stamp:
            return False, db_path
    except (OSError, ValueError, KeyError, TypeError):
        pass
    count, db_path = index_manuscript(
        chapters, hierarchy, state_dir, embedding_model=embedding_model
    )
    (db_path / _STAMP_FILE).write_text(
        json.dumps({"stamp": stamp, "chunks": count}), encoding="utf-8"
    )
    return True, db_path
