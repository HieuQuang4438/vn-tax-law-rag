---
status: living
updated: 2026-11-03
owner: HieuQuang4438
---

# ADR register — vn-tax-law-rag

Every architecture decision in this repo, newest first. Format and the bar for
writing one: `DOCS-CONVENTIONS.md` §7.

This table is the index. An agent writing an ADR creates its own numbered file
and reports it; **the row here is added by the main thread**, because the next
free number is shared state — `CONVENTIONS.md` §9.

| ID | Title | Status | Date | Supersedes |
|---|---|---|---|---|
| [ADR-0002](0002-hybrid-retrieval-without-rerank.md) | Hybrid retrieval with local models, no reranker in v1 | approved | 2026-11-03 | |
| [ADR-0001](0001-chunk-by-legal-structure.md) | Chunk by legal structure and enrich each chunk with its context | proposed | 2026-11-03 | |

Numbering starts at `0001` and never restarts. A superseded ADR keeps its number
and its row; the file moves to `archive/` only under the rule in §7.
