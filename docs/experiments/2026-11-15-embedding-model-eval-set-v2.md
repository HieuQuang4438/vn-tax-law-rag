---
status: approved
updated: 2026-11-19
owner: HieuQuang4438
approved-by: self (built)
issue: 27
---

# Embedding model on eval set v2

Moved on 2026-11-19 from `docs/reference/index.md`, *Embedding experiment*, *Re-run on eval set v2* (#32). The text is as it was written there; the only edits are pointers to sections that now live in another file.

Does Vietnamese_Embedding raise recall@8 once the eval set can tell a change of about +0.03?
The question is #27; the approach is the approved comment on #27. The three variants and the
decision rule are those of [*Embedding experiment*](2026-11-14-embedding-model.md), unchanged. What differs from that run:

- Eval set v2 (`f14d299e3d1e`), and `Fusion()` as it is now, one hit per article (#25).
- The three folders are reused, not rebuilt: they hold the same chunks (`chunks_sha256`
  `f46aee0d2d33`), and `src/index` has not changed since `2360e43`.
- Variant 1 must give every item the same score as `eval/results/2026-11-15-b0cced1.json`, or
  the work stops.
- 3 against 1 is the one comparison that decides, so no Bonferroni interval. 3 against 2 and 2
  against 1 are reported as in [*Embedding experiment*](2026-11-14-embedding-model.md).
- The mean change on the items with `added_in` 1 and 2 is read from each run's breakdown,
  without an interval. The threshold (#12) and one hit per article (#25) were tuned on the
  version 1 questions with bge-m3, so a smaller change there hints at bias toward bge-m3.
- "Distinct articles in top 8" is not reported: with one hit per article it is always 8.
- The tokenizers are not compared again: both revisions are pinned and unchanged.

## Result

Run on 2026-11-15 at commit `7b40a2f`, clean, eval set v2, on the dev laptop (i7-10610U, 16 GB
RAM, CPU only). Variant 1 gives every item the same score as `b0cced1`.

| Variant | EVAL-001 | Paired change vs 1 | EVAL-005 | EVAL-007 | Retrieval median / p95 | Results file |
|---|---|---|---|---|---|---|
| 1 | 0.769 [0.715, 0.813] | — | 0.494 [0.339, 0.644] | 0.678 [0.626, 0.728] | 0.25 / 0.36 s | `2026-11-15-7b40a2f.json` |
| 2 | 0.766 [0.712, 0.810] | −0.003 [−0.008, +0.000] | 0.494 [0.339, 0.644] | 0.678 [0.626, 0.727] | 0.29 / 0.44 s | `2026-11-15-7b40a2f-2.json` |
| 3 | 0.784 [0.731, 0.826] | +0.015 [−0.006, +0.038] | 0.504 [0.352, 0.651] | 0.675 [0.625, 0.724] | 0.25 / 0.37 s | `2026-11-15-7b40a2f-3.json` |

- **Vietnamese_Embedding again does not meet the rule**: its paired interval against variant 1
  includes 0. bge-m3 at 8,192 stays the default, ADR-0002 stands, and `data/` is unchanged.
- Against variant 1 it raised recall on 17 questions and lowered it on 10. EVAL-005 paired
  [−0.084, +0.113], EVAL-007 paired [−0.031, +0.025]. On `plain` questions 0.751 to 0.770, on
  `reference` questions 0.818 to 0.823.
- Against variant 2, the model's effect alone: EVAL-001 +0.018 [−0.004, +0.041], 18 questions
  up and 10 down. This interval also includes 0.
- The cut still costs little: variant 2 lowered one question and raised none.
- **No sign of bias toward bge-m3 on the version 1 questions.** The mean change of variant 3
  against 1 is +0.035 on the 39 with `added_in` 1 and +0.010 on the 145 with `added_in` 2, the
  opposite of what tuning toward bge-m3 would give.
- **The paired interval is 0.044 wide**, against 0.129 on eval set v1: the change a different
  model makes moves many items both ways, so its interval stays wider than #28's 0.019. A change
  of +0.015 is within the noise at n = 184.
- Every variant keeps AC-012.
