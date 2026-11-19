"""Ask the model for a cited answer and resolve its citations (FR-CORE-010, FR-CORE-011, #15).

The rules are `docs/reference/answer.md`, *The answer*: the reply is a list of sentences with
citation ids; each id is resolved against the context's passages and shown as document, article
and clause with a link to the source page, or flagged when it is not in the context.
"""

import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import quote

from pydantic import BaseModel

from src.context import Assembler, Context, Link, Passage, cites
from src.context.assembly import LINK_WORDS, _marked
from src.llm import LLM, Call
from src.retrieval import Retrieval

NOT_FOUND = "Không tìm thấy quy định trả lời câu hỏi này trong các văn bản hiện có."
PROMPT = Path(__file__).resolve().parent.parent / "prompts" / "answer.md"
DOC_ID = re.compile(r"-(\d+)-d1\.html$")
ID = re.compile(r"^(\d+)(?:\.(\d+(?:\.\d+)*))?$")
FLAGGED_LABEL = "Trích dẫn không có trong nguồn được cung cấp:"
DAY = re.compile(r"^(\d{2})/(\d{2})/(\d{4})$")
POINT = re.compile(r"^(\d+)\.(\d+(?:\.\d+)*)[ .]?[a-yđ]")  # `1.25a`, `1.25 b`, `1.25.c`, ... (#33)


class SentenceOutput(BaseModel):
    text: str
    citations: list[str]


class AnswerOutput(BaseModel):
    sentences: list[SentenceOutput]


@dataclass(frozen=True)
class Document:
    label: str  # <loai_van_ban> <so_hieu>
    url: str
    kind: str = ""  # loai_van_ban
    number: str = ""  # so_hieu
    title: str = ""  # trich_yeu
    issued: str | None = None  # ngay_ban_hanh as YYYY-MM-DD


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
    clause: str | None = None  # the clause number as shown
    url: str | None = None
    # For the web page (answer.md, *For the page*, #30).
    doc_id: str | None = None
    heading: str | None = None
    text: str | None = None
    effective: str | None = None
    amended_by: tuple[Link, ...] = ()


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
    notices: int = 0  # the last `notices` sentences are amendment notices


def _normalised(raw: str) -> str:
    text = raw.strip()
    if text.startswith("[") and text.endswith("]"):
        text = text[1:-1].strip()
    return text


def _clause_of(citation_id: str, passages: dict[str, Passage]) -> str:
    """A point-level id as its clause id, the longest clause of the passage that fits; any other id as given."""
    match = POINT.match(citation_id)
    passage = passages.get(match.group(1)) if match else None
    if passage is None or passage.kind != "article":
        return citation_id
    run = match.group(2)
    fits = [k for k in passage.clauses if run == k or run.startswith(k + ".")]
    return f"{passage.id}.{max(fits, key=len)}" if fits else citation_id


def _heading(article: str, title: str) -> str:
    return f"Điều {article}. {title}".strip() if title else f"Điều {article}."


def _fragment(article: str, title: str) -> str:
    return "#:~:text=" + quote(_heading(article, title), safe="").replace("-", "%2D")


def _iso(day: str | None) -> str | None:
    """`dd/mm/yyyy` as `YYYY-MM-DD`; none for anything else."""
    match = DAY.match(day) if isinstance(day, str) else None
    return f"{match.group(3)}-{match.group(2)}-{match.group(1)}" if match else None


def _clause_text(article_text: str, passage_id: str, clause: str) -> str:
    """The clause's lines: from its clause line to the line before the next one, without the mark."""
    plain = article_text.split("\n")
    marked, clauses = _marked(article_text, passage_id)
    starts = [i for i, (line, mark) in enumerate(zip(plain, marked)) if line != mark]  # one per clause, in order
    position = clauses.index(clause)
    end = starts[position + 1] if position + 1 < len(starts) else len(plain)
    return "\n".join(plain[starts[position]:end])


def _named(citation: "Citation") -> str:
    article = f"Điều {citation.article} {citation.document}"
    return f"khoản {citation.clause} {article}" if citation.clause else article


def markers(ids: tuple[str, ...]) -> str:
    """`[1.25][2]`: a sentence's ids as rendered after it."""
    return "".join(f"[{i}]" for i in ids)


def documents_of(processed_dir: Path) -> dict[str, "Document"]:
    documents = {}
    for path in sorted(processed_dir.glob("*.json")):
        if path.name.startswith("_"):  # the crawler's own files, not pages
            continue
        page = json.loads(path.read_text(encoding="utf-8"))
        match = DOC_ID.search(page["source_url"])
        if not match:
            continue
        metadata = page["metadata"]
        kind, number = metadata["loai_van_ban"], metadata["so_hieu"]
        documents[match.group(1)] = Document(f"{kind} {number}", page["source_url"], kind, number,
                                             metadata.get("trich_yeu", ""), _iso(metadata.get("ngay_ban_hanh")))
    return documents


