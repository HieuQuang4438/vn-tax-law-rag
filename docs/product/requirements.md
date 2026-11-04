---
status: approved
updated: 2026-11-04
owner: HieuQuang4438
approved-by: peer
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
| GOAL-001 | Answer a Vietnamese tax question from all relevant documents at once, including follow-up questions in a conversation. | PROB-001 |
| GOAL-002 | Answer from the current wording and say when a provision was amended. | PROB-002 |
| GOAL-003 | Back every claim with a citation the reader can open and check; say "not found" rather than guess. | PROB-003 |
| GOAL-004 | Make answer quality, speed and cost numbers that a script reproduces, not impressions. | PROB-003 |

## Functional requirements

### Build the corpus and the index

| ID | Requirement | Since | Until | Status | Note |
|---|---|---|---|---|---|
| FR-CORE-001 | Crawl every document listed in the source summary articles — the 2026 tax document list and the personal income tax list — once each; cache each page; extract document metadata and the full text as ordered blocks. | — | — | approved | Built: `scripts/crawl_index.py` |
| FR-CORE-002 | Split each document into chunks along its legal structure: one article per chunk; an article over 800 tokens is split into its clauses (Khoản); an article over 800 tokens with no clauses stays whole. Only article text is chunked: the heading block, the preamble ("Căn cứ…"), chapter titles, the signature block and appendix forms are not. Every chunk records document, chapter, article, clause and its parent article. | — | — | approved | ADR-0001. 800 is a starting value, set by #12 |
| FR-CORE-003 | Give every chunk a context header naming its document number, document title (trích yếu), chapter, article and — for a clause chunk — clause, stored apart from the chunk text. Header + text is what gets indexed; text alone is what is shown and cited. | — | — | approved | ADR-0001 |
| FR-CORE-004 | Record the effective date of every chunk, read from its document's own effectiveness article: the document's date by default, and the specific date where that article sets one for particular articles or clauses. | — | — | approved | ADR-0001 |
| FR-CORE-005 | Record amends / amended-by, replaces and repeals links at article or clause level. A link whose target document is not in the corpus is kept, with the target identified by document number, article and clause, and marked out-of-corpus. | — | — | approved | ADR-0001 |
| FR-CORE-006 | Build a vector index and a keyword index over the same chunk ids, offline, and persist both. | — | — | approved | ADR-0002 |

### Answer a question

| ID | Requirement | Since | Until | Status | Note |
|---|---|---|---|---|---|
| FR-CORE-016 | Keep the conversation of a session. Before retrieval, rewrite a follow-up question into a standalone question using the earlier turns; a question that needs no context is left unchanged. | — | — | approved | Design open: LLM rewrite or LLM-free (concatenate / fuse both queries), decided by EVAL-005 |
| FR-CORE-007 | Resolve explicit document and article references in a question directly from chunk metadata. | — | — | approved | ADR-0002 |
| FR-CORE-008 | Retrieve chunks by fusing keyword and vector results and keep the top 8. | — | — | approved | ADR-0002. k = 8 matches EVAL-001 |
| FR-CORE-009 | Assemble the model's context from retrieved chunks: deduplicate, add the parent article of a clause, add the amending text of an amended chunk, give each passage a citation id, fit a token budget. | — | — | approved | |
| FR-CORE-010 | Answer in Vietnamese using only the assembled passages, citing a passage for every claim. When a cited provision has been amended, say so and cite the amending provision. | — | — | approved | LLM not chosen |
| FR-CORE-011 | Show each citation as document, article and clause with a link to the source page; flag any citation id that was not in the context. | — | — | approved | |
| FR-CORE-012 | Reply that the documents do not cover the question when retrieval finds nothing relevant or the passages do not answer it. | — | — | approved | Threshold set by eval |
| FR-CORE-013 | State with every answer that it is information with sources, not legal or tax advice. | — | — | approved | |
| FR-CORE-014 | Offer a web chat interface for multi-turn conversations, showing each answer with its citations. | — | — | approved | |

### Measure

| ID | Requirement | Since | Until | Status | Note |
|---|---|---|---|---|---|
| FR-CORE-015 | Run the eval set through the pipeline with one command and record every score, with per-question latency and token cost, and the configuration that produced them. | — | — | approved | |

## Non-functional requirements

| ID | Requirement | Since | Until | Status | Note |
|---|---|---|---|---|---|
| NFR-001 | Indexing and retrieval run on a CPU-only machine with 16 GB RAM, without paid services. | — | — | approved | ADR-0002 |
| NFR-002 | Retrieval for one question completes within 2 s on the dev laptop, index already built. | — | — | approved | |
| NFR-003 | Crawled pages and derived text are never committed or published; only code is. | — | — | approved | `.gitignore` |
| NFR-004 | The crawler waits at least 3 s between live requests and never re-fetches a cached page. | — | — | approved | Built |
| NFR-005 | Rebuilding the index from cached pages is one command and gives the same chunks every time. | — | — | approved | |
| NFR-006 | From question to complete answer: median ≤ 10 s and p95 ≤ 20 s on the demo hardware (Hugging Face Spaces CPU Basic), measured over the eval set. | — | — | approved | Provisional until the first measurement |
| NFR-007 | Average model cost per question ≤ 0.01 USD, computed from recorded token usage at the provider's list price on the day of the run. | — | — | approved | Provisional until the LLM is chosen (#13) |

## Traceability

Test column is filled in as tests are written; a requirement with no AC is not shippable.

| Goal | Requirement | Acceptance | Test |
|---|---|---|---|
| GOAL-001 | FR-CORE-001 | AC-001 | — |
| GOAL-001 | FR-CORE-002, FR-CORE-003 | AC-002, AC-003 | — |
| GOAL-002 | FR-CORE-004 | AC-004 | — |
| GOAL-002 | FR-CORE-005 | AC-005 | — |
| GOAL-001 | FR-CORE-006, FR-CORE-008 | AC-006, EVAL-001 | — |
| GOAL-001 | FR-CORE-016 | AC-014, EVAL-005 | — |
| GOAL-001 | FR-CORE-007 | AC-007 | — |
| GOAL-002, GOAL-003 | FR-CORE-009 | AC-008 | — |
| GOAL-002, GOAL-003 | FR-CORE-010, FR-CORE-011 | AC-009, AC-015, EVAL-002, EVAL-003 | — |
| GOAL-003 | FR-CORE-012 | EVAL-004 | — |
| GOAL-003 | FR-CORE-013, FR-CORE-014 | AC-010 | — |
| GOAL-004 | FR-CORE-015 | AC-011 | — |
| GOAL-001 | NFR-001, NFR-002 | AC-012 | — |
| — | NFR-003, NFR-004, NFR-005 | AC-013 | — |
| GOAL-004 | NFR-006, NFR-007 | AC-016 | — |
