"""The LLM judge of an eval run: EVAL-002, EVAL-003, EVAL-006 and AC-015 (#15).

The rules are `docs/reference/answer.md`, *The judge*. Interface stub.
"""

from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel

from src.answer import Answer
from src.llm import LLM, Call

PROMPT = Path(__file__).resolve().parent.parent / "prompts" / "judge.md"


class SentenceVerdict(BaseModel):
    cited_supports: bool
    context_supports: bool


class JudgeOutput(BaseModel):
    sentences: list[SentenceVerdict]
    key_facts: list[bool]
    contradicts: bool
    says_amended: bool


@dataclass(frozen=True)
class Verdict:
    cited: tuple[bool | None, ...]
    supported: tuple[bool, ...]
    facts: tuple[bool, ...]
    contradicts: bool
    says_amended: bool | None
    correct: bool
    call: Call | None


class Judge:
    def __init__(self, llm: LLM):
        self.llm = llm

    def judge(self, question: str, key_facts: list[str], answer: Answer, amended: tuple[str, ...] = ()) -> Verdict:
        return Verdict((), (), (), False, None, False, None)
