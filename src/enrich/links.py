"""Amendment links (FR-CORE-005): read directives on the amending side, invert them onto chunks.

The rules are specified in `docs/reference/chunk-schema.md`, "Amendment links" and
`data/enriched/links.jsonl`. Approach approved on #5.
"""

import re
from dataclasses import dataclass, field

from src.chunking import Chunk, ChunkedDocument, Issue
from src.chunking.chunker import _quote_depth, doc_id_of
from src.enrich.effective import EFFECTIVENESS_TITLE, effective_dates

KINDS = r"Bộ luật|Luật|Nghị định|Thông tư liên tịch|Thông tư|Nghị quyết|Quyết định"
NUMBER = r"\d{1,4}/\d{4}/[A-ZĐ][A-ZĐ0-9-]*[A-ZĐ0-9]"
# A law's name runs from a capital letter to its number, never across another document kind.
NAME = rf"(?: [A-ZĐ](?:(?!\b(?:{KINDS})\b)[^\d“”();,.:])*?)?"
TOKEN = re.compile(
    rf"(?P<doc>(?P<kind>{KINDS}){NAME}\s+(?:số\s*:?\s*)?(?P<number>{NUMBER}))"
    rf"|(?P<this>(?:{KINDS}) này)"
    r"|(?P<form>[Mm]ẫu số:?\s*(?P<code>\d{1,3}(?:/[A-ZĐa-z0-9-]*[A-ZĐ0-9])?)(?P<annex_of>,\s*Phụ lục [IVXLl\d]+)?)"
    r"|(?P<part>Phụ lục (?:[IVXLl]+|\d+)|Chương (?:[IVXL]+|\d+))(?![\wđ])"
    r"|(?P<points>(?:[Cc]ác )?[Đđ]iểm [a-zđ](?:\.\d+)?(?:\s*(?:,|và(?=\s))\s*(?:điểm\s+)?[a-zđ](?:\.\d+)?(?![\wđ]))*)(?![\wđ])"
    r"|[Kk]hoản (?P<clause>\d+[a-zđ]?)(?![\wđ])"
    r"|Điều (?P<article>\d+[a-zđ]?)(?![\wđ])"
    r"|(?P<after>(?:vào )?sau)(?= (?:khoản|điểm|Điều) )"
)
POINT = re.compile(r"[a-zđ](?:\.\d+)?(?![\wđ])")
# What may stand between two parts of one provision run, or between a provision and its document.
CONNECTOR = re.compile(r"[,;]?\s*(?:và|của|tại|(?:theo danh mục mẫu biểu\s+)?(?:ban hành\s+)?kèm theo)?\s*[,;]?")

VERBS = (("Sửa đổi, bổ sung", "amends"), ("Sửa đổi", "amends"), ("Bổ sung", "amends"), ("Bỏ cụm từ", "amends"),
         ("Thay thế", "replaces"), ("Bãi bỏ", "repeals"))
VERB_START = re.compile(r"^(?P<verb>" + "|".join(re.escape(v) for v, _ in VERBS) + r")\b\s*")
TYPE_OF = dict(VERBS)
MID_VERB = re.compile(
    r"(?<![Đđ]ược )(?<!bị )(?<!hoặc )\b(?P<verb>thay thế|bãi bỏ)\s*"
    rf"(?=:|(?:{KINDS})\b|[Mm]ẫu số|Danh mục|Phụ lục|quy định tại|nội dung tại|các quy định|Điều \d|[Kk]hoản \d)"
)
ENDS = re.compile(r"\bhết hiệu lực\b")
NUMBERED = re.compile(r"^\d+[a-z]?\.\s*")
LETTERED = re.compile(r"^[a-zđ](?:\.\d+)*\)\s*")
CONTAINER = re.compile(r"^(?:một số|các) (?:điều|khoản|điểm)\b")
QUOTED = re.compile(r"“[^”]*”?")
# "Thay thế X bằng|thành Y": Y is the replacement. Only before what can replace ("giá thành" is not).
REPLACEMENT = re.compile(r"\s(?:bằng|thành)\s(?=Danh mục|[Mm]ẫu số|Phụ lục|quy định|các )")
PAREN = re.compile(r"\(([^()]*)\)")


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


