---
status: draft
updated: 2026-11-16
owner: HieuQuang4438
---

# Cited answers

How a question's context ([context.md](context.md)) becomes a cited answer: the model call,
the answer's form, how each citation id is resolved and shown, and the judge that scores the
answers in the eval run. The rules are FR-CORE-010 and FR-CORE-011, their tests AC-009 and
AC-015, and EVAL-002, EVAL-003 and EVAL-006 ([acceptance.md](../product/acceptance.md)). The
model is ADR-0003's. The approach is the approved comment on #15.

## The model call — `src.llm`

Every call to the Gemini API goes through `src.llm.LLM`; nothing else imports google-genai
(CONVENTIONS §5).

```python
from src.llm import LLM

llm = LLM()                                       # LLM_MODEL, the first key of GOOGLE_API_KEYS
call = llm.generate("answer", system, user, AnswerOutput)
call.parsed                                       # an AnswerOutput
```

| Name | What it is |
|---|---|
| `LLM(model=LLM_MODEL, api_key=None, client=None, sleep=time.sleep, clock=time.monotonic)` | `api_key` none means `GOOGLE_API_KEYS[0]`: one key, one quota (approved on #15, choice 9). `client` replaces the google-genai client, for tests. A model with no entry in `PRICES` raises `ValueError` naming it. |
| `LLM.generate(prompt, system, user, schema, validate=None)` | One call. `prompt` is the prompt's name, for the log; `system` its text; `user` the request; `schema` a pydantic model the reply must fit. `validate`, if given, is called with the parsed reply and raises `ValueError` when the reply does not fit the request. Returns a `Call`. |
| `Call` | `parsed`, the reply as a `schema` instance; `model`; `prompt`; `input_tokens`; `output_tokens`, answer and thinking tokens together; `latency_s`, of the attempt that succeeded; `cost_usd`; `attempts`. |
| `LLMError` | Raised when a call gets no usable reply. |
| `PRICES` | USD per million tokens, input and output: `gemini-3.5-flash-lite` 0.30 and 2.50, read 2026-11-16 (`PRICES_READ`; ADR-0003). |

**The request** sends the system instruction, the user text, `response_mime_type`
`application/json` and `response_schema` `schema`, with a 60 s timeout (`TIMEOUT_S`) and the
SDK's own retries off. Nothing else is set. `temperature`, `top_p` and `top_k` are deprecated
and ignored by `gemini-3.5-flash-lite` and later models (Google's *What's new in Gemini 3.6*,
read 2026-11-16); CONVENTIONS §5's `temperature=0` therefore cannot apply. The thinking level
is the model's default, `minimal` for Flash-Lite. This is choice 8A of #15, as the pilot ran.

**Pacing.** Two calls start at least `MIN_INTERVAL_S` = 4 s apart, under the free tier's 15
requests per minute (ADR-0003). The wait uses `clock` and `sleep`.

**Retries.** A 429, a 5xx, a dropped connection, a timeout, or a reply that is not valid JSON
for `schema` or that `validate` refuses, is tried again after `BACKOFF_S` × 2^(n−1) seconds
(`BACKOFF_S` = 10: 10, 20, 40, 80), up to `ATTEMPTS` = 5 attempts in all; after the fifth,
`LLMError`. Any other 4xx raises `LLMError` at once.

**Log.** Logger `src.llm`: one `INFO` line per call with model, prompt name, input and output
tokens, latency and cost; one `WARNING` line per retry with its reason. Neither carries the
key, the request or the reply.

**Cost** is `(input_tokens × input price + output_tokens × output price) / 1,000,000`.

## The answer — `src.answer`

```python
from src.answer import Answerer

answerer = Answerer.load()                         # the assembler, the documents and an LLM
answer = answerer.answer(question, retrieval)       # a src.retrieval.Retrieval
answer.text                                        # what the reader sees
```

| Name | What it is |
|---|---|
| `Answerer(assembler, llm, documents)` | `assembler`: an `src.context.Assembler`; `documents`: doc_id → `Document`. |
| `Answerer.load(data_dir=Path("data"), llm=None)` | `Assembler.load(data_dir)` and the documents of `data_dir/processed/*.json`; `llm` none means `LLM()`. |
| `Answerer.answer(question, retrieval)` | Assembles the context and asks the model. An empty context gives the not-found answer without a call. |
| `Document` | `label`: `<loai_van_ban> <so_hieu>`, e.g. `Luật 48/2024/QH15`; `url`: the page's `source_url`. The doc_id is the number in `-<id>-d1.html`. |
| `Answer` | `sentences: list[Sentence]`; `citations: list[Citation]`, every distinct id cited, in first-use order, those not in the context included; `flagged: list[str]`, the ids not in the context, in first-use order; `not_found: bool`; `text: str`, as rendered below; `context: Context`; `call: Call` or none; `latency_s: dict[str, float]`, `assembly` and `generation`, the latter the call's `latency_s` (0 without a call), so pacing waits and retries are not counted. |
| `Sentence` | `text: str`; `citations: tuple[str, ...]`, as normalised below. |
| `Citation` | `id: str`; `in_context: bool`; and when in the context: `passage: str`, `document: str` (the label), `article: str`, `clause: str` or none, the clause number as shown (below), `url: str`. |
| `AnswerOutput` | The reply schema: `{"sentences": [{"text": str, "citations": [str]}]}`. |
| `NOT_FOUND` | `Không tìm thấy quy định trả lời câu hỏi này trong các văn bản hiện có.` |

**Prompt.** `src/prompts/answer.md` is the system instruction. The user text is
`Passages:\n\n<context.text>\n\nQuestion: <question>`, as in the pilot. The prompt asks for
Vietnamese, sentences that each carry the ids of the passages they come from (`1`, or `1.25`
for a clause), nothing beyond the passages, the `NOT_FOUND` sentence alone with no ids when the
passages do not answer, and, when a provision used has a link line, to say it was amended,
replaced or repealed and to cite the passage named on that line (FR-CORE-010). The not-found
wording is the pilot's; when to use it is #16's.

**Ids as written.** Each id the model gives is trimmed and stripped of one pair of brackets
(`" [1.25] "` → `1.25`). Duplicates within one sentence are kept once.

**Resolving an id.** Against the context's passages:

| Id | In the context when | Shown as |
|---|---|---|
| `n` | passage n exists | its document and article; for an amending passage of a clause chunk, also that clause |
| `n.k` | passage n is an `article` passage and k is in its `clauses` | its document, article and clause k |
| anything else | never | flagged |

A clause is shown by its number as written: `k` up to the first `.` (`3.2` is `khoản 3`).

**Not found.** The answer is not found when it has no sentence, or exactly one sentence whose
trimmed text is `NOT_FOUND` and which has no id.

**Rendering.** `Answer.text`, Markdown:

```text
Hàng hóa của hộ kinh doanh có doanh thu năm từ 1 tỷ đồng trở xuống không chịu thuế giá trị gia tăng. [1.25][3]

Nguồn:
- [1.25] [Luật 48/2024/QH15, Điều 5, khoản 25](https://luatvietnam.vn/…-379409-d1.html#:~:text=…)
- [3] [Luật 149/2025/QH15, Điều 1, khoản 2](https://luatvietnam.vn/…-421739-d1.html#:~:text=…)

Trích dẫn không có trong nguồn được cung cấp: [7]
```

- The sentences, joined by one space, each followed by its ids as `[id]` with no space between
  them; a sentence with no id has none.
- After a blank line, when any id is in the context: `Nguồn:` and one line per such id, in
  first-use order: `- [id] `, then a link whose text is `<label>, Điều <article>`, with
  `, khoản <clause>` for a clause.
- After a blank line, when there are flagged ids: `Trích dẫn không có trong nguồn được cung
  cấp:` and the flagged ids, each as `[id]`, separated by one space. A flagged id is never a
  source line (FR-CORE-011, AC-009).
- A not-found answer is the `NOT_FOUND` sentence alone.

**Links** (choice 7A). `<url>#:~:text=<Điều <article>. <title>>`, the article's title from
`articles.jsonl`; `Điều <article>.` alone when the title is empty. The fragment is
percent-encoded (`urllib.parse.quote`, nothing safe) and `-` is written `%2D`, since text
fragments read `-` as a separator. The source page has no anchor per article (checked on a
cached page, #15); a browser that supports text fragments scrolls to the article heading, any
other opens the page at its top.

## The judge — `src.eval.judge`

Scores the answers of an eval run (choices 2A, 3A, 4A, 6A of #15): one call per answer to an
answerable standalone question, with the same model (`LLM()`) and `src/prompts/judge.md`. A
not-found answer gets no call.

| Name | What it is |
|---|---|
| `Judge(llm)` | |
| `Judge.judge(question, key_facts, answer, amended=())` | `amended`: the citation ids of the amended provisions AC-015 asks about. Returns a `Verdict`. |
| `Verdict` | `cited: tuple[bool \| None, ...]`, per sentence, whether its cited passages support it, none for a sentence with no id; `supported: tuple[bool, ...]`, per sentence, whether the context supports it; `facts: tuple[bool, ...]`, per key fact, whether the answer states it; `contradicts: bool`, whether the answer contradicts a key fact; `says_amended: bool \| None`, none when `amended` is empty; `correct: bool`, every fact stated and none contradicted; `call: Call`. |
| `JudgeOutput` | The reply schema: `{"sentences": [{"cited_supports": bool, "context_supports": bool}], "key_facts": [bool], "contradicts": bool, "says_amended": bool}`. |

The request is the system instruction and this user text, the last line only when `amended` is
not empty:

```text
Passages:

<context.text>

Question: <question>

Answer sentences:
1. <sentence text> [1.25][2]
2. <sentence text>

Key facts:
1. <key fact>

Amended provisions: [1.25], [3]
```

Each sentence is followed by its ids as in the rendered answer, flagged ones included, and by
nothing when it has none. A reply whose `sentences` or `key_facts`
length differs from the request's is refused by `validate`, and so retried. A flagged id
supports nothing: a sentence whose ids are all flagged is `cited` false, whatever the judge
replies.
