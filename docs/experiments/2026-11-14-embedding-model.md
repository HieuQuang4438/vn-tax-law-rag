---
status: approved
updated: 2026-11-19
owner: HieuQuang4438
approved-by: self (built)
issue: 11
---

# Embedding model

Moved on 2026-11-19 from `docs/reference/index.md`, *Embedding experiment* (#32). The text is as it was written there; the only edits are pointers to sections that now live in another file.

Does `AITeamVN/Vietnamese_Embedding`, bge-m3 fine-tuned for Vietnamese retrieval, raise
recall@8 over bge-m3? Approach approved on #11, which replaces the issue's multilingual-e5: e5
reads at most 512 tokens, and at the 1,600 threshold many indexed texts are longer.
Vietnamese_Embedding reads at most 2,048, so the 12 longest of the 1,286 indexed texts are cut
(counted with bge-m3's tokenizer, special tokens included); a control variant, bge-m3 cut at
2,048, separates the model's effect from the cut's.

| Variant | Model | Input limit | Folder | Role |
|---|---|---|---|---|
| 1 | `BAAI/bge-m3` `5617a9f6` | 8,192 | `data/index/` | baseline, the default index |
| 2 | `BAAI/bge-m3` `5617a9f6` | 2,048 | `data/index-bge-2048/` | control |
| 3 | `AITeamVN/Vietnamese_Embedding` `dea33aa1` | 2,048 | `data/index-vn-embedding/` | candidate |

3 against 1 decides; 3 against 2 is the model's effect alone; 2 against 1 is the cost of the cut.

Decision rule, fixed before the run: Vietnamese_Embedding replaces bge-m3 only if the paired 95%
bootstrap interval of its EVAL-001 change against variant 1 lies entirely above 0 and AC-012
still holds. Variant 2 is a diagnostic and never a candidate. If variant 3 wins, it becomes the
default, a new ADR supersedes ADR-0002 for the embedding model, carrying its other decisions
over unchanged, and `data/` is rebuilt.

Setup, the same for every run: one commit, eval set v1, chunk threshold 1,600 (1,286 chunks),
`syllable` BM25, k = 8, RRF 60, 50 candidates, `rewrite: none`, the dev laptop (i7-10610U,
16 GB RAM, CPU only). Variant 1 is the default index, rebuilt from its cache at that commit.
Variants 2 and 3 are built with `--model`, `--input-limit` and `--out`, each with its own copy of
the vector cache (`--cache`), since a build prunes its model's cache folder to its own keys, and
scored with `python -m src.eval.run --index`. Before the run, Vietnamese_Embedding's
`tokenizer.json` is compared byte for byte with bge-m3's; if they differ, the texts over 2,048
are counted again with its own tokenizer and reported.

Reported for each variant: EVAL-001, EVAL-005 and EVAL-007 with their intervals, the paired
change against variant 1 (and, for 3, against 2), texts embedded and cut, build time, retrieval
latency, and the results file.

Run on 2026-11-14 at commit `2360e43`, eval set v1 (`d33b390e4894…`). Before the run, the two
`tokenizer.json` files differed in bytes (Vietnamese_Embedding's is written in a newer format,
`prepend_scheme` for `add_prefix_space`), but they gave the same token ids for all 1,286 indexed
texts, and its own tokenizer also puts 12 of them over 2,048.

| Variant | EVAL-001 | Paired change vs 1 | EVAL-005 | EVAL-007 | Distinct articles in top 8 | Texts embedded | Index build | Retrieval median / p95 | Results file |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 0.678 [0.592, 0.764] | — | 0.575 [0.333, 0.817] | 0.686 [0.590, 0.780] | 6.82 | 0 | 3.9 s | 0.19 / 0.26 s | `2026-11-14-2360e43.json` |
| 2 | 0.665 [0.569, 0.757] | −0.013 [−0.038, +0.000] | 0.575 [0.333, 0.817] | 0.686 [0.584, 0.781] | 6.82 | 12 | 147 s | 0.18 / 0.28 s | `2026-11-14-2360e43-2.json` |
| 3 | 0.708 [0.618, 0.797] | +0.030 [−0.035, +0.094] | 0.628 [0.408, 0.850] | 0.726 [0.636, 0.811] | 7.08 | 1,286 | 3,778 s | 0.17 / 0.24 s | `2026-11-14-2360e43-3.json` |

- **Vietnamese_Embedding does not meet the rule**: its paired interval against variant 1
  includes 0. bge-m3 at 8,192 stays the default, ADR-0002 stands, and `data/` is unchanged.
- Against variant 1 it raised recall on 7 questions and lowered it on 4; on `plain` questions
  0.618 to 0.677, on `reference` questions 0.812 to 0.778. It raised 3 follow-up turns and
  lowered none (EVAL-005 paired [+0.000, +0.127]); context precision EVAL-007 paired
  [−0.025, +0.113].
- Against variant 2, the model's effect alone: EVAL-001 +0.043 [−0.031, +0.110], 8 questions
  up and 4 down. This interval also includes 0.
- The cut costs little on this set: variant 2 lowered one question and raised none.
- The means lean towards Vietnamese_Embedding on every recall and precision metric but the
  `reference` form. With 39 questions the intervals are too wide to tell; a larger eval set
  could run the comparison again from these two folders' commands.
- Embedding all 1,286 texts with Vietnamese_Embedding took 63 minutes, under the 1.2–1.6 h
  estimated. Every variant keeps AC-012.
