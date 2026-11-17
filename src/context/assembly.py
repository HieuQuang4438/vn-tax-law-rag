"""Turn a retrieval result into the passages the model reads (FR-CORE-009, #14).

The rules are `docs/reference/context.md`: one passage per parent article, the amending source
chunks after the article they change, citation ids `[n]` and `[n.k]`, and a token budget filled
by the longest run of whole articles in rank order.
"""

import json
import re
from collections import Counter, defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from src.chunking.chunker import CLAUSE, _quote_depth
from src.retrieval import Retrieval, Unresolved

BUDGET = 24_000  # bge-m3 tokens over Context.text, approved on #14
CLAUSE_PART = re.compile(r" > Khoản [^>\]]*\]$")
LINK_WORDS = {"amends": "được sửa đổi, bổ sung bởi", "replaces": "được thay thế bởi", "repeals": "bị bãi bỏ bởi"}


@dataclass(frozen=True)
class Link:
    """One link line: the amended chunk's id, the link type, the source's id; ids without brackets."""
    target: str
    type: str  # amends, replaces, repeals
    source: str


@dataclass(frozen=True)
class Passage:
    id: str
    kind: str  # article, amending
    doc_id: str
    article: str
    chunk_ids: tuple[str, ...]
    clauses: tuple[str, ...]
    text: str
    links: tuple[Link, ...] = ()  # stub: not yet filled


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


def _marked(text: str, passage_id: str) -> tuple[list[str], tuple[str, ...]]:
    """The article's lines, each clause line prefixed `[n.k] `, and the clause ids in order.

    A clause line is one the chunker would start a clause at, the quotation depth counted from
    the article's first line; a repeated number gets `.2`, `.3`, ... as the chunker's ids do.
    """
    lines, clauses, seen = [], [], Counter()
    depth = 0
    for line in text.split("\n"):
        match = None if depth > 0 else CLAUSE.match(line)
        depth, _ = _quote_depth(line, depth)
        if match:
            number = match.group(1)
            seen[number] += 1
            clause = number if seen[number] == 1 else f"{number}.{seen[number]}"
            clauses.append(clause)
            line = f"[{passage_id}.{clause}] {line}"
        lines.append(line)
    return lines, tuple(clauses)


class Assembler:
    def __init__(self, chunks: list[dict], articles: list[dict], count_tokens: Callable[[str], int],
                 budget: int = BUDGET):
        self.chunks = {chunk["id"]: chunk for chunk in chunks}
        self.chunks_of: dict[str, list[dict]] = defaultdict(list)
        for chunk in chunks:
            self.chunks_of[chunk["parent_id"]].append(chunk)
        self.articles = {article["id"]: article for article in articles}
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
        ranked = list(dict.fromkeys(self.chunks[hit.chunk_id]["parent_id"] for hit in retrieval.hits))
        unresolved = list(retrieval.unresolved)
        if not ranked:
            return Context(unresolved=unresolved)
        # The longest run of articles, in rank order, whose text fits; the top article always stays.
        for kept in range(len(ranked), 0, -1):
            passages = self._passages(ranked[:kept])
            text = "\n\n".join(passage.text for passage in passages)
            tokens = self.count_tokens(text)
            if tokens <= self.budget or kept == 1:
                return Context(passages, text, tokens, ranked[kept:], unresolved)
        raise AssertionError("unreachable: the top article is always kept")

    def _passages(self, articles: list[str]) -> list[Passage]:
        in_context = set(articles)
        order: list[tuple[str, str]] = []  # (kind, article id or source chunk id)
        added: set[str] = set()
        for article_id in articles:
            order.append(("article", article_id))
            for chunk in self.chunks_of[article_id]:
                for link in chunk["amended_by"]:
                    source = link["source"]
                    if self.chunks[source]["parent_id"] in in_context or source in added:
                        continue
                    added.add(source)
                    order.append(("amending", source))
        ids = {key: str(number) for number, (_, key) in enumerate(order, 1)}

        def cite(chunk_id: str) -> str:
            chunk = self.chunks[chunk_id]
            if chunk["parent_id"] not in in_context:
                return f"[{ids[chunk_id]}]"
            passage_id = ids[chunk["parent_id"]]
            if chunk["clause"] in (None, "0"):
                return f"[{passage_id}]"
            return f"[{passage_id}.{chunk_id.split(':K', 1)[1]}]"

        passages = []
        for kind, key in order:
            if kind == "amending":
                source = self.chunks[key]
                passages.append(Passage(ids[key], kind, source["doc_id"], source["article"], (key,), (),
                                        f"[{ids[key]}] {source['header']}\n{source['text']}"))
                continue
            article, chunks = self.articles[key], self.chunks_of[key]
            header = CLAUSE_PART.sub("]", chunks[0]["header"])
            lines, clauses = _marked(article["text"], ids[key])
            links = [f"{cite(chunk['id'])} {LINK_WORDS[link['type']]} {cite(link['source'])}."
                     for chunk in chunks for link in chunk["amended_by"]]
            passages.append(Passage(ids[key], kind, article["doc_id"], article["article"],
                                    tuple(chunk["id"] for chunk in chunks), clauses,
                                    "\n".join([f"[{ids[key]}] {header}", *lines, *links])))
        return passages
