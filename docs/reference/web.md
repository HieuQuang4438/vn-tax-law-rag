---
status: approved
updated: 2026-11-18
owner: HieuQuang4438
approved-by: peer
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
   session under a spinner, `SPINNER`; its turn is then shown as in 4. When asking fails, in
   retrieval or in the model call (`LLMError`, a spent quota included), the error is logged and
   `ERROR` is shown as an error in the assistant message, not a stack trace. `Session.ask` adds
   a turn only once it is answered, so a failed question is not kept and is gone on the next
   run.

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

One run on the real index and model, 2 turns, a question and a follow-up written for this run,
not taken from the eval set (choice 4A). At commit `420aa3e`, on the dev laptop (CPU), through
`AppTest` over `src/app.py` with nothing put in the session, so the page loaded the index and
`LLM()` itself; `gemini-3.5-flash-lite`, rewriter `concat`.

| | Seconds | What the page showed | Cost (USD) |
|---|---|---|---|
| Load | 30.8 | the chat input, no error: bge-m3 and both indexes loaded | |
| Turn 1, on the revenue under which a household business pays no VAT | 5.8 | an answer, 3 sources as links, 1 flagged id, the notice, `DETAILS` with the query and the 3 passages | 0.0040 |
| Turn 2, the follow-up "and personal income tax?" | 2.9 | the not-found answer, the notice, `DETAILS` with the `concat` query | 0.0049 |

- No exception and no error in any run of the page. Generation took 2.41 s and 1.28 s of the
  two turns.
- `python -m streamlit run src/app.py` serves the page: `/_stcore/health` answers `ok` and the
  page HTTP 200.
- Beyond AC-010: in turn 1 the model cited an id that was not in the context, shown apart as
  flagged (FR-CORE-011); the follow-up of turn 2 was answered as not found. Both are findings
  on the answers (EVAL-002, EVAL-005), not on the page.
- The error handling changed after the run (`be0c71c`: a failed retrieval shows `ERROR` too);
  the path the run took is unchanged.
