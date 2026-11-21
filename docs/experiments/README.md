---
status: living
updated: 2026-11-21
owner: HieuQuang4438
---

# Experiment register — vn-tax-law-rag

Every measured run in this repo, newest first: one file per question, dated by the day its
configuration was fixed. Format and the `status` values: `DOCS-CONVENTIONS.md` §3, *`experiments/` —
measured runs*. Raw per-item results stay in `eval/results/`; each file points at its own.

This table is the index. An agent recording a run writes its own file and reports it; **the row
here is added by the main thread**, because the register is shared state — `CONVENTIONS.md` §9.

| Date | Question | Issue | Status | Conclusion | Superseded by |
|---|---|---|---|---|---|
| 2026-11-20 | [Context of 12 hits instead of 8](2026-11-20-context-k-12.md) | #36 | approved | inconclusive, 8 kept: EVAL-009 +0.002 [−0.024, +0.029]; EVAL-006 +0.022 [−0.011, +0.052] | |
| 2026-11-20 | [Prompt for every part of the question, two runs per arm](2026-11-20-every-part-prompt-two-runs.md) | #38 | approved | inconclusive, prompt reverted: EVAL-009 +0.007 [−0.019, +0.033]; EVAL-006 +0.057 [+0.022, +0.092] | |
| 2026-11-20 | [Run-to-run noise in EVAL-006](2026-11-20-eval006-noise.md) | #37 | approved | k = 2 runs per arm: projected half-width ±0.028 against ±0.040 for one; the judge alone changes 4 of 184 verdicts | |
| 2026-11-19 | [Prompt for every part of the question](2026-11-19-every-part-prompt.md) | #34 | approved | inconclusive, prompt reverted: EVAL-006 +0.027 [−0.016, +0.071] | |
| 2026-11-19 | [Point-level citation ids](2026-11-19-point-level-ids.md) | #33 | approved | kept: EVAL-002 0.774 to 0.950, +0.176 [+0.103, +0.263]; flagged ids 85 to 2 | |
| 2026-11-18 | [Follow-up rewriters](2026-11-18-follow-up-rewriters.md) | #19 | approved | `concat` chosen; no rewriter separates from `none`, so the four are re-measured on eval set v3 | |
| 2026-11-17 | [Not-found reply, generation run](2026-11-17-not-found-generation.md) | #16 | approved | EVAL-004 0.982, target met; AC-015 not met: 21 pass, 7 fail | |
| 2026-11-16 | [Cited answers, generation runs](2026-11-16-cited-answers-generation.md) | #15 | approved | two runs; EVAL-002 0.855 and 0.868, EVAL-006 0.380 and 0.402; AC-015 not met | |
| 2026-11-15 | [Re-check of one hit per article on eval set v2](2026-11-15-per-article-eval-set-v2.md) | #28 | approved | `per_article` stays: EVAL-001 +0.012 [+0.004, +0.023] | |
| 2026-11-15 | [Embedding model on eval set v2](2026-11-15-embedding-model-eval-set-v2.md) | #27 | approved | bge-m3 stays: Vietnamese_Embedding +0.015 [−0.006, +0.038] | |
| 2026-11-15 | [Retrieval baseline, eval set v2](2026-11-15-retrieval-baseline-eval-set-v2.md) | #26 | approved | EVAL-001 0.769, EVAL-005 0.494, EVAL-007 0.678 | |
| 2026-11-15 | [Fusion tuning](2026-11-15-fusion-tuning.md) | #25 | approved | `per_article` adopted: EVAL-001 +0.036 [+0.006, +0.071] | |
| 2026-11-14 | [Cut diagnosis](2026-11-14-cut-diagnosis.md) | #24 | approved | verdict `ranking`: 30 of the 43 standalone misses are ranked 9 to 50 | |
| 2026-11-14 | [Chunk threshold](2026-11-14-chunk-threshold.md) | #12 | approved | `MAX_TOKENS` 1,600: EVAL-001 +0.044 [+0.005, +0.091] over 800 | |
| 2026-11-14 | [Embedding model](2026-11-14-embedding-model.md) | #11 | approved | bge-m3 stays: Vietnamese_Embedding +0.030 [−0.035, +0.094] | |
| 2026-11-13 | [BM25 tokenizer](2026-11-13-bm25-tokenizer.md) | #10 | approved | `syllable` stays: neither segmenter's interval lies above 0 | |
| 2026-11-13 | [Retrieval baseline, eval set v1](2026-11-13-retrieval-baseline-eval-set-v1.md) | #9 | approved | EVAL-001 0.633, EVAL-005 0.575, EVAL-007 0.676; EVAL-001 target kept at 0.80 | |
| 2026-11-13 | [Retrieval latency and references](2026-11-13-retrieval-latency-and-references.md) | #8 | approved | AC-012 met: median 0.448 s, 95th percentile 0.775 s; AC-007: all 4 named articles retrieved | |

