---
status: draft
updated: 2026-11-03
owner: HieuQuang4438
---

# Acceptance — vn-tax-law-rag

When a requirement in [requirements.md](requirements.md) counts as met. `AC-nnn` are pass/fail
checks; `EVAL-nnn` are quality metrics with a target, scored by the eval runner (FR-CORE-015)
over the eval set defined below.

## Acceptance criteria

| ID | Criterion | Checks |
|---|---|---|
| AC-001 | A crawl of the summary article yields every listed document, each with number, type, issuer and issue date, and every article from Điều 1 to its last with no gap. | FR-CORE-001 |
| AC-002 | Every chunk carries document, chapter, article, clause and parent ids; no chunk is appendix-form text; an article over the split threshold is split into clauses and none under it is. | FR-CORE-002 |
| AC-003 | Every chunk has a non-empty context header naming its document number and article, stored in a separate field from its text. | FR-CORE-003 |
| AC-004 | Every document has an effective date, or is listed in a report of documents where none could be read. | FR-CORE-004 |
| AC-005 | On a hand-checked list of the amending provisions in the corpus, every one produces both the `amends` link and the matching `amended_by` link. | FR-CORE-005 |
| AC-006 | The vector index and the keyword index contain exactly the same set of chunk ids. | FR-CORE-006 |
| AC-007 | For each eval question that names an article of a document, that article is among the retrieved chunks. | FR-CORE-007 |
| AC-008 | For a fixed set of retrieved chunks, assembly is deterministic, contains no duplicate passage, includes the parent article of every clause and the amending text of every amended chunk, and stays within the token budget. | FR-CORE-009 |
| AC-009 | Every citation id in an answer resolves to a passage that was in the context; an id that does not is flagged in the output. | FR-CORE-010, FR-CORE-011 |
| AC-010 | The web interface answers a question end to end, shows citations as links to the source, and shows the not-advice notice. | FR-CORE-013, FR-CORE-014 |
| AC-011 | One command runs the full eval set and writes a results file holding every EVAL score, the commit and the configuration. | FR-CORE-015 |
| AC-012 | Index build and retrieval run on the dev laptop (CPU, 16 GB RAM) with no paid service; median retrieval time over the eval set is under 2 s. | NFR-001, NFR-002 |
| AC-013 | `git ls-files data/` lists nothing but `.gitkeep`; re-running the crawler on a full cache makes no network request; two index builds from the same cache produce identical chunk files. | NFR-003, NFR-004, NFR-005 |

## Eval targets

Targets are provisional: they are set before the first baseline run and revised once, against
that baseline, by a recorded decision — never quietly to fit a result.

| ID | Metric | Target | Checks |
|---|---|---|---|
| EVAL-001 | Retrieval recall@k on answerable questions | ≥ 0.80 at k = 8 | FR-CORE-006, FR-CORE-008 |
| EVAL-002 | Citation correctness | ≥ 0.90 | FR-CORE-010, FR-CORE-011 |
| EVAL-003 | Faithfulness | ≥ 0.90 | FR-CORE-010 |
| EVAL-004 | Not-found accuracy on unanswerable questions | ≥ 0.80 | FR-CORE-012 |

## Measurement definitions

**Eval set.** 30–50 Vietnamese questions written by hand, each with the expected answer in a
sentence and the list of articles (or clauses) that support it. At least 20% are unanswerable
from the corpus — outside its scope, or about repealed rules — with an empty expected list.
Questions mix plain-language wording with explicit references ("Điều 9 Luật 48/2024"), and
cover every tax type in the corpus. The set is versioned; a score is only comparable to
scores from the same set version.

**recall@k** — over answerable questions, the share of expected articles that appear among the
top k retrieved chunks, averaged per question. A clause chunk counts for its parent article.

**Citation correctness** — over cited claims in answers to answerable questions, the share
whose cited passage actually supports the claim. Judged by an LLM against the passage, with a
hand-checked sample of at least 20 claims per run to confirm the judge.

**Faithfulness** — over answers to answerable questions, the share of claims supported by the
passages in the context, whether cited or not. Same judge and spot-check as above.

**Not-found accuracy** — over unanswerable questions, the share answered with the not-found
reply rather than an answer.

Every run reports all four, including the ones that got worse.
