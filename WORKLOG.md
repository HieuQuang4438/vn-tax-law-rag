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
