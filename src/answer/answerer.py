"""Ask the model for a cited answer and resolve its citations (FR-CORE-010, FR-CORE-011, #15).

The rules are `docs/reference/answer.md`, *The answer*. Interface stub: `answer` returns an empty
answer.
"""

from dataclasses import dataclass, field
from pathlib import Path

from pydantic import BaseModel

from src.context import Assembler, Context
from src.llm import LLM, Call
from src.retrieval import Retrieval

NOT_FOUND = "Không tìm thấy quy định trả lời câu hỏi này trong các văn bản hiện có."
PROMPT = Path(__file__).resolve().parent.parent / "prompts" / "answer.md"


class SentenceOutput(BaseModel):
    text: str
    citations: list[str]


class AnswerOutput(BaseModel):
    sentences: list[SentenceOutput]


@dataclass(frozen=True)
class Document:
    label: str  # <loai_van_ban> <so_hieu>
    url: str


@dataclass(frozen=True)
class Sentence:
    text: str
    citations: tuple[str, ...]


@dataclass(frozen=True)
class Citation:
    id: str
    in_context: bool
    passage: str | None = None
    document: str | None = None
    article: str | None = None
    clause: str | None = None
    url: str | None = None


@dataclass
class Answer:
    sentences: list[Sentence] = field(default_factory=list)
    citations: list[Citation] = field(default_factory=list)
    flagged: list[str] = field(default_factory=list)
    not_found: bool = False
    text: str = ""
    context: Context = field(default_factory=Context)
    call: Call | None = None
    latency_s: dict[str, float] = field(default_factory=dict)


class Answerer:
    def __init__(self, assembler: Assembler, llm: LLM, documents: dict[str, Document]):
        self.assembler, self.llm, self.documents = assembler, llm, documents

    @classmethod
    def load(cls, data_dir: Path = Path("data"), llm: LLM | None = None) -> "Answerer":
        return cls(Assembler.load(data_dir), llm or LLM(), {})

    def answer(self, question: str, retrieval: Retrieval) -> Answer:
        return Answer()