@dataclass(frozen=True)
class _Context:
    number: str | None = None  # the inherited document
    article: str | None = None
    clause: str | None = None


@dataclass
class _Item:
    article: str | None = None
    clause: str | None = None
    point: str | None = None
    part: str | None = None
    anchor: str | None = None  # the clause an added provision is placed after


@dataclass
class _Group:
    number: str | None
    kind: str | None
    items: list[_Item]
    gap_before: str  # text between the previous token and the group's first token
    after_previous_doc: int  # index of the document token before this group's own, -1 if none
    doc_index: int  # index of this group's document token, -1 if inherited


@dataclass
class _Corpus:
    by_number: dict[str, str]  # so_hieu -> doc_id
    laws: list[tuple[str, str]]  # (Luật <trich_yeu>, so_hieu), longest name first
    chunks: dict[str, list[Chunk]]  # doc_id -> chunks in order


def _clean(text: str, replaces: bool) -> str:
    """The directive's object, ready to read: no quoted wording, no history or exception in brackets."""
    text = QUOTED.sub(" ", text)
    if replaces and (cut := REPLACEMENT.search(text)):
        text = text[:cut.start()]

    def bracket(match: re.Match) -> str:
        inner = match.group(1)
        if TOKEN.search(inner) and (re.search(rf"(?:{KINDS})\s", inner) or inner.lstrip().startswith("trừ")):
            return " "
        return " " + inner + " "

    text = PAREN.sub(bracket, text)
    return re.sub(r"\s+", " ", text)


def _named_laws(text: str, corpus: _Corpus, taken: list[tuple[int, int]]) -> list[tuple[int, int, str]]:
    found = []
    for name, number in corpus.laws:
        for match in re.finditer(re.escape(name) + r"(?![\wđ])(?!\s+số)", text):
            span = (match.start(), match.end())
            if not any(s < span[1] and span[0] < e for s, e in taken):
                taken.append(span)
                found.append((span[0], span[1], number))
    return found


def _tokens(text: str, corpus: _Corpus) -> list[tuple[int, int, str, re.Match | str]]:
    kinds = ("doc", "this", "form", "part", "points", "clause", "article", "after")
    tokens = [(m.start(), m.end(), next(k for k in kinds if m.group(k) is not None), m) for m in TOKEN.finditer(text)]
    taken = [(s, e) for s, e, _, _ in tokens]
    tokens += [(s, e, "named", number) for s, e, number in _named_laws(text, corpus, taken)]
    return sorted(tokens, key=lambda t: t[0])


def _kind_of(number: str, corpus: _Corpus, written: str | None) -> str | None:
    if written:
        return "Thông tư" if written.startswith("Thông tư") else written
    return "Luật" if any(n == number for _, n in corpus.laws) else None


