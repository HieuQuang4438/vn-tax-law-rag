# Eval diagnosis of run 271adae

Written 2026-11-19. A post-hoc look at one results file, `eval/results/2026-11-18-271adae.json`
(eval set v2, commit `271adae`, retrieval as at `b0cced1`, answers and judge
`gemini-3.5-flash-lite`). Nothing was run again and no LLM was called. The groupings were chosen
after looking at the data, so every pattern here is a lead to test, not a finding: each option at
the end becomes an experiment with its own rule before anything changes.

Read from structured fields only (`recall`, `not_found`, `correct`, `sentences`,
`cited_sentences`, `cited_supported`, `flagged`, `expected`, `notices`, `dropped`, `tax_type`,
`form`, `added_in`), over the 184 answerable standalone questions. No question or answer text
was read.

## 1. EVAL-002: the citation ids, not the reasoning

| Items | Cited sentences | EVAL-002 |
|---|---|---|
| all | 376 | 0.774 |
| the 39 with a flagged id | 111 | 0.378 |
| the other 145 | 265 | 0.940 |

85 ids were flagged as not in the context (AC-009). 82 of them have a passage that exists and a
clause suffix with a point letter: `N.Na`, `N.Nb`, `N.N c`, `N.Nđ`, … The model cites down to the
point (điểm a, b, c of a clause); the id scheme stops at the clause, so the id matches nothing and
the sentence counts as unsupported. The other 3: one clause past the passages, two bare letters.

The earlier suspicion that the judge misgrades amendment notice sentences finds no support here:
items with notices score 0.78, items without 0.77.

## 2. EVAL-006: generation more than retrieval

| recall@8 | n | correct | share | not found |
|---|---|---|---|---|
| all expected articles | 110 | 59 | 0.54 | 8 |
| some | 60 | 13 | 0.22 | 14 |
| none | 14 | 2 | 0.14 | 8 |

- With every expected article in the top 8, 51 of 110 are lost: 43 answered and judged wrong, 8
  not found (q148, q154, q156, q167, q186, q240, q29, q75). Perfect retrieval alone would leave
  EVAL-006 near 0.54, against a target of 0.80.
- The 43 answered wrong with full recall: q102, q108, q109, q114, q115, q12, q122, q134, q137,
  q142, q151, q157, q165, q168, q169, q17, q170, q171, q173, q177, q182, q199, q205, q208, q209,
  q213, q22, q231, q233, q33, q37, q44, q48, q64, q73, q74, q77, q79, q82, q83, q86, q88, q90.
- Of 154 answered, 141 have every sentence judged supported, and 66 of those are correct: the
  answers are faithful but incomplete or off the point. The results file keeps only `correct`,
  not the judge's reason, so which of the two is not known.

## 3. Short answers to questions that need several articles

| Sentences in the answer | n | correct |
|---|---|---|
| 1–3 | 160 | 0.35 |
| 4 or more | 23 | 0.78 |

| Expected articles | n | correct |
|---|---|---|
| 1 | 71 | 0.62 |
| 2 | 58 | 0.34 |
| 3 | 33 | 0.24 |
| 4 or more | 22 | 0.09 |

`src/prompts/answer.md` at `271adae` says nothing about covering every part of the question.
Correlation only: questions that need more articles may simply be harder.

## 4. Smaller signals

- `household`: EVAL-006 0.14 (n = 28), 10 not found; also the lowest EVAL-001 (0.500 at
  `b0cced1`).
- All 30 not-found answers count as wrong: 30 of the 110 wrong.
- Context cut by the budget (`dropped`): 16 items, 0.50 correct. Not the main loss.

## Limits

- No judge reasons in the results file, so "missing a point" and "wrong" cannot be told apart.
  A hand-check of the 43 above, or the judge writing its reason to the file, would settle it.
- The judge is the answer model; on the `271adae` hand-check it agreed with the owner on 16 of 20
  `correct` grades.

## Options

| # | Change | Aimed at | Cost |
|---|---|---|---|
| 1 | Point-level ids normalised to the clause (`1.25a` to `1.25`), or the prompt told ids stop at the clause | EVAL-002; 0.940 on the unflagged items is an upper bound, not a forecast | very low |
| 2 | The answer prompt asks for every part of the question, from every passage that bears on it | EVAL-006 | low, one run |
| 3 | A stronger model on the same contexts | EVAL-006 | API spend |
| 4 | The context built from the top 12 hits instead of 8, the retrieval metrics still at 8 | EVAL-006, AC-015 | low, one run and a flag |

Retrieval is not where most answers are lost, so its options come last, and they reach ranks 9
and below without a reranker:

- AC-015's 15 retrieval misses are the amended provision itself not retrieved. Context assembly
  already adds the amending provision of every chunk it carries (FR-CORE-009,
  `docs/reference/context.md`, *Amending passages*), so these are recall misses.
- ADR-0002 measured bge-reranker-v2-m3 on the dev laptop at 19 to 28 s for 20 pairs, against
  AC-012's median under 2 s. An LLM reranker puts retrieval behind an API, against AC-012 and
  ADR-0002, and at about 440 tokens a chunk, 50 candidates are some 22,000 tokens a question.
- More hits in the context reach the same ranks with no new model: #24 found 30 of the 43
  standalone misses ranked 9 to 50 (eval set v1). The cost is the budget: at 8 hits the median
  context is about 13,000 of its 24,000 tokens, and 16 items already drop articles.

Options 1 to 4 are filed as #33, #34, #35 and #36.

## Method

Python over the results file: items with `answerable` true and `conversation` null; recall
bucketed as 1, between 0 and 1, and 0; EVAL-002 per group as the sum of `cited_supported` over
the sum of `cited_sentences`; flagged ids classified by shape with the digits replaced.
