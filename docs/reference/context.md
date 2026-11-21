---
status: approved
updated: 2026-11-21
owner: HieuQuang4438
approved-by: peer
---

# Context assembly

What `src.context` makes of a retrieval result: the passages the model reads, each with a
citation id, cut to a token budget. It reads the enriched chunks and the full articles
([chunk-schema.md](chunk-schema.md)); it calls no model and makes no network request. The rule
is FR-CORE-009, its test AC-008. The approach is the approved comment on #14.

## Interface

```python
from src.context import Assembler

assembler = Assembler.load()              # the chunks, the articles and the bge-m3 tokenizer, once per process
context = assembler.assemble(retrieval)   # a src.retrieval.Retrieval
context.text        # what the model reads
context.passages    # list[Passage], in the order of context.text
```

| Name | What it is |
|---|---|
| `Assembler(chunks, articles, count_tokens, budget=BUDGET)` | `chunks`: the records of `data/enriched/chunks.jsonl`; `articles`: the records of `articles.jsonl`; `count_tokens`: a function from text to its token count. |
| `Assembler.load(data_dir=Path("data"), count_tokens=None, budget=BUDGET)` | The same, from `data_dir/enriched/chunks.jsonl` and `data_dir/chunks/articles.jsonl`. With no `count_tokens`, the bge-m3 tokenizer, loaded offline (`src.chunking.tokens.bge_m3_token_counter`). |
| `Assembler.assemble(retrieval)` | A `Context` for one retrieval result. The same retrieval always gives an equal `Context`, with the same `text` byte for byte. |
| `Context` | `passages: list[Passage]`; `text: str`, the passages' texts joined by one blank line (`"\n\n"`), `""` when there are none; `tokens: int`, `count_tokens(text)`; `dropped: list[str]`, the ids of the articles left out for the budget, in rank order; `unresolved: list[Unresolved]`, the retrieval's, unchanged. |
| `Passage` | `id: str`, the citation number (`"1"`, `"2"`, …); `kind: str`, `article` or `amending`; `doc_id: str`; `article: str`; `chunk_ids: tuple[str, ...]`, every chunk of the article in file order for an `article` passage, the source chunk alone for an `amending` one; `clauses: tuple[str, ...]`, the clause ids marked in it, in order, empty for an `amending` passage; `text: str`, the passage as sent; `links: tuple[Link, ...]`, its link lines, in order, empty for an `amending` passage. |
| `Link` | One link line: `target: str`, the amended chunk's id; `type: str`, `amends`, `replaces` or `repeals`; `source: str`, the source's id. Ids without brackets: `1.25`, `3`. |
| `BUDGET` | 24,000 tokens. |

## Passages

**Article passages.** Each retrieved chunk brings its whole parent article (`parent_id`), from
`articles.jsonl`. An article is one passage however many of its chunks were retrieved, so a
clause's text is never sent twice. Articles are ordered by their best-ranked retrieved chunk:
the reference slots come first, as retrieval ranks them.

**Amending passages.** For every chunk of an article passage, retrieved or not, each entry of
its `amended_by` brings the entry's `source` chunk: the chunk alone, not its parent article. It
becomes an `amending` passage placed after the article passage it changes, unless the source is
already in the context:

- its parent article is an article passage of the context, or
- it is already an `amending` passage, placed after an earlier article.

Amending passages after one article come in the order of the amended chunks in the file, then of
their `amended_by` entries. An amending passage is not itself checked for `amended_by`.

**Duplicates.** One article, one passage; one source chunk, at most one passage, and none when its
article is in the context. Identical text in two different provisions is kept: they are
different sources.

## Citation ids

Passages are numbered `1`, `2`, … in order. `[n]` cites passage n.

An article passage also marks its clauses. A clause line is one the chunker would start a
clause at: it matches `^(\d+)\.\s` and does not start inside a quotation, with the quotation depth
counted from the article's first line (chunk-schema.md, ADR-0001). Clause k of passage n is cited
`[n.k]`. A clause number repeated in one article gets `.2`, `.3`, … from its second occurrence, as
the chunker's ids do (`K3.2`), so it is cited `[n.3.2]`. On the corpus (2026-11-16) 660 of
the 744 articles have clause lines, and none repeats a number. `[n]` stays valid for the article's
intro lines or for the whole article.

A clause chunk (`:K<k>`) of a split article is `[n.k]`; a whole-article chunk and a `:K0` intro
chunk are `[n]`. An amending passage has no clause ids: `[m]`.