class Answerer:
    def __init__(self, assembler: Assembler, llm: LLM, documents: dict[str, Document]):
        self.assembler, self.llm, self.documents = assembler, llm, documents
        self.prompt = PROMPT.read_text(encoding="utf-8")

    @classmethod
    def load(cls, data_dir: Path = Path("data"), llm: LLM | None = None) -> "Answerer":
        return cls(Assembler.load(data_dir), llm or LLM(), documents_of(data_dir / "processed"))

    def answer(self, question: str, retrieval: Retrieval) -> Answer:
        started = time.perf_counter()
        context = self.assembler.assemble(retrieval)
        assembly = time.perf_counter() - started
        if not context.passages:
            return Answer([Sentence(NOT_FOUND, ())], [], [], True, NOT_FOUND, context, None,
                          {"assembly": assembly, "generation": 0})
        user = f"Passages:\n\n{context.text}\n\nQuestion: {question}"
        call = self.llm.generate("answer", self.prompt, user, AnswerOutput)
        passages = {p.id: p for p in context.passages}
        sentences = [Sentence(s.text, tuple(dict.fromkeys(_clause_of(_normalised(i), passages) for i in s.citations)))
                     for s in call.parsed.sentences]
        not_found = not sentences or (len(sentences) == 1 and sentences[0].text.strip() == NOT_FOUND
                                      and not sentences[0].citations)
        notices = [] if not_found else self._notices(sentences, passages)
        sentences += notices
        citations = [self._resolve(i, passages) for i in dict.fromkeys(i for s in sentences for i in s.citations)]
        flagged = [c.id for c in citations if not c.in_context]
        text = NOT_FOUND if not_found else self._render(sentences, citations, flagged)
        return Answer(sentences, citations, flagged, not_found, text, context, call,
                      {"assembly": assembly, "generation": call.latency_s}, len(notices))

    def _notices(self, sentences: list[Sentence], passages: dict[str, Passage]) -> list[Sentence]:
        """One sentence per link whose amended provision is cited, its source cited or not (choices A2, 2')."""
        ids = dict.fromkeys(i for s in sentences for i in s.citations)
        cited = [i for i in ids if self._resolve(i, passages).in_context]
        notices = []
        for passage in passages.values():
            for link in passage.links:
                if any(cites(i, link.target) for i in cited):
                    target, source = self._resolve(link.target, passages), self._resolve(link.source, passages)
                    text = f"{_named(target)} {LINK_WORDS[link.type]} {_named(source)}."
                    notices.append(Sentence(text[0].upper() + text[1:], (link.target, link.source)))
        return notices

    def _resolve(self, citation_id: str, passages: dict[str, Passage]) -> Citation:
        match = ID.match(citation_id)
        passage = passages.get(match.group(1)) if match else None
        if passage is None:
            return Citation(citation_id, False)
        clause = match.group(2)
        if passage.kind == "article":
            if clause is not None and clause not in passage.clauses:
                return Citation(citation_id, False)
            article_id = f"{passage.doc_id}:D{passage.article}"
            article = self.assembler.articles[article_id]
            text = article["text"] if clause is None else _clause_text(article["text"], passage.id, clause)
            own = self.assembler.chunks.get(f"{article_id}:K{clause}") if clause is not None else None
            if own is not None:
                effective = own["effective_date"]
            else:
                dates = {chunk["effective_date"] for chunk in self.assembler.chunks_of[article_id]}
                effective = dates.pop() if len(dates) == 1 else None
        else:
            if clause is not None:
                return Citation(citation_id, False)
            chunk = self.assembler.chunks[passage.chunk_ids[0]]
            article_id = chunk["parent_id"]
            clause = chunk["clause"] if chunk["clause"] not in (None, "0") else None
            text, effective = chunk["text"], chunk["effective_date"]
        shown = clause.split(".")[0] if clause else None
        document = self.documents[passage.doc_id]
        title = self.assembler.articles[article_id]["title"]
        links = tuple(link for link in passage.links if cites(citation_id, link.target))
        return Citation(citation_id, True, passage.id, document.label, passage.article, shown,
                        document.url + _fragment(passage.article, title), passage.doc_id,
                        _heading(passage.article, title), text, effective, links)

    @staticmethod
    def _render(sentences: list[Sentence], citations: list[Citation], flagged: list[str]) -> str:
        body = " ".join(s.text + (" " + markers(s.citations) if s.citations else "") for s in sentences)
        parts = [body]
        sources = [c for c in citations if c.in_context]
        if sources:
            lines = ["Nguồn:"]
            for c in sources:
                label = f"{c.document}, Điều {c.article}" + (f", khoản {c.clause}" if c.clause else "")
                lines.append(f"- [{c.id}] [{label}]({c.url})")
            parts.append("\n".join(lines))
        if flagged:
            parts.append(FLAGGED_LABEL + " " + " ".join(f"[{i}]" for i in flagged))
        return "\n\n".join(parts)
