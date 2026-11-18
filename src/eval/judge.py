"""The LLM judge of an eval run: EVAL-002, EVAL-003, EVAL-006 and AC-015 (#15).

The rules are `docs/reference/answer.md`, *The judge*: one call per answer, the answer's own
sentences as the claims, with the same model as the answers (choices 2A, 3A, 4A, 6A of #15).
"""

from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel

from src.answer import Answer
from src.answer.answerer import markers
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
        self.prompt = PROMPT.read_text(encoding="utf-8")

    def judge(self, question: str, key_facts: list[str], answer: Answer, amended: tuple[str, ...] = ()) -> Verdict:
        sentences = "\n".join(f"{n}. {s.text}" + (f" {markers(s.citations)}" if s.citations else "")
                              for n, s in enumerate(answer.sentences, 1))
        facts = "\n".join(f"{n}. {fact}" for n, fact in enumerate(key_facts, 1))
        user = (f"Passages:\n\n{answer.context.text}\n\nQuestion: {question}\n\n"
                f"Answer sentences:\n{sentences}\n\nKey facts:\n{facts}")
        if amended:
            user += "\n\nAmended provisions: " + ", ".join(f"[{i}]" for i in amended)

        def validate(reply: JudgeOutput) -> None:
            if len(reply.sentences) != len(answer.sentences):
                raise ValueError(f"{len(reply.sentences)} sentence verdicts for {len(answer.sentences)} sentences")
            if len(reply.key_facts) != len(key_facts):
                raise ValueError(f"{len(reply.key_facts)} key fact verdicts for {len(key_facts)} key facts")

        call = self.llm.generate("judge", self.prompt, user, JudgeOutput, validate=validate)
        reply: JudgeOutput = call.parsed
        flagged = set(answer.flagged)
        cited = tuple(None if not s.citations else (False if set(s.citations) <= flagged else v.cited_supports)
                      for s, v in zip(answer.sentences, reply.sentences))
        facts_stated = tuple(reply.key_facts)
        return Verdict(cited, tuple(v.context_supports for v in reply.sentences), facts_stated, reply.contradicts,
                       reply.says_amended if amended else None, all(facts_stated) and not reply.contradicts, call)
