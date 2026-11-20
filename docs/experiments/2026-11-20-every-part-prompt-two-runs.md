---
status: approved
updated: 2026-11-20
owner: HieuQuang4438
approved-by: self (built)
issue: 38
---

# Prompt for every part of the question, two runs per arm

With two runs per arm, does #34's prompt rule, answering every part of the question with one
provision per sentence, raise key-fact coverage (EVAL-009) on eval set v2 without lowering
EVAL-006? The question is #38; the approach is the approved comment on #38, choices 1A, 2A and 3A.

#34 ran the rule once against one baseline run and could not tell it from noise
([the every-part prompt record](2026-11-19-every-part-prompt.md)). #37 set two runs per arm for
a generation experiment ([the noise record](2026-11-20-eval006-noise.md)), and #39 made EVAL-009
the deciding metric, with EVAL-006 guarded.

**The change.** #34's rule, word for word (#34's choice 1B), back in `src/prompts/answer.md`
after the rule on partial answers, with its spec and its test (`b7aff32`, `9191469`). The answer
prompt hash, `60741967`, is the one of `0dd6f44`.

> Answer every part of the question, using every passage that bears on it. Give each condition,
> exception, rate, threshold or deadline the passages state in its own sentence; do not fold
> several provisions into one sentence.

**Runs.** `python -m src.eval.run --generate --rewrite none --seed 1`, then `--seed 2`, at
`9191469`. Everything as at `e8c4f1b` apart from the prompt: eval set v2 (`f14d299e`), retrieval
as at `b0cced1` (bge-m3, `syllable` BM25, `TOP_K` 8, `RRF_K` 60, 50 candidates, one hit per
article), `rewrite: none`, answer and judge `gemini-3.5-flash-lite`, the same judge prompt
(`2643e130`), budget 24,000, google-genai 3.3.0.

**Baseline** (choice 1A): the seed 1 and seed 2 runs of `e8c4f1b`, as re-scored with EVAL-009 by
#39, `eval/results/2026-11-20-dc5ddea-2.json` and `-3.json`. Both arms draw with the same seeds.

