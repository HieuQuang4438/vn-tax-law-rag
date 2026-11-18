"""Read every chunk's effective date from its document's own text — FR-CORE-004, approach on #4.

The rules are specified in `docs/reference/chunk-schema.md`, "Effective date".
"""

import re
from dataclasses import dataclass
from datetime import date

from src.chunking import Chunk, ChunkedDocument, Issue
from src.chunking.chunker import doc_id_of

KIND = r"(?:Luật|Nghị định|Thông tư)"
DATE = r"\d{1,2} tháng \d{1,2} năm \d{4}|\d{1,2}/\d{1,2}/\d{4}"
EFFECTIVENESS_TITLE = re.compile(r"hiệu lực thi hành|điều khoản thi hành", re.IGNORECASE)
DOCUMENT_DATE = re.compile(
    rf"{KIND} này có hiệu lực(?: thi hành)? (?:kể )?từ ngày (?P<date>ký ban hành|được thông qua|{DATE})"
)
EXCEPTION = re.compile(rf"có hiệu lực(?: thi hành)? (?:kể )?từ ngày (?P<date>{DATE})")
REFERENCE = re.compile(
    r"(?:(?:điểm (?P<point>[\w.]+) )?khoản (?P<clause>\d+) )?Điều (?P<article>\d+)"
    r"|các điều (?P<list>\d+(?:, \d+)* và \d+)"
)
THIS_DOCUMENT = re.compile(rf"\s+(?:của\s+)?{KIND}\s+này\b")
OTHER_DOCUMENT = re.compile(r"\s+(?:của\s+)?(?:Bộ luật|Luật|Nghị định|Thông tư|Nghị quyết|Quyết định)\b")
WHOLE = re.compile(rf"^(?:\d+\.\s+)?(?:(?:Các |các )?[Qq]uy định tại\s+)?@(?P<ref>\d+)(?:\s+(?:của\s+)?{KIND}\s+này)?$")
APPLICATION = re.compile(r"áp dụng (?:kể )?từ (?:kỳ tính thuế|ngày)")
UNTIL = re.compile(r"đến hết ngày")


@dataclass(frozen=True)
class EffectiveDates:
    by_chunk: dict[str, str | None]
    issues: list[Issue]


@dataclass(frozen=True)
class _Reference:
    article: str
    clause: str | None
    point: str | None
    text: str


def _iso(text: str) -> str:
    numbers = [int(n) for n in re.findall(r"\d+", text)]
    day, month, year = numbers
    return date(year, month, day).isoformat()


def _document_date(match: re.Match, doc: dict) -> str | None:
    found = match.group("date")
    if found in ("ký ban hành", "được thông qua"):
        issued = (doc.get("metadata", {}).get("ngay_ban_hanh") or "").strip()
        return _iso(issued) if re.fullmatch(r"\d{1,2}/\d{1,2}/\d{4}", issued) else None
    return _iso(found)


def _references(subject: str) -> list[list[tuple[_Reference, bool]]] | None:
    """The subject's references to this document, each with whether it is whole; None if none.

    The subject is cut into conjuncts at `và`; a conjunct that is only `[Quy định tại] <reference>
    [của <kind> này]` names the provision itself (whole), anything else names a subject inside it.


    A line is about this document when one of its references is followed by `[của] <kind> này`;
    a bare reference beside it counts too, one followed by another document's name does not.
    """
    refs: list[list[_Reference]] = []  # one entry per reference; a list reference holds several
    marked = ""
    position = 0
    anchored = False
    for match in REFERENCE.finditer(subject):
        rest = subject[match.end():]
        if OTHER_DOCUMENT.match(rest) and not THIS_DOCUMENT.match(rest):
            continue
        anchored = anchored or bool(THIS_DOCUMENT.match(rest))
        marked += subject[position:match.start()] + f"@{len(refs)}"
        position = match.end()
        if match.group("list"):
            numbers = re.findall(r"\d+", match.group("list"))
            refs.append([_Reference(n, None, None, match.group(0)) for n in numbers])
        else:
            refs.append([_Reference(match.group("article"), match.group("clause"), match.group("point"),
                                    match.group(0))])
    if not refs or not anchored:
        return None
    marked += subject[position:]
    groups = []
    for conjunct in re.split(r"\s+và\s+|;\s*", marked.strip()):
        indexes = [int(i) for i in re.findall(r"@(\d+)", conjunct)]
        if not indexes:
            continue
        whole = WHOLE.match(conjunct.strip()) is not None
        groups.append([(ref, whole) for i in indexes for ref in refs[i]])
    return groups


def effective_dates(doc: dict, chunked: ChunkedDocument) -> EffectiveDates:
    doc_id = doc_id_of(doc)
    chunks = chunked.chunks
    issues: list[Issue] = []
    article = next((a for a in reversed(chunked.articles) if EFFECTIVENESS_TITLE.search(a.title)), None)
    if article is None:
        issues.append(Issue(doc_id, "no_effective_date", "",
                            "no article titled hiệu lực thi hành or điều khoản thi hành"))
        return EffectiveDates({c.id: None for c in chunks}, issues)

    lines = article.text.split("\n")
    default, default_line = None, None
    for i, line in enumerate(lines):
        if match := DOCUMENT_DATE.search(line):
            default, default_line = _document_date(match, doc), i
            break
    if default is None:
        issues.append(Issue(doc_id, "no_effective_date", article.article,
                            f"no readable date in Điều {article.article}: {article.text[:120]}"))

    by_chunk: dict[str, str | None] = {c.id: default for c in chunks}
    for i, line in enumerate(lines):
        if default is not None and i != default_line and (match := EXCEPTION.search(line)):
            groups = _references(line[:match.start()])
            for group in groups or []:
                for ref, whole in group:
                    _apply(ref, whole, _iso(match.group("date")), line, chunks, by_chunk, doc_id, issues)
        if APPLICATION.search(line):
            issues.append(Issue(doc_id, "application_period", article.article, line[:200]))
        if UNTIL.search(line):
            issues.append(Issue(doc_id, "effective_until", article.article, line[:200]))
    return EffectiveDates(by_chunk, issues)


def _apply(ref: _Reference, whole: bool, when: str, line: str, chunks: list[Chunk],
           by_chunk: dict[str, str | None], doc_id: str, issues: list[Issue]) -> None:
    in_article = [c for c in chunks if c.article == ref.article]
    if ref.clause is None:
        targets = in_article
    else:
        targets = [c for c in in_article if c.clause == ref.clause]  # empty when the article is one chunk
    if whole and ref.point is None and targets:
        for chunk in targets:
            by_chunk[chunk.id] = when
        return
    issues.append(Issue(doc_id, "partial_effective_date", ref.article, f"{ref.text}: {line[:200]}"))

