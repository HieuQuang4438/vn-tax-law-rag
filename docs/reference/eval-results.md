---
status: draft
updated: 2026-11-14
owner: HieuQuang4438
---

# Eval results

What `python -m src.eval.run` does and the results file it writes. It runs the eval set
([eval-set.md](eval-set.md)) through the pipeline and scores the metrics defined in
[acceptance.md](../product/acceptance.md#measurement-definitions). The rules are FR-CORE-015,
AC-011 and AC-016. The approach is the approved comment on #9.

Today the pipeline is retrieval only ([retrieval.md](retrieval.md)). The metrics that need an
answer are written as not run until generation exists (#15, #16).

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
| `--compare` | none | an earlier results file to compare with |

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
| EVAL-002, EVAL-003, EVAL-004, EVAL-006, EVAL-008 | | not run: `no generation stage` |

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

**Breakdown.** EVAL-001 and EVAL-007 again, per `form` and per `tax_type`, each group with its
own n. Only groups with at least one item are written.

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

```json
{
  "format": 1,
  "run": {"started": "2026-11-13T15:04:05+07:00", "command": "python -m src.eval.run", "seconds": 41.3},
  "configuration": {...},
  "scores": {"EVAL-001": {...}, "...": {}},
  "breakdown": {"form": {...}, "tax_type": {...}},
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
| `index` | from the index folder's `manifest.json`: `model`, `revision`, `chunks_sha256`, `chunk_count`, `bm25_tokenizer`, `chunking` (null for a manifest without it) |
| `pipeline` | `stages` (`["retrieval"]`), `rewrite` (`none`), `top_k`, `rrf_k`, `candidates` |
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

**`breakdown`**: `form` and `tax_type`, each a mapping from the group to
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
- every item whose recall dropped: its id, old and new recall.

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
