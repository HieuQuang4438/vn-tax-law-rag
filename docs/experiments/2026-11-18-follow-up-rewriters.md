---
status: approved
updated: 2026-11-19
owner: HieuQuang4438
approved-by: self (built)
issue: 19
---

# Follow-up rewriters

Moved on 2026-11-19 from `docs/reference/eval-results.md`, *Baseline*, *Follow-up rewriters* (#32). The text is as it was written there; the only edits are pointers to sections that now live in another file.

The four rewriters of [conversation.md](../reference/conversation.md), recorded on #19: retrieval-only runs at
commit `6e9ee24`, eval set v2, retrieval as at `b0cced1`, each with `--rewrite <name>` and, for
the three rewriters, `--compare` with the `none` run and `--comparisons 3`. EVAL-001 and
EVAL-007 are those of `none` in every run: standalone questions go through no rewriter.

| Rewriter | File | EVAL-005 | paired vs `none` | Bonferroni |
|---|---|---|---|---|
| `none` | `eval/results/2026-11-18-6e9ee24.json` | 0.494 [0.339, 0.644] | | |
| `concat` | `eval/results/2026-11-18-6e9ee24-2.json` | 0.526 [0.360, 0.670] | +0.032 [−0.146, +0.195] | [−0.172, +0.237] |
| `fuse` | `eval/results/2026-11-18-6e9ee24-3.json` | 0.480 [0.322, 0.627] | −0.014 [−0.129, +0.098] | [−0.172, +0.129] |
| `llm` | `eval/results/2026-11-18-6e9ee24-4.json` | 0.629 [0.473, 0.767] | +0.134 [+0.017, +0.259] | [−0.003, +0.296] |

- `llm` against `concat`, from the two files: +0.102, paired [+0.002, +0.224], Bonferroni
  [−0.009, +0.250] at 3 comparisons.
- The choice (choice 3A on #19): `concat`, the LLM-free rewriter with the higher EVAL-005;
  `llm`'s Bonferroni lower bound over it is not above 0. No rewriter separates from `none`
  (choice 4A), so the four are re-measured on an eval set v3 with more follow-up turns
  (approved on #19). EVAL-005 misses its target (≥ 0.70) under every rewriter.
- AC-014: in every run no first turn was rewritten; under `concat`, `fuse` and `llm` all 30
  follow-ups went through the rewriter and got a query other than their question.
- Recall dropped against `none` on 6 follow-ups under `concat` (c04.2, c05.3, c06.3, c12.2,
  c15.3, c16.2), 2 under `fuse` (c15.3, c16.2) and 3 under `llm` (c04.2, c05.3, c06.2).
- `concat` and `fuse` gave 2 reference hits on follow-ups, from an article named in an earlier
  question; `none` and `llm` gave none.
- `llm` ran once, and its rewrites are not deterministic: another run may score otherwise. It
  made 30 calls, 0.0043 USD in all, its rewrite 0.84 s median; the other rewrites take
  under a millisecond. Retrieval-only latency is 0.19 s median under `none` and 0.21 s under
  `concat`.
