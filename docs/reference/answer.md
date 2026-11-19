---
status: draft
updated: 2026-11-19
owner: HieuQuang4438
---

# Cited answers

How a question's context ([context.md](context.md)) becomes a cited answer: the model call,
the answer's form, how each citation id is resolved and shown, and the judge that scores the
answers in the eval run. The rules are FR-CORE-010, FR-CORE-011 and FR-CORE-012, their tests
AC-009 and AC-015, and EVAL-002, EVAL-003, EVAL-004 and EVAL-006
([acceptance.md](../product/acceptance.md)). The model is ADR-0003's. The approach is the
approved comment on #15; when an answer is not found, the approved comment on #16; the fields
the web page reads, the approved comments on #30; point-level ids, the approved comment on #33;
the rule on every part of the question, the approved comment on #34.

## The model call — `src.llm`

Every call to the Gemini API goes through `src.llm.LLM`; nothing else imports google-genai
(CONVENTIONS §5).

```python
from src.llm import LLM

llm = LLM()                                       # LLM_MODEL, every key of GOOGLE_API_KEYS
call = llm.generate("answer", system, user, AnswerOutput)
call.parsed                                       # an AnswerOutput
```

| Name | What it is |
|---|---|
| `LLM(model=LLM_MODEL, api_keys=None, clients=None, sleep=time.sleep, clock=time.monotonic)` | `api_keys` none means `GOOGLE_API_KEYS`, every key, each with its own client (*Keys*). `clients`, for tests, replaces the google-genai clients, one per key. A model with no entry in `PRICES` raises `ValueError` naming it. |
| `LLM.keys` | How many keys it holds. |
| `LLM.generate(prompt, system, user, schema, validate=None)` | One call. `prompt` is the prompt's name, for the log; `system` its text; `user` the request; `schema` a pydantic model the reply must fit. `validate`, if given, is called with the parsed reply and raises `ValueError` when the reply does not fit the request. Returns a `Call`. |
| `Call` | `parsed`, the reply as a `schema` instance; `model`; `prompt`; `input_tokens`; `output_tokens`, answer and thinking tokens together; `latency_s`, of the attempt that succeeded; `cost_usd`; `attempts`. |
| `LLMError` | Raised when a call gets no usable reply. `quota: bool`, *Retries*. |
| `PRICES` | USD per million tokens, input and output: `gemini-3.5-flash-lite` 0.30 and 2.50, read 2026-11-16 (`PRICES_READ`; ADR-0003). |

**The request** sends the system instruction, the user text, `response_mime_type`
`application/json` and `response_schema` `schema`, with a 60 s timeout (`TIMEOUT_S`) and the
SDK's own retries off. Nothing else is set. `temperature`, `top_p` and `top_k` are deprecated
and ignored by `gemini-3.5-flash-lite` and later models (Google's *What's new in Gemini 3.6*,
read 2026-11-16); CONVENTIONS §5's `temperature=0` therefore cannot apply. The thinking level
is the model's default, `minimal` for Flash-Lite. This is choice 8A of #15, as the pilot ran.

**Pacing.** Two calls start at least `MIN_INTERVAL_S` = 4 s apart, under the free tier's 15
requests per minute (ADR-0003). The wait uses `clock` and `sleep`.

