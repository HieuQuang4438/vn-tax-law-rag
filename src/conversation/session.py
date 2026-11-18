"""A session keeps one conversation (#19). Rules: `docs/reference/conversation.md`, *The session*."""

from dataclasses import dataclass, field
from typing import Any

from src.conversation import rewrite as rewrites
from src.conversation.rewrite import DEFAULT_REWRITER, Rewrite
from src.retrieval import TOP_K, Retrieval


@dataclass
class Turn:
    question: str  # as asked
    rewrite: Rewrite
    retrieval: Retrieval
    answer: Any  # a src.answer.Answer


def ask(retriever: Any, answerer: Any, question: str, earlier: tuple[str, ...] | list[str] = (),
        rewriter: Any = None, k: int = TOP_K) -> Turn:
    """One turn without a session (#30, choice 6A): `docs/reference/conversation.md`, *Without a session*."""
    if rewriter is None:
        rewriter = rewrites.rewriter(DEFAULT_REWRITER)
    rewrite = rewriter.rewrite(question, list(earlier))
    if len(rewrite.queries) == 1:
        retrieval = retriever.retrieve(rewrite.queries[0], k=k)
    else:
        retrieval = retriever.fuse(list(rewrite.queries), k=k)
    # Choice 2A on #19: generation sees the rewritten question and the passages, no earlier turn.
    return Turn(question, rewrite, retrieval, answerer.answer(rewrite.question, retrieval))


@dataclass
class Session:
    retriever: Any
    answerer: Any
    rewriter: Any = None  # none: rewriter(DEFAULT_REWRITER)
    k: int = TOP_K
    turns: list[Turn] = field(default_factory=list)

    def __post_init__(self):
        if self.rewriter is None:
            self.rewriter = rewrites.rewriter(DEFAULT_REWRITER)

    def ask(self, question: str) -> Turn:
        turn = ask(self.retriever, self.answerer, question, [turn.question for turn in self.turns], self.rewriter,
                   self.k)
        self.turns.append(turn)
        return turn
