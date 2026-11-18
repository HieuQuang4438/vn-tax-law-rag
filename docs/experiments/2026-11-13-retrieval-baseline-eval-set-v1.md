---
status: approved
updated: 2026-11-19
owner: HieuQuang4438
approved-by: self (built)
issue: 9
---

# Retrieval baseline, eval set v1

Moved on 2026-11-19 from `docs/reference/eval-results.md`, *Baseline* (#32). The text is as it was written there; the only edits are pointers to sections that now live in another file.

The first clean run, recorded on #9: `eval/results/2026-11-13-1d257ea.json`. Eval set v1, commit
`1d257ea`, retrieval only with each turn as written, k = 8, RRF 60, 50 candidates, bge-m3
`5617a9f6`, syllable BM25, on the dev laptop (i7-10610U, 16 GB RAM, CPU only).

| Metric | Value | n | 95% interval | Target |
|---|---|---|---|---|
| EVAL-001 recall@8 | 0.633 | 39 | 0.539–0.727 | ≥ 0.80, not met |
| EVAL-005 recall@8, follow-up turns, no rewrite | 0.575 | 10 | 0.333–0.817 | ≥ 0.70, not met |
| EVAL-007 context precision@8 | 0.676 | 39 | 0.571–0.773 | ≥ 0.60, met |

- Recall is 0.771 on `reference` questions and 0.572 on `plain` ones.
- Retrieval latency is 0.35 s median and 0.69 s p95.
- 48 of the 111 expected articles are missed: 9 of the 15 amending articles and 39 of the 96
  base articles. Of the missed ones, 18 rank 9–20 and 16 rank 21–50 when 50 hits are
  retrieved; 14 are not among them.

EVAL-001's target was confirmed at 0.80 after this baseline, approved on #9. It is not revised
again; the gap is the work of the retrieval issues.

Since #12 the chunks are split over 1,600 tokens, not 800. At that threshold, commit `ab4a8fa`,
otherwise as above: EVAL-001 0.678 [0.592, 0.764], EVAL-005 0.575 [0.333, 0.817], EVAL-007
0.686 [0.590, 0.780], in `eval/results/2026-11-14-ab4a8fa-3.json`
([*Threshold experiment*](2026-11-14-chunk-threshold.md)). The table above stays the record
of the first baseline.

Since #25 the top 8 holds one hit per article. At commit `e2051f7`, otherwise as at `ab4a8fa`:
EVAL-001 0.714 [0.634, 0.791], EVAL-005 0.600 [0.333, 0.867], EVAL-007 0.701 [0.607, 0.793], in
`eval/results/2026-11-15-e2051f7.json` ([*Fusion tuning*](2026-11-15-fusion-tuning.md)).
