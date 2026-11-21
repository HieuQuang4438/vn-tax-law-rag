---
status: approved
updated: 2026-11-20
owner: HieuQuang4438
approved-by: self (built)
issue: 34
---

# Prompt for every part of the question

Does an answer prompt that asks the model to answer every part of the question, from every
passage that bears on it, raise EVAL-006 on eval set v2? The question is #34; the approach is the
approved comment on #34, choices 1B, 2A and 3A.

At `271adae`, answers of 1 to 3 sentences were judged correct 0.35 of the time and answers of 4
or more 0.78, and correctness fell with the number of expected articles
(`eval/results/2026-11-18-271adae.json`, structured fields). The prompt had no rule on covering
the whole question.

**The change.** One rule added to `src/prompts/answer.md`, after the rule on partial answers
(choice 1B):

> Answer every part of the question, using every passage that bears on it. Give each condition,
> exception, rate, threshold or deadline the passages state in its own sentence; do not fold
> several provisions into one sentence.

**Run.** `python -m src.eval.run --generate --rewrite none --compare
eval/results/2026-11-19-69f6ab4.json`. Everything as at `69f6ab4` apart from the prompt: eval set
v2 (`f14d299e`), the same index (bge-m3 `5617a9f6`, `syllable` BM25, 1,286 chunks), `TOP_K` 8,
`RRF_K` 60, 50 candidates, one hit per article, `rewrite: none`, answer and judge
`gemini-3.5-flash-lite`, the same judge prompt (by hash), budget 24,000, bootstrap seed and
resamples; no temperature or seed set, as before. The baseline is #33's run (choice 2A).

**Decision rule** (in #34, fixed before the run). Keep the prompt when the paired 95% interval of
the EVAL-006 change lies entirely above 0, neither EVAL-002 nor EVAL-003 changes with an interval
entirely below 0, and EVAL-004 stays at or above 0.80. When EVAL-006's interval includes 0, record
the run as inconclusive and revert the prompt, its spec and its test (choice 3A).

## Result

Run on 2026-11-19 at commit `0dd6f44`, clean, on the dev laptop (i7-10610U, 16 GB RAM, CPU only):
`eval/results/2026-11-19-0dd6f44.json`. 6,118 s; 0.0050 USD per item, 1.21 USD in all, and the
judge's 147 calls 0.74 USD.

| Metric | `69f6ab4` | `0dd6f44` | Paired change |
|---|---|---|---|
| EVAL-006 | 0.386, n = 184 | 0.413 [0.342, 0.484], n = 184 | +0.027 [−0.016, +0.071] |
| EVAL-002 | 0.950, n = 379 | 0.968 [0.951, 0.983], n = 507 | +0.019 [−0.002, +0.043] |
| EVAL-003 | 0.971, n = 155 | 0.974 [0.956, 0.989], n = 147 | +0.003 [−0.014, +0.019] |
| EVAL-004 | 0.982, n = 56 | 0.982 [0.946, 1.000], n = 56 | 0 |
| EVAL-001, EVAL-005, EVAL-007 | 0.769, 0.494, 0.678 | the same | 0, every item |

- **Inconclusive, so the prompt is reverted (choice 3A).** EVAL-006's interval includes 0.
  EVAL-002, EVAL-003 and EVAL-004 pass their guards. The prompt, its spec in
  `docs/reference/answer.md`, its test and its changelog line are reverted in `1e4f1a2`; the
  answer prompt is again the one of `69f6ab4`, by hash.
- **The paired intervals of EVAL-002, EVAL-003 and EVAL-006 are computed outside the runner,** as
  in [the point-level id record](2026-11-19-point-level-ids.md): the same 184 items resampled
  1,000 times with the run's seed, EVAL-002 as the ratio of the sums in each resample, EVAL-003
  over the items answered in each run.
- **17 items changed verdict:** 11 from wrong to correct, 6 from correct to wrong. An unchanged
  rerun changed 11 (the point-level id record, *Run-to-run noise*), so the net 5 is within what
  noise alone moves.

## Beside the decision

| | `69f6ab4` | `0dd6f44` |
|---|---|---|
| Sentences per answered item, mean (median) | 2.45 (2) | 3.45 (2) |
| Answers of 7 sentences or more | 7 | 19 |
| Not found, answerable | 29 | 37 |
| Output tokens per item, mean (median) | 194 (132) | 231 (135) |
| Generation latency, median and p95 | 2.36 s, 8.22 s | 6.84 s, 30.75 s |
| Answer cost per item | 0.0050 USD | 0.0050 USD |

EVAL-006 by the number of expected articles, and by answer length:

| Expected articles | n | `69f6ab4` | `0dd6f44` |
|---|---|---|---|
| 1 | 71 | 0.63 | 0.63 |
| 2 | 58 | 0.31 | 0.38 |
| 3 | 33 | 0.18 | 0.21 |
| 4 or more | 22 | 0.09 | 0.09 |

| Sentences | `69f6ab4` | `0dd6f44` |
|---|---|---|
| 1 to 3 | 54 of 155, 0.35 | 48 of 140, 0.34 |
| 4 to 6 | 12 of 22, 0.55 | 14 of 24, 0.58 |
| 7 or more | 5 of 7, 0.71 | 14 of 19, 0.74 |

- **Answers grew at the top only.** The median stayed at 2 sentences; the mean rose by one, from
  the 12 more answers of 7 sentences or more. Within each length band, correctness barely moved.
- **Not found rose from 29 to 37** on answerable questions (by recall@8: 12 all, 18 some, 7 none),
  against the rule's intent. One of them, q186, is an empty reply (9 output tokens, no sentence),
  which counts as not found by definition. Unanswerable: 55 of 56, unchanged.
- **Latency breaks NFR-006** (median ≤ 10 s, p95 ≤ 20 s): 6.88 s median and 30.53 s p95 over the
  full pipeline, 240 items. Generation latency counts only the attempt that succeeded, and the
  median output grew by 3 tokens, so the prompt is not the evident cause. The API was busier: 189
  server errors (503) and 15 rate limits (429) in the log, against 123 and 2 for `69f6ab4`. Not
  measured further; the prompt is reverted.
- **Cost stays under NFR-007** (≤ 0.01 USD per item).
- AC-015: 20 pass, 6 fail, 15 retrieval misses, of 41; 7 uncited: not met. Fails q01, q37, q56,
  q197, q199, q200, the same six as at `69f6ab4`.

## What follows

The run cannot tell a real effect below about +0.04 from noise. Answer text is stored
(`data/eval-answers/`): across two unchanged runs, 105 of 184 answers changed text, and of the 11
verdicts that changed, only one had the same text, so most of the noise is the answer model's,
not the judge's. A noise issue comes before any rerun of this prompt (choice 3A).