def _groups(text: str, context: _Context, corpus: _Corpus) -> list[_Group]:
    """Read the object left to right: provisions and parts, bound to the document on their right."""
    groups: list[_Group] = []
    run: list[_Item] = []
    anchor: _Item | None = None
    run_start: int | None = None
    previous_end = 0
    gap_before_run = ""
    doc_tokens = 0
    last_doc = -1

    def fill(items: list[_Item]) -> list[_Item]:
        kept = []
        for item in items:
            if item.part:
                kept.append(item)
            elif item.article is None:
                if context.article is None:
                    continue
                item.article = context.article
                if item.clause is None and item.point is not None:
                    item.clause = context.clause
                kept.append(item)
            else:
                kept.append(item)
        return kept

    for start, end, kind, match in _tokens(text, corpus):
        gap = text[previous_end:start]
        if kind in ("doc", "named", "this"):
            if kind == "this":
                run, anchor = [], None
            else:
                number = match.group("number") if kind == "doc" else match
                written = match.group("kind") if kind == "doc" else "Luật"
                items = fill(run)
                gap_here = gap_before_run if run else gap
                groups.append(_Group(number, _kind_of(number, corpus, written), items, gap_here,
                                     last_doc, doc_tokens))
                last_doc = doc_tokens
                doc_tokens += 1
                run, anchor = [], None
            run_start = None
            previous_end = end
            continue
        if run and not CONNECTOR.fullmatch(gap) and kind != "after":
            # A run broken by other text: what lacks an article cannot be placed.
            run = [item for item in run if item.article or item.part] + \
                  [item for item in fill([i for i in run if not (i.article or i.part)])]
        if not run:
            gap_before_run = gap
            run_start = start
        if kind == "after":
            anchor = _Item()
        elif kind in ("form", "part"):
            if kind == "form":
                part = "Mẫu số " + match.group("code") + (", " + match.group("annex_of").split(",", 1)[1].strip()
                                                          if match.group("annex_of") else "")
            else:
                part = match.group("part")
            run.append(_Item(part=part))
        elif kind == "points":
            letters = POINT.findall(re.sub(r"^(?:[Cc]ác )?[Đđ]iểm ", "", match.group("points")).replace("điểm", " "))
            target = anchor if anchor is not None else None
            if target is not None:
                target.point = letters[0]
            else:
                run += [_Item(point=letter) for letter in letters]
        elif kind == "clause":
            clause = match.group("clause")
            if anchor is not None:
                anchor.clause = clause
            else:
                open_points = [i for i in run if i.point and i.clause is None and i.article is None]
                if open_points:
                    for item in open_points:
                        item.clause = clause
                else:
                    run.append(_Item(clause=clause))
        elif kind == "article":
            article = match.group("article")
            waiting = [i for i in run if i.article is None and not i.part]
            if anchor is not None:
                for item in waiting:
                    item.article = article
                    item.anchor = item.anchor or anchor.clause
                anchor = None
            elif waiting:
                for item in waiting:
                    item.article = article
            else:
                run.append(_Item(article=article))
        if anchor is not None and kind != "after":
            for item in run:
                if item.anchor is None and anchor.clause:
                    item.anchor = anchor.clause
        previous_end = end
    if run:
        for item in run:
            if anchor is not None and anchor.clause and item.anchor is None:
                item.anchor = anchor.clause
        items = fill(run)
        if items and context.number:
            groups.append(_Group(context.number, _kind_of(context.number, corpus, None), items,
                                 gap_before_run, last_doc, -1))
    return groups


def _targets(groups: list[_Group]) -> list[_Group]:
    """Which groups the directive acts on; the rest describe a target's history or title."""
    if not groups:
        return []
    first = groups[0]
    chosen = [first]
    for group in groups[1:]:
        before = group.gap_before.rstrip()
        if not group.items:
            if (group.kind == first.kind and re.search(r"(?:\bvà|;)$", before)
                    and group.after_previous_doc == chosen[-1].doc_index and chosen[-1].doc_index >= 0):
                chosen.append(group)
        elif first.items and re.search(r"(?:,|\bvà|;)$", before):
            chosen.append(group)
    return chosen


def _clause_key(clause: str) -> tuple[int, str]:
    match = re.match(r"(\d+)(.*)", clause)
    return (int(match.group(1)), match.group(2)) if match else (0, clause)


def _target_chunks(doc_id: str, item: _Item | None, corpus: _Corpus) -> list[str]:
    chunks = corpus.chunks.get(doc_id, [])
    if item is None:
        return [c.id for c in chunks]
    if item.part:
        return []
    of_article = [c for c in chunks if c.article == item.article]
    if item.clause is None:
        return [c.id for c in of_article]
    split = [c for c in of_article if c.clause not in (None, "0")]
    if not split:
        return [c.id for c in of_article]
    if exact := [c for c in split if c.clause == item.clause]:
        return [exact[0].id]
    if item.anchor and (anchored := [c for c in split if c.clause == item.anchor]):
        return [anchored[0].id]
    below = [c for c in split if re.fullmatch(r"\d+", c.clause) and _clause_key(c.clause) < _clause_key(item.clause)]
    return [max(below, key=lambda c: _clause_key(c.clause)).id] if below else []


