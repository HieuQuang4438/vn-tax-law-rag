"""Cut a parsed document into article and clause chunks — FR-CORE-002, ADR-0001, approach on #2."""

import json
import re
from collections.abc import Callable, Iterator
from dataclasses import asdict, dataclass, field
from pathlib import Path

MAX_TOKENS = 800  # ADR-0001 starting value; tuned by #12
MIN_INTRO_TOKENS = 100  # text before clause 1 longer than this becomes its own chunk

DOC_ID = re.compile(r"-(\d+)-d1\.html$")
ARTICLE = re.compile(r"^Điều\s+(\d+)\s*\.\s*(.*)$")
CLAUSE = re.compile(r"^(\d+)\.\s")
CHAPTER = re.compile(r"^(?:Chương|CHƯƠNG)\s+([IVXLCDM]+)\s*$")
SECTION = re.compile(r"^(?:Mục|MỤC)\s+\d+\s*$")
# Where article text ends: the signature block, a law's adoption statement, or the appendix.
END = re.compile(
    r"^(?:Nơi nhận\s*:"
    r"|_{5,}\s*$"
    r"|Luật này được Quốc hội"
    r"|(?:PHỤ LỤC|Phụ lục)(?:\s+[IVXLCDMl\d]+)?\s*$"
    r"|Mẫu số\s*:?\s*\S+\s*(?:\((?:Ban hành )?[Kk]èm theo|$))"
)
# Titles that end a legal document: effect, implementation, transition.
CLOSING_TITLE = re.compile(r"hiệu lực|thi hành|chuyển tiếp|tổ chức thực hiện", re.IGNORECASE)
OPEN_QUOTE, CLOSE_QUOTE, STRAIGHT_QUOTE = "“", "”", "\""


@dataclass(frozen=True)
class Article:
    id: str
    doc_id: str
    chapter: str | None
    chapter_title: str | None
    article: str
    title: str
    text: str


@dataclass(frozen=True)
class Chunk:
    id: str
    doc_id: str
    chapter: str | None
    chapter_title: str | None
    article: str
    clause: str | None
    parent_id: str
    text: str


@dataclass(frozen=True)
class Issue:
    doc_id: str
    kind: str  # duplicate_heading | article_gap | clause_numbering | unbalanced_quotes | mismatched_quotes
    # | hidden_heading | unexpected_last_article | missing_chapter_title
    article: str
    detail: str


@dataclass(frozen=True)
class ChunkedDocument:
    articles: list[Article]
    chunks: list[Chunk]
    issues: list[Issue]


@dataclass
class _Line:
    text: str
    quoted: bool  # starts inside a quotation, so it cannot open an article or a clause


@dataclass
class _Draft:
    number: str
    title: str
    chapter: str | None
    chapter_title: str | None
    lines: list[_Line] = field(default_factory=list)

    @property
    def text(self) -> str:
        return "\n".join(line.text for line in self.lines)


def doc_id_of(doc: dict) -> str:
    match = DOC_ID.search(doc.get("source_url", ""))
    if not match:
        raise ValueError(f"no document id in source_url: {doc.get('source_url')!r}")
    return match.group(1)


def _lines(doc: dict) -> Iterator[str]:
    for block in doc["blocks"]:
        for line in block["text"].split("\n"):
            if line.strip():
                yield line.strip()


def _is_title(line: str) -> bool:
    return line == line.upper() and not (CHAPTER.match(line) or SECTION.match(line) or ARTICLE.match(line))


def _quote_depth(line: str, depth: int) -> tuple[int, bool]:
    """Quotation depth after the line, and whether a straight " closed a “ opened on it.

    A straight " closes only a “ from the same line, so straight quotes inside multi-line
    amending text cannot end it. Approved on #2.
    """
    opened_here = 0
    mismatched = False
    for char in line:
        if char == OPEN_QUOTE:
            depth, opened_here = depth + 1, opened_here + 1
        elif char == CLOSE_QUOTE:
            depth, opened_here = depth - 1, max(0, opened_here - 1)
        elif char == STRAIGHT_QUOTE and opened_here:
            depth, opened_here, mismatched = depth - 1, opened_here - 1, True
    return depth, mismatched


