"""Load the hand-written eval set, with each provision resolved to its article (#7).

Format and rules: `docs/reference/eval-set.md`.
"""

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

TAX_TYPES = ("administration", "vat", "pit", "cit", "sct", "household")
FORMS = ("plain", "reference")
UNANSWERABLE = ("out_of_scope", "repealed")


class EvalSetError(ValueError):
    """The set has errors; `errors` holds the checker's messages."""

    def __init__(self, errors: list[str]):
        super().__init__("\n".join(errors))
        self.errors = errors


@dataclass(frozen=True)
class Provision:
    text: str  # as written in the set
    article: str  # article id, as in articles.jsonl: `379409:D5`
    chunk: str  # the clause chunk in a split article, else the article chunk


@dataclass
class Item:
    id: str
    line: int
    question: str
    tax_type: str
    form: str
    answer: str
    key_facts: list[str] = field(default_factory=list)
    provisions: list[Provision] = field(default_factory=list)
    unanswerable: str | None = None


@dataclass
class Conversation:
    id: str
    line: int
    turns: list[Item] = field(default_factory=list)


@dataclass
class EvalSet:
    version: int
    as_of: date | None
    sha256: str
    questions: list[Item] = field(default_factory=list)
    conversations: list[Conversation] = field(default_factory=list)


def load_eval_set(path: Path, processed_dir: Path, enriched_dir: Path) -> EvalSet:
    """The set with every provision resolved; raises `EvalSetError` if the checker finds errors."""
    return EvalSet(version=0, as_of=None, sha256="")
