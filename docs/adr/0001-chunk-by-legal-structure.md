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

Measured on the crawled text, appendix forms cut by a rough regex: 638 articles, 564k tokens
(bge-m3 tokenizer). Tokens per article: p50 532, p75 1,136, p90 2,064, max 8,087 — the largest
is close to bge-m3's 8,192-token limit. Share of articles above a split threshold: 59% above
400, 37% above 800, 30% above 1,000, 18% above 1,500. The count is slightly inflated by
articles quoted inside forms and amended text in two circulars. Appendix forms are most of the
raw volume.
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
- One chunk per whole article, never split: articles run to 8k tokens and the long ones mix
  several topics, which dilutes retrieval; the largest would also hit the embedding limit.
- One chunk per clause always: most clauses are too short to carry meaning, even with a header.

## Decision
One article per chunk, split into clauses when the article is over a token threshold — 800
to start, the value set by experiment (#12); appendix forms
are excluded; every chunk carries a rule-built context header (document number and title,
chapter, article, clause), its effective date read from the document's own "Hiệu lực thi
hành" article, and `amends` / `amended_by` links at article or clause level.

Details that follow from it:
- Articles are detected by text, `^Điều \d+\s*\.`, not by the site's markup.
- Header and text are separate fields: header + text is indexed, text alone is shown and cited.
- `amends` is extracted from the amending text; `amended_by` is its inverse over the whole
  corpus. Replacements and repeals use the same edge shape.

## Consequences
- At 800 tokens about 37% of articles are split, so clause chunks are common, not an edge
  case. 800 is a starting value, not a measured optimum; changing it is a parameter change
  recorded in the requirements, not a new ADR.
- Questions answered only by an appendix form cannot be answered in v1.
- Augmentation must be able to pull a split clause's parent article back in, so chunks keep a
  parent id.
- Amendment links depend on a regex over amending phrasings; phrasings it misses leave an
  outdated article unflagged. The regex has to be checked against every amending document.
- An LLM-written context header ("contextual retrieval") is not ruled out; adopting it would
  be a new ADR backed by an eval result.
