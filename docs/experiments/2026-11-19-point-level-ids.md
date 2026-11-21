---
status: approved
updated: 2026-11-20
owner: HieuQuang4438
approved-by: self (built)
issue: 33
---

# Point-level citation ids

Does reading a point-level citation id (`1.25a`, `1.25 b`, `1.25.c`) as its clause raise EVAL-002
on eval set v2? The question is #33; the approach is the approved comment on #33, choices 1A, 2A
and 3A; the rule is `docs/reference/answer.md`, *Point-level ids*.

At `271adae` (`eval/results/2026-11-18-271adae.json`), 85 citation ids were flagged in 39 of the
184 answerable standalone questions, 82 of them a passage and a clause in the context followed by
a point letter. EVAL-002 was 0.378 over the 111 cited sentences of those 39 items and 0.940 over
the 265 of the others.

**Run.** `python -m src.eval.run --generate --rewrite none --compare
eval/results/2026-11-18-271adae.json`. Everything as at `271adae` apart from the id rewrite: eval
set v2 (`f14d299e`), the same index (bge-m3 `5617a9f6`, `syllable` BM25, 1,286 chunks), `TOP_K` 8,
`RRF_K` 60, 50 candidates, one hit per article, `rewrite: none`, answer and judge
`gemini-3.5-flash-lite`, the same answer and judge prompts (by hash), budget 24,000, bootstrap
seed and resamples. `--rewrite none` because `271adae` predates the `concat` default of #19.

**Decision rule** (in #33, fixed before the run). Keep the change when the paired 95% interval of
the EVAL-002 change lies entirely above 0, and neither EVAL-003 nor EVAL-006 changes with an
interval entirely below 0.

## Result

Run on 2026-11-19 at commit `69f6ab4`, clean, on the dev laptop (i7-10610U, 16 GB RAM, CPU only):
`eval/results/2026-11-19-69f6ab4.json`. 2,624 s; 0.0050 USD per item, 1.19 USD in all, and the
judge's 155 calls 0.76 USD.

| Metric | `271adae` | `69f6ab4` | Paired change |
|---|---|---|---|
| EVAL-002 | 0.774, n = 376 | 0.950 [0.926, 0.971], n = 379 | **+0.176 [+0.103, +0.263]** |
| EVAL-003 | 0.961, n = 154 | 0.971 [0.954, 0.987], n = 155 | +0.010 [−0.007, +0.029] |
| EVAL-006 | 0.402, n = 184 | 0.386 [0.315, 0.457], n = 184 | −0.016 [−0.049, +0.022] |
| EVAL-004 | 0.982, n = 56 | 0.982 [0.946, 1.000], n = 56 | 0 |
| EVAL-001, EVAL-005, EVAL-007 | 0.769, 0.494, 0.678 | the same | 0, every item |

- **The change is kept (the rule's first case).** EVAL-002's interval lies entirely above 0 and
  meets its target (≥ 0.90); EVAL-003's and EVAL-006's intervals include 0.
- **The direct effect:** 85 flagged ids over the answerable standalone questions at `271adae`,
  2 at `69f6ab4`, in 2 items. The results file keeps ids after the rewrite, so the rewrites
  themselves are not counted (approved on #33).
- **The paired intervals of EVAL-002, EVAL-003 and EVAL-006 are computed outside the runner,**
  which pairs only the retrieval metrics: the same 184 items resampled 1,000 times with the run's
  seed, EVAL-002 as the ratio of the sums in each resample, EVAL-003 over the items answered in
  each run.
- **The judge reads a rewritten id as the whole clause,** so a sentence that cited one point is
  judged against all of the clause's points: more lenient than the point itself. Not measured.
- Not found on 29 of 184 answerable questions (by recall@8: 7 all, 15 some, 7 none), 30 at
  `271adae`; 55 of 56 unanswerable, unchanged.
- AC-015: 21 pass, 6 fail, 15 retrieval misses, of 42; 6 uncited: not met. Fails q01, q37, q56,
  q197, q199, q200.
- Latency 2.42 s median and 8.15 s p95 over 240 items.

## Run-to-run noise in EVAL-006

The id rewrite runs after the model has answered, so it cannot change what the model writes; yet
EVAL-006 moved on 11 items, 4 up and 7 down, all with every expected article retrieved. Neither
the answer call nor the judge call sets a temperature or a seed (`src/llm.py`), so both sample:

- 79 of the 184 answers have the same text in both runs (`data/eval-answers/`, compared by
  equality, not read); the other 105 were written differently. Output token counts include
  thinking tokens, so they do not tell the two apart. Of the 11, q146 went from 6 sentences to 2
  and q238 from 4 to 1.
- q174 has the same text in both runs and still went from correct to wrong: the judge marked one
  of its four key facts as missing the second time. It is the only one of the 11 with the same
  text, so the other 10 changed answer as well as verdict. q178 has the same sentence count,
  near-identical output tokens (176 and 174) and the same citations, but its text differs.

A rerun of an unchanged configuration therefore moves EVAL-006 by a few hundredths. A change to
the prompt (#34) or the context (#36) has to clear that before its interval can lie above 0.
