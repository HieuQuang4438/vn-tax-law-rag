---
status: approved
updated: 2026-11-21
owner: HieuQuang4438
approved-by: peer
---

# Eval results

What `python -m src.eval.run` does and the results file it writes. It runs the eval set
([eval-set.md](eval-set.md)) through the pipeline and scores the metrics defined in
[acceptance.md](../product/acceptance.md#measurement-definitions). The rules are FR-CORE-015,
AC-011 and AC-016. The approach is the approved comment on #9; re-judging, comparing several
runs and the noise script, the approved comment on #37; EVAL-009 and re-scoring, the approved
comment on #39.

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
| `--rewrite` | `concat` (`DEFAULT_REWRITER`) | the rewriter of the conversation turns, one of `none`, `concat`, `fuse`, `llm` ([conversation.md](conversation.md), approved on #19); `llm` spends API quota, with or without `--generate` |
| `--compare` | none | an earlier results file to compare with |
| `--comparisons` | 1 | how many variants are compared with the same baseline; above 1, `--compare` also prints the Bonferroni interval (#25) |
| `--seed` | none | the seed of every model call of the run, answers, rewrites and judge alike (`LLM(seed=…)`, [answer.md](answer.md), *Seed*), recorded as `configuration.pipeline.seed`; without it the pipeline has no `seed` key, as before #37. Runs of one configuration take seeds 1 to k, and each arm of a comparison the same ones (approved on #37, *a seed per run*). It does not run with `--rejudge` |
| `--context-k` | `TOP_K` (8) | with `--generate`, how many hits the answer's context is assembled from: `AnswerPipeline` retrieves that many for each standalone question and the item's `hits` hold them all, while `recall` and `context_precision`, and so EVAL-001 and EVAL-007, still take the first `TOP_K` (approved on #36, choice 1A). Recorded as `configuration.pipeline.context_k`; without it the pipeline has no `context_k` key. Conversation turns are not generated and still retrieve `TOP_K`, so EVAL-005 is unchanged. It must be at least `TOP_K`, and it does not run without `--generate` |
| `--rescore` | none | an earlier `--generate` results file: score its stored verdicts again, with no API call (*Re-scoring a run*, #39) |
| `--rejudge` | none | an earlier `--generate` results file: judge its stored answers again instead of running the pipeline (*Re-judging a run*, #37); spends API quota |
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
4. runs every standalone question as written, then every conversation turn through the
   rewriter, in file order, a turn's earlier questions being those of the turns before it in its
   conversation (conversation.md, *In the eval run*);
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
| EVAL-002, EVAL-003, EVAL-004, EVAL-006, EVAL-008, EVAL-009 | | not run: `no generation stage`; with `--generate`, see *Generation stage* |

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

- **Latency** per item is per stage, in seconds, as the pipeline measures it: `retrieval`, the
  time of the `retrieve` call, or of the `fuse` call for two queries; and, with a rewriter other
  than `none`, for a follow-up turn `rewrite` first, the time of the rewrite, which for `llm` is
  its call's `latency_s`, so pacing waits and retries are not counted. The item's total is the
  sum of its stages.
- The run reports the median and the 95th percentile (`statistics.quantiles(totals, n=20)[-1]`)
  of the totals over every item, against NFR-006 (median ≤ 10 s, p95 ≤ 20 s). The scope is
  written with them: `retrieval only, dev laptop` when the stages hold no `generation`, while
  NFR-006 is measured with generation on the demo hardware.
- **Cost** per item is its input and output tokens and their price in USD: for a follow-up turn
  under `llm`, those of its rewrite call. With no LLM in the pipeline both token counts and the
  price are 0, and the run says `no LLM in the pipeline`.
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
  "run": {"started": "2026-11-13T15:04:05+07:00", "command": "python -m src.eval.run --generate --seed 1", "seconds": 41.3},
  "configuration": {...},
  "scores": {"EVAL-001": {...}, "...": {}},
  "breakdown": {"form": {...}, "tax_type": {...}, "added_in": {...}},
  "latency": {...},
  "cost": {...},
  "items": [{...}]
}
```

**`run`** holds `started`, the local start time; `command`, `python -m src.eval.run` followed by
the options the command was given, in the order given, whether they came from the shell
(`sys.argv`) or from a call to `main(argv)` (#40); and `seconds`, the run's wall time. A resumed
run's `seconds` covers its last segment only.

**`configuration`**

| Key | Value |
|---|---|
| `commit` | full hash of `HEAD` |
| `dirty` | true when tracked files differ from `HEAD` (`git diff HEAD`); untracked files do not count |
| `diff_sha256` | `sha256` of the output of `git diff HEAD` when dirty, else null |
| `eval_set` | `path`, `version`, `sha256` of the set file |
| `index` | from the index folder's `manifest.json`: `model`, `revision`, `chunks_sha256`, `chunk_count`, `bm25_tokenizer`, `chunking`, `input_limit`, `truncated` (each null for a manifest without it) |
| `pipeline` | `stages` (`["retrieval"]`, with `rewrite` first when the rewriter is not `none`), `rewrite` (the rewriter's name), `top_k`, then the retriever's `Fusion.config()`: `rrf_k`, `candidates`, `keyword_weight`, `vector_weight`, `per_article`; with `llm`, then `rewrite_model` and `rewrite_prompt`, the `sha256` of `src/prompts/rewrite.md` |
| `bootstrap` | `resamples` 1000, `seed` 0, `level` 0.95 |
| `versions` | `python` and the installed `bm25s`, `chromadb`, `numpy`, `pyvi`, `sentence-transformers`, `torch`, `underthesea`; null for one not installed |
| `machine` | `os` (`platform.platform()`), `cpu` (`platform.processor()`), `cpu_count`, `ram_gb` (null when it cannot be read) |

**`scores`**, one entry per EVAL id, EVAL-001 to EVAL-009:

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
| `rewritten` | for a turn, true when a query its rewriter gave differs from its question; null for a question |
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

## Comparing several runs

Approved on #37, step 3B. Each answer is one draw from the model, so a generation run repeated
k times and averaged per item gives a narrower interval than one run.

```bash
python -m src.eval.compare --old a1.json,a2.json --new b1.json,b2.json [--comparisons n]
```

`--old` and `--new` each take one or more results files, comma-separated: the runs of one
configuration. The command reads them and prints the comparison; it writes nothing. It exits
with 2, printing the reason, when two of the files have different eval sets
(`different eval sets: scores are not comparable`), or when the files of one side have different
`configuration.pipeline`, its `seed` aside (`the runs of one side differ in configuration`): the
runs of one side differ by their seeds and nothing else.

**Per item, per side**, over the side's runs:

| ID | Over | Item value |
|---|---|---|
| EVAL-001, EVAL-007 | standalone questions with a `recall` | the mean of `recall`, of `context_precision` |
| EVAL-005 | follow-up turns with a `recall` | the mean of `recall` |
| EVAL-006 | answerable standalone questions with a `correct` | the mean of `correct`, 1 or 0 |
| EVAL-009 | answerable standalone questions with a `key_facts` | the mean of the item's coverage, as under *Generation stage* |
| EVAL-004 | unanswerable standalone questions generated | the mean of `not_found`, 1 or 0 |
| EVAL-002 | answerable standalone questions | the sums of `cited_supported` and of `cited_sentences` over the runs where it was judged |
| EVAL-003 | answerable standalone questions | the mean of `supported / sentences` over the runs where it was judged with at least one sentence; none when there is no such run |

An item is paired when it has a value on both sides, `EVAL-003` aside: there every item of the
population is kept and a side's value is the mean over its items that have one. The items are
taken in the order of the first file of `--new`, so with one file per side EVAL-001, EVAL-005
and EVAL-007 get the same `paired` interval as `--compare`.

**Printed**: a first line naming the commits of each side, then one line per EVAL id with a value
on both sides: old, new and the change, to 3 decimals, then `paired [low, high]`, the paired
95% bootstrap interval of the change, and with `--comparisons n` above 1 `bonferroni [low,
high]`, as under *Comparing two runs*. A side's value is the mean of its paired items' values;
for EVAL-002 the ratio of the sums. The intervals resample the paired items as under *Interval*,
with the same seed, and take in each resample:

- EVAL-001, EVAL-004, EVAL-005, EVAL-006, EVAL-007: the mean of the per-item differences
  (`paired_bootstrap_interval`);
- EVAL-002: the new side's ratio of the sums minus the old side's
  (`paired_ratio_bootstrap_interval`);
- EVAL-003: the new side's mean over its items with a value minus the old side's
  (`paired_nanmean_bootstrap_interval`).

## Generation stage

`--generate` adds context assembly, generation and the judge ([answer.md](answer.md)), approved
on #15. Without it the run is retrieval only and calls no API. With it, on eval set v2, a run
makes 240 generation calls and at most 184 judge calls, within the free tier's 500 requests
per day (ADR-0003).

- The pipeline is `AnswerPipeline(retriever, answerer, context_k=None)`: `generates` is true,
  `answer(question)` retrieves `context_k` hits (`TOP_K` when none), assembles and generates, and
  `retrieve(question, earlier=())` rewrites and retrieves `TOP_K`. Its stages are `retrieval`,
  `assembly`, `generation`, with `rewrite` first when the rewriter is not `none`. Its config has
  `context_k` only when it is given (`--context-k`, #36).
- Standalone questions are generated; conversation turns are only retrieved, through the
  rewriter (`generated: false`; choice 2A on #19 leaves their generation out of the scores).
  The warm-up call only retrieves.
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
| EVAL-009 | the answers to answerable standalone questions with key facts | per answer, its **coverage**: 0 when `not_found` or `contradicts`, else `facts_stated / key_facts`; the mean (approved on #39); no target |

EVAL-002's interval resamples items, as under *Interval*, and takes the ratio of the sums in each
resample (`ratio_bootstrap_interval`), since sentences of one answer are not independent. The
three judged scores carry `judge`, the judge's model, and the summary prints
`judge <model>, not hand-checked` after them: a judged score stands only with the hand-check
recorded beside it in the run's file in [docs/experiments/](../experiments/README.md). EVAL-004 reads `not_found` alone: it needs no judge,
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
| `facts_stated`, `key_facts`, `contradicts` | the key facts the verdict marks as stated, the item's key facts, and the verdict's `contradicts`; for a not-found answer to an answerable question 0, the item's key facts and null; null for one not judged and for an unanswerable one (#39) |
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
  Then one section per answer, `## A<n> · <id>`: the question, the key facts, the answer, one
  blank line `Fact <n> stated:` per key fact, numbered from 1 (#39, choice 5A), and the blank line
  `Correct:`. Then one section per answer graded on `says_amended` (AC-015, choice 3
  on #15), `## M<n> · <id>`: the question, the line `**Amended provisions.**` with the record's
  `amended` ids as `[1.25], [3]`, the whole context in a folded `<details>` block, the answer,
  the rule `Yes when the answer says that each of these provisions was amended, replaced or
  repealed.`, and the blank line `Says amended:`. No verdict is on the sheet.
- The key is a JSON block: `{"S1": {"id", "sentence", "cited", "supported"}, "A1": {"id",
  "facts", "correct"}, "M1": {"id", "says_amended"}, …}`, the judge's verdicts.
- `score <sheet>` reads `yes` or `no`, in any case, after each of those labels, skips blank
  ones, and prints `cited: <agreeing> of <graded>`, then `supported:`, `facts:`, `correct:` and
  `says_amended:`. A `Fact <n> stated:` line is graded against the n-th of the key's `facts`.

## Re-judging a run

Approved on #37, step 1A. `--rejudge <results file>` judges the stored answers of an earlier
`--generate` run again, so a change of verdict is the judge's alone.

```bash
python -m src.eval.run --rejudge eval/results/2026-11-19-69f6ab4.json
```

- It reads the results file and its answers file, `<data>/eval-answers/<results file stem>.jsonl`,
  and loads the eval set as `--set` names it. It runs no retrieval and no generation. It exits
  with 2, printing the reason, with `--generate` or `--seed`, when the answers file is missing, or when the
  set's `sha256` is not the results file's.
- **Judged again**: each answers record whose `verdict` is not null, with the question and key
  facts of its item in the set, its `sentences`, its `flagged` ids, its passages joined as the
  context text (`"\n\n".join` of their `text`, as `Context.text`) and its `amended` ids. One
  judge call each, as under *Generation stage*. Every other record and item is copied unchanged.
- **The item** of each judged record gets the new `cited_supported`, `supported`, `correct`,
  `facts_stated`, `key_facts`, `contradicts`, `judge_latency_s`, `judge_tokens` and `judge_cost_usd`. Its `ac015`, when it has `asked` ids,
  gets `says_amended` true when `amended` is empty and the new verdict's otherwise, and `passes`
  again from it.
- **The new results file**: `scores` are the earlier file's, with EVAL-002, EVAL-003, EVAL-006 and
  EVAL-009 scored again from the items; `generation` and `ac015` computed again; `breakdown`, `latency`,
  `cost` and every other item key unchanged. `configuration` is the earlier file's with `commit`,
  `dirty`, `diff_sha256`, `versions` and `machine` of this run, and in `pipeline` the
  `judge_model` and the judge prompt's hash of this run. `run` adds `rejudge_of`, the earlier
  file's stem. The file is named and written as any results file, and the answers file beside
  it holds the copied records with the new `verdict`.
- The summary is printed; `--compare` works as for any run.

## Run-to-run noise

Approved on #37, step 0A. `scripts/noise.py` measures how much a rerun of one configuration moves
EVAL-006. It reads results files and their answers files, structured fields only, and prints
counts and numbers, never text.

```bash
python scripts/noise.py --runs a.json,b.json,c.json [--pairs old.json:new.json,...] [--answers data/eval-answers]
```

- **Same text**: two answers whose lists of sentence texts are equal character for character.
  **Same normalised text**: equal after dropping every punctuation character (Unicode category
  `P`) and collapsing whitespace to one space, trimmed.
- **For each two of `--runs`**: over the answerable standalone questions with a `correct` in
  both, how many have the same text and the same normalised text, how many changed verdict, and
  of those how many have the same text and the same normalised text; and the half-width of the
  paired EVAL-006 interval between the two (`paired_bootstrap_interval`).
- **Projection**, from three or more runs: σ̄², the mean over the items with a `correct` in every
  run of the sample variance (n − 1) of the item's `correct` across the runs; and for k = 1 to 5
  the projected half-width of a paired EVAL-006 change at k runs per arm,
  1.96 · √(2 σ̄² / (k n)), n those items.
- **For each `--pairs` entry**: binary EVAL-006 and the **share of key facts stated** side by side,
  each with its paired interval. The share of an answerable standalone question is the mean of its
  verdict's `facts`, 0 for a not-found answer, and none without a verdict otherwise.

**Runs per arm: k = 2**, set by
[2026-11-20-eval006-noise.md](../experiments/2026-11-20-eval006-noise.md) (#37): the smallest k
whose projected half-width of a paired EVAL-006 change is within ±0.03 (±0.028; one run gives
±0.040). A generation experiment runs each arm twice, `--seed 1` and `--seed 2`, and compares
them with `python -m src.eval.compare`. A retrieval-only run does not sample and needs one.
It decides on EVAL-009, with EVAL-006 guarded: EVAL-006 must not change with an interval
entirely below 0 (approved on #39, choice 4A).

## Re-scoring a run

Approved on #39, choice 6A. `--rescore <results file>` scores the stored verdicts of an earlier
`--generate` run again, with no API call, so a run from before a score existed gets it.

```bash
python -m src.eval.run --rescore eval/results/2026-11-19-69f6ab4.json
```

- It reads the results file, its answers file and the eval set as `--rejudge` does, and exits
  with 2 for the same reasons, and with `--generate`, `--seed` or `--rejudge`.
- **The item** of each answerable standalone question that was generated gets `facts_stated`,
  `key_facts` and `contradicts` as under *Generation stage*: from its record's `verdict` when it
  has one, as for a not-found answer when it is not found. Its keys are then in the order of
  *Generation stage*. Every other item key is unchanged.
- **The new results file**: `scores` are the earlier file's, with EVAL-002, EVAL-003, EVAL-006
  and EVAL-009 scored from the items, in EVAL id order; everything else is as under *Re-judging
  a run*, with `rescore_of` in `run` instead of `rejudge_of` and the judge's settings in
  `pipeline` unchanged. The answers file beside it is a copy of the earlier one.

**Generation runs.** Every clean `--generate` run is recorded in
[docs/experiments/](../experiments/README.md): its file, EVAL-002, EVAL-003, EVAL-006, the not-found counts, AC-015, and the hand-check agreement.

## Baseline

Every recorded run is a file in [docs/experiments/](../experiments/README.md): the
baselines of eval set v1 and v2, the follow-up rewriters and every generation run. Later
runs on eval set v2 compare against its baseline,
[2026-11-15-retrieval-baseline-eval-set-v2.md](../experiments/2026-11-15-retrieval-baseline-eval-set-v2.md),
and each says what it changed. The newest score of each metric against its target is in the
register's [*Standing scores*](../experiments/README.md#standing-scores).
