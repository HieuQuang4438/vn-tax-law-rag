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

#30 replaces the Streamlit page with a FastAPI app, `src/web/`, that serves a static page and
a JSON API (approved comment on #30, choice 0A). The API is below, *The API*; the Streamlit
page stays until the static page replaces it.

## Running it

```bash
python -m streamlit run src/app.py
```

From the repo root, with the index built ([index.md](index.md)) and `.env` filled in. A
missing API key stops the page at start, as every entrypoint does (`src/config.py`).

The FastAPI app:

```bash
python -m src.web                    # http://127.0.0.1:8000; --host and --port to change
```

## The API — `src/web/`

`src.web.create_app(load)` makes the app; `python -m src.web` serves `create_app()` with
uvicorn. `load` returns the retriever and the answerer; by default it is `Retriever.load()` and
`Answerer.load()` over `data/`, with one `LLM()`, as the Streamlit page loads them.

**Loading.** The app starts serving at once and loads in a background thread when it starts
(the index takes about 30 s), so the page can show that it is loading rather than fail to
connect. The load runs once per process; every request shares the retriever, the answerer and
the wrapper's pacing of 15 requests a minute (ADR-0003). A load that raises is logged and
leaves the app in `error`; it is retried only when asked (`POST /api/load`). Questions are
answered one at a time: a lock holds each one from rewrite to answer, since the retriever and
the wrapper's pacing are not made for threads.

**Stateless** (choice 6A). The app keeps no conversation. The page sends the earlier questions
of its conversation with each new one; `src.conversation.ask` rewrites with the default
rewriter, `concat`, which reads the last two ([conversation.md](conversation.md)). A question
that fails is not kept by the page, so it is never sent as an earlier question.

Every body is JSON. Every error body is `{"error": <code>}`.

| Endpoint | Answer |
|---|---|
| `GET /api/status` | `{"status": s}`, `s` one of `loading`, `ready`, `error` |
| `POST /api/load` | In `error`, starts loading again; in any other state does nothing. Then as `GET /api/status` |
| `GET /api/documents` | `{"documents": [...]}`: every document the answerer loaded, in its order, each `id`, `kind`, `number`, `title`, `url`, `issued` (choice 5A; [answer.md](answer.md), `Document`) |
| `POST /api/ask` | Takes `{"question": str, "earlier": [str]}`; answers below |

`POST /api/ask` takes `question`, stripped, of 1 to `MAX_CHARS` (2000) characters, and
`earlier`, the earlier questions oldest first, at most `MAX_EARLIER` (100) of them, each of at
most `MAX_CHARS` characters; `earlier` may be left out. A body that does not fit is refused
with 422. Its answer:

| Status | When | Body |
|---|---|---|
| 200 | answered | below |
| 422 | the body does not fit | FastAPI's validation error |
| 429 | `LLMError` with `quota` true ([answer.md](answer.md), *Retries*; choice 2A) | `{"error": "quota"}` |
| 500 | any other failure, in rewrite, retrieval or the model call; logged | `{"error": "error"}` |
| 503 | not loaded yet, or the load failed | `{"error": "loading"}`, `{"error": "load_error"}` |

`/api/documents` answers 503 the same way. The 200 body of `/api/ask`:

| Field | Value |
|---|---|
| `question` | the question as asked, stripped |
| `sentences` | `Answer.sentences`, each `{"text", "citations"}`, the amendment notices last |
| `notices` | `Answer.notices`: how many of the last sentences are notices |
| `not_found` | `Answer.not_found` |
| `sources` | the citations in the context, in `Answer.citations` order (below) |
| `flagged` | `Answer.flagged`: the ids not in the context |
| `seconds` | the time from the request read to the answer, for the page to show |

Each source is one `Citation` joined to its `Document` by `doc_id`: `id`, `document` (the
label), `kind`, `number`, `title`, `issued`, `article`, `clause`, `heading`, `url`, `text`,
`effective`, and `amended_by` as `{"target", "type", "source"}` ([answer.md](answer.md),
*For the page*). `Answer.text` is not sent: the page renders the sentences and the sources.

## The page — `src/app.py`

A Streamlit script. Its texts are constants of `src.app`, in Vietnamese:

| Name | Text |
|---|---|
| `TITLE` | `Hỏi đáp pháp luật thuế Việt Nam` |
| `PLACEHOLDER` | `Đặt câu hỏi về thuế…` |
| `NOTICE` | `Đây là thông tin kèm nguồn, không phải tư vấn pháp lý hay tư vấn thuế.` |
| `NEW_CONVERSATION` | `Cuộc hội thoại mới` |
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
     answer, a not-found answer included (choice 2A). Nothing more: each source's link opens
     its page on the source site, at the article where the browser supports text fragments.
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

The API's tests, `tests/web/test_api.py`, go through FastAPI's `TestClient` with a `load` that
returns a fake retriever and a fake answerer, so nothing loads the index and nothing goes to the
network (#30, *Risks*).

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
- After #17 was closed, the `DETAILS` expander was dropped (choice 3B instead of 3A): it showed
  each cited passage's id, not its text (`Citation.passage` is the id), and the source links
  already open the text. The run's other rows hold.
