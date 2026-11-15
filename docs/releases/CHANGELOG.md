# Changelog

Format: [Keep a Changelog](https://keepachangelog.com). Versioning: [SemVer](https://semver.org).
Newest first. Every line cites the IDs it moved — see `DOCS-CONVENTIONS.md` §6.

## [Unreleased]

### Added

- Context header on every chunk, apart from its text: `python -m src.enrich` writes
  `data/enriched/chunks.jsonl`; chunks and articles carry `chapter_title`. FR-CORE-003, AC-003,
  ADR-0001.
- Effective date on every chunk, read from its document's effectiveness article, with whole
  and partial exceptions; `data/enriched/issues.jsonl` reports undated documents, partial
  exceptions, application rules and end dates. FR-CORE-004, AC-004, ADR-0001.
- Amendment links: every amend, replace and repeal directive in the amending documents and the
  effectiveness articles becomes a link in `data/enriched/links.jsonl`, out-of-corpus targets
  kept and marked; each amended chunk lists its links in `amended_by`. 175 links on the corpus,
  checked against a hand-read list. FR-CORE-005, AC-005, ADR-0001.
- Vector and keyword indexes: `python -m src.index` writes a bge-m3 Chroma collection and a
  bm25s index over the same chunk ids to `data/index/`, with a manifest; vectors are cached by
  text, so a rebuild embeds only changed chunks, and the BM25 files are byte-identical across
  builds. FR-CORE-006, NFR-005, AC-006, AC-013, ADR-0002.
- One command rebuilds everything from the cached pages: `python scripts/rebuild.py` runs parse,
  chunk, enrich and index in order, and stops on a failed step or a document that failed to
  parse. NFR-005, AC-013.
- Eval set format and checker: `eval/questions.yaml` holds questions with expected answer, key
  facts and provisions written as cited; `python -m src.eval.check` resolves each provision to
  its article, checks the set's shape and warns on amended provisions. New metrics EVAL-006
  answer correctness, EVAL-007 context precision@k, EVAL-008 answer relevancy. FR-CORE-015,
  EVAL-006, EVAL-007, EVAL-008.
- Eval set v1: 50 questions (39 answerable, 11 unanswerable) across the six tax types and 6
  conversations, in `eval/questions.yaml`; questions drafted without reading the corpus, answers
  from the corpus, reviewed by the owner and cold-read (`eval-set.md`, *Provenance*). FR-CORE-015,
  EVAL-001–EVAL-008.
- Reference lookup and hybrid retrieval: `src.retrieval` finds explicit references (document
  numbers, base-law names, article and clause) and gives each named article the first slots,
  then fills the top 8 by reciprocal rank fusion of BM25 and bge-m3 results; a document named
  without an article lifts its chunks, and an unresolved reference is reported with its reason.
  Median 0.45 s per question on the dev laptop. FR-CORE-007, FR-CORE-008, NFR-002, AC-007,
  AC-012, ADR-0002.
- Eval runner: `python -m src.eval.run` sends every eval question and turn through the
  pipeline, scores recall@8 (EVAL-001, EVAL-005) and context precision@8 (EVAL-007) with a
  seeded bootstrap interval, records the answer metrics as not run, latency per stage and
  cost, and writes a results file with the commit and the configuration to `eval/results/`;
  `--compare` shows what changed since an earlier run. FR-CORE-015, AC-011, AC-016.
- BM25 tokenizer as a build option: `python -m src.index --tokenizer {syllable,underthesea,pyvi}
  --out <folder>` builds a variant index from the shared vector cache, and the retriever
  tokenizes questions like the index; `python -m src.eval.run --index` scores a variant, and
  `--compare` reports a paired bootstrap interval of each retrieval change. The segmenters are in
  `requirements-experiments.txt`. Measured on eval set v1, neither segmenter beats syllable
  tokens on recall@8 (paired intervals include 0), so `syllable` stays. ADR-0002, #10.
- Chunk-threshold variants: `python -m src.chunking --max-tokens <n> --out <folder>`,
  `python -m src.enrich --chunks --out`, `python -m src.index --enriched --cache` and
  `python -m src.eval.run --enriched` build and score chunks cut at another threshold. The
  split parameters travel as `params.json` into the index manifest (`chunking`) and every
  results file. FR-CORE-002, ADR-0001, #12.
- Embedding model as a build option: `python -m src.index --model
  {BAAI/bge-m3,AITeamVN/Vietnamese_Embedding} --input-limit <n>` builds with either pinned model,
  offline. A text over the limit is cached under a key that carries the limit, so lowering it
  re-embeds only those texts. The manifest and every results file record `input_limit` and
  `truncated`, and the retriever embeds questions with the model the index names. Measured on
  eval set v1, Vietnamese_Embedding raises recall@8 from 0.678 to 0.708, but its paired
  interval includes 0 (+0.030 [−0.035, +0.094]), so bge-m3 stays. ADR-0002, #11.
- Cut diagnosis: `python -m src.eval.diagnose` scores recall@k at k = 8 to 50 on one uncut
  ranking per question, and places each expected article missing from the top 8 (below the
  cut, beyond 50, not in the pool) with its ranks in the full BM25 and vector rankings, writing
  to `eval/results/diagnostics/`. `Retriever.rankings` returns the uncut orders `retrieve`
  cuts from. Measured on eval set v1, 30 of the 43 articles missing from the top 8 are ranked 9
  to 50, and recall@20 is 0.850, so the next step is tuning the fusion. FR-CORE-008, ADR-0002,
  #24.
- Fusion setting as a run option: `Retriever` takes a `Fusion` (`rrf_k`, `keyword_weight`,
  `vector_weight`, `per_article`, `candidates`), and `python -m src.eval.run` and
  `python -m src.eval.diagnose` take `--rrf-k`, `--keyword-weight`, `--vector-weight`,
  `--per-article` and `--candidates`, recorded under `pipeline` in every results file. With
  `per_article`, a chunk whose article already has a chunk above it is skipped, so the top 8
  holds 8 articles. `--compare --comparisons n` also prints a Bonferroni interval of each paired
  change. With `per_article` off, the results are those before #25. FR-CORE-008, ADR-0002, #25.
- Eval set sizes by version and `added_in`: `python -m src.eval.check` keeps 30–50 questions and
  at least 5 conversations for version 1, and from version 2 asks for 225–250 questions, 180–200
  of them answerable, and at least 20 conversations. A question or a conversation may carry
  `added_in`, the set version that added it (1 when absent), and every results file records it
  per item and breaks EVAL-001 and EVAL-007 down by it, so items added after a round of tuning
  are scored apart. An `answer` left as `TODO`, the placeholder of the first drafting step, is
  an error on every question and turn. FR-CORE-015, EVAL-001, EVAL-007, #26.

### Changed

- One hit per article by default: after the reference slots, a chunk whose article already has
  a chunk above it is skipped, so the top 8 holds 8 articles; `--no-per-article` turns it off.
  Measured on eval set v1 against five other fusion variants (`RRF_K` 20 and 120, either list
  weighted 2, 100 candidates), recall@8 0.678 to 0.714, paired change +0.036 [+0.006, +0.071],
  the only variant whose interval lies above 0. Its Bonferroni interval over the six comparisons
  starts at 0, so it is re-checked on eval set v2. FR-CORE-008, ADR-0002, #25.

- Clause-split threshold 800 to 1,600 tokens: 1,286 chunks instead of 1,923, 98 articles split
  instead of 238. Measured on eval set v1 against 400, 800 and no split, recall@8 0.633 to
  0.678, paired change +0.044 [+0.005, +0.091], the only threshold whose interval lies above 0.
  FR-CORE-002, AC-002, ADR-0001, #12.

### Deprecated

### Removed

### Fixed

- Parsed text no longer carries the site's own words: its "Bổ sung" label on amended
  provisions (12 lines) and its comment blocks between provisions (22 blocks, 3 of them inside
  chunks, e.g. a note on the 2% VAT cut inside the VAT Law's rate clause). FR-CORE-001.
- The bge-m3 token count that sets chunk splits is read from the pinned revision in the local
  cache: `python -m src.chunking` and `python -m src.enrich` made 12 connection attempts to
  the Hugging Face Hub per run and read its `main`, so a later upstream tokenizer could have
  moved the splits. A missing revision stops with the download command. Chunks unchanged
  (1,923). NFR-005.