def _drafts(doc: dict, doc_id: str, issues: list[Issue]) -> list[_Draft]:
    """Walk the text once, tracking chapter and quotation depth, and collect article bodies."""
    drafts: list[_Draft] = []
    chapter: str | None = None
    chapter_title: str | None = None
    depth = 0
    opened_in = ""  # article where the open quotation started
    title_of = ""  # "chapter" or "section": the heading whose title line may come next
    untitled = False  # the current chapter has no title line; reported at its first article
    for line in _lines(doc):
        if drafts and END.match(line):
            break
        quoted = depth > 0
        is_heading = False
        if not quoted:
            if title_of:
                pending, title_of = title_of, ""
                if _is_title(line):
                    if pending == "chapter":
                        chapter_title = line
                    continue
                if pending == "chapter":
                    untitled = True
            if match := CHAPTER.match(line):
                if untitled:
                    issues.append(Issue(doc_id, "missing_chapter_title", "",
                                        f"no all-caps title line after {chapter} heading, which has no article"))
                chapter, chapter_title, title_of, untitled = f"Chương {match.group(1)}", None, "chapter", False
                continue
            if SECTION.match(line):
                title_of = "section"
                continue
            if match := ARTICLE.match(line):
                drafts.append(_Draft(match.group(1), match.group(2).strip(), chapter, chapter_title))
                is_heading = True
                if untitled:
                    issues.append(Issue(doc_id, "missing_chapter_title", match.group(1),
                                        f"no all-caps title line after {chapter} heading"))
                    untitled = False
        if drafts:
            if not is_heading:  # chunk text leaves the heading out; it lives in Article.title
                drafts[-1].lines.append(_Line(line, quoted))
            opened, mismatched = _quote_depth(line, depth)
            if mismatched:
                issues.append(Issue(doc_id, "mismatched_quotes", drafts[-1].number,
                                    f'“ closed with a straight " on its line: {line[:80]}'))
            if depth == 0 and opened > 0 and not line.startswith(OPEN_QUOTE):
                # Quoted text that runs on opens at a line start; a mid-line quote left open is a
                # source error and must not hide the rest of the article. Approved on #2.
                issues.append(Issue(doc_id, "unbalanced_quotes", drafts[-1].number,
                                    "quotation opened mid-line and not closed on its line"))
                opened = 0
            if depth == 0 and opened > 0:
                opened_in = drafts[-1].number
            depth = max(0, opened)
    if untitled or title_of == "chapter":
        issues.append(Issue(doc_id, "missing_chapter_title", "",
                            f"no all-caps title line after {chapter} heading, which has no article"))
    if depth > 0:
        issues.append(Issue(doc_id, "unbalanced_quotes", opened_in, f"{depth} quotation(s) never closed"))
    return drafts


def _merge_duplicates(drafts: list[_Draft], doc_id: str, issues: list[Issue]) -> list[_Draft]:
    """A heading repeated in a row is one article written twice; keep the fuller copy."""
    kept: list[_Draft] = []
    for draft in drafts:
        if kept and kept[-1].number == draft.number:
            issues.append(Issue(doc_id, "duplicate_heading", draft.number, "heading repeated in a row; kept the longer"))
            if len(draft.text) > len(kept[-1].text):
                kept[-1] = draft
            continue
        kept.append(draft)
    return kept


def _check_numbering(drafts: list[_Draft], doc_id: str, issues: list[Issue]) -> None:
    expected = 1
    for draft in drafts:
        number = int(draft.number)
        if number != expected:
            issues.append(Issue(doc_id, "article_gap", draft.number, f"expected Điều {expected}"))
        expected = number + 1


def _check_end(drafts: list[_Draft], doc_id: str, issues: list[Issue]) -> None:
    """Catch articles lost at the end of the text, which `_check_numbering` cannot see.

    Both checks approved on #2, after an open quotation hid 16 of 25 articles in 439780.
    """
    if not drafts:
        return
    last = drafts[-1]
    for draft in drafts:
        for line in draft.lines:
            match = ARTICLE.match(line.text) if line.quoted else None
            if match and int(match.group(1)) > int(last.number):
                issues.append(Issue(doc_id, "hidden_heading", match.group(1),
                                    f"read as quoted inside Điều {draft.number}: {line.text[:80]}"))
    if not CLOSING_TITLE.search(last.title):
        issues.append(Issue(doc_id, "unexpected_last_article", last.number,
                            f"last article does not close the document: {last.title[:80]}"))


