---
status: approved
updated: 2026-11-19
owner: HieuQuang4438
approved-by: self (built)
issue: 24
---

# Cut diagnosis

Moved on 2026-11-19 from `docs/reference/retrieval.md`, *Cut diagnosis* — the question, the decision rule as it stood at the run, and the result. How `src.eval.diagnose` works stays there (#32). The text is as it was written there; the only edits are pointers to sections that now live in another file.

Of the expected articles missing from the top 8, how many are retrieved but ranked below the
cut, and how many no list retrieves at all? The question is #24. The approach is the approved
comment on #24. ADR-0002 reopens the reranker question only if the misses are ranked below the cut.

**Decision rule** (approved on #24). Over the misses of the standalone questions: if at least
half are `below_cut`, the verdict is `ranking`, and the next issue tunes the fusion. Otherwise
it is `retrieval`, and the next issue changes the embedding, BM25 or the chunks. The verdict is
`borderline` when moving two misses across the line would change it, and is then reported, not
acted on. With no misses there is no verdict: `result` is null. The follow-up turns are reported
but do not decide.

## Result

Run on 2026-11-15 at commit `20e8896`, clean, eval set v1. The index was today's `data/index`
(bge-m3@8192, `syllable` BM25, 1,286 chunks), and the run was on the dev laptop (i7-10610U,
16 GB RAM, CPU only). The file is `eval/results/diagnostics/2026-11-15-20e8896.json`.

| k | Standalone recall@k (n = 39) | Follow-up recall@k (n = 10) |
|---|---|---|
| 8 | 0.678 [0.592, 0.764] | 0.575 [0.333, 0.817] |
| 12 | 0.748 [0.664, 0.826] | 0.600 [0.333, 0.867] |
| 16 | 0.778 [0.702, 0.848] | 0.600 [0.333, 0.867] |
| 20 | 0.850 [0.778, 0.915] | 0.687 [0.440, 0.933] |
| 30 | 0.898 [0.836, 0.953] | 0.687 [0.440, 0.933] |
| 50 | 0.922 [0.865, 0.971] | 0.757 [0.567, 0.933] |

- **Verdict: `ranking`, not borderline.** 30 of the 43 standalone misses (70%) are ranked 9 to
  50. 5 are beyond 50, and 8 are not in the pool. The misses come from 25 of the 39 questions.
- **Most misses sit just below the cut.** Of the 30, 21 are at ranks 9 to 20 (10 of them at 9
  to 12), 6 at 21 to 30, and 3 at 31 to 50. recall@20 is 0.850, above the EVAL-001 target of
  0.80. recall@8 is 0.678.
- **Both lists usually find them.** 22 of the 43 misses are in the top 50 of both the BM25 and
  the vector list, 7 in BM25 only and 6 in vector only. 8 are in neither.
- **The 8 not in the pool are far from either cut.** Their best BM25 rank is 55 to 713, and
  their best vector rank is 52 to 827.
- **Split articles and references.** 6 misses are split articles. None comes from an
  unresolved reference.
- **Follow-up turns,** as written, have 14 misses: 6 below the cut, 5 beyond 50 and 3 not in
  the pool. They do not decide.
- **The check passes.** recall@8 equals the runner's EVAL-001 and EVAL-005 on the same index
  (0.678 and 0.575, as in the #11 run).

ADR-0002's condition for reconsidering a reranker is now met: the right article is retrieved
but ranked below the cut. A cross-encoder still costs 19–28 s per 20 pairs on this laptop
(ADR-0002), so the next issue tunes the fusion, as the decision rule says. Its options are left
to that issue's proposal.
