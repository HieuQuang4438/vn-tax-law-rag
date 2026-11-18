# Worklog — vn-tax-law-rag

> Append-only journal. One block per working session: **what was done / what was decided and why / what is actually true**.
>
> Rules — full version in `CONVENTIONS.md` §8:
>
> - Newest on top. Never edit an earlier block; correct it in a new one.
> - Three parts per block: `Done` · `Decided + why` · `Real state / warnings`.
> - Label **verified** separately from **assumed**. Only what was run this session counts as verified.
> - Remaining work does not go here — that is issues and milestones (§7).
> - No secrets. No raw error dumps; quote the one decisive line.

---

## Session 8 — 2026-11-17 to 2026-11-18 · Not-found reply, multi-turn conversation and the web page (#16, #19, #17)

**Done**

- #16: the answer prompt narrowed: `NOT_FOUND` only when no passage bears on the question, a
  partial answer otherwise; no similarity floor (choices 1A, 2A) (`271adae`). EVAL-004 read from
  `not_found` alone, with no judge; the not-found answers to answerable questions counted by
  recall@k (`answerable_by_recall`).
- #16: run `271adae` recorded and hand-checked; #16 closed (`2a10b8c`).
- #19: `src.conversation`: four rewriters (`none`, `concat`, `fuse`, `llm`), `Session`,
  `Retriever.fuse`; `src.eval.run --rewrite` (`6e9ee24`). Four retrieval-only runs at `6e9ee24`
  recorded; `concat` made the default of the session and of the run (`fa72e25`); #19 closed
  (`5fdfcc3`).
- #17: `src/app.py`, a Streamlit chat page over `Session`, the not-advice notice under every
  answer, `docs/reference/web.md` (`420aa3e`); a failed retrieval shows the error message too
  (`be0c71c`); one end-to-end run recorded; #17 closed (`68231f8`).
- #17 after the close: the "Chi tiết" expander dropped, choice 3B (`dbc8a66`), posted as an
  Approved comment on #17.
- `acceptance.md`, `requirements.md`, `architecture.md` and `web.md` approved by the owner.

**Decided + why**

- #16, 1A over a similarity floor: the not-found decision stays with the model, so no
  threshold has to be tuned on the eval set it is scored on.
- #19, `concat` under rule 3A: the LLM-free rewriter with the higher EVAL-005; `llm` scored
  higher (0.629 against 0.526) but its Bonferroni lower bound over `concat` is −0.009. No
  rewriter separates from `none` (4A), so eval set v3, adding conversations, was approved on
  #19; not started.
- #17, the notice in the page, not in `Answer.text` (2A): the eval and the judge see the same
  answers as before.
