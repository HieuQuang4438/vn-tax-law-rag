---
status: draft
updated: 2026-11-16
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
- cost: the average per item with the note, against NFR-007.

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
  AC-015 asks about (below). Unanswerable questions and not-found answers get no judge call.

**Scores** with `--generate`:

| ID | Over | Value |
|---|---|---|
| EVAL-002 | the sentences with at least one id, in the answers to answerable standalone questions | the share whose `cited` verdict is true: the sum over items of `cited_supported` over the sum of `cited_sentences`; `n` is that sum of sentences |
| EVAL-003 | the answers to answerable standalone questions, not-found answers excluded | per answer, `supported / sentences`; the mean; `n` is the answers |
| EVAL-006 | the answers to answerable standalone questions | 1 when `correct`, 0 otherwise, a not-found answer included as 0; the mean |
| EVAL-004 | | not run: `scored by #16` |
| EVAL-008 | | not run: `not scored` |

EVAL-002's interval resamples items, as under *Interval*, and takes the ratio of the sums in each
resample (`ratio_bootstrap_interval`), since sentences of one answer are not independent. The
three judged scores carry `judge`, the judge's model, and the summary prints
`judge <model>, not hand-checked` after them: a judged score stands only with the hand-check
recorded beside it in *Generation runs*.

**`generation`**, a top-level key after `cost`, null without `--generate`:

| Key | Value |
|---|---|
| `answered` | items generated |
| `not_found` | `{"answerable": …, "answerable_of": …, "unanswerable": …, "unanswerable_of": …}`, standalone questions answered not found, and how many were generated |
| `flagged` | `{"ids": …, "items": …}`: citation ids not in the context, and the items with one (AC-009) |
| `judge` | `{"model": …, "calls": …, "cost_usd": …}` |

**`ac015`**, a top-level key after `generation`, null without `--generate`. An answerable
standalone question **applies** when one of its provisions' chunks has an `amended_by` entry: the
provision's `chunk`, or, when that is not a chunk id (an article named whole in a split
article), every chunk of the article. It is **in the context** when one of those amended chunks
is in an article passage of its context; otherwise it is a **retrieval miss**, and AC-015 does
not judge it (acceptance.md, approved on #15, choice 5A). The ids passed to the judge are the
amended chunks' ids in the context: `[n]` for a whole-article or `:K0` chunk, `[n.k]` for a
clause chunk. The question **passes** when its answer is not not-found, cites an id in the
context whose passage holds an `amended_by` source of those chunks (the amending passage of
that chunk, or the article passage that contains it), and the judge's `says_amended` is true
(choice 6A).

| Key | Value |
|---|---|
| `applies`, `retrieval_misses`, `passes`, `fails` | item ids, in run order |
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
| `cited_supported`, `supported` | sentences whose `cited`, and whose `supported`, verdict is true; null when not judged |
| `correct` | the verdict's; false for a not-found answer to an answerable question; null for an unanswerable one |
| `ac015` | null when AC-015 does not apply; else `{"in_context", "cites_amending", "says_amended", "passes"}`, the last three null for a retrieval miss |
| `judge_latency_s`, `judge_tokens`, `judge_cost_usd` | the judge call's; null when not judged |

**`configuration.pipeline`** with `--generate` adds, after the fusion settings: `model`,
`prices` (`{"read", "input", "output"}`), `prompts` (`{"answer": sha256, "judge": sha256}` of
the prompt files), `judge_model`, `context_budget`, and `google_genai`, the installed version.

**Answers file.** The results file carries no answer text. The answers go to
`data/eval-answers/<results file stem>.jsonl`, gitignored, since they
quote the corpus (NFR-003): one line per generated item, `{"id", "passages": [{"id", "text"}], "sentences":
[{"text", "citations"}], "flagged", "not_found", "verdict"}`, `verdict` being `{"cited",
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
  have an id in the context, then 20 judged answers; all of them when there are fewer.
- The sheet has one section per sentence, `## S<n> · <id> · sentence <i>` (i counted from 1 in
  its answer): the question, the sentence with its ids, its cited passages, the whole context
  in a folded `<details>` block, and the blank lines `Cited supports:` and `Context supports:`.
  Then one section per answer, `## A<n> · <id>`: the question, the key facts, the answer, and the
  blank line `Correct:`. No verdict is on the sheet.
- The key is a JSON block: `{"S1": {"id", "sentence", "cited", "supported"}, "A1": {"id",
  "correct"}, …}`, the judge's verdicts.
- `score <sheet>` reads `yes` or `no`, in any case, after each of those labels, skips blank
  ones, and prints `cited: <agreeing> of <graded>`, then `supported:` and `correct:`.

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
