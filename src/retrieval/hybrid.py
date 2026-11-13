"""Reference slots plus reciprocal rank fusion of keyword and vector results (#8, FR-CORE-008).

Format and rules: `docs/reference/retrieval.md`. Interface stub: not implemented yet.
"""

from dataclasses import dataclass, field
from pathlib import Path

from src.index import Embedder

TOP_K = 8
RRF_K = 60
CANDIDATES = 50


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


def rrf(lists: list[list[str]], constant: int = RRF_K) -> list[tuple[str, float]]:
    """Fused (chunk_id, score) pairs, best first."""
    return []


class Retriever:
    def __init__(self, index_dir: Path, enriched_dir: Path, processed_dir: Path, embedder: Embedder):
        pass

    @classmethod
    def load(cls, data_dir: Path = Path("data"), embedder: Embedder | None = None) -> "Retriever":
        return cls(data_dir / "index", data_dir / "enriched", data_dir / "processed", embedder)

    def retrieve(self, question: str, k: int = TOP_K) -> Retrieval:
        return Retrieval()
