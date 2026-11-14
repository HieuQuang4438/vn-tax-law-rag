"""Build the vector index and the keyword index over the enriched chunks (#6).

Format and rules: `docs/reference/index.md`.
"""

import gc
import hashlib
import json
import os
import shutil
import sys
import time
import unicodedata
from importlib.metadata import version
from pathlib import Path
from typing import Protocol

import bm25s
import chromadb
import numpy as np
from bm25s.tokenization import Tokenized
from chromadb.api.client import SharedSystemClient
from chromadb.config import Settings

from src.chunking.tokens import (
    EMBEDDING_MODEL,
    EMBEDDING_MODELS,
    EMBEDDING_REVISION,
    ModelNotCachedError,
    pinned_snapshot,
)
from src.index.tokenizers import get_tokenizer

EMBEDDING_INPUT_LIMIT = 8192  # bge-m3 maximum input, in tokens; the largest indexed text is 3,363
BM25_TOKENIZER = "syllable"
COLLECTION = "chunks"
EMBED_GROUP = 64  # texts per embedder call; the cache is saved after each, so a stopped build keeps them
CHROMA_BATCH = 1000
VERSIONED = ("bm25s", "chromadb", "sentence-transformers", "torch")


class Embedder(Protocol):
    model: str
    revision: str
    input_limit: int  # tokens; a longer text is cut when embedded (#11)

    def embed(self, texts: list[str]) -> list[list[float]]:
        """One unit-length vector per text, in order."""
        ...

    def count_tokens(self, text: str) -> int:
        """The model's token count of `text`, special tokens included, nothing cut (#11)."""
        ...


class _BgeM3:
    model = EMBEDDING_MODEL
    revision = EMBEDDING_REVISION

    def __init__(self, transformer):
        self._transformer = transformer
        self._done = 0

    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors = self._transformer.encode(texts, batch_size=4, normalize_embeddings=True, convert_to_numpy=True)
        self._done += len(texts)
        print(f"  embedded {self._done}", file=sys.stderr, flush=True)
        return vectors.tolist()


def load_embedder(cache_dir: Path | None = None, model: str = EMBEDDING_MODEL,
                  input_limit: int | None = None) -> Embedder:  # stub: model and input_limit ignored (#11)
    """bge-m3 at the pinned revision, from the local cache only (approved on #6).

    The snapshot folder is resolved with `local_files_only` and the model is loaded from that
    folder, so no Hub call is made. `HF_HUB_OFFLINE` alone is not enough: huggingface_hub reads it
    once, at import, and a process that imported it earlier still sends requests.
    """
    os.environ["HF_HUB_OFFLINE"] = "1"
    from sentence_transformers import SentenceTransformer

    folder = str(pinned_snapshot(cache_dir))
    transformer = SentenceTransformer(folder, device="cpu", local_files_only=True)
    transformer.max_seq_length = EMBEDDING_INPUT_LIMIT
    return _BgeM3(transformer)


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class _VectorCache:
    def __init__(self, folder: Path):
        self.folder = folder

    def load(self) -> dict[str, np.ndarray]:
        keys_path, vectors_path = self.folder / "keys.json", self.folder / "vectors.npy"
        if not (keys_path.is_file() and vectors_path.is_file()):
            return {}
        keys = json.loads(keys_path.read_text(encoding="utf-8"))
        return dict(zip(keys, np.load(vectors_path)))

    def save(self, vectors: dict[str, np.ndarray]) -> None:
        self.folder.mkdir(parents=True, exist_ok=True)
        keys = sorted(vectors)
        matrix = np.stack([vectors[k] for k in keys]) if keys else np.zeros((0, 0), dtype=np.float32)
        np.save(self.folder / "vectors.npy", matrix.astype(np.float32))
        (self.folder / "keys.json").write_text(json.dumps(keys), encoding="utf-8", newline="\n")


