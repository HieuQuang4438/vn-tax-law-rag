---
status: approved
updated: 2026-11-19
owner: HieuQuang4438
approved-by: self (built)
issue: 28
---

# Re-check of one hit per article on eval set v2

Moved on 2026-11-19 from `docs/reference/retrieval.md`, *Fusion tuning*, *Re-check on eval set v2* (#32). The text is as it was written there; the only edits are pointers to sections that now live in another file.

Does one hit per article still raise recall@8 on eval set v2? The question is #28; the
approach is the approved comment on #28. Only `per_article` changes. Everything else is as at
the v2 baseline (`eval/results/2026-11-15-b0cced1.json`, [the eval set v2 baseline](2026-11-15-retrieval-baseline-eval-set-v2.md)):
eval set v2, today's index (bge-m3@8192, `syllable` BM25, 1,286 chunks), `TOP_K` 8, `RRF_K` 60,
50 candidates, weights 1 and 1, `rewrite: none`, bootstrap seed 0, the dev laptop, one clean
commit for both runs.

**Runs.**

1. `python -m src.eval.run --no-per-article`, the setting before #25.
2. `python -m src.eval.run --compare <run 1 file>`, the default: its paired changes are the
   change that `per_article` brings. Against `b0cced1`, every per-item score must be the same,
   or the work stops.

**Decision rule** (approved on #28). One comparison, so no Bonferroni interval:

1. **Keep** `per_article` when the paired 95% interval of its EVAL-001 change lies entirely above
   0 and the guard of #25 holds: the EVAL-007 paired interval not entirely below 0, the median
   latency (AC-012) at most 2 s.
2. **Turn it off** when the interval lies entirely below 0.
3. **Otherwise keep it**, recorded as inconclusive.

EVAL-005 (n = 29) is reported, but does not decide. The mean change on the items with
`added_in` 1 and 2 is read from each run's breakdown, without an interval: `per_article` was
chosen on the version 1 questions, so a larger change there hints at tuning bias, without
proving it.

## Result

Run on 2026-11-15 at commit `4d2fda4`, clean, eval set v2, on the dev laptop (i7-10610U, 16 GB
RAM, CPU only), with the index as above. Run 1 is `eval/results/2026-11-15-4d2fda4.json`, run 2
`-2`. Run 2 gives every item the same score as `b0cced1`.

| Run | EVAL-001 recall@8 | EVAL-005 recall@8 | EVAL-007 precision@8 | Median latency |
|---|---|---|---|---|
| 1 `--no-per-article` | 0.756 [0.703, 0.802] | 0.486 [0.333, 0.635] | 0.646 [0.597, 0.693] | 0.248 s |
| 2 default | 0.769 [0.715, 0.813] | 0.494 [0.339, 0.644] | 0.678 [0.626, 0.728] | 0.266 s |
| Paired change | **+0.012 [+0.004, +0.023]** | +0.009 [0.000, +0.026] | +0.032 [+0.021, +0.045] | |

- **`per_article` stays on (rule 1).** Its paired EVAL-001 interval lies entirely above 0. It
  raises recall on 6 questions and lowers it on none.
- **The guard passes.** The EVAL-007 interval lies above 0, and the median latency is 0.266 s.
- **The gain sits on the version 1 questions.** The mean change is +0.036 on the 39 with
  `added_in` 1, the same as on eval set v1, and +0.006 on the 145 with `added_in` 2. 4 of the 6
  raised questions are from version 1. This hints that the change measured on #25 was partly
  tuned to those questions; on the new ones it is small.
- **The paired interval is 0.019 wide**, against 0.065 on eval set v1 (#25), so v2 separates a
  change of this size from 0.

This resolves the "re-check on eval set v2" of [*Fusion tuning*](2026-11-15-fusion-tuning.md), *Result*.
