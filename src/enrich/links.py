"""Amendment links (FR-CORE-005): read directives on the amending side, invert them onto chunks.

The rules are in `docs/reference/chunk-schema.md`, *Amendment links*. Approach approved on #5.
Interface only: the extraction is not built yet.
"""

from dataclasses import dataclass, field

from src.chunking.chunker import ChunkedDocument, Issue


@dataclass(frozen=True)
class Link:
    type: str  # amends | replaces | repeals
    source: str  # chunk id of the directive
    target_number: str
    target_doc: str | None
    target_article: str | None
    target_clause: str | None
    target_point: str | None
    target_part: str | None
    target_chunks: list[str]
    in_corpus: bool


@dataclass
class AmendmentLinks:
    links: list[Link] = field(default_factory=list)
    amended_by: dict[str, list[dict]] = field(default_factory=dict)  # target chunk id -> [{type, source}]
    issues: list[Issue] = field(default_factory=list)


def amendment_links(corpus: list[tuple[dict, ChunkedDocument]]) -> AmendmentLinks:
    """Every link in the corpus, each target chunk's inverse links, and unresolved directives."""
    return AmendmentLinks()