- #17, 3B after the close: the expander showed each passage's id, not its text
  (`Citation.passage` is the id; the test's fake put text there), and the source links already
  open the text.

**Real state / warnings**

- Verified 2026-11-18: 654 tests pass, 19 deselected; `develop` matches `origin/develop`; #16,
  #19 and #17 are closed; `main` is 116 commits behind `origin/develop`.
- At `271adae`: EVAL-004 0.982 [0.946, 1.000] (n=56); EVAL-002 0.774, down from 0.868, the
  paired change not significant; EVAL-006 0.402 against a target of 0.80; AC-015 21 pass,
  7 fail. 30 of 184 answerable questions got "not found" (8 all, 14 some, 8 none by recall@k).
- At `6e9ee24`: EVAL-005 is 0.494 (`none`), 0.526 (`concat`), 0.480 (`fuse`), 0.629 (`llm`);
  every rewriter misses the target of 0.70.
- The page's run at `420aa3e`: 30.8 s to load bge-m3 and both indexes, loaded on the first
  page open, not at server start; turns of 5.8 s and 2.9 s. The follow-up under `concat` was
  answered "not found", and turn 1 cited an id not in the context.
- Assumed, not measured: the judge misgrades the amendment notice sentences, a cause of the
  EVAL-002 drop; no issue for it.
- Correction: the Approved comment on #17 for 3B speaks of the run's "`DETAILS` column"; the
  table has no such column, `DETAILS` was named in its "What the page showed" cells. Not
  corrected on the issue.
- Open in v0.3: #18 (deploy) and #22 (ask back). The owner asked about replacing Streamlit
  with a static HTML page over a FastAPI backend; nothing decided, no issue.

## Session 7 — 2026-11-16 to 2026-11-17 · Context assembly and cited answers (#14, #15)

**Done**

- #14: `src.context` assembles the model's context from retrieved chunks
  (`docs/reference/context.md`): one passage per parent article, the amending source after the
  article with a link line, a budget of 24,000 bge-m3 tokens. AC-008 green (`6ad3bba`).
- #15: `src.llm`, the one google-genai wrapper; `src.answer`, sentences with citation ids, ids
  not in the context flagged; `src.eval.judge`; `src.eval.run --generate`;
  `src.eval.handcheck` (`8f53271`). Key rotation on 429 and 5xx, choice 9B (`6cbf23a`).
- #15: first generation run `2026-11-16-6cbf23a`, hand-checked, recorded (`bef64ae`).
- #15: amendment notices, choice A2, and AC-015 narrowed to cited amended clauses, choice B2
  (`4091435`); run `2026-11-17-4091435` recorded, not hand-checked.
- #15: a notice for every cited amended provision, its source cited or not (choice 2'); a
  noticed provision counts as said amended without the judge (choice 1); `says_amended` in
  the hand-check (choice 3) (`f4889e6`).
- #15 closed with AC-015 not met (`db7bc04`). `acceptance.md` and `architecture.md` approved
  by the owner.

**Decided + why**

- #15 closed without a new `--generate` run (owner, Approved comment on #15): the effect of
  `f4889e6` on AC-015, estimated at about 19 pass and 8 fail of 27, is left to the next run of
  a later issue, which also gives the first `says_amended` sheet.
- Choice 2' over 2: q16 cites the amended clause and its source in one sentence, which 2 would
  not reach.
- Of the 12 AC-015 fails at `4091435`, 8 are answer quality and retrieval (6 do not cite the
  listed amended clause, 2 not found), which no notice changes: left to a later issue.

**Real state / warnings**

- Verified 2026-11-17: 597 tests pass, 19 deselected; `develop` matches `origin/develop`; #15
  is closed.
- Assumed, not measured: `f4889e6` raises AC-015 passes.
- At `4091435` EVAL-006 is 0.402 against a target of 0.80, and 33 of 184 answerable questions
  got "not found".
- At `6cbf23a` the owner agreed with the judge on all 20 sampled answers; all 20 sampled
  sentences were judged supported, so the hand-check has not yet seen the judge catch an
  unsupported one.
- Free tier at `4091435`: 150 key changes, all on 503.
- Correction: an Approved comment on #15 called the `says_amended` hand-check choice 4; a later
  comment corrects it to choice 3.

## Session 6 — 2026-11-15 to 2026-11-16 · Re-checks on eval set v2 and the generation LLM (#28, #27, #13)

**Done**

- #28: one hit per article re-checked on eval set v2 against `--no-per-article`: recall@8
  +0.012 [+0.004, +0.023], the gain on the v1 items (+0.036 against +0.006 on `added_in: 2`).
  Kept (`7b40a2f`).
- #27: `AITeamVN/Vietnamese_Embedding` re-run on eval set v2: +0.015 [−0.006, +0.038]. bge-m3
  stays; ADR-0002 stands (`008a98a`).
- #13: `src.config` reads numbered keys `GOOGLE_API_KEY_1`, `_2`, ... (`3266dca`).
- #13: LLM pilot `scripts/llm_pilot.py`: 24 questions added in v2 (seed 0), the same top 8 and
  a minimal prompt for both models, free tier, graded blind by the owner. Results in
  `eval/results/llm-pilot/`.
- #13: ADR-0003 approved: `gemini-3.5-flash-lite` on the Gemini API free tier; `LLM_MODEL`
  defaults to it (`907d5b5`). `architecture.md`, `requirements.md` and `acceptance.md`
  re-approved by the owner; `architecture.md` no longer gives the set as 30–50 questions.

**Decided + why**

- Only Gemini models compared: one provider and account already set up (proposal on #13).
- `gemini-3.8-flash` dropped from the pilot: 3 of 24 items in three runs, at 108 s, 11.5 s
  and 128 s, then 503 and dropped connections; `gemini-3.6-flash` took its place (Approved
  comment on #13).
- Flash-Lite over 3.6 Flash: they differ on 2 of 18 answerable items; 3.6 Flash breaks NFR-006
  (p95 21.1 s), NFR-007 from 2027 (0.0176 USD), and allows 20 free requests per day.
- The pilot's wrong answers are all "not found" on answerable questions, mostly with the
  expected articles in the top 8: left to prompt design (#15), not a model criterion.

**Real state / warnings**

- Verified 2026-11-16: 459 tests pass; `python -m src.main` reports `gemini-3.5-flash-lite`;
  the API serves that id as version `3.5-flash-lite-07-2026`.
- Free-tier limits, per project: Flash-Lite 15 per minute and 500 per day (owner, AI Studio
  rate-limit page); 3.6 Flash 20 per day (429 response).
- The 3.6 Flash pilot sent 24 requests, above its 20 per day, and finished after a 429 moved
  to the next key.
- AI Studio showed 17/15 per minute on `gemini-3.1-flash-lite`, which no code in the repos
  calls; the source is unknown. Flash-Lite requests were not redirected (`model_version`
  checked).
- The pilot files do not record `model_version`; ADR-0003 asks results files to.
- Pilot latency is generation alone, from the dev laptop; nothing measured on Spaces.
- Correction to Session 5: choice 4A asked for ≥ 50 answerable turns and the set has 51; 29
  of them are follow-ups, the turns EVAL-005 scores.
- Correction to Session 5: the owner records that the step 1 and step 2 sessions of eval set
  v2 ran Claude Opus 5.5; `eval-set.md` says so and is approved.

---

## Session 5 — 2026-11-15 · Eval set v2 (#26, #28)

**Done**

- #28 opened: re-check one hit per article on eval set v2, paired against `--no-per-article`.
- #26: the checker takes its size bounds from the set version (v1: 30–50 questions, ≥ 5
  conversations; v2: 225–250, 180–200 answerable, ≥ 20 conversations), an optional `added_in`
  per question and conversation, and reports an `answer` left as `TODO`. Results files carry
  `added_in` per item and in the breakdown.
- #26: eval set v2 written by separate sessions under the four-step provenance (questions,
  ChatGPT question review, answers, owner sample of 49, cold read by 3 subagents over all 226
  new items: 5 wrong, 23 minor, all applied in `b0cced1`). Provenance row in `eval-set.md`.
- #26: v2 baseline at `b0cced1`: EVAL-001 0.769 [0.715, 0.813] n=184, EVAL-005 0.494 [0.339,
  0.644] n=29, EVAL-007 0.678 [0.626, 0.728].

**Decided + why**

- Size bounds keyed by version, not replaced: replacing them would have failed the committed v1
  file and every eval run during the writing period (Approved comment on #26).
- Owner sample = the 19 items step 2 flagged + 30 random (5 per tax type, seed 0), so the
  decisions step 2 made alone are all read.
- `answer: TODO` became a checker error after q247 passed the checker with it.
- The baseline ran at `b0cced1`, the last commit that changes the set; the closing commit adds
  only docs and the results file.

**Real state / warnings**

- Verified: checker 0 errors, 28 known warnings; v1 items byte-identical to before v2; 240
  questions (184 answerable, 56 unanswerable, 23.3%), 22 conversations; 451 tests pass.
- Choice 4A aimed at ≥ 50 answerable turns; EVAL-005 has 29, interval width 0.31.
- The cold read flagged 10 items in the owner's sample, which the owner had read without
  finding errors. The subagents made 4–19 tool calls each; their depth was not checked.
- Step 1 and step 2 models not recorded (Claude Code sessions).
- `acceptance.md` is `in-review` until the owner re-approves; `architecture.md` still says
  "30–50 questions".
- 10 reference questions name the wrong document; they score recall 0.600 at the baseline.

---

## Session 4 — 2026-11-14 to 2026-11-15 · Embedding model and the cut diagnosis (#11, #24, #25)

**Done**

- #11: the index builder takes `--model` and `--input-limit` from a table of pinned models
  (`EMBEDDING_MODELS`: bge-m3 `5617a9f6` at 8,192, `AITeamVN/Vietnamese_Embedding` `dea33aa1` at
  2,048), offline. A text over the limit is cached under a key that carries the limit. The
  manifest and every results file record `input_limit` and `truncated`, and `Retriever.load`
  embeds questions with the model the manifest names.
- #11: three variants scored at `2360e43` on eval set v1. bge-m3 stays the default. Table in
  `docs/reference/index.md`, *Embedding experiment*; results files `eval/results/2026-11-14-2360e43*.json`.
- #24 (opened this session): `Retriever.rankings` returns the uncut BM25, vector and final
  orders, and `retrieve` takes its hits as the first k of `final`. `python -m src.eval.diagnose`
  scores recall at k = 8 to 50 and places each article missing from the top 8. It was run at
  `20e8896`; results are in `docs/reference/retrieval.md`, *Cut diagnosis*, and
  `eval/results/diagnostics/2026-11-15-20e8896.json`.
- #25 opened: fusion tuning, milestone v0.2.

**Decided + why**

- e5 was replaced by Vietnamese_Embedding in #11's proposal. e5 reads at most 512 tokens, so
  most long chunks would have been cut. bge-m3 at 2,048 was added as a control, to separate
  the model from the cut.
- bge-m3 stays: Vietnamese_Embedding's paired interval includes 0 (+0.030 [−0.035, +0.094]),
  by the rule set before the run. Its means were higher on EVAL-001, 005 and 007, and the owner
  asked whether to keep it anyway. The rule was kept: changing it after the results would void
  the comparison, and the three metrics share the same 39 questions.
- The issues for re-measuring embeddings and for eval set v2 were drafted but not created.
  They wait on what #24 and #25 show is worth optimizing.
- A reranker is not reopened, although #24 meets ADR-0002's condition (the right article is
  retrieved but ranked below the cut). A cross-encoder still takes 19–28 s per 20 pairs on the
  dev laptop.
- #24's rule: if at least half the standalone misses rank 9 to 50, the verdict is `ranking`.
  `borderline` means two misses moved across the line would change the verdict; this detail
  was fixed in the spec, not in the proposal.
- #25 is to score a small grid of variants declared before the first run, not tune
  step by step, because 39 questions overfit easily.

**Real state / warnings**

- Verified on 2026-11-15: 389 unit tests pass. The corpus tests for retrieval, the runner and
  the diagnosis pass, including recall@8 from the diagnosis equal to the runner's EVAL-001 and
  EVAL-005.
- Verified, #11: EVAL-001 0.678 (bge-m3@8192), 0.665 (bge-m3@2048), 0.708 (Vietnamese_Embedding).
  Embedding all 1,286 texts with Vietnamese_Embedding took 63 minutes.
- Verified, #24: 30 of 43 standalone misses rank 9 to 50, 21 of them at 9 to 20. recall@20 is
  0.850 and recall@50 0.922. 22 of the 43 are in the top 50 of both lists.
- Assumed, not measured: fusion tuning can lift the misses at 9 to 20. The 22 found by both lists
  may not move with `RRF_K` or weights alone.
- The `retrieve` refactor is meant to change nothing. It is checked by the earlier retrieval tests
  and by the matching recall@8, not by a byte comparison of hits.
- Vietnamese_Embedding's `tokenizer.json` differs in bytes from bge-m3's but gives the same ids
  on all 1,286 texts. The model (about 4.5 GB) sits in the local HF cache. `data/index-bge-2048/`
  and `data/index-vn-embedding/` sit locally (gitignored).
- `develop` was 11 commits ahead of `origin` before this block. The push is the owner's.

---

## Session 3 — 2026-11-14 · Offline token counter and the clause-split threshold (#23, #12)

**Done**

- #23 (bug, opened during #12's proposal): the bge-m3 token counter reads `tokenizer.json` from
  the pinned revision `5617a9f6` in the local cache, through `pinned_snapshot()` in
  `src/chunking/tokens.py`, which the index builder now shares; a missing revision raises
  `ModelNotCachedError` with the `hf download` command. Chunks unchanged (1,923). NFR-005.
- #12: variant commands for a threshold experiment (`python -m src.chunking --max-tokens --out`,
  `python -m src.enrich --chunks --out`, `python -m src.index --enriched --cache`,
  `python -m src.eval.run --enriched`). The split parameters travel as `params.json` from
  chunking through enrich into the index manifest (`chunking`) and every results file.
