"""Enrich every chunk: its context header (FR-CORE-003, #3), effective date (FR-CORE-004, #4) and
the amendment links that change it (FR-CORE-005, #5).

All three are specified in `docs/reference/chunk-schema.md` (`data/enriched/`).
"""

import json
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path

from src.chunking import Article, Chunk, ChunkedDocument, Issue
from src.chunking.chunker import doc_id_of
from src.enrich.effective import effective_dates
from src.enrich.links import amendment_links

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
    effective_date: str | None
    amended_by: list[dict] = field(default_factory=list)  # [{type, source}], see links.py


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


def _enrich(doc: dict, chunked: ChunkedDocument) -> tuple[list[EnrichedChunk], list[Issue]]:
    document = _document_part(doc)
    titles = {article.id: article.title for article in chunked.articles}
    dates = effective_dates(doc, chunked)
    chunks = [
        EnrichedChunk(**asdict(chunk), header=f"{document} {_position_part(chunk, titles[chunk.parent_id])}",
                      effective_date=dates.by_chunk[chunk.id])
        for chunk in chunked.chunks
    ]
    return chunks, dates.issues


def enrich_document(doc: dict, chunked: ChunkedDocument) -> list[EnrichedChunk]:
    return _enrich(doc, chunked)[0]


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _write_jsonl(path: Path, records: list) -> None:
    lines = [json.dumps(asdict(record), ensure_ascii=False) + "\n" for record in records]
    path.write_text("".join(lines), encoding="utf-8", newline="\n")


def build(processed_dir: Path, chunks_dir: Path, out_dir: Path) -> tuple[list[EnrichedChunk], list[Issue]]:
    """Enrich the chunker's output; write `chunks.jsonl` in the chunker's order, `links.jsonl` and
    `issues.jsonl`."""
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
    issues_by_doc: dict[str, list[Issue]] = {}
    corpus: list[tuple[dict, ChunkedDocument]] = []
    for doc_id, chunks in chunks_by_doc.items():  # dicts keep the file's order, sorted by doc id
        if doc_id not in docs:
            raise ValueError(f"chunks of document {doc_id} but no parsed document in {processed_dir}")
        chunked = ChunkedDocument(articles_by_doc.get(doc_id, []), chunks, [])
        chunks_of_doc, issues_by_doc[doc_id] = _enrich(docs[doc_id], chunked)
        enriched += chunks_of_doc
        corpus.append((docs[doc_id], chunked))

    links = amendment_links(corpus)
    enriched = [replace(c, amended_by=links.amended_by.get(c.id, [])) for c in enriched]
    for issue in links.issues:
        issues_by_doc[issue.doc_id].append(issue)
    issues = [issue for doc_issues in issues_by_doc.values() for issue in doc_issues]

    out_dir.mkdir(parents=True, exist_ok=True)
    _write_jsonl(out_dir / "chunks.jsonl", enriched)
    _write_jsonl(out_dir / "links.jsonl", links.links)
    _write_jsonl(out_dir / "issues.jsonl", issues)
    return enriched, issues
