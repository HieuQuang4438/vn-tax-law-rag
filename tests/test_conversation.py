"""FR-CORE-016 multi-turn conversation. Approach approved on #19.
AC-014: every follow-up turn goes through the rewriter before retrieval, and every first turn is
passed through unchanged.

The rules are `docs/reference/conversation.md`. Unit tests use a fake model, retriever and
answerer, so nothing goes to the network.
"""

import pytest

from src.conversation import EARLIER, PROMPT, REWRITERS, Rewrite, RewriteOutput, Session, rewriter
from src.llm import Call
from src.retrieval import Hit, Retrieval

Q1 = "Thuế suất thuế giá trị gia tăng đối với cửa hàng tạp hóa là bao nhiêu?"
Q2 = "Còn hộ kinh doanh thì sao?"
Q3 = "Khai thuế theo quý hay theo năm?"
REWRITTEN = "Hộ kinh doanh tạp hóa nộp thuế giá trị gia tăng theo tỷ lệ bao nhiêu?"


class FakeLLM:
    """Returns the given question for every call and records each request."""

    model = "gemini-3.5-flash-lite"

    def __init__(self, question: str = REWRITTEN):
        self.question = question
        self.requests: list[tuple] = []

    def generate(self, prompt, system, user, schema, validate=None):
        self.requests.append((prompt, system, user, schema, validate))
        return Call(schema.model_validate({"question": self.question}), self.model, prompt, 300, 40, 0.8, 0.0001, 1)


# --- Rewriters ----------------------------------------------------------------------------------

def test_the_rewriters_and_how_many_earlier_questions_they_read():
    assert REWRITERS == ("none", "concat", "fuse", "llm")
    assert EARLIER == 2
    assert [rewriter(name, FakeLLM()).name for name in REWRITERS] == list(REWRITERS)


def test_the_default_rewriter_is_concat_as_chosen_on_19():
    import src.conversation as conversation

    assert getattr(conversation, "DEFAULT_REWRITER", None) == "concat"


def test_a_session_uses_the_default_rewriter_unless_given_another():
    assert getattr(Session(FakeRetriever(), FakeAnswerer(), None).rewriter, "name", None) == "concat"
    assert Session(FakeRetriever(), FakeAnswerer(), rewriter("fuse")).rewriter.name == "fuse"


def test_an_unknown_rewriter_is_refused():
    with pytest.raises(ValueError):
        rewriter("rerank")


@pytest.mark.parametrize("name", REWRITERS)
def test_ac014_a_first_turn_is_passed_through_unchanged_without_a_call(name):
    llm = FakeLLM()
    assert rewriter(name, llm).rewrite(Q1) == Rewrite(Q1, (Q1,))
    assert llm.requests == []


def test_none_keeps_a_follow_up_as_written():
    assert rewriter("none").rewrite(Q2, [Q1]) == Rewrite(Q2, (Q2,))


def test_concat_joins_the_earlier_questions_and_the_follow_up_in_order():
    assert rewriter("concat").rewrite(Q2, [Q1]) == Rewrite(f"{Q1} {Q2}", (f"{Q1} {Q2}",))


def test_a_rewriter_reads_the_last_earlier_questions_only():
    rewrite = rewriter("concat").rewrite(Q3, ["Câu hỏi đầu tiên?", Q1, Q2])
    assert rewrite.queries == (f"{Q1} {Q2} {Q3}",)


def test_fuse_retrieves_the_follow_up_and_the_concatenation():
    rewrite = rewriter("fuse").rewrite(Q2, [Q1])
    assert (rewrite.question, rewrite.queries, rewrite.call) == (f"{Q1} {Q2}", (Q2, f"{Q1} {Q2}"), None)


def test_llm_asks_the_model_with_the_prompt_and_the_earlier_questions():
    llm = FakeLLM()
    rewriter("llm", llm).rewrite(Q3, [Q1, Q2])
    assert len(llm.requests) == 1
    prompt, system, user, schema, validate = llm.requests[0]
    assert (prompt, system, schema) == ("rewrite", PROMPT.read_text(encoding="utf-8"), RewriteOutput)
    assert user == f"Earlier questions:\n1. {Q1}\n2. {Q2}\n\nFollow-up: {Q3}"
    assert validate is not None


def test_llm_returns_the_models_question_trimmed_with_its_call():
    rewrite = rewriter("llm", FakeLLM(f"  {REWRITTEN} \n")).rewrite(Q2, [Q1])
    assert (rewrite.question, rewrite.queries) == (REWRITTEN, (REWRITTEN,))
    assert rewrite.call is not None and rewrite.call.prompt == "rewrite"
    assert rewrite.latency_s == pytest.approx(0.8)


def test_llm_refuses_an_empty_question_so_the_call_retries():
    llm = FakeLLM()
    rewriter("llm", llm).rewrite(Q2, [Q1])
    validate = llm.requests[0][4] if llm.requests else None
    assert validate is not None
    with pytest.raises(ValueError):
        validate(RewriteOutput(question=" \n"))
    validate(RewriteOutput(question=REWRITTEN))


def test_the_prompt_asks_for_one_standalone_question_and_keeps_one_that_stands_alone():
    prompt = PROMPT.read_text(encoding="utf-8")
    assert "one\nstandalone question" in prompt or "one standalone question" in prompt
    assert "Do not answer the question" in prompt
    assert "If the follow-up already stands alone, return it unchanged." in prompt


# --- The session --------------------------------------------------------------------------------

class FakeRetriever:
    def __init__(self):
        self.calls: list[tuple] = []

    def retrieve(self, question, k=8):
        self.calls.append(("retrieve", question, k))
        return Retrieval([Hit("379409:D9", ("keyword",), 0.5)], [])

    def fuse(self, questions, k=8):
        self.calls.append(("fuse", tuple(questions), k))
        return Retrieval([Hit("379409:D5:K25", ("keyword", "vector"), 0.03)], [])