## Text as sent

An article passage:

```text
[1] [Luật 48/2024/QH15 — Thuế giá trị gia tăng] [Điều 5. Đối tượng không chịu thuế]
[1.1] 1. Sản phẩm trồng trọt chưa chế biến.
[1.25] 25. Hàng hóa, dịch vụ của hộ kinh doanh có doanh thu năm từ 500 triệu đồng trở xuống.
[1.25] được sửa đổi, bổ sung bởi [2].

[2] [Luật 149/2025/QH15 — Sửa đổi, bổ sung một số điều của Luật Thuế giá trị gia tăng] [Điều 1. Sửa đổi, bổ sung một số điều của Luật Thuế giá trị gia tăng]
Sửa đổi, bổ sung khoản 25 Điều 5 Luật Thuế giá trị gia tăng số 48/2024/QH15 như sau:
```

(Article 5 shortened here; a passage carries the whole article.)

- **First line.** `[n] ` and the header of a whole-article chunk of that article (chunk-schema.md,
  *Header form*): the header with no `Khoản` part.
- **Body.** The article's `text`, each clause line prefixed with `[n.k] `.
- **Link lines.** One line per `amended_by` entry of the article's chunks, in the order above:
  the amended chunk's id, the link type, and where the source is in the context — an amending
  passage `[m]`, or `[p]` / `[p.k]` when its article is in the context.

  | `type` | Line |
  |---|---|
  | `amends` | `[n.k] được sửa đổi, bổ sung bởi [m].` |
  | `replaces` | `[n.k] được thay thế bởi [m].` |
  | `repeals` | `[n.k] bị bãi bỏ bởi [m].` |

An amending passage is `[m] `, the source chunk's own header, a newline and its `text`.

The approved choice put the link type on the amending passage. It is written on the amended
passage's link line instead, so one form also covers a source already in the context, which has
no amending passage of its own.

## Token budget

`Context.tokens` is at most `BUDGET`: 24,000 bge-m3 tokens, counted over `Context.text`. The
budget covers the passages only, not the system prompt, the question or the history.

Over the budget, whole articles are dropped from the lowest-ranked up, each with the amending
passages placed after it: the context is the longest run of articles, in rank order, whose text
fits. Text is never cut inside a passage. Ids are given after the cut, so they have no gaps. The
dropped articles' ids go to `Context.dropped`. The top article is always kept: if it alone, with
its amending passages, is over the budget, the context is that article and `tokens` is over
`BUDGET`. On the corpus this cannot happen: the largest article is 8,072 tokens, and an amending
source at most 567.

bge-m3 is not the generation model's tokenizer. On the LLM pilot (#13, 18 questions, top 8
chunks), Gemini counted 1.10 times as many tokens as bge-m3 in the median, 1.21 at most.

**Measured on 2026-11-16** at commit `e881246`, eval set v2 (its 240 questions; the 22
conversations not included), top 8, default `Fusion()`, bge-m3 `5617a9f6`, before any cut:

| | Median | p95 | Max |
|---|---|---|---|
| Top 8 chunks, header + text | 7,071 | 10,687 | 14,755 |
| Their articles + the retrieved chunks' amending sources | 11,902 | 23,882 | 29,800 |

| Budget | Questions over it, of 240 |
|---|---|
| 16,000 | 63 |
| 24,000 | 11 |
| 32,000 | 0 |

102 of the 240 had a retrieved chunk with an `amended_by` entry. The corpus has 33 links;
their source chunks are 423 tokens in the median, 567 at most.

**Assembled** on 2026-11-16, same setup, `Context.tokens` after the cut, with the 52 turns of
the 22 conversations as well (each turn's own text, not rewritten):

| | Questions (240) | Conversation turns (52) |
|---|---|---|
| Tokens, median / p95 / max | 12,851 / 23,213 / 23,902 | 15,929 / 23,587 / 23,819 |
| Cut by the budget | 17 (24 articles dropped) | 7 (9 articles dropped) |
| Amending passages | 222 | 33 |
| Link lines | 384 | 53 |
| Assembly time, median / max | 0.061 s / 0.625 s | 0.075 s / 0.357 s |

More are cut than the 11 measured before: the context adds link lines, clause marks and the
amending text of every amended chunk of an article, not only of the retrieved one. AC-008 holds
on all 292 (`pytest -m corpus`, `test_ac008_on_the_eval_set`).