def _links(type_: str, source: str, groups: list[_Group], corpus: _Corpus) -> list[Link]:
    links = []
    for group in groups:
        doc_id = corpus.by_number.get(group.number)
        for item in group.items or [None]:
            links.append(Link(
                type_, source, group.number, doc_id,
                item.article if item else None, item.clause if item else None,
                item.point if item else None, item.part if item else None,
                _target_chunks(doc_id, item, corpus) if doc_id else [], doc_id is not None,
            ))
    return links


def _context_of(groups: list[_Group], fallback: _Context) -> _Context:
    if not groups:
        return fallback
    first = groups[0]
    item = first.items[0] if first.items else None
    return _Context(first.number or fallback.number, item.article if item else None, item.clause if item else None)


def _first_document(text: str, corpus: _Corpus) -> str | None:
    for _, _, kind, match in _tokens(text, corpus):
        if kind == "doc":
            return match.group("number")
        if kind == "named":
            return match
    return None


def _source_lines(article_text: str, chunks: list[Chunk]) -> list[tuple[str, str, bool]]:
    """Each line of the article with the chunk holding it and whether it starts inside a quotation."""
    owned = [(line, c.id) for c in chunks for line in c.text.split("\n")]
    out, position, depth = [], 0, 0
    for line in article_text.split("\n"):
        source = chunks[0].id
        if position < len(owned) and owned[position][0] == line:
            source = owned[position][1]
            position += 1
        out.append((line, source, depth > 0 or line.startswith("“")))
        opened, _ = _quote_depth(line, depth)
        if depth == 0 and opened > 0 and not line.startswith("“"):
            opened = 0
        depth = max(0, opened)
    return out