class FakeAnswerer:
    def __init__(self):
        self.calls: list[tuple] = []

    def answer(self, question, retrieval):
        self.calls.append((question, retrieval))
        return f"answer {len(self.calls)}"


class Recording:
    """A rewriter that records what it was given."""

    def __init__(self, inner):
        self.inner, self.name, self.calls = inner, inner.name, []

    def rewrite(self, question, earlier=()):
        self.calls.append((question, tuple(earlier)))
        return self.inner.rewrite(question, earlier)


def test_a_session_keeps_its_turns_and_gives_each_the_questions_before_it():
    recording = Recording(rewriter("concat"))
    session = Session(FakeRetriever(), FakeAnswerer(), recording)
    turns = [session.ask(q) for q in (Q1, Q2, Q3)]
    assert recording.calls == [(Q1, ()), (Q2, (Q1,)), (Q3, (Q1, Q2))]
    assert session.turns == turns
    assert [t.question for t in session.turns] == [Q1, Q2, Q3]


def test_ac014_a_first_turn_is_retrieved_and_answered_as_asked():
    retriever, answerer = FakeRetriever(), FakeAnswerer()
    turn = Session(retriever, answerer, rewriter("concat")).ask(Q1)
    assert retriever.calls == [("retrieve", Q1, 8)]
    assert answerer.calls == [(Q1, turn.retrieval)]
    assert turn.rewrite == Rewrite(Q1, (Q1,))


def test_ac014_a_follow_up_is_retrieved_and_answered_with_its_rewrite():
    retriever, answerer = FakeRetriever(), FakeAnswerer()
    session = Session(retriever, answerer, rewriter("concat"))
    session.ask(Q1)
    turn = session.ask(Q2)
    assert retriever.calls[1:] == [("retrieve", f"{Q1} {Q2}", 8)]
    assert answerer.calls[1:] == [(f"{Q1} {Q2}", turn.retrieval)]
    assert (turn.question, turn.answer) == (Q2, "answer 2")


def test_two_queries_are_fused_and_generation_gets_the_concatenation():
    retriever, answerer = FakeRetriever(), FakeAnswerer()
    session = Session(retriever, answerer, rewriter("fuse"), k=5)
    session.ask(Q1)
    turn = session.ask(Q2)
    assert retriever.calls == [("retrieve", Q1, 5), ("fuse", (Q2, f"{Q1} {Q2}"), 5)]
    assert [h.chunk_id for h in turn.retrieval.hits] == ["379409:D5:K25"]
    assert [question for question, _ in answerer.calls] == [Q1, f"{Q1} {Q2}"]


def test_generation_sees_the_rewritten_question_not_the_earlier_turns():
    """Choice 2A on #19: the standalone question and the passages, as for a standalone question."""
    retriever, answerer = FakeRetriever(), FakeAnswerer()
    session = Session(retriever, answerer, rewriter("llm", FakeLLM()))
    session.ask(Q1)
    session.ask(Q2)
    assert retriever.calls[1:] == [("retrieve", REWRITTEN, 8)]
    assert [question for question, _ in answerer.calls] == [Q1, REWRITTEN]


# --- Without a session (#30, choice 6A) ------------------------------------------------------------

def test_ask_rewrites_with_the_given_earlier_questions_and_returns_the_turn():
    from src.conversation import ask

    recording = Recording(rewriter("concat"))
    retriever, answerer = FakeRetriever(), FakeAnswerer()
    turn = ask(retriever, answerer, Q2, [Q1], recording)
    assert recording.calls == [(Q2, (Q1,))]
    assert retriever.calls == [("retrieve", f"{Q1} {Q2}", 8)]
    assert answerer.calls == [(f"{Q1} {Q2}", turn.retrieval)]
    assert (turn.question, turn.answer) == (Q2, "answer 1")


def test_ask_passes_a_first_question_through_with_the_default_rewriter():
    from src.conversation import ask

    retriever = FakeRetriever()
    turn = ask(retriever, FakeAnswerer(), Q1)
    assert turn.rewrite == Rewrite(Q1, (Q1,))
    assert retriever.calls == [("retrieve", Q1, 8)]


def test_ask_uses_the_default_rewriter_and_k_unless_given_others():
    from src.conversation import ask

    retriever = FakeRetriever()
    ask(retriever, FakeAnswerer(), Q2, [Q1])
    ask(retriever, FakeAnswerer(), Q2, [Q1], rewriter("fuse"), k=5)
    assert retriever.calls == [("retrieve", f"{Q1} {Q2}", 8), ("fuse", (Q2, f"{Q1} {Q2}"), 5)]


def test_ask_gives_the_turn_a_session_with_the_same_earlier_questions_gives():
    from src.conversation import ask

    session = Session(FakeRetriever(), FakeAnswerer(), rewriter("concat"))
    session.ask(Q1)
    session.ask(Q2)
    expected = session.ask(Q3)
    turn = ask(FakeRetriever(), FakeAnswerer(), Q3, [Q1, Q2], rewriter("concat"))
    assert (turn.question, turn.rewrite, turn.retrieval) == (expected.question, expected.rewrite, expected.retrieval)


def test_ask_keeps_nothing_between_calls():
    from src.conversation import ask

    retriever, answerer = FakeRetriever(), FakeAnswerer()
    first = ask(retriever, answerer, Q2, [Q1])
    second = ask(retriever, answerer, Q2, [Q1])
    assert first.rewrite == second.rewrite
    assert retriever.calls[0] == retriever.calls[1]
