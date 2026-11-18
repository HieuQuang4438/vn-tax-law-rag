"""A session keeps one conversation (#19). Rules: `docs/reference/conversation.md`, *The session*."""

from dataclasses import dataclass, field
from typing import Any

from src.conversation.rewrite import Rewrite
from src.retrieval import TOP_K, Retrieval


@dataclass
class Turn:
    question: str  # as asked
    rewrite: Rewrite
    retrieval: Retrieval
    answer: Any  # a src.answer.Answer


@dataclass
class Session:
    retriever: Any
    answerer: Any
    rewriter: Any
    k: int = TOP_K
    turns: list[Turn] = field(default_factory=list)

    def ask(self, question: str) -> Turn:
        rewrite = self.rewriter.rewrite(question, [turn.question for turn in self.turns])
        if len(rewrite.queries) == 1:
            retrieval = self.retriever.retrieve(rewrite.queries[0], k=self.k)
        else:
            retrieval = self.retriever.fuse(list(rewrite.queries), k=self.k)
        # Choice 2A on #19: generation sees the rewritten question and the passages, no earlier turn.
        turn = Turn(question, rewrite, retrieval, self.answerer.answer(rewrite.question, retrieval))
        self.turns.append(turn)
        return turn
