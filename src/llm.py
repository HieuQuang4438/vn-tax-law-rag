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

PRICES = {"gemini-3.5-flash-lite": (0.30, 2.50),  # USD per 1M tokens, input and output (ADR-0003)
          "gemini-3.8-flash": (0.75, 3.75),  # through 2026-12-31, then 1.50 / 7.50 (pricing page, 2026-11-21)
          "gemini-4-hydrogen": (1.50, 7.50)}  # pricing page, 2026-11-21
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
    """No usable reply. `quota`: the last attempt failed with 429 on every key (answer.md, *Retries*)."""

    def __init__(self, message: str = "", quota: bool = False):
        super().__init__(message)
        self.quota = quota


class _Retry(Exception):
    """A failure worth another attempt; the message is its reason. `quota`: every key answered it with 429."""

    def __init__(self, message: str, quota: bool = False):
        super().__init__(message)
        self.quota = quota


class LLM:
    def __init__(self, model: str | None = None, api_keys: tuple[str, ...] | list[str] | None = None,
                 clients: list | None = None, sleep: Callable[[float], None] = time.sleep,
                 clock: Callable[[], float] = time.monotonic, seed: int | None = None):
        self.model = model or LLM_MODEL
        self.seed = seed  # sent on every attempt when set (answer.md, *Seed*, #37)
        if self.model not in PRICES:
            raise ValueError(f"no price for model {self.model!r}; add it to src.llm.PRICES")
        if clients is None:
            options = types.HttpOptions(timeout=TIMEOUT_S * 1000, retry_options=types.HttpRetryOptions(attempts=1))
            clients = [genai.Client(api_key=key, http_options=options) for key in (api_keys or GOOGLE_API_KEYS)]
        self._clients = list(clients)
        self.keys = len(self._clients)
        self._current = 0  # the key requests go out with (answer.md, *Keys*)
        self._sleep, self._clock = sleep, clock
        self._last_start: float | None = None

    def _pace(self) -> None:
        if self._last_start is not None:
            wait = self._last_start + MIN_INTERVAL_S - self._clock()
            if wait > 0:
                self._sleep(wait)
        self._last_start = self._clock()

    def _send(self, user: str, config) -> tuple[Any, float]:
        """One attempt: the current key first; a 429 or a 5xx moves to the next key at once."""
        quota = True  # every key so far answered with 429
        for _ in range(self.keys):
            self._pace()
            started = self._clock()
            try:
                response = self._clients[self._current].models.generate_content(model=self.model, contents=user,
                                                                                 config=config)
                return response, self._clock() - started
            except errors.ClientError as error:
                if error.code != 429:
                    raise LLMError(f"{self.model}: client error {error.code}") from error
                reason, last = "429", error
            except errors.ServerError as error:
                reason, last, quota = f"server error {error.code}", error, False
            except httpx2.TransportError as error:
                raise _Retry(type(error).__name__) from error
            following = (self._current + 1) % self.keys
            if self.keys > 1:
                log.warning("%s: %s on key %d of %d, moving to key %d of %d",
                            self.model, reason, self._current + 1, self.keys, following + 1, self.keys)
            self._current = following
        raise _Retry(reason if self.keys == 1 else f"429 or 5xx on every key, the last {reason}", quota) from last

    def _attempt(self, system: str, user: str, schema: type, validate) -> tuple[Any, Any, float]:
        config = types.GenerateContentConfig(system_instruction=system, response_mime_type="application/json",
                                             response_schema=schema, seed=self.seed)
        response, seconds = self._send(user, config)
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
                    raise LLMError(f"{self.model} {prompt}: no usable reply after {ATTEMPTS} attempts",
                                   reason.quota) from reason
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
