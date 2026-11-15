"""Load and check the hand-written eval set, with each provision resolved to its article (#7).

Format, rules and messages: `docs/reference/eval-set.md`.
"""

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import yaml

TAX_TYPES = ("administration", "vat", "pit", "cit", "sct", "household")
FORMS = ("plain", "reference")
UNANSWERABLE = ("out_of_scope", "repealed")
QUESTIONS = (30, 50)
UNANSWERABLE_SHARE = 0.20
CONVERSATIONS = 5
TURNS = (2, 3)
KEY_FACTS = (1, 4)

ITEM_FIELDS = ("id", "question", "tax_type", "form", "answer", "key_facts", "provisions", "unanswerable")
ITEM_REQUIRED = ("question", "tax_type", "form", "answer")
SET_FIELDS = ("version", "as_of", "questions", "conversations")
CONVERSATION_FIELDS = ("id", "turns")
LINE = "__line__"

PROVISION = re.compile(r"(?P<number>\S+)\s+điều\s+(?P<article>\d+[a-zđ]?)(?:\s+khoản\s+(?P<clause>\d+[a-zđ]?))?",
                       re.IGNORECASE)
NAMES_A_PROVISION = re.compile(r"điều\s+\d|\d+/\d{4}", re.IGNORECASE)
OUTSIDE_SECTION = "## Amendments from outside the corpus"
OUTSIDE_ARTICLES = re.compile(r"Articles? (\w+(?: and \w+)*)")


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
    added_in: int = 1  # the set version that added it (#26); a turn takes its conversation's


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


@dataclass
class Report:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class _LineLoader(yaml.SafeLoader):
    """Records the line each mapping starts on, so a message can point at its question."""


def _mapping_with_line(loader: _LineLoader, node: yaml.MappingNode) -> dict:
    mapping = loader.construct_mapping(node, deep=True)
    mapping[LINE] = node.start_mark.line + 1
    return mapping


_LineLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _mapping_with_line)


def _key(text: str) -> str:
    return unicodedata.normalize("NFC", text).casefold()


def _article_of(chunk_id: str) -> str:
    return re.sub(r":K[^:]+$", "", chunk_id)


class Corpus:
    """What the checker needs from the local corpus: numbers, chunk ids, amendment links."""

    def __init__(self, processed_dir: Path, enriched_dir: Path, corpus_md: Path | None = None):
        self.documents: dict[str, tuple[str, str]] = {}  # casefolded so_hieu -> (doc_id, so_hieu)
        for path in sorted(processed_dir.glob("*.json")):
            if path.name.startswith("_"):
                continue
            doc = json.loads(path.read_text(encoding="utf-8"))
            number = doc.get("metadata", {}).get("so_hieu")
            match = re.search(r"-(\d+)-d1\.html", doc.get("source_url", ""))
            if number and match:
                self.documents[_key(number)] = (match.group(1), number)
        self.chunks: dict[str, list[dict]] = {}  # article id -> its chunks, in file order
        self.chunk_ids: set[str] = set()
        for line in (enriched_dir / "chunks.jsonl").read_text(encoding="utf-8").splitlines():
            chunk = json.loads(line)
            self.chunks.setdefault(chunk["parent_id"], []).append(chunk)
            self.chunk_ids.add(chunk["id"])
        self.outside = self._outside(corpus_md) if corpus_md else set()

    @staticmethod
    def _outside(corpus_md: Path) -> set[str]:
        """Article ids in corpus.md's table of amendments made from outside the corpus."""
        text = corpus_md.read_text(encoding="utf-8")
        if OUTSIDE_SECTION not in text:
            return set()
        section = text.split(OUTSIDE_SECTION, 1)[1].split("\n## ", 1)[0]
        articles = set()
        for row in section.splitlines():
            cells = [cell.strip() for cell in row.strip().strip("|").split("|")]
            match = re.match(r"(\d+)", cells[0]) if len(cells) >= 2 else None
            if not match:
                continue
            for group in OUTSIDE_ARTICLES.findall(cells[1]):
                articles.update(f"{match.group(1)}:D{n}" for n in group.split(" and "))
        return articles

    def resolve(self, text: str) -> Provision:
        """The provision's article and chunk; raises ValueError with the checker's message."""
        written = " ".join(unicodedata.normalize("NFC", text).split())
        match = PROVISION.fullmatch(written)
        if not match:
            raise ValueError(f'cannot read provision "{text}"')
        number, article, clause = match["number"], match["article"].lower(), match["clause"]
        if _key(number) not in self.documents:
            raise ValueError(f'unknown document "{number}"')
        doc_id, so_hieu = self.documents[_key(number)]
        article_id = f"{doc_id}:D{article}"
        if article_id not in self.chunks:
            raise ValueError(f"no Điều {article} in {so_hieu}")
        if clause is None or article_id in self.chunk_ids:  # whole article, or a clause of an unsplit one
            return Provision(text, article_id, article_id)
        chunk_id = f"{article_id}:K{clause.lower()}"
        if chunk_id not in self.chunk_ids:
            raise ValueError(f"no khoản {clause} in Điều {article} of {so_hieu}")
        return Provision(text, article_id, chunk_id)

    def amending_articles(self, provision: Provision) -> list[str]:
        """Articles of the in-corpus sources whose links reach the provision, in order, once each."""
        chunks = self.chunks[provision.article]
        if provision.chunk != provision.article:
            chunks = [c for c in chunks if c["id"] == provision.chunk]
        sources = [_article_of(link["source"]) for c in chunks for link in c.get("amended_by", [])]
        return list(dict.fromkeys(sources))


