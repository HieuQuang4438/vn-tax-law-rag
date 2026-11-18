---
status: approved
updated: 2026-11-19
owner: HieuQuang4438
approved-by: self (built)
issue: 15
---

# Cited answers, generation runs

Moved on 2026-11-19 from `docs/reference/eval-results.md`, *Baseline*, *Generation runs* — the two runs of #15 (#32). The text is as it was written there; the only edits are pointers to sections that now live in another file.

Clean `--generate` runs, on the dev laptop, judge `gemini-3.5-flash-lite`. The hand-check is the
owner's, blind, on the sheet `python -m src.eval.handcheck sheet` writes.

| File | EVAL-002 | EVAL-003 | EVAL-004 | EVAL-006 | Not found | AC-015 | Hand-check |
|---|---|---|---|---|---|---|---|
| `eval/results/2026-11-16-6cbf23a.json` | 0.855 [0.782, 0.909], n = 345 | 0.990 [0.977, 1.000], n = 155 | not scored | 0.380 [0.310, 0.457], n = 184 | 29 of 184 answerable, 55 of 56 unanswerable | 3 pass, 30 fail, 15 retrieval misses, of 48: not green | cited 20 of 20, supported 20 of 20, correct 20 of 20 |
| `eval/results/2026-11-17-4091435.json` | 0.868 [0.799, 0.921], n = 394 | 0.985 [0.971, 0.995], n = 151 | not scored | 0.402 [0.332, 0.473], n = 184 | 33 of 184 answerable, 55 of 56 unanswerable | 15 pass, 12 fail, 15 retrieval misses, of 42; 6 uncited: not green | not hand-checked |

`2026-11-16-6cbf23a`, eval set v2, commit `6cbf23a`, retrieval as at `b0cced1`:

- EVAL-002 and EVAL-006 miss their targets (≥ 0.90, ≥ 0.80); EVAL-003 meets its (≥ 0.90).
- The judge called 7 of the 20 sampled answers correct, and the owner agreed on all 20: the low
  EVAL-006 is the answers', not the judge's.
- All 20 sampled sentences were judged `cited` and `supported`, so the hand-check does not yet
  show the judge catching an unsupported sentence.
- 72 citation ids not in the context, in 39 items, were flagged (AC-009).
- Latency is 2.28 s median and 4.84 s p95 over 240 items; cost is 0.0049 USD per item, the
  judge's 155 calls 0.7651 USD.
- The keys changed 109 times, 106 on a 503 and 3 on a 429; 7 attempts failed on every key and
  succeeded after the backoff.

`2026-11-17-4091435`, eval set v2, commit `4091435` (amendment notices, choice A2; AC-015 narrowed,
choice B2), retrieval as at `b0cced1`:

- Not hand-checked: #15 closed without a further run (approved on #15), so its judged scores
  stand on the judge alone; the hand-checked run is `6cbf23a`.
- 18 answers got one amendment notice each.
- AC-015, of 42 to which it applies, against 48 at `6cbf23a` (6 now uncited): 15 pass, 15
  retrieval misses, 12 fail. The 12 fails, counted from ids and citations only:
  - 3 (q04, q196, q203) carry a notice covering the asked provision and were judged
    `says_amended: false`; from `f4889e6` a noticed provision is said amended without the judge;
  - 1 (q16) cites the amended clause and its source in one sentence without saying it was
    amended; from `f4889e6` it gets a notice (choice 2');
  - 6 (q01, q37, q117, q197, q199, q221) do not cite the listed amended clause;
  - 2 (q56, q200) are not found.
- **AC-015 is not met at the close of #15.** The changes of `f4889e6` were not measured by a run;
  the 8 fails of the last two kinds stay with them, as answer quality and retrieval, which
  neither the notice nor the scope of AC-015 changes. They are left to a later issue.
- 67 citation ids not in the context, in 32 items, were flagged (AC-009).
- Latency is 2.69 s median and 10.24 s p95 over 240 items; cost is 0.0050 USD per item, the
  judge's 151 calls 0.7477 USD.
- The keys changed 150 times, all on a 503; 6 attempts failed, 5 on every key and 1 on a read
  timeout, and succeeded after the backoff.
