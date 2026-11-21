---
status: approved
updated: 2026-11-19
owner: HieuQuang4438
approved-by: self (built)
issue: 16
---

# Not-found reply, generation run

Moved on 2026-11-19 from `docs/reference/eval-results.md`, *Baseline*, *Generation runs* — the run of #16 (#32). The text is as it was written there; the only edits are pointers to sections that now live in another file.

Clean `--generate` runs, on the dev laptop, judge `gemini-3.5-flash-lite`. The hand-check is the
owner's, blind, on the sheet `python -m src.eval.handcheck sheet` writes.

| File | EVAL-002 | EVAL-003 | EVAL-004 | EVAL-006 | Not found | AC-015 | Hand-check |
|---|---|---|---|---|---|---|---|
| `eval/results/2026-11-18-271adae.json` | 0.774 [0.700, 0.850], n = 376 | 0.961 [0.940, 0.981], n = 154 | 0.982 [0.946, 1.000], n = 56 | 0.402 [0.332, 0.473], n = 184 | 30 of 184 answerable (by recall@8: 8 all, 14 some, 8 none), 55 of 56 unanswerable | 21 pass, 7 fail, 15 retrieval misses, of 43; 5 uncited: not green | cited 19 of 20, supported 19 of 20, correct 16 of 20, says_amended 4 of 6 |

`2026-11-18-271adae`, eval set v2, commit `271adae` (not-found rule narrowed, choice 2A on #16;
notices and AC-015 as changed by `f4889e6`, choices 1, 2' and 3 on #15), retrieval as at
`b0cced1`, the same index and model as `4091435`:

- EVAL-004 meets its target; the narrower rule left the 55 of 56 unchanged. Not found on
  answerable questions went from 33 to 30 against `4091435`: 7 answered now, 4 not found now, 26
  not found in both. That is within the variation of one prompt across two runs (29 at
  `6cbf23a`, 33 at `4091435`), so it is not attributed to the rule (a risk named on #16).
- EVAL-002 fell from 0.868 to 0.774 and EVAL-003 from 0.985 to 0.961. Over the 147 items judged
  in both runs, the model's sentences, notices left out, went from 0.881 to 0.786: a paired
  change of −0.095 [−0.202, +0.006], items resampled as under [*Interval*](../reference/eval-results.md#scores), so not shown to
  differ. The notices were judged `cited` false on 12 of 32, against 7 of 18 at `4091435`.
- Hand-check, the owner's, blind:
  - `cited` and `supported` 19 of 20; the one disagreement (S9) is a notice the judge called
    unsupported and the owner supported. 2 of the 20 sampled sentences were notices;
  - `correct` 16 of 20; in all 4 disagreements the judge called incorrect an answer the owner
    called correct, so EVAL-006 may understate the answers. At `6cbf23a` all 20 agreed;
  - `says_amended` 4 of 6, the first such check; in the 2 disagreements (q56, q117) the judge
    said amended and the owner did not. Both fail AC-015 anyway, since neither cites the
    amending passage, so the AC-015 counts stand.
- AC-015, of 43, against 42 at `4091435`: 21 pass, 15 retrieval misses, 7 fail, and 5 uncited.
  The 7 fails, from ids and citations only:
  - 2 (q01, q37) cite the amending passage but ask about a provision no notice covers, judged
    not said to be amended;
  - 4 (q56, q117, q197, q199) do not cite the amending passage;
  - 1 (q200) is not found.
  AC-015 is not met; the fails are answer quality and retrieval, as at `4091435`.
- 85 citation ids not in the context, in 39 items, were flagged (AC-009), against 67 in 32.
- Latency is 4.12 s median and 8.07 s p95 over 240 items; cost is 0.0050 USD per item, the
  judge's 154 calls 0.7548 USD.
- The keys changed 61 times, 60 on a 503 and 1 on a 429; 3 attempts failed, 2 on every key and
  1 on a dropped connection, and succeeded on the retry.
