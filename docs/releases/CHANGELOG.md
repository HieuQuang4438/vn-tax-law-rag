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

### Changed

### Deprecated

### Removed

### Fixed

- Parsed text no longer carries the site's own words: its "Bổ sung" label on amended
  provisions (12 lines) and its comment blocks between provisions (22 blocks, 3 of them inside
  chunks, e.g. a note on the 2% VAT cut inside the VAT Law's rate clause). FR-CORE-001.
