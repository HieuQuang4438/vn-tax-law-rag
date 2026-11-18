"""The one wrapper around the Gemini API (CONVENTIONS §5). Approach approved on #15.

The rules are `docs/reference/answer.md`, *The model call*. A fake client stands in for
google-genai, and a fake clock for time, so nothing goes to the network and nothing sleeps.
"""

import json
import logging
import socket
from types import SimpleNamespace

import httpx2
import pytest
from google.genai import errors
from pydantic import BaseModel

from src.llm import ATTEMPTS, BACKOFF_S, MIN_INTERVAL_S, PRICES, PRICES_READ, TIMEOUT_S, LLM, LLMError


class Reply(BaseModel):
    words: list[str]


def response(payload, prompt_tokens=1000, answer_tokens=200, thinking_tokens=50):
    """A google-genai response in the shape `generate_content` returns."""
    text = payload if isinstance(payload, str) else json.dumps(payload)
    try:
        parsed = Reply.model_validate_json(text)
    except ValueError:
        parsed = None
    usage = SimpleNamespace(prompt_token_count=prompt_tokens, candidates_token_count=answer_tokens,
                            thoughts_token_count=thinking_tokens)
    return SimpleNamespace(text=text, parsed=parsed, usage_metadata=usage,
                           candidates=[SimpleNamespace(finish_reason="STOP")])


def api_error(kind, code):
    return kind(code, {"error": {"code": code, "message": "refused", "status": "UNAVAILABLE"}})


