"""Find explicit document and article references in a question (#8, FR-CORE-007).

Forms and rules: `docs/reference/retrieval.md`, *References*. Interface stub: not implemented yet.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Reference:
    text: str  # the span of the question it covers
    kind: str | None  # "Luật", "Nghị định", "Thông tư", or None
    number: str | None  # as written; the law's so_hieu for a base-law name
    article: str | None
    clause: str | None


def find_references(question: str) -> list[Reference]:
    """The references in the question, in order, before any corpus lookup."""
    return []
