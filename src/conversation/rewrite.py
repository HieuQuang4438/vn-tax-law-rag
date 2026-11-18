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
DEFAULT_REWRITER = "concat"  # chosen on #19 by EVAL-005, choice 3A
PROMPT = Path(__file__).resolve().parent.parent / "prompts" / "rewrite.md"


class RewriteOutput(BaseModel):
    question: str


@dataclass(frozen=True)
class Rewrite:
    question: str  # what generation gets
    queries: tuple[str, ...]  # what retrieval gets, one or two
    call: Call | None = None
    latency_s: float = 0.0


def _validate(parsed: RewriteOutput) -> None:
    if not parsed.question.strip():
        raise ValueError("the rewritten question is empty")


class Rewriter:
    def __init__(self, name: str, llm=None):
        self.name, self.llm = name, llm
        self.prompt = PROMPT.read_text(encoding="utf-8") if name == "llm" else None

    def rewrite(self, question: str, earlier: Sequence[str] = ()) -> Rewrite:
        earlier = list(earlier)[-EARLIER:]
        if not earlier or self.name == "none":  # a first turn, or no rewrite (AC-014)
            return Rewrite(question, (question,))
        joined = " ".join([*earlier, question])
        if self.name == "concat":
            return Rewrite(joined, (joined,))
        if self.name == "fuse":
            return Rewrite(joined, (question, joined))
        numbered = "\n".join(f"{n}. {q}" for n, q in enumerate(earlier, start=1))
        user = f"Earlier questions:\n{numbered}\n\nFollow-up: {question}"
        call = self.llm.generate("rewrite", self.prompt, user, RewriteOutput, _validate)
        text = call.parsed.question.strip()
        return Rewrite(text, (text,), call, call.latency_s)


def rewriter(name: str, llm=None) -> Rewriter:
    """The rewriter of that name; `llm` none means `LLM()` for `llm`."""
    if name not in REWRITERS:
        raise ValueError(f"unknown rewriter {name!r}; one of {', '.join(REWRITERS)}")
    if name == "llm" and llm is None:
        from src.llm import LLM

        llm = LLM()
    return Rewriter(name, llm)
