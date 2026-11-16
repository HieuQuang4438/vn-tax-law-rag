"""The one wrapper around the Gemini API (CONVENTIONS §5, #15): pacing, retries, logging, cost.

The rules are `docs/reference/answer.md`, *The model call*. Nothing else imports google-genai.
"""

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import httpx2
from google import genai
from google.genai import errors, types
from pydantic import ValidationError

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


class _Retry(Exception):
    """A failure worth another attempt; the message is its reason."""


class LLM:
    def __init__(self, model: str | None = None, api_key: str | None = None, client=None,
                 sleep: Callable[[float], None] = time.sleep, clock: Callable[[], float] = time.monotonic):
        self.model = model or LLM_MODEL
        if self.model not in PRICES:
            raise ValueError(f"no price for model {self.model!r}; add it to src.llm.PRICES")
        if client is None:
            options = types.HttpOptions(timeout=TIMEOUT_S * 1000, retry_options=types.HttpRetryOptions(attempts=1))
            client = genai.Client(api_key=api_key or GOOGLE_API_KEYS[0], http_options=options)
        self._client, self._sleep, self._clock = client, sleep, clock
        self._last_start: float | None = None

    def _pace(self) -> None:
        if self._last_start is not None:
            wait = self._last_start + MIN_INTERVAL_S - self._clock()
            if wait > 0:
                self._sleep(wait)
        self._last_start = self._clock()

    def _attempt(self, system: str, user: str, schema: type, validate) -> tuple[Any, Any, float]:
        config = types.GenerateContentConfig(system_instruction=system, response_mime_type="application/json",
                                             response_schema=schema)
        self._pace()
        started = self._clock()
        try:
            response = self._client.models.generate_content(model=self.model, contents=user, config=config)
        except errors.ClientError as error:
            if error.code == 429:
                raise _Retry("429") from error
            raise LLMError(f"{self.model}: client error {error.code}") from error
        except errors.ServerError as error:
            raise _Retry(f"server error {error.code}") from error
        except httpx2.TransportError as error:
            raise _Retry(type(error).__name__) from error
        seconds = self._clock() - started
        parsed = response.parsed if isinstance(response.parsed, schema) else None
        if parsed is None:
            try:
                parsed = schema.model_validate_json(response.text or "")
            except ValidationError as error:
                raise _Retry("reply does not fit the schema") from error
        if validate is not None:
            try:
                validate(parsed)
            except ValueError as error:
                raise _Retry(f"reply refused: {error}") from error
        return parsed, response, seconds

    def generate(self, prompt: str, system: str, user: str, schema: type,
                 validate: Callable[[Any], None] | None = None) -> Call:
        for attempt in range(1, ATTEMPTS + 1):
            try:
                parsed, response, seconds = self._attempt(system, user, schema, validate)
            except _Retry as reason:
                log.warning("%s %s: attempt %d of %d failed: %s", self.model, prompt, attempt, ATTEMPTS, reason)
                if attempt == ATTEMPTS:
                    raise LLMError(f"{self.model} {prompt}: no usable reply after {ATTEMPTS} attempts") from reason
                self._sleep(BACKOFF_S * 2 ** (attempt - 1))
                continue
            usage = response.usage_metadata
            input_tokens = (usage.prompt_token_count or 0) if usage else 0
            output_tokens = ((usage.candidates_token_count or 0) + (usage.thoughts_token_count or 0)) if usage else 0
            prices = PRICES[self.model]
            cost = (input_tokens * prices[0] + output_tokens * prices[1]) / 1_000_000
            log.info("%s %s: %d input tokens, %d output tokens, %.2f s, %.5f USD, %d attempts",
                     self.model, prompt, input_tokens, output_tokens, seconds, cost, attempt)
            return Call(parsed, self.model, prompt, input_tokens, output_tokens, seconds, cost, attempt)
        raise AssertionError("unreachable")
