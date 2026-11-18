"""FR-CORE-013/014 web chat page. Approach approved on #17.
AC-010: the web interface answers a question end to end, shows citations as links to the
source, and shows the not-advice notice.

The rules are `docs/reference/web.md`. Streamlit's AppTest runs the page with a fake retriever
and a fake answerer, so nothing loads the index and nothing goes to the network.
"""

from pathlib import Path

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from src.answer import NOT_FOUND, Answer, Citation, Sentence
from src.app import ERROR, LOAD_ERROR, NOTICE
from src.conversation import Session
from src.llm import LLMError
from src.retrieval import Hit, IndexNotReadyError, Retrieval, Retriever

APP = Path(__file__).resolve().parents[1] / "src" / "app.py"
Q1 = "Thuế suất thuế giá trị gia tăng đối với cửa hàng tạp hóa là bao nhiêu?"
Q2 = "Còn hộ kinh doanh thì sao?"
URL = "https://luatvietnam.vn/thue/luat-thue-gia-tri-gia-tang-379409-d1.html"
LINK = f"[Luật 48/2024/QH15, Điều 5, khoản 25]({URL}#:~:text=%C4%90i%E1%BB%81u%205.)"
SENTENCE = "Hộ kinh doanh có doanh thu năm từ 200 triệu đồng trở xuống không chịu thuế giá trị gia tăng."


def cited() -> Answer:
    citation = Citation("1.25", True, "1", "Luật 48/2024/QH15", "5", "25", f"{URL}#:~:text=%C4%90i%E1%BB%81u%205.")
    text = f"{SENTENCE} [1.25]\n\nNguồn:\n- [1.25] {LINK}"
    return Answer([Sentence(SENTENCE, ("1.25",))], [citation], [], False, text)


def not_found() -> Answer:
    return Answer([Sentence(NOT_FOUND, ())], [], [], True, NOT_FOUND)


class FakeRetriever:
    def __init__(self):
        self.queries: list[str] = []

    def retrieve(self, query, k=8):
        self.queries.append(query)
        return Retrieval([Hit("379409.5.25", ("vector",), 0.1)])

    def fuse(self, questions, k=8):
        self.queries.extend(questions)
        return Retrieval([Hit("379409.5.25", ("vector",), 0.1)])


class FakeAnswerer:
    """Returns the given answers in order; raises an exception given in their place."""

    def __init__(self, *answers):
        self.answers = list(answers)
        self.questions: list[str] = []

    def answer(self, question, retrieval):
        self.questions.append(question)
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer


@pytest.fixture(autouse=True)
def fresh_cache():
    st.cache_resource.clear()
    yield
    st.cache_resource.clear()


def page(session: Session | None = None) -> AppTest:
    app = AppTest.from_file(str(APP), default_timeout=30)
    if session is not None:
        app.session_state["session"] = session
    app.run()
    return app


def ask(app: AppTest, question: str) -> AppTest:
    app.chat_input[0].set_value(question).run()
    return app


def markdowns(block) -> list[str]:
    return [m.value for m in block.markdown]


def assistant(app: AppTest) -> list:
    return [m for m in app.chat_message if m.name == "assistant"]


# --- AC-010 -------------------------------------------------------------------------------------

def test_ac010_a_question_gets_its_answer_with_the_sources_as_links():
    app = ask(page(Session(FakeRetriever(), FakeAnswerer(cited()))), Q1)
    assert [e.value for e in app.exception] == []
    assert [[m.value for m in message.markdown] for message in app.chat_message if message.name == "user"] == [[Q1]]
    answers = [markdowns(m) for m in assistant(app)]
    assert len(answers) == 1 and cited().text in answers[0]
    assert LINK in answers[0][answers[0].index(cited().text)]


