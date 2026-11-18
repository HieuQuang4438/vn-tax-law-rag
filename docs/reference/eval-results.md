---
status: draft
updated: 2026-11-18
owner: HieuQuang4438
---

# Eval results

What `python -m src.eval.run` does and the results file it writes. It runs the eval set
([eval-set.md](eval-set.md)) through the pipeline and scores the metrics defined in
[acceptance.md](../product/acceptance.md#measurement-definitions). The rules are FR-CORE-015,
AC-011 and AC-016. The approach is the approved comment on #9.

By default the pipeline is retrieval only ([retrieval.md](retrieval.md)), and the metrics that
need an answer are written as not run. `--generate` adds context assembly, generation and an
LLM judge (*Generation stage*, #15).

## Running it

```bash
python -m src.eval.run                                  # eval/questions.yaml, data/, writes to eval/results/
python -m src.eval.run --compare eval/results/<file>    # also prints what changed since that run
```

| Option | Default | Meaning |
|---|---|---|
| `--set` | `eval/questions.yaml` | the eval set |
| `--data` | `data` | the folder holding `processed/`, `enriched/` and `index/` |
| `--enriched` | `<data>/enriched` | the enriched chunks, for a variant chunked another way (#12); it must be the folder the index was built from |
| `--index` | `<data>/index` | the index folder, for a variant built with `python -m src.index --out` |
| `--out` | `eval/results` | where the results file is written |
| `--generate` | off | also assemble, generate and judge, as under *Generation stage*; spends API quota |
| `--compare` | none | an earlier results file to compare with |
| `--comparisons` | 1 | how many variants are compared with the same baseline; above 1, `--compare` also prints the Bonferroni interval (#25) |
| `--rrf-k` | `RRF_K` (60) | the fusion's `rrf_k` ([retrieval.md](retrieval.md#hybrid-search)) |
| `--keyword-weight` | 1 | the fusion's `keyword_weight` |
| `--vector-weight` | 1 | the fusion's `vector_weight` |
| `--per-article`, `--no-per-article` | on | the fusion's `per_article`, on by default since #25 |
| `--candidates` | `CANDIDATES` (50) | the fusion's `candidates` |

The fusion options build the `Fusion` that `Retriever.load` gets (approved on #25). With none
of them, it is `Fusion()`. A value `Fusion` refuses (`--rrf-k` or `--candidates` below 1, a
weight of 0 or less) stops the command with exit code 2 before anything loads.
`--comparisons` below 1 stops it the same way.

The command:

1. loads the eval set with `load_eval_set`, which stops on any checker error;
2. loads the pipeline, the model included, before any timing starts;
3. makes one warm-up call with the first question, not recorded;
4. runs every standalone question, then every conversation turn, in file order, each turn as
   written (`rewrite: none`) until #19 adds the rewrite;
5. writes the results file and prints the summary.

It exits with 0 once the file is written, whether or not the targets are met: a baseline that
misses its target is still a result. With `--compare`, it exits with 2, after writing its own
file, when the two runs used different eval sets.

## Scores

| ID | Scored over | Now |
|---|---|---|
| EVAL-001 | answerable standalone questions | recall@8 |
| EVAL-005 | answerable follow-up turns: every turn after the first of a conversation | recall@8 |
| EVAL-007 | answerable standalone questions | context precision@8 |
| EVAL-002, EVAL-003, EVAL-004, EVAL-006, EVAL-008 | | not run: `no generation stage`; with `--generate`, see *Generation stage* |

- **recall@k** of one item: the share of its expected articles that are the parent article of
  at least one of its first k hits. The expected articles are the `article` of each of its
  provisions, once each.
- **context precision@k** of one item: over the ranks *i* ≤ k whose hit's parent article is
  expected, the mean of precision@*i*, where precision@*i* is the share of the first *i* hits
  whose parent article is expected. 0 when no rank qualifies.
- A score is the mean over its items. The first turn of a conversation is recorded but scored
  in none of them: it is not a follow-up, and the counts in eval-set.md are over standalone
  questions.
- **Interval.** Each score has a 95% bootstrap interval. With `rng = numpy.random.default_rng(0)`
  and n items, `rng.integers(0, n, size=(1000, n))` draws 1,000 resamples of the items with
  replacement; the interval is the 2.5th and 97.5th percentiles (`numpy.percentile`, linear) of
  their means. Two runs differ only where their intervals say so.
- **Target.** From acceptance.md: EVAL-001 ≥ 0.80, EVAL-002 ≥ 0.90, EVAL-003 ≥ 0.90, EVAL-004
  ≥ 0.80, EVAL-005 ≥ 0.70, EVAL-006 ≥ 0.80, EVAL-007 ≥ 0.60; EVAL-008 has none. `passes` is
  `value >= target`, and null when there is no value or no target.

**Breakdown.** EVAL-001 and EVAL-007 again, per `form`, per `tax_type` and per `added_in`
(the set version that added the question, eval-set.md; #26), each group with its own n. Only groups with at least one item are written.

## Latency and cost

- **Latency** per item is per stage, in seconds, as the pipeline measures it: today one stage,
  `retrieval`, the time of one `retrieve` call. The item's total is the sum of its stages.
- The run reports the median and the 95th percentile (`statistics.quantiles(totals, n=20)[-1]`)
  of the totals over every item, against NFR-006 (median ≤ 10 s, p95 ≤ 20 s). The scope is
  written with them: `retrieval only, dev laptop`, while NFR-006 is measured with generation on
  the demo hardware.
- **Cost** per item is its input and output tokens and their price in USD. With no LLM in the
  pipeline both token counts and the price are 0, and the run says `no LLM in the pipeline`.
  The average cost per item is reported against NFR-007 (≤ 0.01 USD).

## The results file

One JSON file per run, UTF-8, two-space indent, keys in the order below. The file name is
`<YYYY-MM-DD>-<first 7 characters of the commit>.json`, with `-dirty` before `.json` for a
run with uncommitted changes. An existing file is never overwritten: a second run the same day
from the same commit adds `-2`, then `-3`.

Results files are committed (approved on #9), so every quoted number has a file behind it. A
run with `dirty: true` is not a baseline and is not committed.

The file holds ids and numbers only: no question text, no answer text and no corpus text.

`python -m src.eval.diagnose` writes its own files, in another format, to
`eval/results/diagnostics/`, named and committed by the same rules
([retrieval.md](retrieval.md#cut-diagnosis), approved on #24).

```json
{
  "format": 1,
  "run": {"started": "2026-11-13T15:04:05+07:00", "command": "python -m src.eval.run", "seconds": 41.3},
  "configuration": {...},
  "scores": {"EVAL-001": {...}, "...": {}},
  "breakdown": {"form": {...}, "tax_type": {...}, "added_in": {...}},
  "latency": {...},
  "cost": {...},
  "items": [{...}]
}
```

**`configuration`**

| Key | Value |
|---|---|
| `commit` | full hash of `HEAD` |
| `dirty` | true when tracked files differ from `HEAD` (`git diff HEAD`); untracked files do not count |
| `diff_sha256` | `sha256` of the output of `git diff HEAD` when dirty, else null |
| `eval_set` | `path`, `version`, `sha256` of the set file |
| `index` | from the index folder's `manifest.json`: `model`, `revision`, `chunks_sha256`, `chunk_count`, `bm25_tokenizer`, `chunking`, `input_limit`, `truncated` (each null for a manifest without it) |
| `pipeline` | `stages` (`["retrieval"]`), `rewrite` (`none`), `top_k`, then the retriever's `Fusion.config()`: `rrf_k`, `candidates`, `keyword_weight`, `vector_weight`, `per_article` |
| `bootstrap` | `resamples` 1000, `seed` 0, `level` 0.95 |
| `versions` | `python` and the installed `bm25s`, `chromadb`, `numpy`, `pyvi`, `sentence-transformers`, `torch`, `underthesea`; null for one not installed |
| `machine` | `os` (`platform.platform()`), `cpu` (`platform.processor()`), `cpu_count`, `ram_gb` (null when it cannot be read) |

**`scores`**, one entry per EVAL id, EVAL-001 to EVAL-008:

| Key | Value |
|---|---|
| `name` | what is scored, as in the table above |
| `value` | the score, or null when not run |
| `n` | items scored |
| `interval` | `[low, high]`, or null |
| `target` | the threshold, or null |
| `passes` | true, false or null |
| `reason` | only when not run: `no generation stage` |

**`breakdown`**: `form`, `tax_type` and `added_in` (keyed by the version as text, `"1"`, `"2"`),
each a mapping from the group to
`{"n": …, "EVAL-001": …, "EVAL-007": …}`.

**`latency`**: `n`, `median_s`, `p95_s`, `stages`, `scope`, and `nfr006`
(`{"median_s": 10, "p95_s": 20}`).

**`cost`**: `average_usd`, `note`, and `nfr007` (`{"average_usd": 0.01}`).

**`items`**, one per question and turn, in run order:

| Key | Value |
|---|---|
| `id` | `q01`, or `c01.2` for a turn |
| `kind` | `question` or `turn` |
| `conversation`, `turn` | the conversation id and the turn number, or null for a question |
| `tax_type`, `form` | as in the set |
| `added_in` | the set version that added the item, as in the set; 1 when the set gives none |
| `answerable` | false when the set gives `unanswerable` |
| `expected` | expected article ids, in provision order, once each; empty when unanswerable |
| `hits` | per hit: `chunk_id`, `article` (its parent), `found_by`, `score` |
| `unresolved` | the reason of each unresolved reference; not its text, which is question text |
| `recall`, `context_precision` | the item's scores, or null when unanswerable |
| `latency_s` | per stage |
| `tokens` | `{"input": …, "output": …}` |
| `cost_usd` | the item's cost |

## The summary

Printed after the file is written:

- the file's path, and `DIRTY: uncommitted changes, not a baseline` when dirty;
- one line per EVAL id: the id and its name, its value to 3 decimals with `n` and its
  interval, its target, and `PASS` or `FAIL`; `not run (no generation stage)` instead for those
  not run;
- the breakdown;
- latency: median and p95 with the scope, against NFR-006;
- cost: the average per item with the note, against NFR-007;
- with `--generate`, the generation counts, the answerable not-found ones followed by
  `(by recall@k: <all> all, <some> some, <none> none)`, then `AC-015: <passes> pass, <fails> fail,
  <retrieval misses> retrieval misses, of <applies>; <uncited> uncited: GREEN` (or `NOT GREEN`,
  or `nothing applies`), and the failing ids.

## Comparing two runs

`--compare <file>` reads an earlier results file. If its eval set `sha256` differs, the command
prints `different eval sets: scores are not comparable` and exits with 2. Otherwise it prints:

- per EVAL id with a value in both runs: old, new and the change, to 3 decimals; for
  EVAL-001, EVAL-005 and EVAL-007 also `paired [low, high]`, the paired 95% bootstrap interval
  of the change (approved on #10). Over the items scored in both runs, the per-item differences
  new − old are resampled as under *Interval*, with the same seed: the two runs score the same
  items, so this interval is far narrower than the two runs' own intervals side by side;
- with `--comparisons n` above 1, after each `paired` interval also `bonferroni [low, high]`:
  the same per-item differences resampled 10,000 times with seed 0, at level 1 − 0.05 / n
  (approved on #25). Several variants compared with one baseline make a win by chance more
  likely, and this interval corrects for that;
- every item whose recall dropped: its id, old and new recall.

## Generation stage

`--generate` adds context assembly, generation and the judge ([answer.md](answer.md)), approved
on #15. Without it the run is retrieval only and calls no API. With it, on eval set v2, a run
makes 240 generation calls and at most 184 judge calls, within the free tier's 500 requests
per day (ADR-0003).

- The pipeline is `AnswerPipeline(retriever, answerer)`: `generates` is true, `answer(question)`
  retrieves, assembles and generates, and `retrieve(question)` only retrieves. Its stages are
  `retrieval`, `assembly`, `generation`.
- Standalone questions are generated; conversation turns are only retrieved until #19 adds the
  rewrite (`generated: false`). The warm-up call only retrieves.
- After its answer, each answerable standalone question that is not answered `not_found` is
  judged: one call, `Judge.judge(question, key_facts, answer, amended)`, with `amended` the ids
  AC-015 asks about that no notice covers (below), empty when there are none. Unanswerable questions and not-found
  answers get no judge call.

**Scores** with `--generate`:

| ID | Over | Value |
|---|---|---|
| EVAL-002 | the sentences with at least one id, in the answers to answerable standalone questions | the share whose `cited` verdict is true: the sum over items of `cited_supported` over the sum of `cited_sentences`; `n` is that sum of sentences |
| EVAL-003 | the answers to answerable standalone questions, not-found answers excluded | per answer, `supported / sentences`; the mean; `n` is the answers |
| EVAL-006 | the answers to answerable standalone questions | 1 when `correct`, 0 otherwise, a not-found answer included as 0; the mean |
| EVAL-004 | the unanswerable standalone questions generated | 1 when `not_found`, 0 otherwise; the mean (approved on #16) |
| EVAL-008 | | not run: `not scored` |

EVAL-002's interval resamples items, as under *Interval*, and takes the ratio of the sums in each
resample (`ratio_bootstrap_interval`), since sentences of one answer are not independent. The
three judged scores carry `judge`, the judge's model, and the summary prints
`judge <model>, not hand-checked` after them: a judged score stands only with the hand-check
recorded beside it in *Generation runs*. EVAL-004 reads `not_found` alone: it needs no judge,
carries no `judge` and is scored without one.

EVAL-004 does not see the cost of saying not found too often, which falls on answerable
questions. The `not_found` key under `generation` counts those, split by the item's recall@k,
so that a not-found answer with every expected article retrieved shows apart from one whose
articles were not retrieved.

**`generation`**, a top-level key after `cost`, null without `--generate`:

| Key | Value |
|---|---|
| `answered` | items generated |
| `not_found` | `{"answerable": …, "answerable_of": …, "answerable_by_recall": {"all": …, "some": …, "none": …}, "unanswerable": …, "unanswerable_of": …}`, standalone questions answered not found, and how many were generated; `answerable_by_recall` splits the answerable ones by recall@k: 1 (`all`), above 0 and below 1 (`some`), 0 (`none`) |
| `flagged` | `{"ids": …, "items": …}`: citation ids not in the context, and the items with one (AC-009) |
| `judge` | `{"model": …, "calls": …, "cost_usd": …}` |

**`ac015`**, a top-level key after `generation`, null without `--generate`. AC-015 looks at an
answerable standalone question's **amended chunks**: chunks with an `amended_by` entry, taken
from each provision as follows (narrowed on #15, choice B2):

- a **listed clause**, a provision whose `chunk` is a clause chunk (`:K<k>`, not `:K0`): that
  chunk;
- a **listed article**, any other provision (an article named whole, or a clause of an unsplit
  article, whose `chunk` is the article's): every chunk of the article.

With no amended chunk, AC-015 does not apply (`ac015` null). It is **in the context** when one
of the amended chunks is in an article passage of its context; otherwise the question is a
**retrieval miss**, and AC-015 does not judge it (acceptance.md, choice 5A). In the context,
AC-015 **asks about** each amended chunk there of a listed clause, and each amended chunk there
of a listed article that the answer **cites**: an id of the answer equals the chunk's id
(`[n]` for a whole-article or `:K0` chunk, `[n.k]` for a clause chunk), or is `[n]` when the
chunk's id is `[n.k]`, or is an `[n.k]` when the chunk's id is `[n]`. When it asks about none,
the question is **uncited**: AC-015 does not apply to it.

An asked id is **noticed** when one of the answer's amendment notices (its last `notices`
sentences, answer.md) has it as its first id, the link's `target`. A notice is built from the
link line, so it always says the provision was amended: the judge is not asked about a noticed
id (approved on #15, choice 1). The ids passed to the judge are the asked ids not noticed.
`says_amended` is true when every asked id is noticed; otherwise it is the judge's. The question
**passes** when its answer is not not-found, cites an id in the context whose passage holds an
`amended_by` source of those chunks (the amending passage of that chunk, or the article passage
that contains it), and `says_amended` is true (choice 6A).

| Key | Value |
|---|---|
| `applies`, `retrieval_misses`, `uncited`, `passes`, `fails` | item ids, in run order; `applies` holds the retrieval misses and the questions asked about, not the uncited |
| `green` | true when `fails` is empty and `applies` is not; null when nothing applies |

**Latency and cost with `--generate`.** An item's `latency_s` has `retrieval`, `assembly` and
`generation`; the judge is not part of answering and is recorded apart. Median and p95 are over
the generated items only; the scope reads `full pipeline, dev laptop`. An item's `tokens` and
`cost_usd` are its generation call's; the average is over the generated items, against NFR-007.

**Items** get these keys, after `cost_usd`, null for an item not generated:

| Key | Value |
|---|---|
| `generated` | true when the item went through generation |
| `context_tokens`, `dropped` | `Context.tokens` and `Context.dropped` |
| `not_found` | as in answer.md |
| `sentences`, `cited_sentences` | sentences, and those with at least one id |
| `citations`, `flagged` | the distinct ids, in first-use order, and those not in the context |
| `notices` | `Answer.notices`: the amendment notices among `sentences` |
| `cited_supported`, `supported` | sentences whose `cited`, and whose `supported`, verdict is true; null when not judged |
| `correct` | the verdict's; false for a not-found answer to an answerable question; null for an unanswerable one |
| `ac015` | null when the question has no amended chunk; else `{"in_context", "asked", "noticed", "cites_amending", "says_amended", "passes"}`: `asked` the ids AC-015 asks about, null for a retrieval miss and empty for an uncited question; `noticed` the asked ids a notice covers, in the order of `asked`; the last four null for both |
| `judge_latency_s`, `judge_tokens`, `judge_cost_usd` | the judge call's; null when not judged |

**`configuration.pipeline`** with `--generate` adds, after the fusion settings: `model`,
`prices` (`{"read", "input", "output"}`), `prompts` (`{"answer": sha256, "judge": sha256}` of
the prompt files), `judge_model`, `context_budget`, and `google_genai`, the installed version.

**Answers file.** The results file carries no answer text. The answers go to
`data/eval-answers/<results file stem>.jsonl`, gitignored, since they
quote the corpus (NFR-003): one line per generated item, `{"id", "passages": [{"id", "text"}], "sentences":
[{"text", "citations"}], "flagged", "not_found", "amended", "verdict"}`, `amended` being the ids
passed to the judge as `amended` (empty when not judged), `verdict` `{"cited",
"supported", "facts", "contradicts", "says_amended", "correct"}` or null.

**Resume.** Each generated item is appended to `data/eval-answers/progress.jsonl` as it
finishes, after a first line `{"commit", "eval_set_sha256", "pipeline"}`. A `--generate` run
that finds the file with the same first line reuses its items and generates the rest; with
another first line it stops with exit code 2 and names the file. The file is removed once the
results file is written. `run.resumed_items` counts the items reused.

**Hand-check** (acceptance.md: at least 20 claims and 20 judgments per run).

```bash
python -m src.eval.handcheck sheet data/eval-answers/<file>.jsonl   # writes the sheet and its key
python -m src.eval.handcheck score eval/<file>-handcheck.me.md      # prints the agreement
```

- `sheet <answers file> [--set eval/questions.yaml] [--out eval]` writes
  `<out>/<answers file stem>-handcheck.me.md` and `<out>/<answers file stem>-handcheck-key.me.md`,
  both untracked. It reads the questions and key facts from the set file's `questions` directly.
  With one `random.Random(0)`, it samples 20 sentences from the judged answers' sentences that
  have an id in the context, then 20 judged answers, then 20 answers whose verdict has a
  `says_amended` that is not null; all of them when there are fewer. An answers file without
  `amended` (before #15's choice 1) gives no answer of the last kind.
- The sheet has one section per sentence, `## S<n> · <id> · sentence <i>` (i counted from 1 in
  its answer): the question, the sentence with its ids, its cited passages, the whole context
  in a folded `<details>` block, and the blank lines `Cited supports:` and `Context supports:`.
  Then one section per answer, `## A<n> · <id>`: the question, the key facts, the answer, and the
  blank line `Correct:`. Then one section per answer graded on `says_amended` (AC-015, choice 3
  on #15), `## M<n> · <id>`: the question, the line `**Amended provisions.**` with the record's
  `amended` ids as `[1.25], [3]`, the whole context in a folded `<details>` block, the answer,
  the rule `Yes when the answer says that each of these provisions was amended, replaced or
  repealed.`, and the blank line `Says amended:`. No verdict is on the sheet.
- The key is a JSON block: `{"S1": {"id", "sentence", "cited", "supported"}, "A1": {"id",
  "correct"}, "M1": {"id", "says_amended"}, …}`, the judge's verdicts.
- `score <sheet>` reads `yes` or `no`, in any case, after each of those labels, skips blank
  ones, and prints `cited: <agreeing> of <graded>`, then `supported:`, `correct:` and
  `says_amended:`.

**Generation runs.** Every clean `--generate` run is listed in a table under *Baseline*: its
file, EVAL-002, EVAL-003, EVAL-006, the not-found counts, AC-015, and the hand-check agreement.

## Baseline

The first clean run, recorded on #9: `eval/results/2026-11-13-1d257ea.json`. Eval set v1, commit
`1d257ea`, retrieval only with each turn as written, k = 8, RRF 60, 50 candidates, bge-m3
`5617a9f6`, syllable BM25, on the dev laptop (i7-10610U, 16 GB RAM, CPU only).

| Metric | Value | n | 95% interval | Target |
|---|---|---|---|---|
| EVAL-001 recall@8 | 0.633 | 39 | 0.539–0.727 | ≥ 0.80, not met |
| EVAL-005 recall@8, follow-up turns, no rewrite | 0.575 | 10 | 0.333–0.817 | ≥ 0.70, not met |
| EVAL-007 context precision@8 | 0.676 | 39 | 0.571–0.773 | ≥ 0.60, met |

- Recall is 0.771 on `reference` questions and 0.572 on `plain` ones.
- Retrieval latency is 0.35 s median and 0.69 s p95.
- 48 of the 111 expected articles are missed: 9 of the 15 amending articles and 39 of the 96
  base articles. Of the missed ones, 18 rank 9–20 and 16 rank 21–50 when 50 hits are
  retrieved; 14 are not among them.

EVAL-001's target was confirmed at 0.80 after this baseline, approved on #9. It is not revised
again; the gap is the work of the retrieval issues.

Since #12 the chunks are split over 1,600 tokens, not 800. At that threshold, commit `ab4a8fa`,
otherwise as above: EVAL-001 0.678 [0.592, 0.764], EVAL-005 0.575 [0.333, 0.817], EVAL-007
0.686 [0.590, 0.780], in `eval/results/2026-11-14-ab4a8fa-3.json`
([chunk-schema.md](chunk-schema.md), *Threshold experiment*). The table above stays the record
of the first baseline.

Since #25 the top 8 holds one hit per article. At commit `e2051f7`, otherwise as at `ab4a8fa`:
EVAL-001 0.714 [0.634, 0.791], EVAL-005 0.600 [0.333, 0.867], EVAL-007 0.701 [0.607, 0.793], in
`eval/results/2026-11-15-e2051f7.json` ([retrieval.md](retrieval.md), *Fusion tuning*).

The eval set v2 baseline, recorded on #26: `eval/results/2026-11-15-b0cced1.json`. Eval set v2
(184 answerable standalone questions, 29 answerable follow-up turns), commit `b0cced1`, otherwise
as at `e2051f7`. A v2 score is not compared paired with a v1 score.

| Metric | Value | n | 95% interval | Target |
|---|---|---|---|---|
| EVAL-001 recall@8 | 0.769 | 184 | 0.715–0.813 | ≥ 0.80, not met |
| EVAL-005 recall@8, follow-up turns, no rewrite | 0.494 | 29 | 0.339–0.644 | ≥ 0.70, not met |
| EVAL-007 context precision@8 | 0.678 | 184 | 0.626–0.728 | ≥ 0.60, met |

- Recall is 0.714 on the 39 version 1 questions and 0.783 on the 145 added in version 2.
- Recall by tax type runs from 0.500 (`household`) to 0.933 (`cit`).
- The 184 questions expect 164 distinct articles; version 1 expects 73 of them.
- The 10 reference questions that name the wrong document (answered by the right one, step 2)
  score 0.600: q65, q72, q74, q84, q122, q185, q212, q213, q240, q242.
- Retrieval latency is 0.38 s median and 0.90 s p95 over 292 items.

### Generation runs

Clean `--generate` runs, on the dev laptop, judge `gemini-3.5-flash-lite`. The hand-check is the
owner's, blind, on the sheet `python -m src.eval.handcheck sheet` writes.

| File | EVAL-002 | EVAL-003 | EVAL-004 | EVAL-006 | Not found | AC-015 | Hand-check |
|---|---|---|---|---|---|---|---|
| `eval/results/2026-11-16-6cbf23a.json` | 0.855 [0.782, 0.909], n = 345 | 0.990 [0.977, 1.000], n = 155 | not scored | 0.380 [0.310, 0.457], n = 184 | 29 of 184 answerable, 55 of 56 unanswerable | 3 pass, 30 fail, 15 retrieval misses, of 48: not green | cited 20 of 20, supported 20 of 20, correct 20 of 20 |
| `eval/results/2026-11-17-4091435.json` | 0.868 [0.799, 0.921], n = 394 | 0.985 [0.971, 0.995], n = 151 | not scored | 0.402 [0.332, 0.473], n = 184 | 33 of 184 answerable, 55 of 56 unanswerable | 15 pass, 12 fail, 15 retrieval misses, of 42; 6 uncited: not green | not hand-checked |
| `eval/results/2026-11-18-271adae.json` | 0.774 [0.700, 0.850], n = 376 | 0.961 [0.940, 0.981], n = 154 | 0.982 [0.946, 1.000], n = 56 | 0.402 [0.332, 0.473], n = 184 | 30 of 184 answerable (by recall@8: 8 all, 14 some, 8 none), 55 of 56 unanswerable | 21 pass, 7 fail, 15 retrieval misses, of 43; 5 uncited: not green | cited 19 of 20, supported 19 of 20, correct 16 of 20, says_amended 4 of 6 |

`2026-11-16-6cbf23a`, eval set v2, commit `6cbf23a`, retrieval as at `b0cced1`:

- EVAL-002 and EVAL-006 miss their targets (≥ 0.90, ≥ 0.80); EVAL-003 meets its (≥ 0.90).
- The judge called 7 of the 20 sampled answers correct, and the owner agreed on all 20: the low
  EVAL-006 is the answers', not the judge's.
- All 20 sampled sentences were judged `cited` and `supported`, so the hand-check does not yet
  show the judge catching an unsupported sentence.
- 72 citation ids not in the context, in 39 items, were flagged (AC-009).
- Latency is 2.28 s median and 4.84 s p95 over 240 items; cost is 0.0049 USD per item, the
  judge's 155 calls 0.7651 USD.
- The keys changed 109 times, 106 on a 503 and 3 on a 429; 7 attempts failed on every key and
  succeeded after the backoff.

`2026-11-17-4091435`, eval set v2, commit `4091435` (amendment notices, choice A2; AC-015 narrowed,
choice B2), retrieval as at `b0cced1`:

- Not hand-checked: #15 closed without a further run (approved on #15), so its judged scores
  stand on the judge alone; the hand-checked run is `6cbf23a`.
- 18 answers got one amendment notice each.
- AC-015, of 42 to which it applies, against 48 at `6cbf23a` (6 now uncited): 15 pass, 15
  retrieval misses, 12 fail. The 12 fails, counted from ids and citations only:
  - 3 (q04, q196, q203) carry a notice covering the asked provision and were judged
    `says_amended: false`; from `f4889e6` a noticed provision is said amended without the judge;
  - 1 (q16) cites the amended clause and its source in one sentence without saying it was
    amended; from `f4889e6` it gets a notice (choice 2');
  - 6 (q01, q37, q117, q197, q199, q221) do not cite the listed amended clause;
  - 2 (q56, q200) are not found.
- **AC-015 is not met at the close of #15.** The changes of `f4889e6` were not measured by a run;
  the 8 fails of the last two kinds stay with them, as answer quality and retrieval, which
  neither the notice nor the scope of AC-015 changes. They are left to a later issue.
- 67 citation ids not in the context, in 32 items, were flagged (AC-009).
- Latency is 2.69 s median and 10.24 s p95 over 240 items; cost is 0.0050 USD per item, the
  judge's 151 calls 0.7477 USD.
- The keys changed 150 times, all on a 503; 6 attempts failed, 5 on every key and 1 on a read
  timeout, and succeeded after the backoff.

`2026-11-18-271adae`, eval set v2, commit `271adae` (not-found rule narrowed, choice 2A on #16;
notices and AC-015 as changed by `f4889e6`, choices 1, 2' and 3 on #15), retrieval as at
`b0cced1`, the same index and model as `4091435`:

- EVAL-004 meets its target; the narrower rule left the 55 of 56 unchanged. Not found on
  answerable questions went from 33 to 30 against `4091435`: 7 answered now, 4 not found now, 26
  not found in both. That is within the variation of one prompt across two runs (29 at
  `6cbf23a`, 33 at `4091435`), so it is not attributed to the rule (a risk named on #16).
- EVAL-002 fell from 0.868 to 0.774 and EVAL-003 from 0.985 to 0.961. Over the 147 items judged
  in both runs, the model's sentences, notices left out, went from 0.881 to 0.786: a paired
  change of −0.095 [−0.202, +0.006], items resampled as under *Interval*, so not shown to
  differ. The notices were judged `cited` false on 12 of 32, against 7 of 18 at `4091435`.
- Hand-check, the owner's, blind:
  - `cited` and `supported` 19 of 20; the one disagreement (S9) is a notice the judge called
    unsupported and the owner supported. 2 of the 20 sampled sentences were notices;
  - `correct` 16 of 20; in all 4 disagreements the judge called incorrect an answer the owner
    called correct, so EVAL-006 may understate the answers. At `6cbf23a` all 20 agreed;
  - `says_amended` 4 of 6, the first such check; in the 2 disagreements (q56, q117) the judge
    said amended and the owner did not. Both fail AC-015 anyway, since neither cites the
    amending passage, so the AC-015 counts stand.
- AC-015, of 43, against 42 at `4091435`: 21 pass, 15 retrieval misses, 7 fail, and 5 uncited.
  The 7 fails, from ids and citations only:
  - 2 (q01, q37) cite the amending passage but ask about a provision no notice covers, judged
    not said to be amended;
  - 4 (q56, q117, q197, q199) do not cite the amending passage;
  - 1 (q200) is not found.
  AC-015 is not met; the fails are answer quality and retrieval, as at `4091435`.
- 85 citation ids not in the context, in 39 items, were flagged (AC-009), against 67 in 32.
- Latency is 4.12 s median and 8.07 s p95 over 240 items; cost is 0.0050 USD per item, the
  judge's 154 calls 0.7548 USD.
- The keys changed 61 times, 60 on a 503 and 1 on a 429; 3 attempts failed, 2 on every key and
  1 on a dropped connection, and succeeded on the retry.
