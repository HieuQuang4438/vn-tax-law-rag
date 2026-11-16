"""Turn a retrieval result into the passages the model reads (FR-CORE-009, #14).

The rules are `docs/reference/context.md`. Interface stub: `assemble` returns an empty context.
"""

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from src.retrieval import Retrieval, Unresolved

BUDGET = 24_000  # bge-m3 tokens over Context.text, approved on #14


@dataclass(frozen=True)
class Passage:
    id: str
    kind: str  # article, amending
    doc_id: str
    article: str
    chunk_ids: tuple[str, ...]
    clauses: tuple[str, ...]
    text: str


@dataclass
class Context:
    passages: list[Passage] = field(default_factory=list)
    text: str = ""
    tokens: int = 0
    dropped: list[str] = field(default_factory=list)
    unresolved: list[Unresolved] = field(default_factory=list)


def _read_jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as lines:
        return [json.loads(line) for line in lines]


class Assembler:
    def __init__(self, chunks: list[dict], articles: list[dict], count_tokens: Callable[[str], int],
                 budget: int = BUDGET):
        self.count_tokens = count_tokens
        self.budget = budget

    @classmethod
    def load(cls, data_dir: Path = Path("data"), count_tokens: Callable[[str], int] | None = None,
             budget: int = BUDGET) -> "Assembler":
        if count_tokens is None:
            from src.chunking.tokens import bge_m3_token_counter

            count_tokens = bge_m3_token_counter()
        return cls(_read_jsonl(data_dir / "enriched" / "chunks.jsonl"),
                   _read_jsonl(data_dir / "chunks" / "articles.jsonl"), count_tokens, budget)

    def assemble(self, retrieval: Retrieval) -> Context:
        return Context()