class FakeClock:
    """`clock` and `sleep` for the wrapper: sleeping moves the clock; each request takes 1.5 s."""

    def __init__(self):
        self.now = 1000.0
        self.slept: list[float] = []

    def clock(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds


class FakeClient:
    def __init__(self, replies, clock: FakeClock):
        self.replies, self.clock = list(replies), clock
        self.requests: list[dict] = []
        self.models = self

    def generate_content(self, model, contents, config):
        self.requests.append({"model": model, "contents": contents, "config": config, "at": self.clock.now})
        self.clock.now += 1.5
        assert self.replies, "a request this key has no reply for"
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


def wrapper(*replies, model="gemini-3.5-flash-lite"):
    clock = FakeClock()
    client = FakeClient(replies, clock)
    return LLM(model=model, api_keys=["dummy"], clients=[client], sleep=clock.sleep, clock=clock.clock), client, clock


def rotating(*per_key: list):
    """A wrapper over one fake client per key, each with its own replies."""
    clock = FakeClock()
    clients = [FakeClient(replies, clock) for replies in per_key]
    keys = [f"dummy-{n}" for n in range(1, len(per_key) + 1)]
    return LLM(api_keys=keys, clients=clients, sleep=clock.sleep, clock=clock.clock), clients, clock


GOOD = {"words": ["một", "hai"]}


# --- The request ---------------------------------------------------------------------------------

def test_the_request_carries_the_system_instruction_the_user_text_and_the_schema():
    llm, client, _ = wrapper(response(GOOD))
    llm.generate("answer", "system text", "user text", Reply)
    assert len(client.requests) == 1
    request = client.requests[0]
    assert request["model"] == "gemini-3.5-flash-lite"
    assert request["contents"] == "user text"
    config = request["config"]
    assert config.system_instruction == "system text"
    assert config.response_mime_type == "application/json"
    assert config.response_schema is Reply


def test_the_request_sets_no_sampling_or_thinking_parameter():
    """Deprecated and ignored on gemini-3.5-flash-lite; the thinking level is the model's default."""
    llm, client, _ = wrapper(response(GOOD))
    llm.generate("answer", "system", "user", Reply)
    assert client.requests
    config = client.requests[0]["config"]
    assert (config.temperature, config.top_p, config.top_k, config.thinking_config) == (None, None, None, None)


def test_the_constants_are_the_specified_ones():
    assert PRICES["gemini-3.5-flash-lite"] == (0.30, 2.50)
    assert PRICES_READ == "2026-11-16"
    assert (TIMEOUT_S, MIN_INTERVAL_S, BACKOFF_S, ATTEMPTS) == (60, 4.0, 10, 5)


def test_a_model_without_a_price_is_refused():
    with pytest.raises(ValueError, match="gemini-9-unknown"):
        LLM(model="gemini-9-unknown", api_keys=["dummy"], clients=[FakeClient([], FakeClock())])


# --- The call ------------------------------------------------------------------------------------

def test_the_call_carries_the_parsed_reply_tokens_latency_and_cost():
    llm, _, _ = wrapper(response(GOOD, prompt_tokens=1000, answer_tokens=200, thinking_tokens=50))
    call = llm.generate("answer", "system", "user", Reply)
    assert call.parsed == Reply(words=["một", "hai"])
    assert (call.model, call.prompt) == ("gemini-3.5-flash-lite", "answer")
    assert (call.input_tokens, call.output_tokens) == (1000, 250)
    assert call.latency_s == pytest.approx(1.5)
    assert call.cost_usd == pytest.approx((1000 * 0.30 + 250 * 2.50) / 1_000_000)
    assert call.attempts == 1


def test_a_reply_is_validated_against_the_schema_when_the_sdk_did_not_parse_it():
    reply = response(GOOD)
    reply.parsed = None
    llm, _, _ = wrapper(reply)
    assert llm.generate("answer", "system", "user", Reply).parsed == Reply(words=["một", "hai"])


# --- Pacing --------------------------------------------------------------------------------------

def test_two_calls_start_at_least_four_seconds_apart():
    llm, client, clock = wrapper(response(GOOD), response(GOOD))
    llm.generate("answer", "system", "user", Reply)
    llm.generate("answer", "system", "user", Reply)
    assert len(client.requests) == 2
    assert client.requests[1]["at"] - client.requests[0]["at"] == pytest.approx(MIN_INTERVAL_S)
    assert clock.slept == [pytest.approx(MIN_INTERVAL_S - 1.5)]


# --- Retries -------------------------------------------------------------------------------------

@pytest.mark.parametrize("failure", [
    api_error(errors.ClientError, 429),
    api_error(errors.ServerError, 503),
    httpx2.ConnectError("connection dropped"),
    httpx2.ReadTimeout("timed out"),
    response("not json at all"),
    response({"words": "not a list"}),
], ids=["429", "503", "dropped", "timeout", "not-json", "wrong-shape"])
def test_a_retryable_failure_is_tried_again_after_the_backoff(failure):
    llm, client, clock = wrapper(failure, response(GOOD))
    call = llm.generate("answer", "system", "user", Reply)
    assert call.parsed == Reply(words=["một", "hai"])
    assert call.attempts == 2
    assert len(client.requests) == 2
    assert BACKOFF_S in clock.slept


def test_a_reply_refused_by_validate_is_tried_again():
    def validate(reply):
        if len(reply.words) != 2:
            raise ValueError("two words expected")

    llm, client, _ = wrapper(response({"words": ["một"]}), response(GOOD))
    call = llm.generate("answer", "system", "user", Reply, validate=validate)
    assert call.parsed == Reply(words=["một", "hai"])
    assert len(client.requests) == 2


def test_the_backoff_doubles_and_the_fifth_failure_raises():
    llm, client, clock = wrapper(*[api_error(errors.ServerError, 500)] * 5)
    with pytest.raises(LLMError):
        llm.generate("answer", "system", "user", Reply)
    assert len(client.requests) == ATTEMPTS
    assert [s for s in clock.slept if s >= BACKOFF_S] == [10, 20, 40, 80]


@pytest.mark.parametrize("code", [400, 403, 404])
def test_any_other_client_error_raises_at_once(code):
    llm, client, _ = wrapper(api_error(errors.ClientError, code), response(GOOD))
    with pytest.raises(LLMError):
        llm.generate("answer", "system", "user", Reply)
    assert len(client.requests) == 1


def test_the_latency_is_that_of_the_attempt_that_succeeded():
    llm, _, _ = wrapper(api_error(errors.ClientError, 429), response(GOOD))
    call = llm.generate("answer", "system", "user", Reply)
    assert call.attempts == 2
    assert call.latency_s == pytest.approx(1.5)


# --- Keys (choice 9B widened to 5xx, approved on #15) ------------------------------------------

REFUSED = api_error(errors.ClientError, 429)
BUSY = api_error(errors.ServerError, 503)


def test_the_default_is_every_key_of_the_config():
    from src.config import GOOGLE_API_KEYS

    assert LLM().keys == len(GOOGLE_API_KEYS)
    assert LLM(api_keys=["a", "b", "c"]).keys == 3


@pytest.mark.parametrize("failure", [REFUSED, BUSY, api_error(errors.ServerError, 500)], ids=["429", "503", "500"])
def test_a_429_or_a_5xx_moves_to_the_next_key_at_once(failure):
    llm, clients, clock = rotating([failure], [response(GOOD)])
    call = llm.generate("answer", "system", "user", Reply)
    assert call.parsed == Reply(words=["một", "hai"])
    assert call.attempts == 1
    assert (len(clients[0].requests), len(clients[1].requests)) == (1, 1)
    assert all(s < BACKOFF_S for s in clock.slept)  # pacing only, no backoff


def test_the_new_key_stays_current_for_the_next_call():
    llm, clients, _ = rotating([BUSY], [response(GOOD), response(GOOD)])
    llm.generate("answer", "system", "user", Reply)
    llm.generate("answer", "system", "user", Reply)
    assert (len(clients[0].requests), len(clients[1].requests)) == (1, 2)


def test_after_the_last_key_the_first_comes_again():
    llm, clients, _ = rotating([REFUSED, response(GOOD)], [response(GOOD), BUSY], [REFUSED])
    llm.generate("answer", "system", "user", Reply)  # key 1 refuses, key 2 answers
    call = llm.generate("answer", "system", "user", Reply)  # key 2 is busy, key 3 refuses, key 1 answers
    assert call.attempts == 1
    assert [len(c.requests) for c in clients] == [2, 2, 1]


def test_an_attempt_fails_only_when_every_key_refused_it_or_was_busy():
    llm, clients, clock = rotating([REFUSED, response(GOOD)], [BUSY])
    call = llm.generate("answer", "system", "user", Reply)
    assert call.attempts == 2
    assert [s for s in clock.slept if s >= BACKOFF_S] == [BACKOFF_S]
    assert (len(clients[0].requests), len(clients[1].requests)) == (2, 1)


@pytest.mark.parametrize("failure", [
    httpx2.ConnectError("connection dropped"),
    httpx2.ReadTimeout("timed out"),
    response("not json at all"),
], ids=["dropped", "timeout", "not-json"])
def test_other_failures_retry_on_the_same_key_after_the_backoff(failure):
    llm, clients, clock = rotating([failure, response(GOOD)], [response(GOOD)])
    call = llm.generate("answer", "system", "user", Reply)
    assert call.attempts == 2
    assert (len(clients[0].requests), len(clients[1].requests)) == (2, 0)
    assert BACKOFF_S in clock.slept


def test_a_key_change_is_logged_by_position_with_its_reason(caplog):
    caplog.set_level(logging.INFO, logger="src.llm")
    llm, _, _ = rotating([BUSY], [response(GOOD)])
    llm.generate("answer", "system", "user", Reply)
    changes = [r.getMessage() for r in caplog.records if r.name == "src.llm" and "moving to key" in r.getMessage()]
    assert len(changes) == 1
    assert "503" in changes[0] and "key 1 of 2" in changes[0] and "key 2 of 2" in changes[0]
    logged = " ".join(r.getMessage() for r in caplog.records if r.name == "src.llm")
    assert "dummy-1" not in logged and "dummy-2" not in logged


# --- Log -----------------------------------------------------------------------------------------

def test_each_call_logs_one_line_without_the_key_or_the_texts(caplog):
    caplog.set_level(logging.INFO, logger="src.llm")
    llm, _, _ = wrapper(api_error(errors.ClientError, 429), response(GOOD))
    llm.generate("answer", "SYSTEM-SECRET-TEXT", "USER-SECRET-TEXT", Reply)
    infos = [r for r in caplog.records if r.name == "src.llm" and r.levelno == logging.INFO]
    warnings = [r for r in caplog.records if r.name == "src.llm" and r.levelno == logging.WARNING]
    assert len(infos) == 1 and len(warnings) == 1
    line = infos[0].getMessage()
    for expected in ("gemini-3.5-flash-lite", "answer", "1000", "250"):
        assert expected in line
    logged = " ".join(r.getMessage() for r in caplog.records)
    for secret in ("dummy", "SYSTEM-SECRET-TEXT", "USER-SECRET-TEXT", "một"):
        assert secret not in logged


def test_the_wrapper_makes_no_network_request_with_a_fake_client(monkeypatch):
    attempts = []
    monkeypatch.setattr(socket.socket, "connect", lambda sock, address: attempts.append(address))
    llm, client, _ = wrapper(response(GOOD))
    llm.generate("answer", "system", "user", Reply)
    assert len(client.requests) == 1
    assert attempts == []


# --- Quota (#30, choice 2A) ------------------------------------------------------------------------

def raised_by(llm) -> LLMError:
    with pytest.raises(LLMError) as raised:
        llm.generate("answer", "system", "user", Reply)
    return raised.value


def test_a_429_on_the_one_key_at_every_attempt_is_a_quota_error():
    llm, _, _ = wrapper(*[REFUSED] * ATTEMPTS)
    assert raised_by(llm).quota is True


def test_a_429_on_every_key_of_the_last_attempt_is_a_quota_error():
    llm, _, _ = rotating([REFUSED] * ATTEMPTS, [REFUSED] * ATTEMPTS)
    assert raised_by(llm).quota is True


def test_a_5xx_on_any_key_of_the_last_attempt_is_not_a_quota_error():
    llm, _, _ = rotating([REFUSED] * ATTEMPTS, [BUSY] * ATTEMPTS)
    assert raised_by(llm).quota is False


@pytest.mark.parametrize("failures", [
    [api_error(errors.ServerError, 500)] * ATTEMPTS,
    [httpx2.ReadTimeout("timed out")] * ATTEMPTS,
    [REFUSED] * (ATTEMPTS - 1) + [response("not json at all")],
    [api_error(errors.ClientError, 400)],
], ids=["5xx", "timeout", "429-then-not-json", "400"])
def test_any_other_failure_is_not_a_quota_error(failures):
    llm, _, _ = wrapper(*failures)
    assert raised_by(llm).quota is False
