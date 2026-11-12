"""Build the vector index and the keyword index over the enriched chunks (#6).

Format and rules: `docs/reference/index.md`.
"""

from pathlib import Path
from typing import Protocol

from src.chunking.tokens import EMBEDDING_MODEL

EMBEDDING_REVISION = "5617a9f61b028005a4858fdac845db406aefb181"  # pinned on #6
BM25_TOKENIZER = "syllable"


class Embedder(Protocol):
    model: str
    revision: str

    def embed(self, texts: list[str]) -> list[list[float]]:
        """One unit-length vector per text, in order."""
        ...


class ModelNotCachedError(RuntimeError):
    """The pinned model revision is not in the local Hugging Face cache."""


def tokenize(text: str) -> list[str]:
    """The `syllable` tokens of a chunk or a question."""
    return []


def load_embedder(cache_dir: Path | None = None) -> Embedder:
    """bge-m3 at the pinned revision, from the local cache only."""
    return None  # type: ignore[return-value]


def build(enriched_dir: Path, index_dir: Path, embedder: Embedder) -> dict:
    """Write both indexes, the vector cache and the manifest; return the manifest."""
    return {}