def _is_text_list(value) -> bool:
    return isinstance(value, list) and all(isinstance(v, str) for v in value)


class _Checker:
    def __init__(self, corpus: Corpus):
        self.corpus = corpus
        self.report = Report()
        self.ids: set[str] = set()

    def error(self, message: str, line: int | None = None, item_id: str | None = None) -> None:
        self.report.errors.append(f"line {line}: {item_id}: {message}" if line else message)

    def warn(self, message: str, line: int, item_id: str) -> None:
        self.report.warnings.append(f"line {line}: {item_id}: {message}")

    def item(self, raw, item_id: str | None, is_turn: bool) -> Item | None:
        if not isinstance(raw, dict):
            self.error(f"{'a turn' if is_turn else 'a question'} must be a mapping of fields")
            return None
        line = raw.get(LINE)
        fields = [f for f in raw if f != LINE]
        item_id = item_id if is_turn else str(raw.get("id"))
        say = lambda message: self.error(message, line, item_id)  # noqa: E731
        allowed = ITEM_FIELDS[1:] if is_turn else ITEM_FIELDS
        for name in (ITEM_REQUIRED if is_turn else ("id", *ITEM_REQUIRED)):
            if name not in raw:
                say(f'missing field "{name}"')
        for name in fields:
            if name not in allowed:
                say(f'unknown field "{name}"')
        if not is_turn and "id" in raw:
            if item_id in self.ids:
                say(f'duplicate id "{item_id}"')
            self.ids.add(item_id)
        for name in ("question", "answer"):
            if name in raw and not (isinstance(raw[name], str) and raw[name].strip()):
                say(f'"{name}" must be text')
        if "tax_type" in raw and raw["tax_type"] not in TAX_TYPES:
            say(f'tax_type "{raw["tax_type"]}" is not one of {", ".join(TAX_TYPES)}')
        if "form" in raw and raw["form"] not in FORMS:
            say(f'form "{raw["form"]}" is not one of {", ".join(FORMS)}')
        key_facts, provisions = raw.get("key_facts", []), raw.get("provisions", [])
        for name, value in (("key_facts", key_facts), ("provisions", provisions)):
            if not _is_text_list(value):
                say(f'"{name}" must be a list of text')
        key_facts = key_facts if _is_text_list(key_facts) else []
        provisions = provisions if _is_text_list(provisions) else []
        unanswerable = raw.get("unanswerable")
        if "unanswerable" in raw:
            if unanswerable not in UNANSWERABLE:
                say(f'unanswerable "{unanswerable}" is not one of {", ".join(UNANSWERABLE)}')
            if provisions:
                say("unanswerable but has provisions")
            if key_facts:
                say("unanswerable but has key_facts")
        else:
            if not provisions:
                say("no provisions")
            if not KEY_FACTS[0] <= len(key_facts) <= KEY_FACTS[1]:
                say(f"key_facts: {KEY_FACTS[0]} to {KEY_FACTS[1]}, found {len(key_facts)}")
        resolved = []
        for text in provisions:
            try:
                resolved.append(self.corpus.resolve(text))
            except ValueError as problem:
                say(str(problem))
        self.warnings(raw, resolved, line, item_id)
        return Item(id=item_id, line=line, question=raw.get("question", ""), tax_type=raw.get("tax_type", ""),
                    form=raw.get("form", ""), answer=raw.get("answer", ""), key_facts=list(key_facts),
                    provisions=resolved, unanswerable=unanswerable)

    def warnings(self, raw: dict, provisions: list[Provision], line: int, item_id: str) -> None:
        listed = {p.article for p in provisions}
        for provision in provisions:
            for source in self.corpus.amending_articles(provision):
                if source not in listed:
                    self.warn(f'"{provision.text}" is amended by {source}, which is not listed', line, item_id)
            if provision.article in self.corpus.outside:
                self.warn(f'"{provision.text}" is amended from outside the corpus (corpus.md); '
                          "its text there may not be the law in force", line, item_id)
        question = raw.get("question")
        if raw.get("form") == "reference" and isinstance(question, str) and not NAMES_A_PROVISION.search(question):
            self.warn("form reference but names no provision (Điều <n>) or document number", line, item_id)

    def conversation(self, raw) -> Conversation | None:
        if not isinstance(raw, dict):
            self.error("a conversation must be a mapping of fields")
            return None
        line, conversation_id = raw.get(LINE), str(raw.get("id"))
        say = lambda message: self.error(message, line, conversation_id)  # noqa: E731
        for name in CONVERSATION_FIELDS:
            if name not in raw:
                say(f'missing field "{name}"')
        for name in raw:
            if name not in (*CONVERSATION_FIELDS, LINE):
                say(f'unknown field "{name}"')
        if "id" in raw:
            if conversation_id in self.ids:
                say(f'duplicate id "{conversation_id}"')
            self.ids.add(conversation_id)
        turns = raw.get("turns") if isinstance(raw.get("turns"), list) else []
        if not TURNS[0] <= len(turns) <= TURNS[1]:
            say(f"{TURNS[0]} to {TURNS[1]} turns, found {len(turns)}")
        items = [self.item(turn, f"{conversation_id}.{n}", is_turn=True) for n, turn in enumerate(turns, 1)]
        return Conversation(conversation_id, line, [i for i in items if i])

    def whole(self, raw) -> EvalSet:
        if not isinstance(raw, dict):
            self.error("the set must be a mapping with version, as_of, questions and conversations")
            return EvalSet(version=0, as_of=None, sha256="")
        for name in SET_FIELDS:
            if name not in raw:
                self.error(f'missing field "{name}"')
        for name in raw:
            if name not in (*SET_FIELDS, LINE):
                self.error(f'unknown field "{name}"')
        questions_raw = raw.get("questions") if isinstance(raw.get("questions"), list) else []
        conversations_raw = raw.get("conversations") if isinstance(raw.get("conversations"), list) else []
        questions = [q for q in (self.item(r, None, is_turn=False) for r in questions_raw) if q]
        conversations = [c for c in (self.conversation(r) for r in conversations_raw) if c]

        version, as_of = raw.get("version"), raw.get("as_of")
        if "version" in raw and not (isinstance(version, int) and not isinstance(version, bool) and version >= 1):
            self.error(f'version must be a positive integer, found "{version}"')
        if "as_of" in raw and not isinstance(as_of, date):
            self.error(f'as_of must be a date (YYYY-MM-DD), found "{as_of}"')
        count = len(questions_raw)
        if not QUESTIONS[0] <= count <= QUESTIONS[1]:
            self.error(f"{QUESTIONS[0]} to {QUESTIONS[1]} questions, found {count}")
        if count:
            share = sum(isinstance(r, dict) and "unanswerable" in r for r in questions_raw) / count
            if round(share, 2) < UNANSWERABLE_SHARE:
                self.error(f"unanswerable share {share:.2f} is below {UNANSWERABLE_SHARE:.2f}")
        present = [r for r in questions_raw if isinstance(r, dict)]
        for tax_type in TAX_TYPES:
            if not any(r.get("tax_type") == tax_type for r in present):
                self.error(f'no question with tax_type "{tax_type}"')
        for form in FORMS:
            if not any(r.get("form") == form for r in present):
                self.error(f'no question with form "{form}"')
        if len(conversations_raw) < CONVERSATIONS:
            self.error(f"at least {CONVERSATIONS} conversations, found {len(conversations_raw)}")
        return EvalSet(version=version if isinstance(version, int) else 0,
                       as_of=as_of if isinstance(as_of, date) else None, sha256="",
                       questions=questions, conversations=conversations)


def analyse(path: Path, corpus: Corpus) -> tuple[EvalSet, Report]:
    """The set as far as it can be read, and every error and warning in it."""
    content = path.read_bytes()
    checker = _Checker(corpus)
    try:
        raw = yaml.load(content.decode("utf-8"), Loader=_LineLoader)  # noqa: S506 - a SafeLoader subclass
    except yaml.YAMLError as problem:
        checker.error(f"not valid YAML: {problem}")
        raw = {}
    eval_set = checker.whole(raw)
    eval_set.sha256 = hashlib.sha256(content).hexdigest()
    return eval_set, checker.report


def load_eval_set(path: Path, processed_dir: Path, enriched_dir: Path) -> EvalSet:
    """The set with every provision resolved; raises `EvalSetError` if the checker finds errors."""
    eval_set, report = analyse(path, Corpus(processed_dir, enriched_dir))
    if report.errors:
        raise EvalSetError(report.errors)
    return eval_set
