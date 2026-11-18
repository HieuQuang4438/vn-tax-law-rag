"""The FastAPI app: the JSON API and, later, the static page (#30). Rules: `docs/reference/web.md`."""

import logging
import threading
import time
from collections.abc import Callable
from contextlib import asynccontextmanager
from dataclasses import asdict
from pathlib import Path
from typing import Annotated, Any

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel, StringConstraints, field_validator

from src.conversation import ask
from src.llm import LLMError

MAX_CHARS = 2000  # of a question, and of each earlier question
MAX_EARLIER = 100  # earlier questions a request may carry
DATA = Path("data")

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


def _source(citation, documents: dict) -> dict:
    document = documents[citation.doc_id]
    return {"id": citation.id, "document": citation.document, "kind": document.kind, "number": document.number,
            "title": document.title, "issued": document.issued, "article": citation.article,
            "clause": citation.clause, "heading": citation.heading, "url": citation.url, "text": citation.text,
            "effective": citation.effective, "amended_by": [asdict(link) for link in citation.amended_by]}


def create_app(load: Callable[[], tuple[Any, Any]] | None = None) -> FastAPI:
    """`load` returns the retriever and the answerer; none: the index and the model under `data/`."""
    engine = Engine(load or _load_data)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        engine.start()
        yield

    app = FastAPI(title="vn-tax-law-rag", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)

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
                "sources": [_source(c, documents) for c in result.citations if c.in_context],
                "flagged": list(result.flagged), "seconds": round(time.perf_counter() - started, 3)}

    return app