class _Reader:
    def __init__(self, doc: dict, chunked: ChunkedDocument, corpus: _Corpus):
        self.doc_id = doc_id_of(doc)
        self.chunked = chunked
        self.corpus = corpus
        title = (doc.get("metadata", {}).get("trich_yeu") or "").strip()
        self.amending = title.startswith("Sửa đổi, bổ sung")
        self.base = _Context(_first_document(title, corpus))
        self.links: list[Link] = []
        self.issues: list[Issue] = []

    def directive(self, type_: str, obj: str, source: str, context: _Context) -> list[_Group]:
        groups = _targets(_groups(_clean(obj, type_ == "replaces"), context, self.corpus))
        self.links += _links(type_, source, groups, self.corpus)
        return groups

    def report(self, article: str, line: str) -> None:
        self.issues.append(Issue(self.doc_id, "unresolved_link", article, line[:200]))

    def read(self) -> AmendmentLinks:
        articles = self.chunked.articles
        effectiveness = next((a for a in reversed(articles) if EFFECTIVENESS_TITLE.search(a.title)), None)
        for article in articles:
            chunks = [c for c in self.chunked.chunks if c.parent_id == article.id]
            if not chunks:
                continue
            if article is effectiveness:
                self.read_effectiveness(article, chunks)
            elif self.amending:
                self.read_amending(article, chunks)
        return AmendmentLinks(_unique(self.links), {}, self.issues)

    def read_amending(self, article, chunks: list[Chunk]) -> None:
        context = self.base
        if match := VERB_START.match(article.title):
            obj = article.title[match.end():]
            if CONTAINER.match(obj):
                context = _context_of(_groups(_clean(obj, False), self.base, self.corpus), self.base)
            elif groups := self.directive(TYPE_OF[match.group("verb")], obj, chunks[0].id, self.base):
                context = _context_of(groups, self.base)
        container: _Context | None = None
        for line, source, quoted in _source_lines(article.text, chunks):
            if quoted:
                continue
            numbered, lettered = NUMBERED.match(line), LETTERED.match(line)
            if numbered:
                container = None
            body = line[(numbered or lettered).end():] if (numbered or lettered) else line
            match = VERB_START.match(body)
            if not match:
                continue
            obj = body[match.end():]
            parent = container if (lettered and container) else context
            if CONTAINER.match(obj):
                found = _context_of(_groups(_clean(obj, False), parent, self.corpus), parent)
                if numbered:
                    container = found
                continue
            if not self.directive(TYPE_OF[match.group("verb")], obj, source, parent):
                self.report(article.article, line)

    def read_effectiveness(self, article, chunks: list[Chunk]) -> None:
        list_type: str | None = None
        for line, source, quoted in _source_lines(article.text, chunks):
            if quoted:
                continue
            numbered, lettered = NUMBERED.match(line), LETTERED.match(line)
            if numbered or not lettered:
                list_type = None
            body = line[(numbered or lettered).end():] if (numbered or lettered) else line
            if lettered and list_type:
                if match := VERB_START.match(body):
                    found = self.directive(TYPE_OF[match.group("verb")], body[match.end():], source, self.base)
                else:
                    found = self.directive(list_type, body, source, self.base)
                if not found:
                    self.report(article.article, line)
                continue
            opens = line.rstrip().endswith(":")
            if match := VERB_START.match(body):
                type_, obj = TYPE_OF[match.group("verb")], body[match.end():]
            elif match := MID_VERB.search(body):
                type_ = "replaces" if match.group("verb") == "thay thế" else "repeals"
                obj = body[match.end():]
            elif ENDS.search(body):
                for part in body.split(";"):
                    if end := ENDS.search(part):
                        if self.directive("repeals", part[:end.start()], source, self.base):
                            continue
                        if opens and part is body.split(";")[-1]:
                            list_type = "repeals"
                        else:
                            self.report(article.article, part.strip())
                continue
            else:
                continue
            if not self.directive(type_, obj, source, self.base):
                if opens:
                    list_type = type_
                else:
                    self.report(article.article, line)


def _unique(links: list[Link]) -> list[Link]:
    """One link per source, type and target: a title and its body can name the same target."""
    seen, out = set(), []
    for link in links:
        key = (link.type, link.source, link.target_number, link.target_article, link.target_clause,
               link.target_point, link.target_part)
        if key not in seen:
            seen.add(key)
            out.append(link)
    return out


def amendment_links(corpus: list[tuple[dict, ChunkedDocument]]) -> AmendmentLinks:
    """Every link in the corpus, each target chunk's inverse links, and unresolved directives."""
    by_number, laws, chunks = {}, [], {}
    for doc, chunked in corpus:
        meta = doc.get("metadata", {})
        doc_id = doc_id_of(doc)
        number = (meta.get("so_hieu") or "").strip()
        by_number[number] = doc_id
        chunks[doc_id] = chunked.chunks
        title = (meta.get("trich_yeu") or "").strip()
        if meta.get("loai_van_ban") == "Luật" and title and not title.startswith("Sửa đổi"):
            laws.append(("Luật " + title, number))
    index = _Corpus(by_number, sorted(laws, key=lambda law: -len(law[0])), chunks)

    result = AmendmentLinks()
    dates: dict[str, str | None] = {}
    for doc, chunked in corpus:
        found = _Reader(doc, chunked, index).read()
        result.links += found.links
        result.issues += found.issues
        dates.update(effective_dates(doc, chunked).by_chunk)

    for link in result.links:
        for target in link.target_chunks:
            entries = result.amended_by.setdefault(target, [])
            entry = {"type": link.type, "source": link.source}
            if entry not in entries:  # one entry per type and source, approved on #5
                entries.append(entry)
    for entries in result.amended_by.values():
        entries.sort(key=lambda e: (dates.get(e["source"]) is None, dates.get(e["source"]) or "", e["source"]))
    return result