No file here is `superseded`. The two re-runs on eval set v2, #27 and #28, confirmed the
conclusions they re-checked rather than replacing them, so each earlier file stands and links to
its re-run.

## Standing scores

The newest score of each metric, against its target in
[acceptance.md](../product/acceptance.md). Each score holds for the run its file records, not for
HEAD; a later run that changes one replaces its row, in the same change that adds its register
row. A run whose change is reverted does not replace a row. When several runs measure one
configuration, the row holds their mean, each item averaged over the runs first, with the interval
of those per-item means (#37).

| Metric | Score | n | 95% interval | Target | Met | Measured in |
|---|---|---|---|---|---|---|
| EVAL-001 recall@8 | 0.769 | 184 | 0.715–0.813 | ≥ 0.80 | ⬜ no | [2026-11-15-retrieval-baseline-eval-set-v2.md](2026-11-15-retrieval-baseline-eval-set-v2.md) |
| EVAL-002 citation correctness, 3 runs | 0.954 | 1,162 | 0.934–0.972 | ≥ 0.90 | ✅ yes | [2026-11-20-eval006-noise.md](2026-11-20-eval006-noise.md) |
| EVAL-003 faithfulness, 3 runs | 0.969 | 157 | 0.953–0.983 | ≥ 0.90 | ✅ yes | [2026-11-20-eval006-noise.md](2026-11-20-eval006-noise.md) |
| EVAL-004 not found on unanswerable, 3 runs | 0.982 | 56 | 0.946–1.000 | ≥ 0.80 | ✅ yes | [2026-11-20-eval006-noise.md](2026-11-20-eval006-noise.md) |
| EVAL-005 recall@8, follow-up turns, `concat` | 0.526 | 29 | 0.360–0.670 | ≥ 0.70 | ⬜ no | [2026-11-18-follow-up-rewriters.md](2026-11-18-follow-up-rewriters.md) |
| EVAL-006 answer correctness, 3 runs | 0.364 | 184 | 0.299–0.431 | ≥ 0.80 | ⬜ no | [2026-11-20-eval006-noise.md](2026-11-20-eval006-noise.md) |
| EVAL-007 context precision@8 | 0.678 | 184 | 0.626–0.728 | ≥ 0.60 | ✅ yes | [2026-11-15-retrieval-baseline-eval-set-v2.md](2026-11-15-retrieval-baseline-eval-set-v2.md) |
| EVAL-008 answer relevancy | not run | | | none | | |
| EVAL-009 key-fact coverage, 3 runs | 0.583 | 184 | 0.528–0.637 | none | | [2026-11-20-eval006-noise.md](2026-11-20-eval006-noise.md) |
| AC-012 median retrieval time, `concat` | 0.21 s | | | < 2 s | ✅ yes | [2026-11-18-follow-up-rewriters.md](2026-11-18-follow-up-rewriters.md) |
| AC-015 amended provisions, 3 runs | 21, 21, 22 pass; 6, 7, 5 fail | 42, 43, 42 | | every one passes | ⬜ no | [2026-11-20-eval006-noise.md](2026-11-20-eval006-noise.md) |

EVAL-001, EVAL-007 and AC-012 are retrieval as at `b0cced1`; the generation runs and the rewriter
runs kept that retrieval. The three runs of the generation rows are `69f6ab4`, unseeded, and
`e8c4f1b` with seeds 1 and 2; EVAL-002's n is the cited sentences of all three. EVAL-009 is
those three runs re-scored from their stored verdicts by #39, `eval/results/2026-11-20-dc5ddea.json`,
`-2` and `-3`. AC-015 is given
per run, since its counts do not average: each run's total is its passes, fails and 15 retrieval
misses; 5 or 6 more questions were uncited. AC-015 reports both and judges neither.