**Decision rule** (in #38, fixed before the runs). Keep the prompt when the paired 95% interval of
the EVAL-009 change lies entirely above 0, none of EVAL-006, EVAL-002 and EVAL-003 changes with an
interval entirely below 0, and EVAL-004 stays at or above 0.80. When EVAL-009's interval includes
0, record the result as inconclusive and revert the rule with its spec and test; this wording is
not run again (choice 2A). When EVAL-009 and EVAL-006 move apart, the rule as written decides
(choice 3A).

## Result

Run on 2026-11-20 at commit `9191469`, clean, on the dev laptop (i7-10610U, 16 GB RAM, CPU only):
`eval/results/2026-11-20-9191469.json` (seed 1, 1,922 s) and `eval/results/2026-11-20-9191469-2.json`
(seed 2, 2,326 s). Answers 1.21 and 1.22 USD; the judge's 146 and 149 calls 0.73 and 0.74 USD.

`python -m src.eval.compare --old eval/results/2026-11-20-dc5ddea-2.json,eval/results/2026-11-20-dc5ddea-3.json --new eval/results/2026-11-20-9191469.json,eval/results/2026-11-20-9191469-2.json`:

| Metric | `e8c4f1b`, 2 runs | `9191469`, 2 runs | Paired change |
|---|---|---|---|
| EVAL-009 | 0.579 | 0.585 | +0.007 [−0.019, +0.033] |
| EVAL-006 | 0.353 | 0.410 | +0.057 [+0.022, +0.092] |
| EVAL-002 | 0.958 | 0.970 | +0.013 [−0.008, +0.032] |
| EVAL-003 | 0.968 | 0.990 | +0.022 [+0.007, +0.040] |
| EVAL-004 | 0.982 | 0.982 | 0 |
| EVAL-001, EVAL-005, EVAL-007 | 0.769, 0.494, 0.678 | the same | 0, every item |

- **Inconclusive, so the rule is reverted (choice 2A).** EVAL-009's interval includes 0. The
  guards pass: no interval lies entirely below 0, and EVAL-004 is 0.982. The prompt, its spec in
  `docs/reference/answer.md`, its test and its changelog line are reverted in `31c10bc`; the
  answer prompt is again the one of `e8c4f1b`, by hash (`2873d56f`).
- **EVAL-006 rises and EVAL-009 does not** (choice 3A: the rule as written decides). EVAL-006
  counts an answer only when it states every key fact; EVAL-009 also counts the partial ones and
  scores a not-found answer 0. The rule turns some partial answers into complete ones and turns
  others into not-found answers, so the two metrics part.

## Beside the decision

| | `e8c4f1b` seed 1, seed 2 | `9191469` seed 1, seed 2 |
|---|---|---|
| Not found, answerable, of 184 | 29, 29 | 38, 35 |
| Sentences per answered item, mean (median) | 2.54 (2), 2.53 (2) | 3.40 (2), 3.48 (2) |
| Answers of 7 sentences or more | 10, 10 | 18, 17 |
| Output tokens per item, mean (median), 240 items | 160 (91), 160 (90) | 193 (98), 202 (92) |
| Latency, full pipeline, median and p95 | 2.18 s, 4.57 s; 2.34 s, 6.63 s | 2.44 s, 7.78 s; 3.63 s, 9.21 s |
| Answer cost per item | 0.0050 USD, 0.0050 USD | 0.0051 USD, 0.0051 USD |

- **The per-item split** (184 answerable standalone questions, each item averaged over its arm's
  two runs):
  - **Newly not found:** not-found answers over the two runs rose from 58 to 73. 12 items are
    not found more often with the rule and 4 less often; 10 are not found in both new runs and in
    neither baseline run, 3 the other way round. These cost EVAL-009 −0.018.
  - **More or less complete:** of the 143 items answered in all four runs, 33 state more key
    facts with the rule, 13 fewer and 97 the same. These add +0.025.
  - The net is the +0.007 above. As on #34, the rule raised not-found answers against its intent.
- **Latency meets NFR-006** (median ≤ 10 s, p95 ≤ 20 s) in both runs, unlike #34's run (p95
  30.53 s); the log has 4 server errors (503) and 6 rate limits (429) for seed 1, 12 and 19 for
  seed 2. The p95 rose by about 3 s with the longer answers.
- **Cost meets NFR-007** (≤ 0.01 USD per item).
- AC-015: seed 1 20 pass, 7 fail, 15 retrieval misses, of 42, 6 uncited; seed 2 20 pass, 6 fail,
  15 retrieval misses, of 41, 7 uncited. Not met. Citation ids not in the context (AC-009): 2 in
  2 items, and 0.

**Hand-check**, the owner's, blind, on the sheet `python -m src.eval.handcheck sheet` writes for
the seed 1 run, the first hand-check with EVAL-009 (#39, risk 2):

- `cited` and `supported` 19 of 20; the one disagreement (S14, q196) is a sentence the judge
  called unsupported and the owner supported.
- `facts` 43 of 52; `correct` 16 of 20. All 9 fact disagreements, in 5 answers (q206, q42, q137,
  q195, q126), are facts the judge called stated and the owner did not, and the 4 `correct`
  disagreements (q42, q137, q195, q126) are answers the judge called correct and the owner did
  not. So in this run the judge reads the rule's answers more generously than the owner, and
  EVAL-006 and EVAL-009 may overstate them. At `271adae` the 4 `correct` disagreements went the
  other way. The baseline runs have no hand-check per fact, so how much of EVAL-006's rise is the
  judge's is not measured; the decision does not rest on it, since EVAL-009 did not rise.
- `says_amended` 4 of 6; the 2 disagreements (q56, q117) are, as at `271adae`, answers the judge
  said say amended and the owner did not. Both fail AC-015 anyway.

## What follows

This wording is not run again (choice 2A). A rule that asks for completeness raises the
not-found count as well, on both #34 and here; any rerun is a new issue with another wording, one
that leaves the not-found rule alone. The judge's leniency on the rule's answers is one run's
hand-check; whether it holds for the baseline is not measured.
