"""Reference slots plus reciprocal rank fusion of keyword and vector results (#8, FR-CORE-008).

Format and rules: `docs/reference/retrieval.md`.
"""

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

import bm25s
import chromadb
import numpy as np
from chromadb.api.client import SharedSystemClient
from chromadb.config import Settings

from src.index import EMBEDDING_MODELS, TOKENIZERS, Embedder, get_tokenizer, load_embedder
from src.index.builder import COLLECTION
from src.retrieval.references import Reference, find_references

TOP_K = 8
RRF_K = 60  # starting values, changed only through a recorded experiment (#8)
CANDIDATES = 50  # read at call time: tests lower it


class IndexNotReadyError(RuntimeError):
    """The index is missing, older than the chunks, or built with another model."""


@dataclass(frozen=True)
class Hit:
    chunk_id: str
    found_by: tuple[str, ...]  # in order: reference, keyword, vector, document
    score: float


@dataclass(frozen=True)
class Unresolved:
    text: str
    reason: str  # unknown_document, ambiguous, kind_mismatch, no_article, no_document


@dataclass
class Retrieval:
    hits: list[Hit] = field(default_factory=list)
    unresolved: list[Unresolved] = field(default_factory=list)


@dataclass
class Rankings:
    """The orders `retrieve` cuts from, uncut (#24)."""

    keyword: list[str] = field(default_factory=list)  # every chunk scoring above 0, best first
    vector: list[str] = field(default_factory=list)  # every chunk, best first
    final: list[str] = field(default_factory=list)  # every reference slot, then the fused list
    unresolved: list[Unresolved] = field(default_factory=list)
    candidates: int = CANDIDATES  # how many of keyword and of vector were fused


@dataclass(frozen=True)
class Fusion:
    """How the lists are fused and cut (#25): the starting values, with one hit per article since #25."""

    rrf_k: int = RRF_K
    keyword_weight: float = 1.0
    vector_weight: float = 1.0
    per_article: bool = True  # adopted on #25
    candidates: int | None = None  # None: CANDIDATES, read when the retriever searches

    def __post_init__(self):
        if self.rrf_k < 1:
            raise ValueError(f"rrf_k must be at least 1, not {self.rrf_k}")
        for name in ("keyword_weight", "vector_weight"):
            if getattr(self, name) <= 0:
                raise ValueError(f"{name} must be above 0, not {getattr(self, name)}")
        if self.candidates is not None and self.candidates < 1:
            raise ValueError(f"candidates must be at least 1, not {self.candidates}")

    def candidate_count(self) -> int:
        """How many of each ranking are fused: `candidates`, or `CANDIDATES` as it is now."""
        return CANDIDATES if self.candidates is None else self.candidates

    def config(self) -> dict:
        """The setting as the results files record it."""
        return {"rrf_k": self.rrf_k, "candidates": self.candidate_count(), "keyword_weight": self.keyword_weight,
                "vector_weight": self.vector_weight, "per_article": self.per_article}


def rrf(lists: list[list[str]], constant: int = RRF_K, weights: list[float] | None = None) -> list[tuple[str, float]]:
    """Fused (chunk_id, score) pairs, best first; ties keep first appearance, read rank by rank.

    Each list adds its weight / (constant + rank); with no weights, every list weighs 1 (#25).
    """
    if weights is None:
        weights = [1.0] * len(lists)
    elif len(weights) != len(lists):
        raise ValueError(f"{len(weights)} weights for {len(lists)} lists")
    scores: dict[str, float] = {}
    for rank in range(max((len(ranked) for ranked in lists), default=0)):
        for ranked in lists:
            if rank < len(ranked):
                scores.setdefault(ranked[rank], 0.0)
    for ranked, weight in zip(lists, weights):
        for rank, chunk_id in enumerate(ranked, start=1):
            scores[chunk_id] += weight / (constant + rank)
    order = {chunk_id: i for i, chunk_id in enumerate(scores)}
    return sorted(scores.items(), key=lambda pair: (-pair[1], order[pair[0]]))


