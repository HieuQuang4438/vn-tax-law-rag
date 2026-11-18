"""A session keeps one conversation (#19). Rules: `docs/reference/conversation.md`, *The session*."""

from dataclasses import dataclass, field
from typing import Any

from src.conversation.rewrite import Rewrite
from src.retrieval import TOP_K, Retrieval


@dataclass
class Turn:
    question: str
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
        """Stub: no rewrite, retrieval or answer, and the turn is not kept."""
        return Turn(question, Rewrite(question, (question,)), Retrieval(), None)
