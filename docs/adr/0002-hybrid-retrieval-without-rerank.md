---
status: proposed
updated: 2026-11-03
owner: HieuQuang4438
---

# ADR-0002: Hybrid retrieval with local models, no reranker in v1

## Status
Proposed on 2026-11-03.

## Context
Users ask in plain Vietnamese ("hộ kinh doanh phải nộp thuế gì") and by reference ("Điều 9
Luật 48/2024"). Embeddings handle the first; exact terms and document numbers need keyword
search. A reference alone is a poor keyword query: "Điều 9" occurs in hundreds of chunks, and
tokenizers split numbers like `48/2024/QH15` into fragments.

The project is a portfolio piece and a way to learn RAG, so the retrieval core should be
written and measured by hand rather than hidden in a framework, and it should run without
paid services or a GPU.

CPU benchmark on the dev laptop (i7-10610U, 16 GB RAM, no GPU), 1,824 chunks / 564k tokens:
bge-m3 embeds the corpus in ~95 min (one-off), a query in under 0.5 s; bge-reranker-v2-m3
needs 19–28 s for 20 pairs. Both models together use ~4 GB RAM. The demo target, Hugging Face
Spaces free tier, has 2 vCPU and 16 GB RAM.

Research behind this, not authority: `docs/discovery/rag-pipeline.md` ("Risks checked").

Alternatives considered:
- Vector search only: misses exact references and legal terms.
- Rerank with a local cross-encoder: too slow on CPU for an interactive answer.
- Hosted embedding or rerank APIs: cost and a dependency, before any measurement shows the
  local setup falls short.
- LangChain / LlamaIndex: faster to wire, but hides the steps the project exists to learn.

## Decision
Retrieval is hybrid — BM25 (`bm25s`) and dense vectors (`BAAI/bge-m3` via
`sentence-transformers`, stored in a local Chroma collection) merged by hand-written
reciprocal rank fusion and cut to the top ~5–10 — preceded by a regex that resolves explicit
document and article references directly from chunk metadata, with no reranker in v1.

## Consequences
- The corpus index is built offline and saved; the demo only embeds queries and searches.
- Without a reranker, the cut after fusion decides precision. Fused rank scores are not
  calibrated, so "not found" cannot rest on them alone.
- A reranker comes back as a new ADR if eval shows the right article retrieved but ranked
  below the cut.
- Open and decided by eval, not here: BM25 tokenization (syllables or word-segmented),
  bge-m3 against multilingual-e5, the exact cut.
- The LLM for generation is not part of this decision.
- The Spaces free tier has non-persistent disk; cold-start model download time is unmeasured.