def _embed(texts: list[str], embedder: Embedder, cache: _VectorCache) -> tuple[list[np.ndarray], int]:
    """A vector per text, embedding only digests the cache lacks; the cache ends with exactly these texts."""
    keys = [_digest(t) for t in texts]
    vectors = cache.load()
    missing = list({k: t for k, t in zip(keys, texts) if k not in vectors}.items())  # first-appearance order
    for start in range(0, len(missing), EMBED_GROUP):
        group = missing[start:start + EMBED_GROUP]
        new = embedder.embed([text for _, text in group])
        vectors.update((key, np.asarray(v, dtype=np.float32)) for (key, _), v in zip(group, new))
        cache.save(vectors)
    current = {k: vectors[k] for k in keys}
    cache.save(current)
    return [current[k] for k in keys], len(missing)


def _remove(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)


def _release_chroma() -> None:
    """Close every Chroma client: an open one keeps its files locked on Windows, until collected."""
    SharedSystemClient.clear_system_cache()
    gc.collect()


def _write_chroma(path: Path, rows: list[dict], vectors: list[np.ndarray]) -> None:
    _release_chroma()
    _remove(path)
    client = chromadb.PersistentClient(path=str(path), settings=Settings(anonymized_telemetry=False))
    try:
        collection = client.create_collection(COLLECTION, configuration={"hnsw": {"space": "cosine"}})
        for start in range(0, len(rows), CHROMA_BATCH):
            batch = rows[start:start + CHROMA_BATCH]
            collection.add(
                ids=[row["id"] for row in batch],
                embeddings=np.stack(vectors[start:start + CHROMA_BATCH]),
                metadatas=[{"doc_id": row["doc_id"]} for row in batch],
            )
    finally:
        del client
        _release_chroma()


def _write_bm25(path: Path, rows: list[dict], texts: list[str], tokenize) -> None:
    tokens = [tokenize(t) for t in texts]
    # bm25s numbers its own vocabulary in set order, which changes with PYTHONHASHSEED
    vocab = {token: i for i, token in enumerate(sorted({t for doc in tokens for t in doc}))}
    retriever = bm25s.BM25()
    retriever.index(Tokenized(ids=[[vocab[t] for t in doc] for doc in tokens], vocab=vocab), show_progress=False)
    _remove(path)
    retriever.save(str(path), show_progress=False)
    (path / "ids.json").write_text(json.dumps([row["id"] for row in rows]), encoding="utf-8", newline="\n")


def build(enriched_dir: Path, index_dir: Path, embedder: Embedder, tokenizer: str = "syllable",
          cache_dir: Path | None = None) -> dict:
    """Write both indexes, the vector cache and the manifest; return the manifest.

    `tokenizer` names the BM25 tokenizer (#10); `cache_dir` holds the vector cache, by default
    `index_dir/embeddings`, so a variant index can share the main one's vectors.
    """
    tokenize = get_tokenizer(tokenizer)  # an unknown name stops here, before anything is written
    started = time.perf_counter()
    raw = (enriched_dir / "chunks.jsonl").read_bytes()
    params = enriched_dir / "params.json"
    chunking = json.loads(params.read_text(encoding="utf-8")) if params.is_file() else None
    rows = [json.loads(line) for line in raw.decode("utf-8").splitlines()]
    texts = [row["header"] + "\n" + row["text"] for row in rows]  # indexed text, specified on #3

    index_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = index_dir / "manifest.json"
    manifest_path.unlink(missing_ok=True)  # written last: no manifest means no complete index

    cache_root = cache_dir if cache_dir is not None else index_dir / "embeddings"
    cache = _VectorCache(cache_root / f"{embedder.model.replace('/', '--')}@{embedder.revision}")
    vectors, embedded = _embed(texts, embedder, cache)
    _write_chroma(index_dir / "chroma", rows, vectors)
    bm25_started = time.perf_counter()
    _write_bm25(index_dir / "bm25", rows, texts, tokenize)
    bm25_seconds = round(time.perf_counter() - bm25_started, 1)

    manifest = {
        "model": embedder.model,
        "revision": embedder.revision,
        "dimension": len(vectors[0]) if vectors else 0,
        "chunks_sha256": hashlib.sha256(raw).hexdigest(),
        "chunk_count": len(rows),
        "bm25_tokenizer": tokenizer,
        "bm25_seconds": bm25_seconds,
        "embedded": embedded,
        "seconds": round(time.perf_counter() - started, 1),
        "versions": {name: version(name) for name in VERSIONED + (() if tokenizer == "syllable" else (tokenizer,))},
        "chunking": chunking,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="\n")
    return manifest
