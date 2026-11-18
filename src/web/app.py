"""The FastAPI app: the JSON API and, later, the static page (#30). Rules: `docs/reference/web.md`."""

from collections.abc import Callable
from typing import Any

from fastapi import FastAPI

MAX_CHARS = 2000  # of a question, and of each earlier question
MAX_EARLIER = 100  # earlier questions a request may carry


def create_app(load: Callable[[], tuple[Any, Any]] | None = None) -> FastAPI:
    """`load` returns the retriever and the answerer; none: the index and the model under `data/`."""
    raise NotImplementedError("#30: not implemented yet")
