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
- Eval set v2: 240 questions (184 answerable, 56 unanswerable) and 22 conversations in
  `eval/questions.yaml`, v1 unchanged plus 190 questions and 16 conversations marked `added_in: 2`;
  made by the same steps, the owner reading a sample of 49 and the cold read every new item
  (`eval-set.md`, *Provenance*). Baseline recall@8 0.769 [0.715, 0.813] (`eval-results.md`,
  *Baseline*). FR-CORE-015, EVAL-001–EVAL-008, #26.
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
- Several Google API keys: `src.config` reads `GOOGLE_API_KEY_1`, `GOOGLE_API_KEY_2`, ... up to
  the first gap into `GOOGLE_API_KEYS`, and fails at startup without `GOOGLE_API_KEY_1`;
  `GOOGLE_API_KEY` is no longer read. #13.
- Context assembly: `src.context` turns the top 8 chunks into the passages the model reads,
  one per parent article in rank order, its clauses marked `[n.k]`, the amending text of every
  amended chunk after it with a link line, cut by whole articles to 24,000 bge-m3 tokens; no
  model, no network. AC-008 holds on the 240 questions and 52 turns of eval set v2, median
  12,851 tokens per question (`context.md`). FR-CORE-009, AC-008, #14.
- Cited answers: `src.answer` asks `gemini-3.5-flash-lite` for sentences that each carry
  citation ids, through `src.llm`, the one wrapper around the API (under 15 requests a minute,
  retries with backoff, one log line per call with tokens and cost; a 429 or a 5xx moves to
  the next key of `GOOGLE_API_KEYS` at once, each key its own project). Each id resolves to
  document, article and clause with a link to the source page; an id not in the context is
  listed apart, never as a source. An answer that cites an amended provision gets a notice
  sentence naming it and its amending one, built from the context's link lines.
  `python -m src.eval.run --generate` also answers and judges: EVAL-002, EVAL-003, EVAL-006
  and AC-015 from an LLM judge, checked by hand with `python -m src.eval.handcheck`, its
  `says_amended` verdicts included; AC-015 asks about a listed article's amended clauses only
  when the answer cites them, and takes a provision a notice covers as said to be amended. FR-CORE-010, FR-CORE-011, AC-009, AC-015, EVAL-002, EVAL-003,
  EVAL-006, #15.
- Not-found reply: the model answers the part of a question the passages answer and replies
  not found only when no passage bears on it, with no similarity floor. `--generate` scores
  EVAL-004 from the not-found answers to unanswerable questions, and counts the not-found
  answers to answerable ones by recall@k. FR-CORE-012, EVAL-004, #16.
- Multi-turn conversation: `src.conversation.Session` keeps the turns of one conversation and
  turns each follow-up into a query from the earlier questions before retrieval, through one of
  four rewriters (`none`, `concat`, `fuse`, `llm`); `Retriever.fuse` searches several queries as
  one. `python -m src.eval.run --rewrite <name>` scores a rewriter on EVAL-005; `concat`,
  chosen on EVAL-005, is the default of the session and of the run. FR-CORE-016, AC-014,
  EVAL-005, #19.
- Web chat page: `python -m streamlit run src/app.py` keeps one conversation per browser
  session and shows each answer with its sources as links and the note that it is
  information, not advice. FR-CORE-013, FR-CORE-014, AC-010, #17.
- What the new web page reads: each resolved citation carries its document id, article
  heading, the cited article, clause or amending text, its effective date and the amendment
  links of what it cites; each document carries its kind, number, title and issue date;
  `LLMError.quota` marks a failure that was 429 on every key; `src.conversation.ask` answers one
  turn from the earlier questions without keeping a session. FR-CORE-010, FR-CORE-011,
  FR-CORE-016, #30.
- Web app API: `python -m src.web` serves a FastAPI app that loads the index in the background
  and answers `GET /api/status`, `POST /api/load`, `GET /api/documents` and `POST /api/ask`,
  stateless, with the earlier questions sent by the page; a spent quota is told apart (429)
  from other failures (500). FR-CORE-013, FR-CORE-014, AC-010, #30.
- Web chat page: `python -m src.web` serves the static page built from the approved prototype:
  sources numbered on the page with a panel that shows each one's text, issue and effective
  dates and amendments, the not-advice notice under every answer, a quota message of its own,
  and up to 50 conversations kept in the browser, each one renamable. FR-CORE-011, FR-CORE-013, FR-CORE-014,
  AC-010, #30.

### Changed

- The answer prompt asks for every part of the question, from every passage that bears on it,
  with each condition, exception, rate, threshold or deadline in its own sentence. Kept or
  reverted by the run of #34. FR-CORE-010, EVAL-006, #34.
- A citation id below the clause, at a point (`1.25a`, `1.25 b`, `1.25.c`), is read as its
  clause (`1.25`) when that clause is in the context, so it resolves and is shown and judged as
  the clause instead of being flagged. At `271adae`, 82 of the 85 flagged ids had this shape.
  FR-CORE-011, AC-009, #33.
- Generation model: `LLM_MODEL` defaults to `gemini-3.5-flash-lite` (`DEFAULT_LLM_MODEL` in
  `src.config`) instead of the deprecated `gemini-2.5-flash`, on the Gemini API free tier.
  Chosen by a pilot of 24 eval set v2 questions graded blind (`scripts/llm_pilot.py`):
  `gemini-3.6-flash` scored 0.750 against 0.667 but broke NFR-006 (p95 21.1 s) and, from
  2027, NFR-007; Flash-Lite answered in 1.4 s median and 1.9 s p95 at 0.0024 USD per
  question. FR-CORE-010, NFR-006, NFR-007, ADR-0003, #13.
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

- The Streamlit page `src/app.py`, its tests and `streamlit`: replaced by the page of
  `python -m src.web`. FR-CORE-013, FR-CORE-014, #30.

### Fixed

- Parsed text no longer carries the site's own words: its "Bổ sung" label on amended
  provisions (12 lines) and its comment blocks between provisions (22 blocks, 3 of them inside
  chunks, e.g. a note on the 2% VAT cut inside the VAT Law's rate clause). FR-CORE-001.
- The bge-m3 token count that sets chunk splits is read from the pinned revision in the local
  cache: `python -m src.chunking` and `python -m src.enrich` made 12 connection attempts to
  the Hugging Face Hub per run and read its `main`, so a later upstream tokenizer could have
  moved the splits. A missing revision stops with the download command. Chunks unchanged
  (1,923). NFR-005.
