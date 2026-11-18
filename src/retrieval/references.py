"""Find explicit document and article references in a question (#8, FR-CORE-007).

Forms and rules: `docs/reference/retrieval.md`, *References*.
"""

import re
import unicodedata
from dataclasses import dataclass


@dataclass(frozen=True)
class Reference:
    text: str  # the span of the question it covers
    kind: str | None  # "Luật", "Nghị định", "Thông tư", or None
    number: str | None  # as written; the law's so_hieu for a base-law name
    article: str | None
    clause: str | None


KINDS = {"luật": "Luật", "nghị định": "Nghị định", "nđ": "Nghị định", "thông tư": "Thông tư", "tt": "Thông tư"}

BASE_LAWS = (  # name after "Luật" (and an optional "Thuế"), the law's so_hieu; fixed on #8
    (r"giá\s+trị\s+gia\s+tăng|gtgt", "48/2024/QH15"),
    (r"thu\s+nhập\s+cá\s+nhân|tncn", "109/2025/QH15"),
    (r"thu\s+nhập\s+doanh\s+nghiệp|tndn", "67/2025/QH15"),
    (r"tiêu\s+thụ\s+đặc\s+biệt|ttđb", "66/2025/QH15"),
    (r"quản\s+lý\s+thuế", "108/2025/QH15"),
)

_PARTIAL = r"\d{1,4}/\d{4}"
_SUFFIX = r"/[^\W\d_][\w-]*"  # /QH15, /NĐ-CP, /TT-BTC: starts with a letter
_NUMBER = rf"(?<![\w/]){_PARTIAL}(?:{_SUFFIX})?(?![\w/])"
_FULL = rf"(?<![\w/]){_PARTIAL}{_SUFFIX}(?![\w/])"
_NAMES = "|".join(f"(?P<law{i}>{pattern})" for i, (pattern, _) in enumerate(BASE_LAWS))

DOCUMENT = re.compile(
    rf"(?<!\w)luật\s+(?:thuế\s+)?(?:{_NAMES})(?!\w)(?:\s+số\s+(?P<named>{_NUMBER}))?"
    rf"|(?<!\w)(?P<kind>luật|nghị\s+định|nđ|thông\s+tư|tt)\s+(?:số\s+)?(?P<number>{_NUMBER})"
    rf"|(?P<full>{_FULL})",
    re.IGNORECASE,
)
_N = r"\d+[a-zđ]?(?!\w)"
ARTICLE = re.compile(
    rf"(?<!\w)(?:điểm\s+[a-zđ]\s*,?\s+)?(?:khoản\s+(?P<before>{_N})\s*,?\s+)?điều\s+(?P<article>{_N})"
    rf"(?:\s*,?\s+khoản\s+(?P<after>{_N}))?",
    re.IGNORECASE,
)
AFTER = re.compile(r"\s*,?\s*(?:(?:của|tại|thuộc)\s+)?", re.IGNORECASE)  # article, then document
BEFORE = re.compile(r"\s*,?\s*")  # document, then article


@dataclass(frozen=True)
class _Document:
    start: int
    end: int
    kind: str | None
    number: str


def _documents(text: str) -> list[_Document]:
    found = []
    for match in DOCUMENT.finditer(text):
        if match["full"]:
            found.append(_Document(match.start(), match.end(), None, match["full"]))
        elif match["kind"]:
            kind = KINDS[" ".join(match["kind"].lower().split())]
            found.append(_Document(match.start(), match.end(), kind, match["number"]))
        else:
            law = next(number for i, (_, number) in enumerate(BASE_LAWS) if match[f"law{i}"])
            found.append(_Document(match.start(), match.end(), "Luật", match["named"] or law))
    return found


def find_references(question: str) -> list[Reference]:
    """The references in the question, in order, before any corpus lookup."""
    text = unicodedata.normalize("NFC", question)
    documents = _documents(text)
    distinct = {d.number.casefold() for d in documents}
    bound: set[_Document] = set()
    found: list[tuple[int, Reference]] = []
    for match in ARTICLE.finditer(text):
        if any(d.start < match.end() and match.start() < d.end for d in documents):
            continue
        clause = match["before"] or match["after"]
        after = next((d for d in documents if d.start >= match.end()
                      and AFTER.fullmatch(text, match.end(), d.start)), None)
        before = next((d for d in reversed(documents) if d.end <= match.start()
                       and BEFORE.fullmatch(text, d.end, match.start())), None)
        if after:
            document, span = after, (match.start(), after.end)
        elif before:
            document, span = before, (before.start, match.end())
        elif len(distinct) == 1:
            document, span = documents[0], (match.start(), match.end())
        else:
            found.append((match.start(), Reference(match[0], None, None, match["article"], clause)))
            continue
        bound.add(document)
        found.append((span[0], Reference(text[span[0]:span[1]], document.kind, document.number,
                                         match["article"], clause)))
    for d in documents:
        if d not in bound:
            found.append((d.start, Reference(text[d.start:d.end], d.kind, d.number, None, None)))
    return [reference for _, reference in sorted(found, key=lambda pair: pair[0])]