- #12: four thresholds scored at ab4a8fa on eval set v1; `MAX_TOKENS` becomes 1,600 (1,286
  chunks, 98 articles split). Table and caveats in `docs/reference/chunk-schema.md`, *Threshold
  experiment*; four results files `eval/results/2026-11-14-ab4a8fa*.json`.
- FR-CORE-002, AC-002, architecture, corpus counts, index, retrieval, README and eval-results
  updated to 1,600. requirements, acceptance and architecture went to `in-review` and were
  approved again by the owner.
- The hand-checked links fixture takes the new chunk ids of 25 of its 175 links. Each change
  only replaces a clause chunk with its parent article, now whole; this was checked by script.
  Every other column is unchanged.

**Decided + why**

- The token counter loads the pinned revision offline. Before, it read the Hub's `main` and
  made 12 connection attempts per run, so a new upstream tokenizer could move the splits (#23).
- 8192 stands for "no split": no article on the corpus has header + text over 8,148 tokens, so
  no text is cut at bge-m3's limit (#12, choice 1A).
- 1,600 replaces 800 by the rule set before the run: only its paired interval of the EVAL-001
  change lies above 0 (+0.044 [+0.005, +0.091]), and it keeps AC-012. 400 is
  −0.018 [−0.056, +0.014]; 8192 is +0.032 [−0.044, +0.104] (#12).
- The split is recorded in `params.json` and carried into the manifest. Otherwise a results file
  could not tell which threshold built its index (#12, approved mid-work).

**Real state / warnings**

- Verified on 2026-11-14: 343 unit tests pass (run before the closing commit); the corpus tests
  passed at 1,600 before the three docs' front matter changed.
- Verified: at 1,600, EVAL-001 0.678 [0.592, 0.764], EVAL-005 0.575, EVAL-007 0.686. Against
  800, 6 questions rose and 1 fell.
- The 1,600 margin is thin. The lower end is +0.005, from 3 comparisons against one baseline
  without correction. Part of the gain may come from k: the top 8 holds 6.82 distinct articles
  at 1,600 against 6.31 at 800, and the experiment does not separate the two.
- The default `data/` was rebuilt at 1,600 from the t1600 vector cache, with nothing embedded;
  its chunks and enriched files match the variant's sha256. Variant folders `data/t400/`,
  `data/t1600/` and `data/t8192/` sit locally (gitignored), next to `data/index-*/` from #10.
- Embedding cost on the dev laptop (CPU): about 15 s per new text at 8192, 3,560 s for 238
  texts.
- Verified: #23 is closed on GitHub. `develop` is 3 commits ahead of `origin/develop` (#12's
  tests, implementation and closing commit), so #12 closes on the next push.
- Settled by the owner: `requirements.txt` and `requirements-experiments.txt` take lower bounds
  (`>=`) at the versions installed, following `CONVENTIONS.md` §2. Each results file and index
  manifest still records the versions it ran with.

---

## Session 2 — 2026-11-04 to 2026-11-13 · From the approved docs to a scored retrieval baseline (#1–#10, #21)

**Done**

- Docs: ADR-0002 approved; ADR-0001 corrected (its token counts were per chunk, not per
  article) and approved; brief, architecture walkthrough, requirements (FR-CORE-016, NFR-006,
  NFR-007 added) and acceptance approved (`approved-by: peer`). `corpus.md` and `glossary.md`
  added. Conventions brought up to the templates, and the commit form `<area>: <what changed>`
  declared (df328fc).
- #1: crawler acceptance tests on HTML fixtures, network refused; both summary articles crawled
  (`INDEX_URLS`), 30 documents. FR-CORE-001, AC-001.
- #2: `src/chunking/` cuts by article and clause, splitting over 800 bge-m3 tokens, with
  `articles.jsonl` beside `chunks.jsonl` and source defects reported in `issues.jsonl`: 744
  articles, 1,923 chunks. FR-CORE-002, AC-002.
- #3, #4, #5: `python -m src.enrich` writes `data/enriched/`: a context header per chunk, an
  effective date per chunk from the effectiveness article, and amendment links (175, equal to
  the hand-checked list) inverted onto `amended_by`. FR-CORE-003–005, AC-003–005.
- #21: the parser drops the site's "Bổ sung" label and its comment blocks
  (`div.docitem-binhluan`), which had been read as provisions.
- #6: `src/index/` builds a bge-m3 Chroma collection and a bm25s index over the same chunk ids,
  with a vector cache keyed by text and a manifest written last; `scripts/rebuild.py` runs parse,
  chunk, enrich and index in one command. FR-CORE-006, NFR-005, AC-006, AC-013.
- #7: eval set format and checker (`src/eval/dataset.py`, `python -m src.eval.check`); EVAL-006,
  EVAL-007 and EVAL-008 added to `acceptance.md`; eval set v1 in `eval/questions.yaml`, 50
  questions (11 unanswerable) and 6 conversations. Provenance in `docs/reference/eval-set.md`.
- #22 opened: FR-CORE-017, ask back when a question leaves out a deciding fact.
- #8: `src/retrieval/` resolves explicit references and fuses BM25 and vector results by RRF,
  top 8. FR-CORE-007, FR-CORE-008, AC-007, AC-012.
- #9: `python -m src.eval.run` scores the set and writes `eval/results/`; first baseline
  `eval/results/2026-11-13-1d257ea.json`. FR-CORE-015, AC-011, AC-016.
- #10: BM25 tokenizer as a build option (`syllable`, `underthesea`, `pyvi`), `--index` on the
  runner, paired bootstrap interval in `--compare`; experiment recorded in
  `docs/reference/index.md`, *Tokenizer experiment*.

**Decided + why**

- Chunk ids are `<doc_id>:D<article>[:K<clause>]` with the site's numeric id: unique and stable
  across crawls (#2).
- Article and clause boundaries come from line patterns on the parsed text, skipping lines inside
  a quotation, so quoted amending text stays inside its clause; a quotation opened mid-line ends
  at that line's end and is reported (#2, approved mid-work).
- Source defects are reported, never repaired: duplicate headings, numbering gaps, unbalanced
  quotes, articles lost at a document's end (#2).
- The header is built in a separate enrich stage and never stored with the text; the 800-token
  threshold counts the text only, so adding the header changes no split (#3).
- An exception narrower than a chunk keeps the document's date and is reported as
  `partial_effective_date`: every chunk has one date and nothing is guessed (#4).
- Amendment links are read from the amending side only, the site's notes used as a cross-check
  and never as input; an amended chunk keeps its own date (#5).
- The site's comment blocks were dropped under #21 rather than a new bug: one cause, one fix,
  one rebuild (#21, approved mid-work).
- bge-m3 is loaded from its resolved snapshot folder, not by name: `HF_HUB_OFFLINE` is read once
  at import, and loading by name still opened 12 connections to the Hub in a test run (#6).
- The BM25 vocabulary is built and sorted here and passed to bm25s: bm25s numbers its own
  vocabulary in set order, which changed with `PYTHONHASHSEED` (#6).
- Eval questions were written by a session that read no corpus text, answers by another one
  that did, then reviewed by ChatGPT, the owner and a read-only subagent: questions shaped by the
  corpus wording would flatter retrieval (#7).
- A provision is listed for a question only when the answer states something from it: recall
  divides by the number of expected articles, so a padded list measures its own length (#7).
- Retrieval reads the vectors from Chroma once and compares them exactly instead of querying
  Chroma: a filtered HNSW query is not sure to return every chunk of a document, exact ties keep
  file order, and an open client locks Chroma's files on Windows (#8, approved mid-work).
- EVAL-001 stays at 0.80 after the baseline of 0.633: the target was set before measuring, and
  lowering it to fit is the risk the approach named (#9).
- `syllable` BM25 tokens stay: neither segmenter's paired interval for the EVAL-001 change lies
  above 0 (underthesea −0.006 [−0.058, +0.038], pyvi −0.032 [−0.083, +0.013]) (#10).

**Real state / warnings**

- This block was written on 2026-11-13, after the session's early part had been compacted out of
  context. Items up to #5 and #21 are taken from their commit messages and issue comments, which
  record what was verified when the work was done; they were not re-run for this block.
- Verified on 2026-11-13: 327 unit tests pass; the corpus tests for retrieval (AC-007, AC-012)
  and the runner (AC-011, AC-016) pass.
- Verified: baseline EVAL-001 recall@8 0.633 [0.539, 0.727], EVAL-005 0.575, EVAL-007 0.676.
  48 of 111 expected articles are missed; 30 of those rank below 20, so a larger k alone would
  not close the gap.
- Retrieval latency on the dev laptop varies by about 0.2 s between runs (median 0.24–0.45 s),
  more than between the variants compared.
- Verified: #1–#9 and #21 are closed on GitHub; `develop` is 2 commits ahead of
  `origin/develop` (#10's implementation and its closing commit), so #10 closes on the next push.
- Commits 15d90bf, d8439bb, 102935c and 301af0a use `test:` and `feat:`, after the commit form
  was declared; they are left as they are.
- `requirements.txt` pins with `==`, against `CONVENTIONS.md` §2's `>=`; not yet settled.
- Variant indexes from #10 sit in `data/index-*/` locally (gitignored).

---

## Session 1 — 2026-11-03 · Repo created

**Done**

- Scaffolded from `git-repos/templates/repo/` — minimal + product + public overlays.
- `scripts/crawl_one.py`: fetches one luatvietnam.vn document page, caches raw HTML in
  `data/raw/`, writes metadata + ordered text blocks to `data/processed/<slug>.json` and `.md`.
- `scripts/crawl_index.py`: takes the document links from the summary article's tables
  (sidebar/footer excluded, deduplicated by document id), crawls each with a 3 s delay, writes
  `data/processed/_index.json`.
- Parser rewritten to walk the DOM: headings sitting as bare text next to a table were dropped
  (Law 09/2026/QH16 lost its Article 4).

**Decided + why**

- Source is the HTML page, not the site's "Print" PDF: HTML keeps the chapter/article/clause
  structure that chunking will need; a PDF would have to be re-parsed to get it back.
- The whole page is cached, not just the document body, so parsing can change without re-crawling.
- `data/processed/` is gitignored as well as `data/raw/`: it is third-party page content.
- Visibility: private now, to be flipped public — written as if public.
- LLM provider not chosen; `src/config.py` keeps the scaffold's Gemini default until it is.

**Real state / warnings**

- Verified: all 27 documents crawled, each with articles 1..N and no gaps (checked by `^Điều N\s*\.`).
- Article headings are not uniform: `Điều 1 .` (space before the dot) occurs. Circulars 89 and 86
  contain more `Điều N.` lines than articles — quoted articles inside forms or amended text.
- Verified: crawler run on Circular 90/2026/TT-BTC — 579 blocks, articles 1–38 and appendix forms
  present; metadata (number, type, issuer, issue date, signer, summary) parsed.
- Effective date and validity status are paid-only on the site and are not captured; the
  document's own "Hiệu lực thi hành" article is the fallback.
- Block `kind` (site CSS class) does not map cleanly to articles: 40 `docitem-5` blocks vs 38
  articles. Chunking should detect articles by the `Điều N.` heading.
- Appendix forms make up most of the ~365k characters; chunking must handle or drop them.
