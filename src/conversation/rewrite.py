"""Rewriters: a follow-up turn and its earlier questions become the queries retrieval gets (#19).

Rules: `docs/reference/conversation.md`, *Rewriters*.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel

from src.llm import Call

REWRITERS = ("none", "concat", "fuse", "llm")
EARLIER = 2  # how many earlier questions a rewriter reads, the last ones
PROMPT = Path(__file__).resolve().parent.parent / "prompts" / "rewrite.md"


class RewriteOutput(BaseModel):
    question: str


@dataclass(frozen=True)
class Rewrite:
    question: str  # what generation gets
    queries: tuple[str, ...]  # what retrieval gets, one or two
    call: Call | None = None
    latency_s: float = 0.0


class Rewriter:
    """Stub: every question as written."""

    def __init__(self, name: str, llm=None):
        self.name, self.llm = name, llm

    def rewrite(self, question: str, earlier: Sequence[str] = ()) -> Rewrite:
        return Rewrite(question, (question,))


def rewriter(name: str, llm=None) -> Rewriter:
    return Rewriter(name, llm)
