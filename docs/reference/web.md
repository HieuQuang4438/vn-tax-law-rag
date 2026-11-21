---
status: in-review
updated: 2026-11-21
owner: HieuQuang4438
approved-by: peer
---

# Web interface

The chat page: conversations kept in the browser, each answer with its linked sources and
the note that it is information, not advice. The rules are FR-CORE-013 and FR-CORE-014, their
test AC-010 ([acceptance.md](../product/acceptance.md)). The approach is the approved comment
on #17, and on #30 for the FastAPI app that replaced the Streamlit page (choice 0A): a static
page and a JSON API, `src/web/`. Deployment is #18.

## Running it

```bash
python -m src.web                    # http://127.0.0.1:8000; --host and --port to change
```

From the repo root, with the index built ([index.md](index.md)) and `.env` filled in. A
missing API key stops the app at start, as every entrypoint does (`src/config.py`).

## The API — `src/web/`

`src.web.create_app(load)` makes the app; `python -m src.web` serves `create_app()` with
uvicorn. `load` returns the retriever and the answerer; by default it is `Retriever.load()` and
`Answerer.load()` over `data/`, with one `LLM()`, as the Streamlit page loaded them.

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
| `sources` | the citations in the context, one source per passage, in `Answer.citations` order (below) |
| `flagged` | `Answer.flagged`: the ids not in the context |
| `seconds` | the time from the request read to the answer, for the page to show |

Each source is one passage's citations joined to its `Document` by `doc_id`: `ids`,
`document` (the label), `kind`, `number`, `title`, `issued`, `article`, `clauses`, `heading`,
`url`, `text`, `effective`, and `amended_by` as `{"target", "type", "source"}`
([answer.md](answer.md), *For the page*). `Answer.text` is not sent: the page renders the
sentences and the sources.

