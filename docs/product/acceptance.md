---
status: approved
updated: 2026-11-18
owner: HieuQuang4438
approved-by: peer
---

# Acceptance — vn-tax-law-rag

When a requirement in [requirements.md](requirements.md) counts as met. `AC-nnn` are pass/fail
checks; `EVAL-nnn` are quality metrics with a target, scored by the eval runner (FR-CORE-015)
over the eval set defined below.

## Acceptance criteria

| ID | Criterion | Checks |
|---|---|---|
| AC-001 | A crawl of both summary articles yields every listed document exactly once — 30 documents as of 2026-11-04 — each with number, type, issuer and issue date, and every article from Điều 1 to its last with no gap. | FR-CORE-001 |
| AC-002 | Every chunk carries document, chapter, article, clause and parent ids. No chunk contains appendix-form text, the heading block, the preamble or the signature block. Every article over 1,600 tokens that has clauses is split into them; no article at or under 1,600 is split; an article over 1,600 with no clauses is one chunk. | FR-CORE-002 |
| AC-003 | Every chunk's header names its document number, document title, chapter (where the document has chapters), article, and clause for a clause chunk, in a field separate from its text. The indexed text of a chunk is header + text; the text shown for a citation contains no header. | FR-CORE-003 |
| AC-004 | Every chunk has an effective date, or its document is listed in a report of documents where none could be read. Check case: in Law 09/2026/QH16, articles 1–3 carry 01/01/2026 and the other articles the adoption date, 24/04/2026. | FR-CORE-004 |
| AC-005 | On a hand-checked list of the amending, replacing and repealing provisions in the corpus, every one produces its link; every link to an in-corpus target has the matching inverse link; every link to a document outside the corpus is kept and marked out-of-corpus. | FR-CORE-005 |
| AC-006 | The vector index and the keyword index contain exactly the same set of chunk ids. | FR-CORE-006 |
| AC-007 | For each eval question that names an article of a document, that article is among the retrieved chunks. | FR-CORE-007 |
| AC-008 | For a fixed set of retrieved chunks, assembly is deterministic, contains no duplicate passage, includes the parent article of every clause and the amending text of every amended chunk, and stays within the token budget. | FR-CORE-009 |
| AC-009 | Every citation id in an answer resolves to a passage that was in the context; an id that does not is flagged in the output. | FR-CORE-010, FR-CORE-011 |
| AC-010 | The web interface answers a question end to end, shows citations as links to the source, and shows the not-advice notice. | FR-CORE-013, FR-CORE-014 |
| AC-011 | One command runs the full eval set and writes a results file holding every EVAL score, the commit and the configuration. | FR-CORE-015 |
| AC-012 | Index build and retrieval run on the dev laptop (CPU, 16 GB RAM) with no paid service; median retrieval time over the eval set is under 2 s. | NFR-001, NFR-002 |
| AC-013 | `git ls-files data/` lists nothing but `.gitkeep`; re-running the crawler on a full cache makes no network request; two index builds from the same cache produce identical chunk files. | NFR-003, NFR-004, NFR-005 |
| AC-014 | On the eval set's conversations, every follow-up turn goes through the rewriter before retrieval, and every first turn is passed through unchanged. A rewriter may leave a follow-up that stands alone as it is (approved on #19, choice 5A). | FR-CORE-016 |
| AC-015 | For every answerable eval question whose listed provision has an `amended_by` link and is in the assembled context, the answer says the provision was amended and cites the amending provision. A listed clause counts as listed; for a listed whole article, only the amended clauses of it that the answer cites count, and a question whose answer cites none of them is reported as uncited, not judged. A question whose amended provision is not in the context is reported as a retrieval miss (approved on #15). | FR-CORE-010 |
| AC-016 | The eval results file holds latency and token cost for every question, and the run reports median and p95 latency and the average cost per question against NFR-006 and NFR-007. | NFR-006, NFR-007 |

## Eval targets

Targets are provisional: they are set before the first baseline run and revised once, against
that baseline, by a recorded decision — never quietly to fit a result.

| ID | Metric | Target | Checks |
|---|---|---|---|
| EVAL-001 | Retrieval recall@k on answerable questions | ≥ 0.80 at k = 8 | FR-CORE-006, FR-CORE-008 |
| EVAL-002 | Citation correctness | ≥ 0.90 | FR-CORE-010, FR-CORE-011 |
| EVAL-003 | Faithfulness | ≥ 0.90 | FR-CORE-010 |
| EVAL-004 | Not-found accuracy on unanswerable questions | ≥ 0.80 | FR-CORE-012 |
| EVAL-005 | Retrieval recall@k on follow-up turns of conversations | ≥ 0.70 at k = 8 | FR-CORE-016 |
| EVAL-006 | Answer correctness on answerable questions | ≥ 0.80 | FR-CORE-010 |
| EVAL-007 | Context precision@k on answerable questions | ≥ 0.60 at k = 8 | FR-CORE-006, FR-CORE-008 |
| EVAL-008 | Answer relevancy on answers to answerable questions | reported, no target | FR-CORE-010 |

## Measurement definitions

**Eval set.** Vietnamese questions, drafted in two separate LLM sessions (questions before
reading the corpus, answers after), reviewed by the owner and cold-read, each with the expected answer in a
sentence or a short paragraph, the 1–4 key facts that answer must state, and the list of articles (or clauses) that
support it. An amended provision is listed with the provision that amends it. At least 20% are unanswerable
from the corpus — outside its scope, or about repealed rules — with an empty expected list.
Questions mix plain-language wording with explicit references ("Điều 9 Luật 48/2024"), and
cover every tax type in the corpus. It also holds conversations of 2–3 turns whose
follow-up turns cannot be answered without the earlier ones ("còn hộ kinh doanh thì sao?");
each follow-up has its own expected articles. The size depends on the set version:

| Set version | Standalone questions | Of them answerable | Conversations |
|---|---|---|---|
| 1 | 30–50 | — | at least 5 |
| 2 and later | 225–250 | 180–200 | at least 20 |

Version 2 is sized so that a paired recall@8 change of about +0.03 can be told from 0 (#26).
The set is versioned; a score is only comparable to scores from the same set version. File
format, checks and how each version was made: [eval-set.md](../reference/eval-set.md).

**recall@k** — over answerable questions, the share of expected articles that appear among the
top k retrieved chunks, averaged per question. A clause chunk counts for its parent article.

**Citation correctness** — over cited claims in answers to answerable questions, the share
whose cited passage actually supports the claim. Judged by an LLM against the passage, with a
hand-checked sample of at least 20 claims per run to confirm the judge.

**Faithfulness** — over answers to answerable questions, the share of claims supported by the
passages in the context, whether cited or not. Same judge and spot-check as above.

**Not-found accuracy** — over unanswerable questions, the share answered with the not-found
reply rather than an answer.

**Follow-up recall@k** — recall@k as above, over follow-up turns only, retrieving with the
rewritten question.

**Answer correctness** — over answers to answerable questions, the share that state every key
fact of the expected answer and contradict none. Judged by an LLM against the key facts, with a
hand-checked sample of at least 20 judgments per run to confirm the judge. Faithfulness alone
cannot catch an answer that follows the wrong passage faithfully; this does.

**Context precision@k** — over answerable questions, the sum of precision@i over the ranks
*i* ≤ k whose retrieved chunk belongs to an expected article (a clause chunk counts for its
parent article), divided by the number of such ranks; 0 when there is none. This is the RAGAS
formula, computed on ids. A relevant article missing from the expected list counts as noise, so
the score runs low; such articles are added to the set as a new version, not argued away.

**Answer relevancy** — over answers to answerable questions, not-found replies excluded: the LLM
writes 3 questions from the answer, and the score is the mean bge-m3 cosine between them and the
original question (RAGAS). Reported for trend only: the score has no natural threshold.

**Latency** — wall-clock time from receiving a question to the complete answer, per question.
Reported as median and p95, with the machine it ran on.

**Cost** — input and output tokens per question, from the provider's usage report, times the
provider's list price on the day of the run.

Every run reports all of these, including the ones that got worse.
