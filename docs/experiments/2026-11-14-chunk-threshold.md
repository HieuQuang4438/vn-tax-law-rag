---
status: approved
updated: 2026-11-19
owner: HieuQuang4438
approved-by: self (built)
issue: 12
---

# Chunk threshold

Moved on 2026-11-19 from `docs/reference/chunk-schema.md`, *Threshold experiment* (#32). The text is as it was written there; the only edits are pointers to sections that now live in another file.

Does another clause-split threshold raise recall@8 over 800, the starting value of ADR-0001?
Approach approved on #12, with the
decision rule fixed before the run: a threshold replaces 800 only if the paired 95% bootstrap
interval of its EVAL-001 change lies entirely above 0 and AC-012 still holds; if several do,
the one with the largest mean change.

Thresholds: 400, 800, 1600, and 8192 for no split. 8192 is bge-m3's input limit; no article of
the corpus is over it (the largest is 8,072 tokens), so at 8192 every article is one chunk.

Setup, the same for every run: commit `ab4a8fa`, eval set v1 (`d33b390e4894…`), bge-m3
`5617a9f6`, `syllable` BM25,
k = 8 chunks, RRF 60, 50 candidates, `MIN_INTRO_TOKENS` 100, `rewrite: none`, the dev laptop
(i7-10610U, 16 GB RAM, CPU only). Each variant lives in `data/t<threshold>/`, gitignored
(`data/t*/`), and has its own copy of the vector cache, seeded from the default one: a
build prunes its cache to its own texts, so a shared cache would lose 800's vectors.

```bash
python -m src.chunking --max-tokens 400 --out data/t400/chunks
python -m src.enrich --chunks data/t400/chunks --out data/t400/enriched
mkdir -p data/t400/index && cp -r data/index/embeddings data/t400/index/
python -m src.index --enriched data/t400/enriched --out data/t400/index --cache data/t400/index/embeddings
python -m src.eval.run --enriched data/t400/enriched --index data/t400/index --compare <the 800 results file>
```

Reported for each threshold: chunk count, split articles, EVAL-001 with its paired change
against 800, EVAL-005, EVAL-007, the mean number of distinct articles among the top 8 chunks of
the scored questions (from `hits` in the results file), the enrich counts (links, undated
chunks, issues, largest header + text against the 8,192 limit), texts embedded, build time,
retrieval latency, and the results file.

Run on 2026-11-14. The 800 row is the default index, rebuilt at the same commit; its build
embedded nothing, since its vectors were cached.

| Threshold | Chunks | Split articles | EVAL-001 | Paired change vs 800 | EVAL-005 | EVAL-007 | Distinct articles in top 8 | Texts embedded | Index build | Retrieval median / p95 | Results file |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 400 | 2,411 | 390 | 0.615 [0.524, 0.710] | −0.018 [−0.056, +0.014] | 0.590 [0.373, 0.813] | 0.693 [0.587, 0.789] | 6.13 | 640 | 743 s | 0.21 / 0.29 s | `2026-11-14-ab4a8fa-2.json` |
| 800 | 1,923 | 238 | 0.633 [0.539, 0.727] | — | 0.575 [0.333, 0.817] | 0.676 [0.571, 0.773] | 6.31 | 0 | 2 s | 0.19 / 0.31 s | `2026-11-14-ab4a8fa.json` |
| **1600** | 1,286 | 98 | **0.678** [0.592, 0.764] | **+0.044 [+0.005, +0.091]** | 0.575 [0.333, 0.817] | 0.686 [0.590, 0.780] | 6.82 | 140 | 994 s | 0.19 / 0.32 s | `2026-11-14-ab4a8fa-3.json` |
| 8192 | 744 | 0 | 0.666 [0.564, 0.764] | +0.032 [−0.044, +0.104] | 0.600 [0.333, 0.867] | 0.624 [0.520, 0.721] | 8.00 | 238 | 3,560 s | 0.18 / 0.27 s | `2026-11-14-ab4a8fa-4.json` |

- **1600 is the only threshold that meets the rule**, so `MAX_TOKENS` becomes 1,600
  (FR-CORE-002, AC-002). Against 800 it raised recall on 6 questions and lowered it on 1; on
  `plain` questions 0.572 to 0.618, on `reference` questions 0.771 to 0.812. No follow-up turn
  changed (EVAL-005 paired [0, 0]).
- **The margin is thin.** The interval's lower end is +0.005, and three thresholds were compared
  with one baseline without correction, so one of them could pass by chance.
- **Part of the gain may come from k, not from the vectors.** k counts chunks: at 800 the top 8
  held 6.31 distinct articles on average, at 1600 6.82. Fewer clause chunks of one article
  leave room for other articles, and this experiment does not separate that from a better
  representation.
- 400 lowered recall on 4 questions and raised it on 2. 8192, one chunk per article, raised it
  on 7 and lowered it on 5; its interval includes 0, and its context precision fell
  (EVAL-007 −0.052 [−0.124, +0.016]). Its largest header + text is 8,148 tokens, under the
  8,192 limit, so no text was cut; embedding its 238 new texts took 59 minutes.
- Enrich at every threshold: 175 amendment links, no chunk without an effective date, 15 enrich
  issues. Chunks with `amended_by`: 38 at 400, 37 at 800, 32 at 1600, 27 at 8192. The chunker
  reports 6 issues, 5 at 8192, where no article is split and so no `clause_numbering` can occur.
- Retrieval latency varies by about 0.2 s between runs on this laptop ([*Tokenizer experiment*](2026-11-13-bm25-tokenizer.md)), more than between thresholds; every variant keeps AC-012.
- Each results file records its split in `configuration.index.chunking`.