**Keys** (approved on #15: choice 9B, on 429 and 5xx). Each key of `GOOGLE_API_KEYS` belongs
to its own project, with its own quota. The wrapper sends each request with its current key,
the first one to begin with. A 429 or a 5xx moves it to the next key, in the order of
`GOOGLE_API_KEYS` and back to the first after the last, and the request is sent again with that
key at once: no backoff, only the pacing above. The new key stays current for the calls that
follow. Only when every key has answered the same attempt with 429 or 5xx does the attempt
fail.

**Retries.** An attempt fails when every key answered it with 429 or 5xx, or on a dropped
connection, a timeout, or a reply that is not valid JSON for `schema` or that `validate`
refuses; these last three are tried again with the same key. A failed attempt is tried again
after `BACKOFF_S` × 2^(n−1) seconds (`BACKOFF_S` = 10: 10, 20, 40, 80), up to `ATTEMPTS` = 5
attempts in all; after the fifth, `LLMError`. Any other 4xx raises `LLMError` at once.
`LLMError.quota` is true when the fifth attempt failed because every key answered it with 429,
so the web page can ask the reader to wait rather than show the general error (#30, choice 2A);
it is false for every other failure, a 5xx on any key of that attempt included.

**Log.** Logger `src.llm`: one `INFO` line per call with model, prompt name, input and output
tokens, latency and cost; one `WARNING` line per retry with its reason, and one per key
change with its reason, naming the keys by position (`503 on key 1 of 4, moving to key 2 of
4`). None carries a key, the request or the reply.

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
| `Answerer.load(data_dir=Path("data"), llm=None)` | `Assembler.load(data_dir)` and the documents of `data_dir/processed/*.json`, names starting with `_` skipped as elsewhere; `llm` none means `LLM()`. |
| `Answerer.answer(question, retrieval)` | Assembles the context, asks the model and adds the amendment notices. An empty context gives the not-found answer without a call. |
| `Document` | `label`: `<loai_van_ban> <so_hieu>`, e.g. `Luật 48/2024/QH15`; `url`: the page's `source_url`; `kind`: `loai_van_ban`; `number`: `so_hieu`; `title`: `trich_yeu`; `issued`: `ngay_ban_hanh` as `YYYY-MM-DD`, none when it is missing or not `dd/mm/yyyy`. The doc_id is the number in `-<id>-d1.html`. |
| `Answer` | `sentences: list[Sentence]`, the model's then the amendment notices; `citations: list[Citation]`, every distinct id cited, in first-use order, those not in the context included; `flagged: list[str]`, the ids not in the context, in first-use order; `not_found: bool`; `text: str`, as rendered below; `context: Context`; `call: Call` or none; `latency_s: dict[str, float]`, `assembly` and `generation`, the latter the call's `latency_s` (0 without a call), so pacing waits and retries are not counted; `notices: int`, how many of `sentences`, the last ones, are amendment notices. |
| `Sentence` | `text: str`; `citations: tuple[str, ...]`, as normalised below. |
| `Citation` | `id: str`; `in_context: bool`; and when in the context: `passage: str`, `document: str` (the label), `article: str`, `clause: str` or none, the clause number as shown (below), `url: str`; for the web page (*For the page*, below): `doc_id: str`, `heading: str`, `text: str`, `effective: str` or none, `amended_by: tuple[Link, ...]`. A flagged citation has none of these and an empty `amended_by`. |
| `AnswerOutput` | The reply schema: `{"sentences": [{"text": str, "citations": [str]}]}`. |
| `NOT_FOUND` | `Không tìm thấy quy định trả lời câu hỏi này trong các văn bản hiện có.` |

**Prompt.** `src/prompts/answer.md` is the system instruction. The user text is
`Passages:\n\n<context.text>\n\nQuestion: <question>`, as in the pilot. The prompt asks for
Vietnamese, sentences that each carry the ids of the passages they come from (`1`, or `1.25`
for a clause), nothing beyond the passages, an answer to the part of the question the passages
answer, an answer to every part of the question from every passage that bears on it, one
provision per sentence (below), the `NOT_FOUND` sentence alone with no ids only when no passage
bears on the question (FR-CORE-012, below), and, when a provision used has a link line, to say
it was amended, replaced or repealed and to cite the passage named on that line (FR-CORE-010).
The not-found wording is the pilot's.

**Every part of the question** (approved on #34, choice 1B). After the rule on partial answers,
the prompt asks the model to answer every part of the question, using every passage that bears
on it, and to give each condition, exception, rate, threshold or deadline the passages state in
its own sentence, not folding several provisions into one. At `271adae`, answers of 1 to 3
sentences were judged correct 0.35 of the time and answers of 4 or more 0.78; the rule targets
those short answers. The rule stays only if the run of #34 keeps it by the decision rule fixed
in its approach comment; otherwise it is reverted with this paragraph and its test.

**Ids as written.** Each id the model gives is trimmed and stripped of one pair of brackets
(`" [1.25] "` → `1.25`). Duplicates within one sentence are kept once, after the rewrite below.

**Point-level ids** (approved on #33, choices 1A, 2A and 3A). The model sometimes cites below the
clause, at a point (điểm a, b, …), which the passages do not mark. Such an id is rewritten to its
clause before it is resolved, so it renders, resolves and is judged as that clause id. An id is
point-level when it is

- a run of digits and dots `n.r`, then
- an optional space or `.`, then
- one point letter, `a` to `y` or `đ`, and anything after it,

and passage n is an `article` passage with a clause k in its `clauses` that is `r` itself or
begins `r` followed by a `.`. It becomes `n.k`, with the longest such k:

| Written | Clauses of passage 1 | Becomes |
|---|---|---|
| `1.25a`, `1.25 b`, `1.25.c`, `1.25đ.1` | `25` | `1.25` |
| `1.2.2a` | `2`, `2.2` | `1.2.2` |
| `1.2a` | `2`, `2.2` | `1.2` |
| `1.1.5a` | `1` | `1.1` |

Any other id is kept as written and resolved as below: a bare letter (`a`), a letter after a
passage alone (`1a`), a clause not in the passage (`1.99a`), a point on an `amending` passage
(`2.1a`).

**Resolving an id.** Against the context's passages:

| Id | In the context when | Shown as |
|---|---|---|
| `n` | passage n exists | its document and article; for an amending passage of a clause chunk, also that clause |
| `n.k` | passage n is an `article` passage and k is in its `clauses` | its document, article and clause k |
| anything else | never | flagged |

A clause is shown by its number as written: `k` up to the first `.` (`3.2` is `khoản 3`).

**Not found.** The answer is not found when it has no sentence, or exactly one sentence whose
trimmed text is `NOT_FOUND` and which has no id.

**When it is not found** (FR-CORE-012, approved on #16). The model alone decides, from the
prompt's rule; an empty context gives the not-found answer without a call. The rule is narrowed
(choice 2A): before #16 the prompt asked for `NOT_FOUND` whenever the passages did not answer;
at `4091435` that gave not found on 33 of 184 answerable questions, 10 of them with every
expected article in the top 8, and on 55 of 56 unanswerable ones. The prompt now asks for an
answer to the part the passages answer, and `NOT_FOUND` only when no passage bears on the
question. EVAL-004 measures the rule on the unanswerable questions
([eval-results.md](eval-results.md), *Generation stage*).

There is no floor on retrieval similarity below which the model is not called (choice 1A),
though #16 first named one. The model alone already gave not found on 55 of the 56, so a floor
could add at most one; every question gets a non-empty top 8, so a floor could only turn more
answerable questions into not found; and it would be tuned and scored on the same 56 questions.
Fused scores are not calibrated (ADR-0002), so a floor would rest on dense similarity alone.

**Amendment notices** (approved on #15, choices A2 and 2'). The prompt's rule on link lines is
not followed reliably, so the answerer adds what it leaves out. For each link of the context
(`Passage.links`, context.md) whose amended provision the answer cites, one sentence is added
after the model's, in the order of the links. It is added whether or not the answer also cites
the source: a sentence citing both may still not say that the provision was amended.

- An id **cites** a provision when it equals the provision's id, or is `n` and the provision's
  id is `n.k`, or is an `n.k` and the provision's id is `n` (a whole article). Only ids in the
  context count.
- The sentence is `<amended> <link words> <source>.`, its ids the link's `target` and `source`.
  Each side is written from its resolved citation: `khoản <clause> Điều <article> <label>`, or
  `Điều <article> <label>` without a clause, the first letter of the sentence upper case. The
  link words are those of the link line: `được sửa đổi, bổ sung bởi`, `được thay thế bởi`,
  `bị bãi bỏ bởi`.

```text
Khoản 25 Điều 5 Luật 48/2024/QH15 được sửa đổi, bổ sung bởi khoản 2 Điều 1 Luật 149/2025/QH15. [1.25][2]
```

A not-found answer gets no notice. A notice makes no model call; it says that a provision was
changed, not what it now says, so an answer may still state an amended clause's old wording
(EVAL-006 measures the content).

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

**For the page** (#30: choices 1A and 8A, and the issue date approved after them). The web
page shows each source's text and dates beside the answer, so a citation in the context
carries them, taken from the passages and chunks the answer was made from. `Answer.text` does
not change, so the eval and the judge see the same answers.

- `doc_id`: the passage's document; the page reads `kind`, `title` and `issued` from its
  `Document`.
- `heading`: `Điều <article>. <title>`, the article's title from `articles.jsonl`, or
  `Điều <article>.` when the title is empty, as in the link's fragment.
- `text`: the provision as written in the corpus.
  - `n`, an article passage: the article's `text` from `articles.jsonl`.
  - `n.k`: clause k's lines, from its clause line to the line before the next clause line or
    to the article's end, clause lines as the context marks them ([context.md](context.md)),
    without the `[n.k] ` mark.
  - `m`, an amending passage: the source chunk's `text`.
- `effective`: an `effective_date` from `chunks.jsonl` (FR-CORE-004), of the provision cited.
  - `n.k`: the chunk `<article id>:K<k>` when the article has one; otherwise as for `n`.
  - `n`: the date its article's chunks share; none when they differ.
  - `m`: the source chunk's.

  A date may come before the document's `issued`: a document can take effect retroactively,
  and the date is kept as written ([chunk-schema.md](chunk-schema.md)).
- `amended_by`: the links of the passage (`Passage.links`) whose amended provision the id
  cites, in their order, as for the amendment notices; empty for an amending passage.

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
