"""The one wrapper around the Gemini API (CONVENTIONS §5, #15): pacing, retries, logging, cost.

The rules are `docs/reference/answer.md`, *The model call*. Interface stub.
"""

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from src.config import GOOGLE_API_KEYS, LLM_MODEL

PRICES = {"gemini-3.5-flash-lite": (0.30, 2.50)}  # USD per 1M tokens, input and output (ADR-0003)
PRICES_READ = "2026-11-16"
TIMEOUT_S = 60
MIN_INTERVAL_S = 4.0  # under 15 requests per minute
BACKOFF_S = 10
ATTEMPTS = 5

log = logging.getLogger("src.llm")


@dataclass(frozen=True)
class Call:
    parsed: Any
    model: str
    prompt: str
    input_tokens: int
    output_tokens: int  # answer and thinking tokens
    latency_s: float  # of the attempt that succeeded
    cost_usd: float
    attempts: int


class LLMError(RuntimeError):
    """No usable reply."""


class LLM:
    def __init__(self, model: str | None = None, api_key: str | None = None, client=None,
                 sleep: Callable[[float], None] = time.sleep, clock: Callable[[], float] = time.monotonic):
        self.model = model or LLM_MODEL
        self._api_key = api_key or GOOGLE_API_KEYS[0]
        self._client, self._sleep, self._clock = client, sleep, clock

    def generate(self, prompt: str, system: str, user: str, schema: type,
                 validate: Callable[[Any], None] | None = None) -> Call:
        return Call(None, self.model, prompt, 0, 0, 0.0, 0.0, 0)