@dataclass(frozen=True)
class _Document:
    doc_id: str
    number: str
    kind: str


@dataclass(frozen=True)
class _Article:
    reference: Reference
    article_id: str
    chunk_id: str | None  # the clause chunk, or the unsplit article; None for a split article


def _not_ready(problem: str) -> IndexNotReadyError:
    return IndexNotReadyError(f"{problem}; build the index with: python -m src.index")


def _manifest_embedder(index_dir: Path) -> Embedder:
    """The model the index was built with, checked before it is loaded (#11)."""
    manifest_path = index_dir / "manifest.json"
    if not manifest_path.is_file():
        raise _not_ready(f"no {manifest_path}: the index is missing or its build did not finish")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    model = manifest.get("model")
    if model not in EMBEDDING_MODELS:
        raise _not_ready(f"the index was built with an unknown embedding model {model!r}")
    return load_embedder(model=model, input_limit=manifest.get("input_limit"))


class Retriever:
    def __init__(self, index_dir: Path, enriched_dir: Path, processed_dir: Path, embedder: Embedder,
                 fusion: Fusion | None = None):
        self.fusion = fusion or Fusion()
        manifest_path = index_dir / "manifest.json"
        if not manifest_path.is_file():
            raise _not_ready(f"no {manifest_path}: the index is missing or its build did not finish")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        raw = (enriched_dir / "chunks.jsonl").read_bytes()
        if manifest.get("chunks_sha256") != hashlib.sha256(raw).hexdigest():
            raise _not_ready(f"the index is older than {enriched_dir / 'chunks.jsonl'}")
        if (manifest.get("model"), manifest.get("revision")) != (embedder.model, embedder.revision):
            raise _not_ready(f"the index was built with {manifest.get('model')}@{manifest.get('revision')}, "
                             f"not {embedder.model}@{embedder.revision}")
        tokenizer = manifest.get("bm25_tokenizer")
        if tokenizer not in TOKENIZERS:
            raise _not_ready(f"the index was built with an unknown BM25 tokenizer {tokenizer!r}")
        try:
            self._tokenize = get_tokenizer(tokenizer)
        except ImportError as error:
            raise _not_ready(f"the {tokenizer} tokenizer is not installed ({error}); install "
                             "requirements-experiments.txt or rebuild with the syllable tokenizer") from error
        self._embedder = embedder

        rows = [json.loads(line) for line in raw.decode("utf-8").splitlines()]
        self._ids = [row["id"] for row in rows]
        self._row = {chunk_id: i for i, chunk_id in enumerate(self._ids)}
        self._doc_of = [row["doc_id"] for row in rows]
        self._parent = {row["id"]: row["parent_id"] for row in rows}
        self._article_chunks: dict[str, list[str]] = {}
        for row in rows:
            self._article_chunks.setdefault(row["parent_id"], []).append(row["id"])

        self._documents: dict[str, _Document] = {}  # casefolded so_hieu -> document
        for path in sorted(processed_dir.glob("*.json")):
            if path.name.startswith("_"):
                continue
            doc = json.loads(path.read_text(encoding="utf-8"))
            metadata = doc.get("metadata", {})
            match = re.search(r"-(\d+)-d1\.html", doc.get("source_url", ""))
            if match and metadata.get("so_hieu"):
                self._documents[metadata["so_hieu"].casefold()] = _Document(
                    match.group(1), metadata["so_hieu"], metadata.get("loai_van_ban", ""))

        self._bm25 = bm25s.BM25.load(str(index_dir / "bm25"), show_progress=False)
        bm25_ids = json.loads((index_dir / "bm25" / "ids.json").read_text(encoding="utf-8"))
        self._bm25_rows = np.array([self._row[chunk_id] for chunk_id in bm25_ids])
        self._vocab = self._bm25.vocab_dict
        self._vectors = self._read_vectors(index_dir / "chroma")

    def _read_vectors(self, path: Path) -> np.ndarray:
        """Every chunk's vector from the Chroma collection, in `chunks.jsonl` order.

        Cosine similarity is then computed exactly over all chunks: at 1,286 chunks this is under a
        millisecond, ties fall in file order, and the Chroma files are not held open.
        """
        client = chromadb.PersistentClient(path=str(path), settings=Settings(anonymized_telemetry=False))
        try:
            stored = client.get_collection(COLLECTION).get(include=["embeddings"])
        finally:
            del client
            SharedSystemClient.clear_system_cache()
        found = dict(zip(stored["ids"], stored["embeddings"]))
        missing = [chunk_id for chunk_id in self._ids if chunk_id not in found]
        if missing:
            raise _not_ready(f"{len(missing)} chunks have no vector, first {missing[0]}")
        return np.asarray([found[chunk_id] for chunk_id in self._ids], dtype=np.float32)

    @classmethod
    def load(cls, data_dir: Path = Path("data"), embedder: Embedder | None = None,
             index_dir: Path | None = None, enriched_dir: Path | None = None,
             fusion: Fusion | None = None) -> "Retriever":
        """Both indexes under `data_dir`, or in `index_dir` and `enriched_dir`; unless an embedder is given,
        the model and input limit the index's manifest names, from the local cache (#11); `fusion` as for the
        constructor (#25)."""
        index_dir = index_dir or data_dir / "index"
        return cls(index_dir, enriched_dir or data_dir / "enriched", data_dir / "processed",
                   embedder or _manifest_embedder(index_dir), fusion)

    # --- references

    def _resolve(self, reference: Reference) -> _Document | _Article | Unresolved:
        if reference.number is None:
            return Unresolved(reference.text, "no_document")
        key = reference.number.casefold()
        matches = [d for k, d in self._documents.items() if k == key or k.startswith(key + "/")]
        if not matches:
            return Unresolved(reference.text, "unknown_document")
        if reference.kind:
            of_kind = [d for d in matches if d.kind.casefold() == reference.kind.casefold()]
            if not of_kind:
                return Unresolved(reference.text, "kind_mismatch")
            matches = of_kind
        if len(matches) > 1:
            return Unresolved(reference.text, "ambiguous")
        [document] = matches
        if reference.article is None:
            return document
        article_id = f"{document.doc_id}:D{reference.article.lower()}"
        chunks = self._article_chunks.get(article_id)
        if not chunks:
            return Unresolved(reference.text, "no_article")
        if article_id in chunks:  # not split: the clause, if any, is inside the article chunk
            return _Article(reference, article_id, article_id)
        clause = f"{article_id}:K{reference.clause.lower()}" if reference.clause else None
        return _Article(reference, article_id, clause if clause in chunks else None)

    # --- ranked lists

    def _keyword_ranking(self, tokens: list[str]) -> list[int]:
        """Rows with a positive BM25 score, best first; equal scores in file order."""
        token_ids = [self._vocab[t] for t in tokens if t in self._vocab]
        if not token_ids:
            return []
        scores = np.zeros(len(self._ids), dtype=np.float64)
        scores[self._bm25_rows] = self._bm25.get_scores(token_ids)
        rows = np.flatnonzero(scores > 0)
        return [int(r) for r in rows[np.lexsort((rows, -scores[rows]))]]

    def _vector_ranking(self, question: str) -> list[int]:
        """Every row by cosine similarity to the question, best first; equal scores in file order."""
        [vector] = self._embedder.embed([question])
        similarity = self._vectors @ np.asarray(vector, dtype=np.float32)
        return [int(r) for r in np.argsort(-similarity, kind="stable")]

    def rankings(self, question: str) -> Rankings:
        """The orders `retrieve` cuts from, uncut: its hits are always the first k of `final` (#24)."""
        search = self._search(question)
        return Rankings(keyword=[self._ids[r] for r in search.keyword_rows],
                        vector=[self._ids[r] for r in search.vector_rows],
                        final=list(search.final), unresolved=list(search.unresolved), candidates=search.candidates)

    def retrieve(self, question: str, k: int = TOP_K) -> Retrieval:
        search = self._search(question)
        slots = set(search.slots)
        hits = []
        for chunk_id in search.final[:k]:
            ways = (("reference",) if chunk_id in slots else ()) + tuple(
                way for way in ("keyword", "vector", "document") if chunk_id in search.lists[way])
            hits.append(Hit(chunk_id, ways, search.score.get(chunk_id, 0.0)))
        return Retrieval(hits, search.unresolved)

    def fuse(self, questions: list[str], k: int = TOP_K) -> Retrieval:
        """Stub (#19): no hits."""
        return Retrieval()

    def _search(self, question: str) -> "_Search":
        """Everything `retrieve` and `rankings` read, before any cut at k."""
        articles: list[_Article] = []
        documents: list[_Document] = []
        unresolved: list[Unresolved] = []
        for reference in find_references(question):
            resolved = self._resolve(reference)
            if isinstance(resolved, Unresolved):
                unresolved.append(resolved)
            elif isinstance(resolved, _Article):
                articles.append(resolved)
            elif resolved not in documents:
                documents.append(resolved)

        tokens = self._tokenize(question) + [t for d in documents for t in self._tokenize(d.number)]
        keyword_rows = self._keyword_ranking(tokens)
        vector_rows = self._vector_ranking(question)
        fusion, candidates = self.fusion, self.fusion.candidate_count()
        keyword = [self._ids[r] for r in keyword_rows[:candidates]]
        vector = [self._ids[r] for r in vector_rows[:candidates]]
        lists, weights = [keyword, vector], [fusion.keyword_weight, fusion.vector_weight]
        named: list[str] = []
        if documents:
            doc_ids = {d.doc_id for d in documents}
            within = [[self._ids[r] for r in rows if self._doc_of[r] in doc_ids] for rows in (keyword_rows, vector_rows)]
            named = [chunk_id for chunk_id, _ in rrf(within, fusion.rrf_k)][:candidates]
            lists.append(named)
            weights.append(1.0)  # the document list always weighs 1 (#25)
        fused = rrf(lists, fusion.rrf_k, weights)

        # Every slot, in question order: a cut at k keeps the first k of them, as before #24.
        slots: list[str] = []
        for article in articles:
            chunk_id = article.chunk_id
            if chunk_id is None:
                own = set(self._article_chunks[article.article_id])
                chunk_id = next((c for c, _ in fused if c in own), self._article_chunks[article.article_id][0])
            if chunk_id not in slots:
                slots.append(chunk_id)
        final, taken = list(slots), set(slots)
        above = {self._parent[c] for c in slots}  # the articles with a chunk above, for per_article
        for chunk_id, _ in fused:
            if chunk_id in taken or (fusion.per_article and self._parent[chunk_id] in above):
                continue
            final.append(chunk_id)
            above.add(self._parent[chunk_id])
        return _Search(keyword_rows, vector_rows, slots, final, dict(fused), candidates,
                       {"keyword": set(keyword), "vector": set(vector), "document": set(named)}, unresolved)


@dataclass(frozen=True)
class _Search:
    keyword_rows: list[int]  # every row scoring above 0, best first
    vector_rows: list[int]  # every row, best first
    slots: list[str]  # every reference slot, in question order
    final: list[str]  # the slots, then the fused list
    score: dict[str, float]  # fused score per chunk
    candidates: int  # how many of each ranking were fused
    lists: dict[str, set[str]]  # the chunks of the keyword, vector and document lists
    unresolved: list[Unresolved]