def test_fr_core_013_the_notice_is_under_every_answer_a_not_found_one_included():
    app = ask(ask(page(Session(FakeRetriever(), FakeAnswerer(cited(), not_found()))), Q1), Q2)
    assert [[c.value for c in m.caption] for m in assistant(app)] == [[NOTICE], [NOTICE]]
    assert NOT_FOUND in markdowns(assistant(app)[1])


def test_the_notice_is_not_part_of_the_answer_text():
    app = ask(page(Session(FakeRetriever(), FakeAnswerer(cited()))), Q1)
    turns = app.session_state["session"].turns
    assert [turn.answer.text for turn in turns] == [cited().text]
    assert [NOTICE in m for m in markdowns(assistant(app)[0])] == [False] * len(markdowns(assistant(app)[0]))


def test_a_follow_up_goes_to_the_same_session_through_concat():
    retriever, answerer = FakeRetriever(), FakeAnswerer(cited(), cited())
    session = Session(retriever, answerer)
    app = ask(ask(page(session), Q1), Q2)
    assert app.session_state["session"] is session
    assert len(session.turns) == 2
    assert retriever.queries == [Q1, f"{Q1} {Q2}"]
    assert answerer.questions == [Q1, f"{Q1} {Q2}"]


def test_every_turn_is_shown_again_on_the_next_run():
    app = ask(ask(page(Session(FakeRetriever(), FakeAnswerer(cited(), not_found()))), Q1), Q2)
    app.run()
    assert [m.name for m in app.chat_message] == ["user", "assistant", "user", "assistant"]
    assert [[c.value for c in m.caption] for m in assistant(app)] == [[NOTICE], [NOTICE]]


def test_an_answer_shows_its_text_and_the_notice_only_with_no_details():
    app = ask(ask(page(Session(FakeRetriever(), FakeAnswerer(cited(), not_found()))), Q1), Q2)
    assert [[e.label for e in m.expander] for m in assistant(app)] == [[], []]
    assert [(markdowns(m), [c.value for c in m.caption], [t.value for t in m.text]) for m in assistant(app)] == [
        ([cited().text], [NOTICE], []), ([NOT_FOUND], [NOTICE], [])]


# --- Errors and a new conversation --------------------------------------------------------------

def test_a_failed_model_call_shows_the_error_and_keeps_no_turn():
    session = Session(FakeRetriever(), FakeAnswerer(LLMError("no usable reply")))
    app = ask(page(session), Q1)
    assert [e.value for e in app.exception] == []
    assert [e.value for m in assistant(app) for e in m.error] == [ERROR]
    assert session.turns == []
    app.run()
    assert [m.name for m in app.chat_message] == []


def test_a_failed_retrieval_shows_the_error_and_keeps_no_turn():
    class BrokenRetriever(FakeRetriever):
        def retrieve(self, query, k=8):
            raise RuntimeError("the vector store could not be read")

    session = Session(BrokenRetriever(), FakeAnswerer(cited()))
    app = ask(page(session), Q1)
    assert [e.value for e in app.exception] == []
    assert [e.value for m in assistant(app) for e in m.error] == [ERROR]
    assert session.turns == []


def test_a_new_conversation_clears_the_turns_and_keeps_the_loaded_parts():
    retriever, answerer = FakeRetriever(), FakeAnswerer(cited(), cited())
    app = ask(page(Session(retriever, answerer)), Q1)
    app.button(key="new").click().run()
    session = app.session_state["session"]
    assert (session.turns, session.retriever, session.answerer) == ([], retriever, answerer)
    assert [m.name for m in app.chat_message] == []
    ask(app, Q2)
    assert retriever.queries == [Q1, Q2]


def test_a_missing_index_shows_the_load_error(monkeypatch):
    def not_ready(*args, **kwargs):
        raise IndexNotReadyError("no data/index/manifest.json")

    monkeypatch.setattr(Retriever, "load", not_ready)
    app = page()
    assert [e.value for e in app.exception] == []
    assert [e.value for e in app.error] == [LOAD_ERROR]
    assert len(app.chat_input) == 0
