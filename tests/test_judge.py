"""The LLM judge of an eval run: EVAL-002, EVAL-003, EVAL-006 and AC-015. Approach approved on #15.

The rules are `docs/reference/answer.md`, *The judge*. A fake model returns fixed replies, so
nothing goes to the network.
"""

from pathlib import Path

import pytest

from src.answer import Answer, Citation, Sentence
from src.context import Context
from src.eval.judge import Judge, JudgeOutput
from src.llm import Call, LLMError

ROOT = Path(__file__).resolve().parent.parent
PROMPT = ROOT / "src" / "prompts" / "judge.md"
CONTEXT = Context(text="[1] [Luật 48/2024/QH15 — Thuế giá trị gia tăng] [Điều 5. Đối tượng]\nNội dung.\n\n"
                       "[2] [Luật 149/2025/QH15 — Sửa đổi] [Điều 1. Sửa đổi > Khoản 2]\nNội dung sửa đổi.",
                  tokens=20)


def answer(*sentences: tuple[str, tuple[str, ...]], flagged=()) -> Answer:
    ids = list(dict.fromkeys(i for _, citations in sentences for i in citations))
    return Answer(sentences=[Sentence(text, citations) for text, citations in sentences],
                  citations=[Citation(i, i not in flagged) for i in ids], flagged=list(flagged),
                  not_found=False, text="", context=CONTEXT)


def reply(sentences, facts, contradicts=False, says_amended=False) -> dict:
    return {"sentences": [{"cited_supports": c, "context_supports": s} for c, s in sentences],
            "key_facts": list(facts), "contradicts": contradicts, "says_amended": says_amended}


class FakeLLM:
    """Returns the replies in turn, as `LLM.generate` would: a reply `validate` refuses is retried."""

    def __init__(self, *replies: dict):
        self.replies = list(replies)
        self.requests: list[tuple] = []

    def generate(self, prompt, system, user, schema, validate=None):
        self.requests.append((prompt, system, user, schema))
        for attempt, payload in enumerate(list(self.replies), 1):
            self.replies.pop(0)
            parsed = schema.model_validate(payload)
            try:
                if validate:
                    validate(parsed)
            except ValueError:
                continue
            return Call(parsed, "gemini-3.5-flash-lite", prompt, 15000, 300, 2.0, 0.0012, attempt)
        raise LLMError("no usable reply")


TWO = answer(("Câu một.", ("1", "2")), ("Câu hai.", ()))
FACTS = ["Sự kiện một.", "Sự kiện hai."]


# --- The request ---------------------------------------------------------------------------------

def test_the_request_holds_the_context_question_sentences_and_key_facts():
    llm = FakeLLM(reply([(True, True), (False, True)], [True, True]))
    Judge(llm).judge("Câu hỏi?", FACTS, TWO)
    assert llm.requests == [("judge", PROMPT.read_text(encoding="utf-8"),
                             f"Passages:\n\n{CONTEXT.text}\n\nQuestion: Câu hỏi?\n\n"
                             "Answer sentences:\n1. Câu một. [1][2]\n2. Câu hai.\n\n"
                             "Key facts:\n1. Sự kiện một.\n2. Sự kiện hai.",
                             JudgeOutput)]


def test_the_amended_provisions_are_listed_when_asked_about():
    llm = FakeLLM(reply([(True, True), (False, True)], [True, True], says_amended=True))
    Judge(llm).judge("Câu hỏi?", FACTS, TWO, amended=("1.25", "3"))
    assert llm.requests
    assert llm.requests[0][2].endswith("\n\nAmended provisions: [1.25], [3]")


# --- The verdict ---------------------------------------------------------------------------------

def test_the_verdict_follows_the_reply_per_sentence_and_per_fact():
    llm = FakeLLM(reply([(True, True), (True, False)], [True, False], contradicts=False))
    verdict = Judge(llm).judge("Câu hỏi?", FACTS, TWO)
    assert verdict.cited == (True, None)  # the second sentence has no id
    assert verdict.supported == (True, False)
    assert verdict.facts == (True, False)
    assert verdict.contradicts is False
    assert verdict.call is not None and verdict.call.input_tokens == 15000


@pytest.mark.parametrize("facts, contradicts, correct", [
    ([True, True], False, True),
    ([True, False], False, False),
    ([True, True], True, False),
])
def test_an_answer_is_correct_when_it_states_every_fact_and_contradicts_none(facts, contradicts, correct):
    llm = FakeLLM(reply([(True, True), (False, True)], facts, contradicts=contradicts))
    verdict = Judge(llm).judge("Câu hỏi?", FACTS, TWO)
    assert (verdict.facts, verdict.contradicts) == (tuple(facts), contradicts)
    assert verdict.correct is correct


def test_a_sentence_citing_only_flagged_ids_is_not_supported_by_its_citations():
    flagged = answer(("Câu một.", ("7",)), ("Câu hai.", ("1", "8")), flagged=("7", "8"))
    llm = FakeLLM(reply([(True, True), (True, True)], [True, True]))
    verdict = Judge(llm).judge("Câu hỏi?", FACTS, flagged)
    assert verdict.cited == (False, True)
    assert llm.requests and "1. Câu một. [7]\n2. Câu hai. [1][8]" in llm.requests[0][2]


def test_says_amended_is_none_unless_asked():
    llm = FakeLLM(reply([(True, True), (False, True)], [True, True], says_amended=True))
    assert Judge(llm).judge("Câu hỏi?", FACTS, TWO).says_amended is None
    llm = FakeLLM(reply([(True, True), (False, True)], [True, True], says_amended=False))
    assert Judge(llm).judge("Câu hỏi?", FACTS, TWO, amended=("1",)).says_amended is False


@pytest.mark.parametrize("wrong", [
    reply([(True, True)], [True, True]),
    reply([(True, True), (False, True)], [True]),
], ids=["sentences", "key-facts"])
def test_a_reply_of_the_wrong_length_is_refused_and_retried(wrong):
    llm = FakeLLM(wrong, reply([(True, True), (False, False)], [True, True]))
    verdict = Judge(llm).judge("Câu hỏi?", FACTS, TWO)
    assert verdict.supported == (True, False)
    assert verdict.call is not None and verdict.call.attempts == 2
