"""Give every chunk a context header, apart from its text — FR-CORE-003, approach on #3.

The header form is specified in `docs/reference/chunk-schema.md` (`data/enriched/chunks.jsonl`).
"""

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from src.chunking import Article, Chunk, ChunkedDocument
from src.chunking.chunker import doc_id_of

DOCUMENT_FIELDS = ("loai_van_ban", "so_hieu", "trich_yeu")


@dataclass(frozen=True)
class EnrichedChunk:
    id: str
    doc_id: str
    chapter: str | None
    chapter_title: str | None
    article: str
    clause: str | None
    parent_id: str
    text: str
    header: str


def indexed_text(chunk: EnrichedChunk) -> str:
    """What the indexes see. A citation shows `chunk.text` alone."""
    return chunk.header + "\n" + chunk.text


def _document_part(doc: dict) -> str:
    meta = doc.get("metadata", {})
    missing = [name for name in DOCUMENT_FIELDS if not (meta.get(name) or "").strip()]
    if missing:
        raise ValueError(f"document {doc_id_of(doc)} has no {', '.join(missing)} for its header")
    return f"[{meta['loai_van_ban'].strip()} {meta['so_hieu'].strip()} — {meta['trich_yeu'].strip()}]"


def _position_part(chunk: Chunk, article_title: str) -> str:
    parts = []
    if chunk.chapter:
        parts.append(f"{chunk.chapter}. {chunk.chapter_title}" if chunk.chapter_title else chunk.chapter)
    parts.append(f"Điều {chunk.article}. {article_title}" if article_title else f"Điều {chunk.article}")
    if chunk.clause not in (None, "0"):
        parts.append(f"Khoản {chunk.clause}")
    return "[" + " > ".join(parts) + "]"


def enrich_document(doc: dict, chunked: ChunkedDocument) -> list[EnrichedChunk]:
    document = _document_part(doc)
    titles = {article.id: article.title for article in chunked.articles}
    return [
        EnrichedChunk(**asdict(chunk), header=f"{document} {_position_part(chunk, titles[chunk.parent_id])}")
        for chunk in chunked.chunks
    ]


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def build(processed_dir: Path, chunks_dir: Path, out_dir: Path) -> list[EnrichedChunk]:
    """Enrich the chunker's output; write `chunks.jsonl` in the chunker's order."""
    docs = {}
    for path in processed_dir.glob("*.json"):
        if not path.name.startswith("_"):
            doc = json.loads(path.read_text(encoding="utf-8"))
            docs[doc_id_of(doc)] = doc

    chunks_by_doc: dict[str, list[Chunk]] = {}
    for record in _read_jsonl(chunks_dir / "chunks.jsonl"):
        chunks_by_doc.setdefault(record["doc_id"], []).append(Chunk(**record))
    articles_by_doc: dict[str, list[Article]] = {}
    for record in _read_jsonl(chunks_dir / "articles.jsonl"):
        articles_by_doc.setdefault(record["doc_id"], []).append(Article(**record))

    enriched: list[EnrichedChunk] = []
    for doc_id, chunks in chunks_by_doc.items():  # dicts keep the file's order
        if doc_id not in docs:
            raise ValueError(f"chunks of document {doc_id} but no parsed document in {processed_dir}")
        chunked = ChunkedDocument(articles_by_doc.get(doc_id, []), chunks, [])
        enriched += enrich_document(docs[doc_id], chunked)

    out_dir.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(asdict(chunk), ensure_ascii=False) + "\n" for chunk in enriched]
    (out_dir / "chunks.jsonl").write_text("".join(lines), encoding="utf-8", newline="\n")
    return enriched
