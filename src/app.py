"""FR-CORE-013/014 web chat page (#17). Run with `python -m streamlit run src/app.py`.

Rules: `docs/reference/web.md`.
"""

import logging
from pathlib import Path

import streamlit as st

from src.answer import Answerer, Citation
from src.conversation import Session, Turn
from src.llm import LLM, LLMError
from src.retrieval import IndexNotReadyError, Retriever

TITLE = "Hỏi đáp pháp luật thuế Việt Nam"
PLACEHOLDER = "Đặt câu hỏi về thuế…"
NOTICE = "Đây là thông tin kèm nguồn, không phải tư vấn pháp lý hay tư vấn thuế."
NEW_CONVERSATION = "Cuộc hội thoại mới"
DETAILS = "Chi tiết"
QUERY = "Truy vấn tìm kiếm"
SPINNER = "Đang tìm và trả lời…"
ERROR = "Chưa trả lời được lúc này, vui lòng thử lại sau."
LOAD_ERROR = "Chưa tải được chỉ mục văn bản nên chưa thể trả lời."
DATA = Path("data")

log = logging.getLogger(__name__)


@st.cache_resource(show_spinner=SPINNER)
def _loaded() -> tuple[Retriever, Answerer]:
    """Once per process: every browser session shares the index and one LLM pacing."""
    return Retriever.load(DATA), Answerer.load(DATA, llm=LLM())


def _session() -> Session | None:
    if "session" not in st.session_state:
        try:
            retriever, answerer = _loaded()
        except IndexNotReadyError:
            log.exception("the index could not be loaded")
            return None
        st.session_state["session"] = Session(retriever, answerer)
    return st.session_state["session"]


def _source(citation: Citation) -> str:
    clause = f", khoản {citation.clause}" if citation.clause else ""
    return f"**[{citation.id}] {citation.document}, Điều {citation.article}{clause}**"


def _show_answer(turn: Turn) -> None:
    st.markdown(turn.answer.text)
    st.caption(NOTICE)
    with st.expander(DETAILS):
        st.markdown(f"**{QUERY}**")
        for query in turn.rewrite.queries:
            st.text(query)
        for citation in turn.answer.citations:
            if citation.in_context:
                st.markdown(_source(citation))
                st.text(citation.passage)


def _show(turn: Turn) -> None:
    with st.chat_message("user"):
        st.markdown(turn.question)
    with st.chat_message("assistant"):
        _show_answer(turn)


def _ask(session: Session, question: str) -> None:
    with st.chat_message("user"):
        st.markdown(question)
    with st.chat_message("assistant"):
        try:
            with st.spinner(SPINNER):
                turn = session.ask(question)
        except LLMError:
            log.exception("the answer's model call failed")
            st.error(ERROR)
            return
        _show_answer(turn)


def main() -> None:
    st.set_page_config(page_title=TITLE)
    st.title(TITLE)
    session = _session()
    if session is None:
        st.error(LOAD_ERROR)
        return
    if st.button(NEW_CONVERSATION, key="new"):
        session = Session(session.retriever, session.answerer, session.rewriter, session.k)
        st.session_state["session"] = session
    for turn in session.turns:
        _show(turn)
    question = st.chat_input(PLACEHOLDER)
    if question:
        _ask(session, question)


if __name__ == "__main__":
    main()
