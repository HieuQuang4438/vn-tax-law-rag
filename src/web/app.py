"""The FastAPI app: the static chat page and its JSON API (#30). Rules: `docs/reference/web.md`."""

import html
import json
import logging
import threading
import time
from collections.abc import Callable
from contextlib import asynccontextmanager
from dataclasses import asdict
from pathlib import Path
from typing import Annotated, Any

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, StringConstraints, field_validator

from src.conversation import ask
from src.llm import LLMError
from src.web import texts

MAX_CHARS = 2000  # of a question, and of each earlier question
MAX_EARLIER = 100  # earlier questions a request may carry
DATA = Path("data")
STATIC = Path(__file__).resolve().parent / "static"

log = logging.getLogger(__name__)

Question = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_CHARS)]
Earlier = Annotated[str, StringConstraints(max_length=MAX_CHARS)]


class AskBody(BaseModel):
    question: Question
    earlier: list[Earlier] = []

    @field_validator("earlier")
    @classmethod
    def _few_enough(cls, earlier: list[str]) -> list[str]:
        if len(earlier) > MAX_EARLIER:
            raise ValueError(f"at most {MAX_EARLIER} earlier questions")
        return earlier


def _page() -> str:
    """index.html with the title and the texts of `src.web.texts` filled in."""
    values = json.dumps({name: getattr(texts, name) for name in texts.NAMES}, ensure_ascii=False)
    values = values.replace("</", "<\\/")  # JSON reads `<\/` as `</`; HTML does not end the script block there
    page = (STATIC / "index.html").read_text(encoding="utf-8")
    return page.replace("__TITLE__", html.escape(texts.TITLE)).replace("__TEXTS__", values)


def _load_data() -> tuple[Any, Any]:
    from src.answer import Answerer
    from src.llm import LLM
    from src.retrieval import Retriever

    return Retriever.load(DATA), Answerer.load(DATA, llm=LLM())


class Engine:
    """The retriever and the answerer of the process, loaded once in a background thread."""

    def __init__(self, load: Callable[[], tuple[Any, Any]]):
        self.load = load
        self.status = "loading"
        self.retriever = self.answerer = None
        self._state = threading.Lock()  # guards status and the loading thread
        self._asking = threading.Lock()  # one question at a time
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        with self._state:
            if self._thread is not None and self.status != "error":
                return
            self.status = "loading"
            self._thread = threading.Thread(target=self._run, name="load", daemon=True)
            self._thread.start()

    def _run(self) -> None:
        try:
            retriever, answerer = self.load()
        except Exception:
            log.exception("the index could not be loaded")
            with self._state:
                self.status = "error"
            return
        with self._state:
            self.retriever, self.answerer, self.status = retriever, answerer, "ready"

    def ask(self, question: str, earlier: list[str]):
        with self._asking:
            return ask(self.retriever, self.answerer, question, earlier)


def _not_ready(engine: Engine) -> JSONResponse | None:
    if engine.status == "ready":
        return None
    return JSONResponse({"error": "loading" if engine.status == "loading" else "load_error"}, status_code=503)


def _clause_order(citation) -> tuple[int, ...]:
    return tuple((int(part) if part.isdigit() else 0, part) for part in citation.id.split(".")[1:])


def _source(cited: list, documents: dict) -> dict:
    """One passage's citations, in first-use order, as one source (web.md, *One source per article*, #41)."""
    first = cited[0]
    document = documents[first.doc_id]
    whole = next((c for c in cited if c.id == c.passage), None)
    clauses = sorted((c for c in cited if c.id != c.passage), key=_clause_order)
    if whole is not None:
        text, effective = whole.text, whole.effective
    else:
        text = "\n".join(c.text or "" for c in clauses)
        dates = {c.effective for c in clauses}
        effective = dates.pop() if len(dates) == 1 else None
    links = []
    for citation in cited:
        links += [link for link in citation.amended_by if link not in links]
    return {"ids": [c.id for c in cited], "document": first.document, "kind": document.kind,
            "number": document.number, "title": document.title, "issued": document.issued,
            "article": first.article, "clauses": [c.clause for c in clauses], "heading": first.heading,
            "url": first.url, "text": text, "effective": effective, "amended_by": [asdict(link) for link in links]}


def _sources(citations: list, documents: dict) -> list[dict]:
    passages: dict[str, list] = {}
    for citation in citations:
        if citation.in_context:
            passages.setdefault(citation.passage, []).append(citation)
    return [_source(cited, documents) for cited in passages.values()]


def create_app(load: Callable[[], tuple[Any, Any]] | None = None) -> FastAPI:
    """`load` returns the retriever and the answerer; none: the index and the model under `data/`."""
    engine = Engine(load or _load_data)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        engine.start()
        yield

    app = FastAPI(title="vn-tax-law-rag", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    page = _page()
    app.mount("/static", StaticFiles(directory=STATIC), name="static")

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return page

    @app.get("/api/status")
    def status() -> dict:
        return {"status": engine.status}

    @app.post("/api/load")
    def load_again() -> dict:
        if engine.status == "error":
            engine.start()
        return {"status": engine.status}

    @app.get("/api/documents")
    def documents():
        refused = _not_ready(engine)
        if refused is not None:
            return refused
        return {"documents": [{"id": doc_id, "kind": d.kind, "number": d.number, "title": d.title, "url": d.url,
                               "issued": d.issued} for doc_id, d in engine.answerer.documents.items()]}

    @app.post("/api/ask")
    def answer(body: AskBody):
        started = time.perf_counter()
        refused = _not_ready(engine)
        if refused is not None:
            return refused
        try:
            turn = engine.ask(body.question, body.earlier)
        except LLMError as error:
            log.exception("the question could not be answered")
            return JSONResponse({"error": "quota" if error.quota else "error"},
                                status_code=429 if error.quota else 500)
        except Exception:  # rewrite or retrieval
            log.exception("the question could not be answered")
            return JSONResponse({"error": "error"}, status_code=500)
        result = turn.answer
        documents = engine.answerer.documents
        return {"question": body.question,
                "sentences": [{"text": s.text, "citations": list(s.citations)} for s in result.sentences],
                "notices": result.notices, "not_found": result.not_found,
                "sources": _sources(result.citations, documents),
                "flagged": list(result.flagged), "seconds": round(time.perf_counter() - started, 3)}

    return app