def _clauses(draft: _Draft) -> tuple[list[str], list[tuple[str, list[str]]]]:
    """Split an article body into its intro lines and (clause number, lines) groups."""
    intro: list[str] = []
    clauses: list[tuple[str, list[str]]] = []
    for line in draft.lines:
        match = None if line.quoted else CLAUSE.match(line.text)
        if match:
            clauses.append((match.group(1), [line.text]))
        elif clauses:
            clauses[-1][1].append(line.text)
        else:
            intro.append(line.text)
    return intro, clauses


def _split(
    draft: _Draft,
    article: Article,
    count_tokens: Callable[[str], int],
    min_intro_tokens: int,
    issues: list[Issue],
) -> list[Chunk]:
    intro, clauses = _clauses(draft)
    if not clauses:
        return [_chunk(article, None, article.id, article.text)]

    numbers = [number for number, _ in clauses]
    if numbers != [str(n) for n in range(1, len(numbers) + 1)]:
        issues.append(Issue(article.doc_id, "clause_numbering", article.article, f"clauses {', '.join(numbers)}"))

    chunks: list[Chunk] = []
    intro_text = "\n".join(intro)
    if intro_text and count_tokens(intro_text) > min_intro_tokens:
        chunks.append(_chunk(article, "0", f"{article.id}:K0", intro_text))
    seen: set[str] = set()
    for number, lines in clauses:
        chunk_id = f"{article.id}:K{number}"
        suffix = 2
        while chunk_id in seen:  # repeated clause number: keep ids unique, already reported above
            chunk_id, suffix = f"{article.id}:K{number}.{suffix}", suffix + 1
        seen.add(chunk_id)
        chunks.append(_chunk(article, number, chunk_id, "\n".join(lines)))
    return chunks


def _chunk(article: Article, clause: str | None, chunk_id: str, text: str) -> Chunk:
    return Chunk(chunk_id, article.doc_id, article.chapter, article.chapter_title, article.article, clause,
                 article.id, text)


def chunk_document(
    doc: dict,
    count_tokens: Callable[[str], int],
    max_tokens: int = MAX_TOKENS,
    min_intro_tokens: int = MIN_INTRO_TOKENS,
) -> ChunkedDocument:
    doc_id = doc_id_of(doc)
    issues: list[Issue] = []
    drafts = _merge_duplicates(_drafts(doc, doc_id, issues), doc_id, issues)
    _check_numbering(drafts, doc_id, issues)
    _check_end(drafts, doc_id, issues)

    articles: list[Article] = []
    chunks: list[Chunk] = []
    for draft in drafts:
        article = Article(f"{doc_id}:D{draft.number}", doc_id, draft.chapter, draft.chapter_title, draft.number,
                          draft.title, draft.text)
        articles.append(article)
        if count_tokens(article.text) <= max_tokens:
            chunks.append(_chunk(article, None, article.id, article.text))
        else:
            chunks.extend(_split(draft, article, count_tokens, min_intro_tokens, issues))
    return ChunkedDocument(articles, chunks, issues)


def _write_jsonl(path: Path, records: list) -> None:
    lines = [json.dumps(asdict(record), ensure_ascii=False) + "\n" for record in records]
    path.write_text("".join(lines), encoding="utf-8", newline="\n")


def build(
    processed_dir: Path,
    out_dir: Path,
    count_tokens: Callable[[str], int],
    max_tokens: int = MAX_TOKENS,
) -> list[Issue]:
    """Chunk every parsed document; write chunks, articles and issues as JSONL, ordered by doc id."""
    docs = [json.loads(path.read_text(encoding="utf-8")) for path in processed_dir.glob("*.json")
            if not path.name.startswith("_")]
    docs.sort(key=lambda doc: int(doc_id_of(doc)))

    articles: list[Article] = []
    chunks: list[Chunk] = []
    issues: list[Issue] = []
    for doc in docs:
        result = chunk_document(doc, count_tokens, max_tokens)
        articles += result.articles
        chunks += result.chunks
        issues += result.issues

    out_dir.mkdir(parents=True, exist_ok=True)
    _write_jsonl(out_dir / "chunks.jsonl", chunks)
    _write_jsonl(out_dir / "articles.jsonl", articles)
    _write_jsonl(out_dir / "issues.jsonl", issues)
    params = {"max_tokens": max_tokens, "min_intro_tokens": MIN_INTRO_TOKENS}  # what the split used (#12)
    (out_dir / "params.json").write_text(json.dumps(params, indent=2) + "\n", encoding="utf-8", newline="\n")
    return issues
