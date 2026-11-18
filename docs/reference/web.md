---
status: draft
updated: 2026-11-18
owner: HieuQuang4438
---

# Web interface

The chat page: one conversation per browser session, each answer with its linked sources and
the note that it is information, not advice. The rules are FR-CORE-013 and FR-CORE-014, their
test AC-010 ([acceptance.md](../product/acceptance.md)). The approach is the approved comment
on #17. Deployment is #18.

## Running it

```bash
python -m streamlit run src/app.py
```

From the repo root, with the index built ([index.md](index.md)) and `.env` filled in. A
missing API key stops the page at start, as every entrypoint does (`src/config.py`).

## The page — `src/app.py`

A Streamlit script. Its texts are constants of `src.app`, in Vietnamese:

| Name | Text |
|---|---|
| `TITLE` | `Hỏi đáp pháp luật thuế Việt Nam` |
| `PLACEHOLDER` | `Đặt câu hỏi về thuế…` |
| `NOTICE` | `Đây là thông tin kèm nguồn, không phải tư vấn pháp lý hay tư vấn thuế.` |
| `NEW_CONVERSATION` | `Cuộc hội thoại mới` |
| `DETAILS` | `Chi tiết` |
| `QUERY` | `Truy vấn tìm kiếm` |
| `SPINNER` | `Đang tìm và trả lời…` |
| `ERROR` | `Chưa trả lời được lúc này, vui lòng thử lại sau.` |
| `LOAD_ERROR` | `Chưa tải được chỉ mục văn bản nên chưa thể trả lời.` |

From the top, on every run of the script:

1. The title, `TITLE`.
2. The session (below). When it cannot be made, `LOAD_ERROR` as an error and nothing more.
3. A button `NEW_CONVERSATION`, key `new`. It replaces the session with a new one over the same
   retriever, answerer, rewriter and `k`, so the conversation starts again with no reload.
4. Every turn of the session, oldest first, as two chat messages:
   - **user**: the question as asked;
   - **assistant**: `Answer.text` as Markdown, which holds the sources as links and the
     flagged ids ([answer.md](answer.md), *Rendering*); then `NOTICE` as a caption, under every
     answer, a not-found answer included (choice 2A); then a collapsed expander `DETAILS`
     (choice 3A) holding `QUERY` in bold, each query retrieval got as text, one per query, and
     for each citation in the context, in first-use order, a bold line
     `[<id>] <label>, Điều <article>`, with `, khoản <clause>` for a clause, as in the
     `Nguồn:` list, and the passage as text.
5. A chat input, `PLACEHOLDER`. A question sent is shown as a user message and asked of the
   session under a spinner, `SPINNER`; its turn is then shown as in 4. When the answer's model
   call fails (`LLMError`), the error is logged and `ERROR` is shown as an error in the
   assistant message. `Session.ask` adds a turn only once it is answered, so a failed question
   is not kept and is gone on the next run.

The notice is the page's, not the answer's: `Answer.text` is unchanged, so the eval and the
judge see the same answers as before #17 (choice 2A).

## The session

Kept in `st.session_state["session"]`, one `src.conversation.Session` per browser session,
with the default rewriter, `concat` ([conversation.md](conversation.md)): a follow-up costs no
model call beyond its answer.

When there is none, it is made over the retriever and the answerer of the process, loaded once
by a function cached with `st.cache_resource`: `Retriever.load()` and `Answerer.load()` over
`data/`, with one `LLM()`. Every browser session shares them, and so shares the wrapper's
pacing of 15 requests a minute (ADR-0003). An index that is missing or not finished
(`IndexNotReadyError`) is logged and shows `LOAD_ERROR`; it is not cached, so the next run
tries again.

## Tests — `tests/test_app.py`

Streamlit's `AppTest` runs the page with no browser and no network (choice 4A). A `Session` over
a fake retriever and a fake answerer is put in `st.session_state["session"]` before the first
run; the missing-index case patches `Retriever.load` instead.

## The end-to-end run

One manual run on the real index and model, 2 turns, a question and a follow-up (choice 4A):
not done yet.
