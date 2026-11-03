---
status: draft
updated: 2026-11-03
owner: HieuQuang4438
---

# Requirements — vn-tax-law-rag

What the product owes. Why each choice was made lives in `docs/adr/`; how it is measured
lives in [acceptance.md](acceptance.md). Scope and boundaries: [brief.md](brief.md).

Nothing is released yet, so `Since` is `—` everywhere until the first release fills it in.

## Problems

| ID | Problem |
|---|---|
| PROB-001 | One practical tax question needs a law, its decrees and its circulars read together. |
| PROB-002 | Most tax documents were replaced or amended in 2025–2026; it is hard to tell which provision applies now. |
| PROB-003 | General-purpose chatbots answer tax questions fluently, with wrong or invented citations the reader cannot check. |

## Goals

| ID | Goal | Addresses |
|---|---|---|
| GOAL-001 | Answer a Vietnamese tax question from all relevant documents at once. | PROB-001 |
| GOAL-002 | Answer from the current wording and say when a provision was amended. | PROB-002 |
| GOAL-003 | Back every claim with a citation the reader can open and check; say "not found" rather than guess. | PROB-003 |
| GOAL-004 | Make answer quality a number that a script reproduces, not an impression. | PROB-003 |

## Functional requirements

| ID | Requirement | Since | Until | Status | Note |
|---|---|---|---|---|---|
| FR-CORE-001 | Crawl every document listed in the source summary article; cache each page; extract document metadata and the full text as ordered blocks. | — | — | draft | Built: `scripts/crawl_index.py` |
| FR-CORE-002 | Split each document into chunks along its legal structure; every chunk records document, chapter, article, clause and its parent article. | — | — | draft | ADR-0001 |
| FR-CORE-003 | Give every chunk a context header naming its document, chapter, article and clause, stored apart from the chunk text. | — | — | draft | ADR-0001 |
| FR-CORE-004 | Record each document's effective date, read from its own effectiveness article. | — | — | draft | ADR-0001 |
| FR-CORE-005 | Record amends / amended-by, replaces and repeals links between chunks, at article or clause level. | — | — | draft | ADR-0001 |
| FR-CORE-006 | Build a vector index and a keyword index over the same chunk ids, offline, and persist both. | — | — | draft | ADR-0002 |
| FR-CORE-007 | Resolve explicit document and article references in a question directly from chunk metadata. | — | — | draft | ADR-0002 |
| FR-CORE-008 | Retrieve chunks by fusing keyword and vector results and keep the top k. | — | — | draft | ADR-0002 |
| FR-CORE-009 | Assemble the model's context from retrieved chunks: deduplicate, add the parent article of a clause, add the amending text of an amended chunk, give each passage a citation id, fit a token budget. | — | — | draft | |
| FR-CORE-010 | Answer in Vietnamese using only the assembled passages, citing a passage for every claim. | — | — | draft | LLM not chosen |
| FR-CORE-011 | Show each citation as document, article and clause with a link to the source page; flag any citation id that was not in the context. | — | — | draft | |
| FR-CORE-012 | Reply that the documents do not cover the question when retrieval finds nothing relevant or the passages do not answer it. | — | — | draft | Threshold set by eval |
| FR-CORE-013 | State with every answer that it is information with sources, not legal or tax advice. | — | — | draft | |
| FR-CORE-014 | Offer a web chat interface for asking questions and reading cited answers. | — | — | draft | |
| FR-CORE-015 | Run the eval set through the pipeline with one command and record every score with the configuration that produced it. | — | — | draft | |

## Non-functional requirements

| ID | Requirement | Since | Until | Status | Note |
|---|---|---|---|---|---|
| NFR-001 | Indexing and retrieval run on a CPU-only machine with 16 GB RAM, without paid services. | — | — | draft | ADR-0002 |
| NFR-002 | Retrieval for one question completes within 2 s on the dev laptop, index already built. | — | — | draft | |
| NFR-003 | Crawled pages and derived text are never committed or published; only code is. | — | — | draft | `.gitignore` |
| NFR-004 | The crawler waits at least 3 s between live requests and never re-fetches a cached page. | — | — | draft | Built |
| NFR-005 | Rebuilding the index from cached pages is one command and gives the same chunks every time. | — | — | draft | |

## Traceability

Test column is filled in as tests are written; a requirement with no AC is not shippable.

| Goal | Requirement | Acceptance | Test |
|---|---|---|---|
| GOAL-001 | FR-CORE-001 | AC-001 | — |
| GOAL-001 | FR-CORE-002, FR-CORE-003 | AC-002, AC-003 | — |
| GOAL-002 | FR-CORE-004 | AC-004 | — |
| GOAL-002 | FR-CORE-005 | AC-005 | — |
| GOAL-001 | FR-CORE-006, FR-CORE-008 | AC-006, EVAL-001 | — |
| GOAL-001 | FR-CORE-007 | AC-007 | — |
| GOAL-002, GOAL-003 | FR-CORE-009 | AC-008 | — |
| GOAL-003 | FR-CORE-010, FR-CORE-011 | AC-009, EVAL-002, EVAL-003 | — |
| GOAL-003 | FR-CORE-012 | EVAL-004 | — |
| GOAL-003 | FR-CORE-013, FR-CORE-014 | AC-010 | — |
| GOAL-004 | FR-CORE-015 | AC-011 | — |
| GOAL-001 | NFR-001, NFR-002 | AC-012 | — |
| — | NFR-003, NFR-004, NFR-005 | AC-013 | — |
