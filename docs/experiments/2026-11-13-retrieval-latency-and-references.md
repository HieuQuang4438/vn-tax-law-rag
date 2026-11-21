---
status: approved
updated: 2026-11-19
owner: HieuQuang4438
approved-by: self (built)
issue: 8
---

# Retrieval latency and references, measured on #8

Moved on 2026-11-19 from `docs/reference/retrieval.md`, *Measured* (#32). The text is as it was written there; the only edits are pointers to sections that now live in another file.

On the dev laptop (i7-10610U, 16 GB RAM, CPU only; torch 2.15.0+cpu, sentence-transformers
6.3.0), eval set v1, the index of 1,923 chunks, the code that closes #8, 2026-11-13:

- **AC-012.** 66 questions and turns, one warm-up call not timed: median 0.448 s, 95th
  percentile 0.775 s. Nearly all of it is embedding the question.
- **AC-007.** 13 items have `form: reference`. 4 name an article of a corpus document by number,
  and all 4 articles are retrieved. The other 9 name a document without an article and get a
  document list. No reference in an answerable item is unresolved.