**One source per article** (#41, choices 1A to 4A). The citations in the context that share a
passage (`Citation.passage`: `n`, `n.k`, `n.k.2`, … of one article, or an amending passage `m`)
make one source, so an article cited whole and by a clause is listed once. `Answer` itself does
not change.

- `ids`: the passage's ids the answer cites, in first-use order. The source stands where the
  first of them is first used in `Answer.citations`.
- `clauses`: the clause numbers as shown (`Citation.clause`) of its `n.k` ids, in clause order;
  empty when only `n` is cited.
- `text`: the article's when `n` is among the ids; otherwise its clauses' texts in clause order,
  one per line.
- `effective`: `n`'s when `n` is among the ids; otherwise the clauses' date when they share one,
  none when they differ.
- `amended_by`: the links of all its ids, in the order of `ids`, each once.
- `document`, `kind`, `number`, `title`, `issued`, `article`, `heading` and `url`: those of the
  first id; every id of one passage has the same.

## The page — `src/web/static/`

`GET /` serves `index.html`, its stylesheet and script under `/static/` (`app.css`, `app.js`):
plain HTML, CSS and JS, no build step and no script from another origin; only the fonts come
from Google Fonts. The design tokens and the ten screens are the prototype's at `7b015ed`
(`docs/discovery/prototypes/web-ui.html`, notes `web-ui-notes.md`), with the changes asked on
review: the welcome has two points, not three; the top bar has a button for the source panel;
a text box shows one focus ring, its frame's, not a second one of its own; a conversation can
be renamed. The page calls the
API by relative paths, so it also works under a path prefix.

**Versioned links** (#41). The page links its stylesheet and script as
`static/app.css?v=<hash>` and `static/app.js?v=<hash>`, `<hash>` the first 12 hex digits of the
file's SHA-256 when the app starts. A changed file is a new URL, so a browser that kept the
older one fetches it, rather than running an older script against a newer API.

**Type.** Three fonts, each with the Vietnamese letters: Source Serif 4 (`--font-doc`) for the
words of the documents and the answer, Be Vietnam Pro (`--font-ui`) for the page's own words,
JetBrains Mono (`--font-mono`) for the citation chips and the keys.

- Serif: the answer, the excerpt in the source panel with its article heading above it (bold,
  16 px, the ink color: it is the document's own heading), the document's name heading the
  panel, the welcome's title, and the app's name as its wordmark.
- Sans: everything else, the dialogs' titles and the loading and load error cards included
  (20 px, weight 600): they are the page speaking, not a document. A document's name in a list
  (the sources under an answer, the document list) is sans; heading the panel, it is serif.
- No text under 12 px. No capitals made by `text-transform`: small capitals stack the
  Vietnamese marks; the small labels ("Trả lời", the history's day groups, a document's kind)
  are sentence case, weight 600.
- Every text box is 16 px, so a phone's browser does not zoom in when it is focused.
- Line height: 1.7 (`--lh-body`) for the answer and the excerpt; at least 1.3 for a heading in
  serif, so the marks of a capital do not touch the line above.

**Texts.** The texts that the Streamlit page had keep their wording; they and the quota message
are constants of `src.web.texts`, put in the page as JSON when it is served, so the script holds
no copy of them:

| Name | Text |
|---|---|
| `TITLE` | `Hỏi đáp pháp luật thuế Việt Nam` (the browser tab, after the conversation's title) |
| `PLACEHOLDER` | `Đặt câu hỏi về thuế…` |
| `NOTICE` | `Đây là thông tin kèm nguồn, không phải tư vấn pháp lý hay tư vấn thuế.` |
| `NEW_CONVERSATION` | `Cuộc hội thoại mới` |
| `SPINNER` | `Đang tìm và trả lời…` |
| `ERROR` | `Chưa trả lời được lúc này, vui lòng thử lại sau.` |
| `LOAD_ERROR` | `Chưa tải được chỉ mục văn bản nên chưa thể trả lời.` |
| `QUOTA` | `Đang có nhiều câu hỏi, vui lòng thử lại sau một phút.` (choice 2A) |

The other texts (the welcome, the tips after a not-found answer, the dialogs, the toasts) are
the prototype's, in the page.

**Screens.**

- **Loading and load error** (S1, S2). The page asks `GET /api/status` at once and every 2 s while
  it is `loading`. With no conversation open it shows the loading card, or on `error` the
  `LOAD_ERROR` card with "Thử lại", which sends `POST /api/load` and goes back to loading. The
  question box is off until `ready`; the history can be read meanwhile.
- **New conversation** (S3): the welcome, with two points (each statement has its source; an
  amended provision is said to be amended, with the amending document), and `NOTICE`.
  `NEW_CONVERSATION` always comes back here,
  with no confirmation, since the old conversation stays in the history.
- **Answering** (S4): the question at once, then `SPINNER` with the seconds counted. One question
  at a time: the send button is off until the answer.
- **Answer** (S5, S8): the sentences, the amendment notices as a paragraph of their own. Each
  source gets a number, 1…n in the order of `sources`, shown as a chip after the sentences that
  cite any of its `ids`, once per sentence; a flagged id is a `?` chip, and a note names the
  flagged ids (FR-CORE-011). Under it the sources: document, article and the clauses cited
  ("Điều 3, khoản 1, 2"), its title, "Đã sửa đổi" when it has
  `amended_by`, and a link to the source page in a new tab (AC-010). Then `NOTICE`, under every
  answer, a not-found one included (FR-CORE-013). Then copy, 👍/👎 and the seconds.
- **Source panel**: a chip or a source row opens it. Kind, document, title, place, issue date,
  effective date, "hồi tố, trước ngày ban hành" when the effective date comes first (#30,
  correction to choice 8), one line per amendment link with "Xem nguồn [n]" when its source is
  among the sources, the provision it amends named "Điều này" when that is the source's `n` and
  "Khoản k" when it is one of the source's `n.k`, then the heading and the text, and a link to
  the source page. On a page 1280 px
  wide or more it opens on the first source of a new answer; under 1280 px it is a drawer
  under the top bar, under 900 px a bottom sheet. A button at the right of the top bar,
  `#panel-toggle` (`aria-controls="panel"`, `aria-expanded` while the panel is open), closes it
  or opens it again: on the source last shown in this conversation, else on the first source
  of its last answer that has one; the button is off when the conversation has no source, and
  its icon shows which it will do. It is the panel's only button: the panel's head has its
  title alone, no close button and no icon. Esc closes the panel too, and so does the shade
  behind a drawer or a sheet.
- **Not found** (S6): `NOT_FOUND` as the answer, tips on asking again, a link to the documents.
- **Error** (S7): `ERROR`, or `QUOTA` on a 429, with "Thử lại" (the same question again) and
  "Sửa câu hỏi" (back to the box). The failed question is not kept. A 503 sends the page back to
  loading and the question back to the box.
- **Delete** (S9): the trash on a history row asks first; deleting the open conversation goes back
  to the welcome.
- **Rename**: the pencil on a history row, shown as the trash is, turns its title into a text
  box of at most 100 characters. Enter or leaving the box keeps the new title, trimmed; Esc, or
  a title left empty, keeps the old one. A rename does not move the conversation in the history.
- **Documents** (S10): `GET /api/documents` grouped by kind, filtered as one types.

**History** (choices 3A, 4A, 7A). The conversations are kept in the browser's `localStorage`,
newest first, at most 50: the oldest is dropped. Each keeps its questions, the API's answers and
the votes; nothing goes to the server. Its title is its first question until it is renamed
(*Rename* above). A source kept before #41 has `id` and `clause` in place of `ids` and
`clauses`; the page reads it as `ids` `[id]` and `clauses` `[clause]`, or `[]` without a clause. A write that fails
(storage full or blocked) keeps the conversation for the open page only. Copy puts the answer
with the page's numbers, its sources with their links, and `NOTICE` on the clipboard.

**Safety.** Every text from the API or the corpus is escaped before it is put in the page; a
link is used only when it starts with `http://` or `https://`.

## Tests — `tests/web/`

FastAPI's `TestClient` runs the app with no browser and no network (#30, *Risks*):
`test_api.py` with a `load` that returns a fake retriever and a fake answerer, so nothing loads
the index; `test_page.py` reads the page, its texts, its stylesheet and its script as served.
The script itself is checked by hand in the end-to-end run, not by an automated browser.

## The end-to-end run

One run on the real index and model, 2 turns, a question and a follow-up written for this run,
not taken from the eval set (#30, *Done when*). At commit `3c6529b`, on the dev laptop (CPU):
`python -m src.web` with nothing faked, the page in Chrome, the questions typed in its box;
`gemini-3.5-flash-lite`, rewriter `concat`.

| | Seconds | What the page showed | Cost (USD) |
|---|---|---|---|
| Load, from the server's start to `GET /api/status` answering `ready` | 26.7 | the welcome, the box on | |
| Turn 1, the personal income tax rate on lottery winnings | 10.0 | an answer, 1 source (Nghị định 253/2026/NĐ-CP, Điều 58, khoản 1) as a chip and a row with its link, the panel open on it with the clause's text and its dates, the notice | 0.0038 |
| Turn 2, the follow-up "and income from royalties?" | 21.5 | an answer with both rates, 4 sources as chips and rows with their links, the notice | 0.0033 |

- No error in the page's console or in the server's log; both `POST /api/ask` answered 200.
  Generation took 7.91 s and 21.28 s of the two turns; the rest is retrieval and rewrite.
- The conversation was kept in the browser and the page sent turn 1's question with turn 2
  (choice 6A): `concat` gave retrieval both questions, so turn 2 was answered, not found as in
  the Streamlit run below.
- Beyond AC-010: turn 2's answer repeats turn 1's rate before the new one, since the answer
  sees the rewritten question, both questions joined (#19, choice 2A); a finding on the answers
  (EVAL-005), not on the page. Turn 2's generation, 21.28 s, is the slowest seen on the page.
- Checked by hand before this run, on fakes or the real API: the quota message (a 429), a
  reload keeping the history, the document list, the bottom sheet under 900 px, renaming, the
  panel button, the type.

## The Streamlit page's end-to-end run

Recorded on #17, before #30 replaced the page. One run on the real index and model, 2 turns, a question and a follow-up written for this run,
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
