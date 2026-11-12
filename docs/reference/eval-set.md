---
status: draft
updated: 2026-11-12
owner: HieuQuang4438
---

# Eval set format

What `eval/questions.yaml` holds, and what `python -m src.eval.check` checks in it. What the set
must contain, and how each metric is scored, is in
[acceptance.md](../product/acceptance.md#measurement-definitions); this page is the file format
that carries it. The approach is the approved comment on #7.

The set is written by hand. The checker never changes it: it reads the set and the local corpus
(`data/processed/`, `data/enriched/`) and reports errors and warnings. Errors make it exit with
code 1; warnings do not.

## File

UTF-8 YAML, one file, versioned in git.

```yaml
version: 1                 # raised on every change to the content
as_of: 2026-11-12          # the date the answers hold for: the corpus crawl date
questions:                 # 30-50 standalone questions
  - id: q01
    question: Hộ kinh doanh có doanh thu bao nhiêu thì không phải nộp thuế giá trị gia tăng?
    tax_type: household
    form: plain
    answer: Hộ kinh doanh có doanh thu năm từ 500 triệu đồng trở xuống không phải nộp thuế GTGT.
    key_facts:
      - doanh thu năm từ 500 triệu đồng trở xuống
    provisions:
      - 48/2024/QH15 Điều 5 khoản 25
      - 149/2025/QH15 Điều 1
  - id: q02
    question: Thuế suất thuế sử dụng đất phi nông nghiệp là bao nhiêu?
    tax_type: administration
    form: plain
    answer: Các văn bản trong bộ dữ liệu không quy định thuế sử dụng đất phi nông nghiệp.
    unanswerable: out_of_scope
conversations:             # at least 5, separate from the questions above
  - id: c01
    turns:                 # 2-3 turns; each turn has the fields of a question, without id
      - question: Cá nhân cho thuê nhà phải nộp những loại thuế nào?
        tax_type: pit
        form: plain
        answer: ...
        key_facts: [...]
        provisions: [...]
      - question: Còn hộ kinh doanh thì sao?
        tax_type: household
        form: plain
        answer: ...
        key_facts: [...]
        provisions: [...]
```

The figures in this example show the shape only; they are not checked answers.

### Fields of a question or a turn

| Field | Required | Value |
|---|---|---|
| `id` | questions only | unique across the file; a turn's id is `<conversation id>.<n>`, from 1 |
| `question` | yes | the question as a user would ask it |
| `tax_type` | yes | `administration`, `vat`, `pit`, `cit`, `sct` or `household` |
| `form` | yes | `plain` for plain language, `reference` when the question names a provision or a document number ("Điều 9 Luật 48/2024") |
| `answer` | yes | the expected answer, one sentence; for an unanswerable question, what the not-found reply should say |
| `key_facts` | answerable only | 1–4 short facts that can each be checked: a figure, a rate, a condition, a deadline. An answer is correct when it states every one and contradicts none (EVAL-006) |
| `provisions` | answerable only | the provisions that support the answer, at least one, in the form below |
| `unanswerable` | unanswerable only | `out_of_scope` (the corpus does not cover it) or `repealed` (about a rule no longer in force) |

A question is answerable exactly when it has no `unanswerable` field. Any other field is an
error, so a typo cannot pass as an empty value.

### Provisions

Written the way a provision is cited, one per line:

```text
<document number> Điều <article>[ khoản <clause>]
```

- The document number is its `so_hieu` as in the corpus (`48/2024/QH15`, `252/2026/NĐ-CP`),
  compared without regard to case. Article and clause are numbers, optionally with a letter
  (`Điều 5`, `khoản 1a`). A point (`điểm`) is not written: the clause that holds it is.
- Each provision resolves to the id of its article, as in `articles.jsonl`: `48/2024/QH15 Điều 9`
  → `379409:D9`. Recall and context precision count articles: a clause chunk counts for its
  parent article (acceptance.md, *recall@k*).
- A clause also resolves to its clause chunk when the article is split
  (`48/2024/QH15 Điều 5 khoản 25` → `379409:D5:K25`); in an unsplit article it resolves to the
  article chunk, and the clause is not checked further.
- An amended provision is listed together with the provision that amends it, as approved on #7:
  AC-015 requires the answer to cite the amending text, and recall then checks that it is
  retrieved.

## What the checker reports

Every message about one question or turn starts with `line <n>: <id>: `, where `<n>` is the
line of that question in the file. Messages about the set as a whole have no prefix.

**Errors.**

| Rule | Message contains |
|---|---|
| a required field is absent | `missing field "<field>"` |
| a field not in the table above | `unknown field "<field>"` |
| two questions share an id | `duplicate id "<id>"` |
| `tax_type` not in the list | `tax_type "<value>"` |
| `form` not in the list | `form "<value>"` |
| `unanswerable` not in the list | `unanswerable "<value>"` |
| an answerable question with no provision | `no provisions` |
| an answerable question with fewer than 1 or more than 4 key facts | `key_facts: 1 to 4` |
| an unanswerable question with provisions or key facts | `unanswerable but has provisions`, `unanswerable but has key_facts` |
| a provision not in the form above | `cannot read provision "<text>"` |
| a document number not in the corpus | `unknown document "<number>"` |
| an article not in that document | `no Điều <article> in <number>` |
| a clause missing from a split article | `no khoản <clause> in Điều <article> of <number>` |
| the number of questions | `30 to 50 questions, found <n>` |
| unanswerable questions under 20% of the questions | `unanswerable share <x.xx> is below 0.20` |
| a tax type with no question | `no question with tax_type "<type>"` |
| a form with no question | `no question with form "<form>"` |
| fewer than 5 conversations | `at least 5 conversations, found <n>` |
| a conversation with fewer than 2 or more than 3 turns | `2 to 3 turns` |
| `version` not a positive integer, `as_of` not a date | `version`, `as_of` |

The counts in the last rows are over the standalone questions; conversations are counted apart.

**Warnings.**

| Rule | Message contains |
|---|---|
| an expected provision has `amended_by` (in `data/enriched/chunks.jsonl`) and the article of the amending source is not among the question's provisions | `amended by <source article>, which is not listed` |
| an expected provision's article is in [corpus.md](corpus.md#amendments-from-outside-the-corpus), *Amendments from outside the corpus*: the corpus text there may not be the law in force | `amended from outside the corpus` |
| `form: reference` but the question names no article (`Điều <n>`) and no document number | `form reference but names no provision` |

For the second warning the checker reads the table in `corpus.md`, which owns that list: the
document id from the first column, and every article number written as `Article <n>` or
`Articles <n> and <m>` in the second. A row with no article, such as an annex, adds nothing.

## Loading it

`src.eval.dataset.load_eval_set(path, processed_dir, enriched_dir)` returns the set with each
provision resolved to its article id, together with the file's `sha256` and its `version`. It
raises `EvalSetError`, carrying the checker's errors, when there is any. Every eval result records
the version and the `sha256`: a score is comparable only with scores from the same version
(acceptance.md, *Eval set*).

## Cold read

Once written, the set is read once by a subagent that took no part in writing it, given only the
set file and the local corpus, with no cloud and no Hugging Face Hub access (CONVENTIONS §9). For
every question it checks that the listed provisions support the answer and the key facts, that
an unanswerable question has no answer in the corpus, and that the wording reads like a user
rather than like the corpus. Its findings are reported to the human owner, who decides what to
change. Approved on #7.
