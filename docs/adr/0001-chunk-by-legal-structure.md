---
status: proposed
updated: 2026-11-03
owner: HieuQuang4438
---

# ADR-0001: Chunk by legal structure and enrich each chunk with its context

## Status
Proposed on 2026-11-03.

## Context
The corpus is 27 Vietnamese tax laws, decrees and circulars, crawled as ordered text blocks
with document metadata. Answers must cite document, article and clause, so a retrieved unit
has to be something a citation can point to.

Measured on the crawled text, appendix forms excluded: about 640 articles; tokens per article
(bge-m3 tokenizer) p50 186, p90 751, max 3,289. Appendix forms are most of the raw volume.
Article headings are not uniform (`Điều 1 .` occurs), and the site's CSS classes do not map
cleanly to articles.

A clause on its own often cannot be understood or retrieved: "Trường hợp quy định tại khoản 1
Điều này…" names neither its document nor its topic. Amending documents are the same — "khoản
25 Điều 5 được sửa đổi như sau: …" — and an original article that has been amended still reads
as current.

Research behind this, not authority: `docs/discovery/rag-pipeline.md`.

Alternatives considered:
- Fixed-size token windows with overlap: simple, but cuts across articles, so a chunk cannot
  be cited as one provision.
- One chunk per whole article, never split: the largest articles (3k tokens) mix several
  topics and dilute retrieval.
- One chunk per clause always: most clauses are too short to carry meaning, even with a header.

## Decision
One article per chunk, split into clauses when the article is over ~800 tokens; appendix forms
are excluded; every chunk carries a rule-built context header (document number and title,
chapter, article, clause), its effective date read from the document's own "Hiệu lực thi
hành" article, and `amends` / `amended_by` links at article or clause level.

Details that follow from it:
- Articles are detected by text, `^Điều \d+\s*\.`, not by the site's markup.
- Header and text are separate fields: header + text is indexed, text alone is shown and cited.
- `amends` is extracted from the amending text; `amended_by` is its inverse over the whole
  corpus. Replacements and repeals use the same edge shape.

## Consequences
- About 1 article in 10 is split; ~800 tokens is a starting value for eval to tune, not a
  measured optimum.
- Questions answered only by an appendix form cannot be answered in v1.
- Augmentation must be able to pull a split clause's parent article back in, so chunks keep a
  parent id.
- Amendment links depend on a regex over amending phrasings; phrasings it misses leave an
  outdated article unflagged. The regex has to be checked against every amending document.
- An LLM-written context header ("contextual retrieval") is not ruled out; adopting it would
  be a new ADR backed by an eval result.
