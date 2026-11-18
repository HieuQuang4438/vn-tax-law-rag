---
status: approved
updated: 2026-11-19
owner: HieuQuang4438
approved-by: self (built)
issue: 25
---

# Fusion tuning

Moved on 2026-11-19 from `docs/reference/retrieval.md`, *Fusion tuning* (#32). The text is as it was written there; the only edits are pointers to sections that now live in another file.

Which fusion setting raises recall@8, given that 30 of the 43 missed articles sit at ranks 9 to
50 ([*Cut diagnosis*](2026-11-14-cut-diagnosis.md), *Result*)? The question is #25. The approach is the approved comment on
#25. Only the fusion changes. Everything else is fixed: eval set v1, today's index
(bge-m3@8192, `syllable` BM25, 1,286 chunks), `TOP_K` 8, `rewrite: none`, the dev laptop,
bootstrap seed 0, one commit for every run.

**Variants.** Each changes one knob of the setting before #25, `per_article` off. Everything
else stays as it was. Since #25 `per_article` is on by default, so the baseline is reproduced
with `--no-per-article` and every other variant with `--no-per-article` added.

| Variant | Options | Why, from [*Cut diagnosis*](2026-11-14-cut-diagnosis.md) |
|---|---|---|
| Baseline | none | the current setting, re-run at the same commit; it must give recall@8 0.678, or the work stops |
| V1 | `--per-article` | the top 8 holds 6.82 distinct articles on average |
| V2 | `--rrf-k 20` | a smaller constant lifts chunks ranked high in one list |
| V3 | `--rrf-k 120` | a larger constant lifts chunks found by both lists; 22 of the 43 misses are in both |
| V4 | `--keyword-weight 2` | 7 misses are in the BM25 list only |
| V5 | `--vector-weight 2` | 6 misses are in the vector list only |
| V6 | `--candidates 100` | a chunk ranked 51 to 100 in one list still adds to its fused score |

Each variant is scored with `python -m src.eval.run <options> --compare <baseline file>
--comparisons 6`, and placed with `python -m src.eval.diagnose <options>`.

**Decision rule** (approved on #25):

1. **Winner.** A variant wins when the paired 95% interval of its EVAL-001 change against the
   baseline lies entirely above 0, as on #10 to #12.
2. **Multiplicity.** Each winner's Bonferroni interval (`--comparisons 6`, *Comparing two runs*
   in [eval-results.md](../reference/eval-results.md#comparing-two-runs)) is reported. A winner whose
   Bonferroni interval includes 0 is still adopted, marked "re-check on eval set v2".
3. **Guard.** A winner is not adopted when the paired interval of its EVAL-007 change lies
   entirely below 0, or when its median latency (AC-012) is above 2 s. EVAL-005 is reported, but
   with n = 10 it does not decide.
4. **More than one winner.** The winner with the largest mean change is the candidate. One more
   run combines every winner's options. It is adopted only if it passes rules 1 and 3 against
   the baseline and its mean change beats the candidate's. Otherwise the candidate is adopted.
5. **No winner.** `Fusion()` stays the default.

The adopted setting becomes the defaults of `Fusion()`, and the *Fusion* paragraph of [retrieval.md](../reference/retrieval.md#hybrid-search) gets the
new values. ADR-0002 is edited only if the setting contradicts it; none of the variants does.

**Ceiling.** 13 of the 43 misses are beyond rank 50 or in no list, out of the fusion's reach. A
perfect order of today's top 50 reaches recall@8 no higher than recall@50, 0.922.

## Result

Run on 2026-11-15 at commit `c22d922`, clean, eval set v1, before `per_article` became the
default. The index was today's `data/index` (bge-m3@8192, `syllable` BM25, 1,286 chunks), and the
runs were on the dev laptop (i7-10610U, 16 GB RAM, CPU only). The baseline is
`eval/results/2026-11-15-c22d922.json`, and V1 to V6 are `-2` to `-7`. The diagnoses have the
same names under `eval/results/diagnostics/`.

| Variant | EVAL-001 recall@8 | Paired change [95%] | Bonferroni [99.2%] | EVAL-007 paired | Median latency |
|---|---|---|---|---|---|
| Baseline | 0.678 [0.592, 0.764] | — | — | — | 0.252 s |
| **V1 `per_article`** | **0.714** | **+0.036 [+0.006, +0.071]** | [0.000, +0.092] | [−0.002, +0.035] | 0.209 s |
| V2 `rrf_k` 20 | 0.695 | +0.017 [0.000, +0.043] | [0.000, +0.051] | [−0.001, +0.035] | 0.180 s |
| V3 `rrf_k` 120 | 0.678 | 0.000 [0.000, 0.000] | [0.000, 0.000] | [−0.007, +0.002] | 0.216 s |
| V4 `keyword_weight` 2 | 0.694 | +0.017 [−0.026, +0.059] | [−0.045, +0.078] | [−0.043, +0.002] | 0.219 s |
| V5 `vector_weight` 2 | 0.672 | −0.006 [−0.044, +0.027] | [−0.059, +0.043] | [−0.024, +0.050] | 0.180 s |
| V6 `candidates` 100 | 0.667 | −0.011 [−0.051, +0.019] | [−0.068, +0.026] | [−0.012, −0.001] | 0.186 s |

- **V1 is the only winner, and it is adopted.** Its paired interval starts at +0.006. It raises
  recall on 4 questions and lowers it on none. V2 raises it on 2, but its interval starts at
  exactly 0, so it does not win.
- **Re-check on eval set v2.** V1's Bonferroni interval starts at exactly 0 (rule 2). Done on
  #28: kept ([*Re-check on eval set v2*](2026-11-15-per-article-eval-set-v2.md)).
- **The guard passes.** V1's EVAL-007 interval includes 0, and its median latency is 0.209 s.
  EVAL-005 goes from 0.575 to 0.600 [0.000, +0.075].
- **No combined run.** There is one winner, so rule 4 does not apply.
- **The weights and V6 do not help.** V4 raises recall on 5 questions and lowers it on 2, and
  V5 raises it on 2 and lowers it on 3; neither interval excludes 0. V6 lowers EVAL-007, with a
  paired interval entirely below 0.
- **Where the misses moved (V1).** 39 standalone misses instead of 43: 28 below the cut, 3
  beyond 50 and 8 not in the pool. recall@20 is 0.870 and recall@50 0.939.
- **The new default reproduces V1.** At commit `e2051f7`, with no options, EVAL-001 is 0.714
  [0.634, 0.791], EVAL-005 0.600 and EVAL-007 0.701, with every per-item change 0 against V1
  (`eval/results/2026-11-15-e2051f7.json`, and its diagnosis).

recall@8 is still below the EVAL-001 target of 0.80. 28 of the remaining misses are ranked 9 to
50, so the order of the top 50 is still the gap. No fusion knob in the grid closes it.
