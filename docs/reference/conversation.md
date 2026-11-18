---
status: draft
updated: 2026-11-18
owner: HieuQuang4438
---

# Conversation

How a session keeps a conversation and turns each follow-up into the query that retrieval
gets: the rewriters, the session, and how the eval run scores them. The rule is FR-CORE-016,
its tests AC-014 and EVAL-005 ([acceptance.md](../product/acceptance.md)). The approach is the
approved comment on #19.

## Rewriters — `src.conversation.rewrite`

A rewriter takes a question and the earlier questions of its conversation and returns a
`Rewrite`: the queries retrieval gets and the question generation gets.

| Name | What it is |
|---|---|
| `REWRITERS` | `("none", "concat", "fuse", "llm")` |
| `EARLIER` | 2: how many earlier questions a rewriter reads, the last ones |
| `DEFAULT_REWRITER` | `concat`: the rewriter chosen on #19, the session's and the eval run's default |
| `rewriter(name, llm=None)` | The rewriter of that name. `llm` is used by `llm` only; none means `LLM()`. Raises `ValueError` for a name not in `REWRITERS`. |
| `Rewriter.name` | Its name. |
| `Rewriter.rewrite(question, earlier=())` | `earlier`: the earlier questions of the conversation, oldest first. Returns a `Rewrite`. |
| `Rewrite` | `question: str`, what generation gets; `queries: tuple[str, ...]`, what retrieval gets, one or two; `call: Call` or none, the model call of `llm`; `latency_s: float`, the call's `latency_s` for `llm`, else 0. |
| `RewriteOutput` | The reply schema of `llm`: `{"question": str}`. |
| `PROMPT` | `src/prompts/rewrite.md` |

**The first turn.** With `earlier` empty, every rewriter returns `Rewrite(question, (question,))`
and makes no call: a first turn is passed through unchanged (AC-014).

**A follow-up**, with `earlier` not empty, of which the last `EARLIER` are read (choice 1A: the
earlier questions only, not the answers). The **concatenation** is those earlier questions and
the follow-up joined by one space, in order.

| Rewriter | `question` | `queries` |
|---|---|---|
| `none` | the follow-up | the follow-up |
| `concat` | the concatenation | the concatenation |
| `fuse` | the concatenation | the follow-up, then the concatenation; retrieval fuses the two (below) |
| `llm` | the model's question, trimmed | that question |

`EARLIER` is 2 because no conversation of eval set v2 has more than 3 turns, so every
follow-up there reads all its earlier questions; in a longer chat it keeps the query from
growing with every turn.

**`llm`.** One call, `llm.generate("rewrite", PROMPT text, user, RewriteOutput, validate)`, with
the user text

```text
Earlier questions:
1. <earlier question>
2. <earlier question>

Follow-up: <question>
```

`validate` refuses a reply whose `question` is empty once trimmed, so the call retries as for
any reply that does not fit (answer.md, *The model call*). The prompt asks for one Vietnamese
question that can be understood without the earlier ones, taking from them only what the
follow-up leaves out, answering nothing and adding nothing, and for the follow-up unchanged
when it already stands alone (choice 5A).

**A follow-up that stands alone** (choice 5A). `concat` and `fuse` always combine; only `llm`
can leave a follow-up unchanged. A follow-up that changes topic may carry the earlier topic
into its query under `concat`; `fuse` keeps the follow-up's own list beside it.

## Fusing two queries — `Retriever.fuse`

`Retriever.fuse(questions, k=TOP_K)` ([retrieval.md](retrieval.md)) searches each question as
`retrieve` does and joins their uncut lists (`Rankings.final`) by `rrf` with the retriever's
`rrf_k`, each list weighing 1. With `per_article`, a chunk whose parent article already has a
chunk above it is skipped, as in `retrieve`, unless it is a reference slot of one of the
searches: `retrieve` never skips a slot, so one question keeps its two named clauses of one
article. The first k are the hits. A hit's `found_by` holds
every way any of the searches found it, in the fixed order (`reference` when it is a reference
slot of any of them), and its `score` is its score in this fusion. `unresolved` holds each
search's, in question order, an entry with the same text and reason as an earlier one kept
once. With one question, the hits are `retrieve`'s chunks in `retrieve`'s order.

A reference slot keeps no place of its own in the fusion: it is ranked by its places in the
two lists, which for a slot are near the top.

## The session — `src.conversation.Session`

| Name | What it is |
|---|---|
| `Session(retriever, answerer, rewriter=None, k=TOP_K)` | One conversation. `rewriter` none means `rewriter(DEFAULT_REWRITER)`, kept as `Session.rewriter`. |
| `Session.turns` | `list[Turn]`, oldest first. |
| `Session.ask(question)` | Rewrites the question with the questions of `turns` as `earlier`; retrieves with `retriever.retrieve(query, k)` for one query and `retriever.fuse(queries, k)` for two; answers with `answerer.answer(rewrite.question, retrieval)`; adds the turn and returns it. |
| `Turn` | `question: str`, as asked; `rewrite: Rewrite`; `retrieval: Retrieval`; `answer: Answer`. |

**What generation sees** (choice 2A): the rewritten question and the passages, as for a
standalone question; no earlier turn. An answer cannot refer back to an earlier one, and the
citations are checked as for any answer (AC-009).

## In the eval run

`python -m src.eval.run --rewrite <name>` ([eval-results.md](eval-results.md)) runs the
conversation turns through that rewriter; `DEFAULT_REWRITER` is the default, and `none`
keeps each turn as written, as before #19. Each rewriter is its own run, compared with a `none`
run of the same commit by `--compare` and `--comparisons 3`. `RetrievalPipeline` and
`AnswerPipeline` built without a rewriter use `none`.

- The earlier questions of a turn are the questions of the turns before it in its
  conversation, as written in the eval set.
- Turns stay retrieval-only, with or without `--generate`; standalone questions never go
  through a rewriter.
- EVAL-005 scores the result: recall@8 on the answerable follow-up turns.

**Choosing the rewriter** (choice 3A, fixed before measuring): the LLM-free rewriter, `concat`
or `fuse`, with the higher EVAL-005; `llm` instead only if its paired change over that rewriter
has a Bonferroni lower bound above 0 (3 comparisons), since it puts a model call on the
retrieval path (NFR-006, NFR-007), and then with an ADR. The sample is the 29 answerable
follow-ups of eval set v2 (choice 4A).
