"""FR-CORE-013/014 web chat page (#17). Run with `python -m streamlit run src/app.py`.

Rules: `docs/reference/web.md`.
"""

import streamlit as st

TITLE = "Hỏi đáp pháp luật thuế Việt Nam"
PLACEHOLDER = "Đặt câu hỏi về thuế…"
NOTICE = "Đây là thông tin kèm nguồn, không phải tư vấn pháp lý hay tư vấn thuế."
NEW_CONVERSATION = "Cuộc hội thoại mới"
DETAILS = "Chi tiết"
QUERY = "Truy vấn tìm kiếm"
SPINNER = "Đang tìm và trả lời…"
ERROR = "Chưa trả lời được lúc này, vui lòng thử lại sau."
LOAD_ERROR = "Chưa tải được chỉ mục văn bản nên chưa thể trả lời."


def main() -> None:
    st.title(TITLE)
    st.button(NEW_CONVERSATION, key="new")
    st.chat_input(PLACEHOLDER)


if __name__ == "__main__":
    main()
