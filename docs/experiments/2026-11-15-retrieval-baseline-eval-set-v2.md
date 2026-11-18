---
status: approved
updated: 2026-11-19
owner: HieuQuang4438
approved-by: self (built)
issue: 26
---

# Retrieval baseline, eval set v2

Moved on 2026-11-19 from `docs/reference/eval-results.md`, *Baseline* (#32). The text is as it was written there; the only edits are pointers to sections that now live in another file.

The eval set v2 baseline, recorded on #26: `eval/results/2026-11-15-b0cced1.json`. Eval set v2
(184 answerable standalone questions, 29 answerable follow-up turns), commit `b0cced1`, otherwise
as at `e2051f7`. A v2 score is not compared paired with a v1 score.

| Metric | Value | n | 95% interval | Target |
|---|---|---|---|---|
| EVAL-001 recall@8 | 0.769 | 184 | 0.715–0.813 | ≥ 0.80, not met |
| EVAL-005 recall@8, follow-up turns, no rewrite | 0.494 | 29 | 0.339–0.644 | ≥ 0.70, not met |
| EVAL-007 context precision@8 | 0.678 | 184 | 0.626–0.728 | ≥ 0.60, met |

- Recall is 0.714 on the 39 version 1 questions and 0.783 on the 145 added in version 2.
- Recall by tax type runs from 0.500 (`household`) to 0.933 (`cit`).
- The 184 questions expect 164 distinct articles; version 1 expects 73 of them.
- The 10 reference questions that name the wrong document (answered by the right one, step 2)
  score 0.600: q65, q72, q74, q84, q122, q185, q212, q213, q240, q242.
- Retrieval latency is 0.38 s median and 0.90 s p95 over 292 items.
