---
status: draft
updated: 2026-11-04
owner: HieuQuang4438
---

# Brief — vn-tax-law-rag

## Problem

Vietnamese tax rules are split across three layers: a law passed by the National Assembly, the
government decrees that detail it, and the Ministry of Finance circulars that guide those. One
practical question usually needs all three. In 2025–2026 most tax laws were replaced or amended
and new decrees and circulars followed, so even someone who knew the old rules cannot tell which
provision applies now.

General-purpose chatbots answer these questions fluently and often wrongly. They cite repealed
rules, mix up document numbers, or invent articles, and the reader has no way to check.

## Who it is for

- **Household and individual businesses.** A large group with little legal background and a
  tax regime that changed in 2026 (Decree 68/2026, Decree 141/2026, Circular 18/2026). This is
  the primary demo case.
- **Accountants and small-business staff** who know the domain and need the exact article fast.
- **Portfolio readers.** The project is also a worked example of a RAG system built and measured
  end to end.

## Solution

A question-answering agent, in Vietnamese, that answers only from the current tax documents and
cites the document, article and clause behind every claim, linked to the source text. When the
documents do not cover a question, it says so instead of guessing. It holds a conversation:
a follow-up such as "còn hộ kinh doanh thì sao?" is understood in the context of the turns
before it.

Three choices carry the design:

- **Chunk along the legal structure** (article, then clause), not by token count, so every
  retrieved unit is something a citation can point to.
- **Hybrid retrieval.** Users ask in prose ("hộ kinh doanh phải nộp thuế gì") and by reference
  ("Điều 9 Luật 48/2024"); keyword search handles the second, embeddings the first.
- **Measured, not demoed.** A hand-written question set with the expected articles scores
  retrieval and citation correctness, so every change is compared against numbers.

## Boundaries

In scope:

- The 30 tax laws, decrees and circulars listed as current in two luatvietnam.vn summary
  articles: the 2026 list of tax documents (27), and the personal income tax list, which adds
  the Personal Income Tax Law 109/2025, Decree 253/2026 and
  Circular 87/2026. Without the second list the most-asked tax type had no law in the corpus.
- Vietnamese questions and answers.
- Answers grounded in, and citing, those documents only.

Out of scope:

- **Legal or tax advice.** Answers are information with sources, not advice; the interface says so.
- Documents no longer in force, and the history of how a rule changed.
- Appendix forms and templates, at least in the first version: they are most of the text by
  volume and little of the value for question answering.
- Detailed customs and import-export duty rules beyond what the listed documents contain.
- Keeping up with new documents automatically; the corpus is refreshed by re-running the crawler.
- Publishing the corpus. Only the crawler is public; crawled text stays local.

## Known hard parts

- **Amendments.** Law 149/2025 amends Law 48/2024; Decrees 359/2025 and 144/2026 amend Decree
  181/2025. An answer from the original text can be out of date. The first version records
  which document amends which; resolving the amended text comes later.
- **Validity dates** are paid-only on the source site, so they come from each document's own
  "Hiệu lực thi hành" article.
- **Uneven source formatting.** Article headings vary (`Điều 1 .`), and some circulars quote
  other documents' articles inside forms.
