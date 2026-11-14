---
status: draft
updated: 2026-11-15
owner: HieuQuang4438
---

# Retrieval

What `src.retrieval` returns for a question, and how it is found. It reads the indexes in
`data/index/` ([index.md](index.md)), the enriched chunks ([chunk-schema.md](chunk-schema.md)) and
the documents' metadata in `data/processed/`. The rules are FR-CORE-007, FR-CORE-008, NFR-002 and
[ADR-0002](../adr/0002-hybrid-retrieval-without-rerank.md). The approach is the approved comment
on #8.

Two steps run for every question:

1. **References.** Explicit references to a document or an article ("Điều 9 Luật 48/2024") are
   found by pattern and resolved from metadata (FR-CORE-007).
2. **Hybrid search.** The whole question goes to the keyword index and the vector index. Their
   ranked lists are merged by reciprocal rank fusion (FR-CORE-008).

Resolved articles take the first slots, and the fused list fills the rest, up to k = 8. There
is no reranker (ADR-0002). Dates and `amended_by` are not used here. Context assembly (#14)
reads them from the enriched chunks.

## Interface

```python
from src.retrieval import Retriever

retriever = Retriever.load()                  # the index's model from the local cache, once per process
result = retriever.retrieve("Điều 9 Luật 48/2024 áp dụng cho hộ kinh doanh không?")
result.hits         # list[Hit], at most k, best first
result.unresolved   # list[Unresolved], in question order
```

| Name | What it is |
|---|---|
| `Retriever(index_dir, enriched_dir, processed_dir, embedder)` | Reads both indexes, the chunks and the documents' metadata. The embedder embeds the question, as at build time. |
| `Retriever.load(data_dir=Path("data"), embedder=None, index_dir=None, enriched_dir=None)` | The same, from `enriched_dir`, `data_dir/processed` and `index_dir`, which are `data_dir/enriched` and `data_dir/index` when not given. With no embedder, the model and input limit the index's manifest names are loaded offline by `src.index.load_embedder` (approved on #11); a manifest without `input_limit` gets the model's maximum. |
| `Retriever.retrieve(question, k=TOP_K)` | A `Retrieval` for one question. |
| `Retriever.rankings(question)` | A `Rankings` for one question: the orders `retrieve` cuts from, uncut, for *Cut diagnosis* (approved on #24). |
| `Rankings` | `keyword: list[str]`, every chunk with a BM25 score above 0, best first; `vector: list[str]`, every chunk, best first; `final: list[str]`, every reference slot, then the fused list; `unresolved: list[Unresolved]`, as `retrieve` reports them. Each list is in the order `retrieve` uses. |
| `Retrieval` | `hits: list[Hit]`, `unresolved: list[Unresolved]`. |
| `Hit` | `chunk_id: str`, `found_by: tuple[str, ...]`, `score: float`. |
| `Unresolved` | `text: str`, the reference as written in the question; `reason: str`, one of the reasons below. |
| `find_references(question)` | The `Reference`s in the question, in order, before any corpus lookup. |
| `Reference` | `text`, `kind`, `number`, `article`, `clause`, as described under *References*. |
| `rrf(lists, constant=RRF_K)` | Reciprocal rank fusion of ranked lists of chunk ids, as described under *Fusion*. |
| `IndexNotReadyError` | Raised by the constructor when the index cannot be used, as described under *Loading*. |
| `TOP_K`, `RRF_K`, `CANDIDATES` | 8, 60, 50. |

`retrieve(question, k).hits` are always the first k of `rankings(question).final`, for every k
and every question, including one that names more than k articles: the slots are filled in
question order, so a smaller cut keeps the first of them. The keyword list is the first
`CANDIDATES` of `Rankings.keyword`, and the vector list the first `CANDIDATES` of
`Rankings.vector`.

`found_by` lists every way the chunk was found, in this order: `reference` (it fills a reference
slot), `keyword` (it is in the keyword list), `vector` (it is in the vector list), `document` (it
is in the document list). `score` is the chunk's fused score. A reference slot whose chunk is in
no list has score 0.

## Loading

The constructor checks that the index fits what it is asked to search. It raises
`IndexNotReadyError`, with a message naming the problem and `python -m src.index`, when:

- `index_dir/manifest.json` is missing, which means the build is missing or did not finish;
- the manifest's `chunks_sha256` is not the `sha256` of `enriched_dir/chunks.jsonl`, which means
  the index is older than the chunks;
- the manifest's `model` or `revision` differs from the embedder's, which means the question
  would be embedded by another model than the chunks;
- the manifest's `bm25_tokenizer` is not one of `syllable`, `underthesea`, `pyvi`.

`Retriever.load` with no embedder raises the same error, before loading any model, when the
manifest is missing or its `model` is not in `EMBEDDING_MODELS` ([index.md](index.md)).

The model is loaded once, by `Retriever.load`, and every `retrieve` call reuses it. Nothing goes
to the network: the model comes from the local cache, as at build time ([index.md](index.md)),
and both indexes are local.

## References

`find_references` reads the question in Unicode NFC, ignoring case, and finds two kinds of
reference: documents and articles.

**Documents.**

| Written | Example | Resolves to |
|---|---|---|
| a full number | `48/2024/QH15`, `252/2026/NĐ-CP` | the document with that `so_hieu` |
| a kind word, optionally `số`, then a number | `Luật 48/2024`, `Luật số 48/2024`, `Nghị định 68/2026`, `NĐ 68/2026`, `Thông tư số 89/2026/TT-BTC`, `TT 89/2026` | the document whose `so_hieu` is that number, or starts with it followed by `/` |
| the name of a base law | `Luật Thuế GTGT`, `Luật Quản lý thuế` | that law, from the alias list below |

- The kind words are `Luật`, `Nghị định` and `NĐ`, and `Thông tư` and `TT`. A kind word must
  match the document's `loai_van_ban`: `Luật` a Luật, `Nghị định`/`NĐ` a Nghị định,
  `Thông tư`/`TT` a Thông tư.
- A number with no kind word and no suffix (`68/2026`) is not a reference. It may be a month
  ("tháng 12/2025"). A number that is part of a longer one (`12/2025` in `15/12/2025`) is not a
  reference either.
- A base-law name followed by `số <number>` is one reference, by that number.

The alias list, fixed. Every name may be written with or without `Thuế` after `Luật`, and in
either case:

| Name | Law |
|---|---|
| `Luật Thuế giá trị gia tăng`, `Luật Thuế GTGT` | 48/2024/QH15 |
| `Luật Thuế thu nhập cá nhân`, `Luật Thuế TNCN` | 109/2025/QH15 |
| `Luật Thuế thu nhập doanh nghiệp`, `Luật Thuế TNDN` | 67/2025/QH15 |
| `Luật Thuế tiêu thụ đặc biệt`, `Luật Thuế TTĐB` | 66/2025/QH15 |
| `Luật Quản lý thuế` | 108/2025/QH15 |

A name resolves to the base law, never to a law that amends it. A law name not in the list is
not a reference, and the question still goes to hybrid search.

**Articles.** `Điều <n>`, `khoản <m> Điều <n>` or `Điều <n> khoản <m>`, where a number may carry
a letter (`Điều 5a`, `khoản 1a`). A point in front (`điểm a khoản 2 Điều 9`) is read as its
clause. An article is bound to one document:

1. the document reference right after it, optionally after `,`, `của`, `tại` or `thuộc`
   ("Điều 9 Luật 48/2024", "khoản 2 Điều 9 của Nghị định 68/2026");
2. otherwise, the document reference right before it, optionally after `,`
   ("Nghị định 68/2026, Điều 5");
3. otherwise, the only document the question names ("Theo Nghị định 68/2026 thì … quy định tại
   Điều 5 là gì?");
4. otherwise, none. The article is reported `no_document`. Carrying a document over from an
   earlier turn is #19's work.

A document with no article bound to it is a document reference on its own.

A `Reference` holds the reference as written: `text` is the span of the question it covers,
`kind` is `Luật`, `Nghị định`, `Thông tư` or None, `number` is the number as written (the law's
`so_hieu` for a name), and `article` and `clause` are the numbers as written, or None.

**Resolution.** Against the corpus, compared without regard to case:

| Case | Outcome |
|---|---|
| the number matches no document | unresolved, `unknown_document` |
| a partial number matches more than one document of the kind written (of any kind, when no kind word is written) | unresolved, `ambiguous` |
| the kind word contradicts the document's type ("Thông tư 68/2026", a decree) | unresolved, `kind_mismatch` |
| the article is not in the document | unresolved, `no_article` |
| an article bound to no document | unresolved, `no_document` |
| a document with no article | resolved to the document: a document list, below |
| an article | resolved to the article: a reference slot, below |

A clause missing from a split article resolves as if no clause were named. An unresolved
reference changes nothing else: the question is searched as if it were not there.

## Hybrid search

Three ranked lists of chunk ids, each at most `CANDIDATES` (50) long:

- **Keyword list.** The question's tokens, by the tokenizer the index was built with
  (`bm25_tokenizer` in its manifest, [index.md](index.md)), scored by the BM25 index.
  Tokens not in the vocabulary are dropped. Chunks scoring 0 are not in the list. Equal scores
  keep `chunks.jsonl` order. The full `so_hieu` of each document referenced without an article
  is added to the tokens: a user writes `68/2026`, the index holds the token `68/2026/nđ-cp`.
- **Vector list.** The question embedded by the same model as the chunks, compared by cosine
  similarity with every chunk's vector. The vectors are read from the Chroma collection once,
  at load, and the comparison is exact over all chunks rather than through Chroma's approximate
  search: at 1,286 chunks it takes under a millisecond, equal scores keep `chunks.jsonl` order,
  and the Chroma files are not held open while the retriever lives.
- **Document list.** Only when the question references a document without an article. Every
  chunk of the documents so referenced, ranked by `rrf` of their keyword rank and vector rank
  among those chunks alone. Chunks from other documents can still win over them, so a wrong
  document in the question does not hide the right answer.

**Fusion.** `rrf(lists)` scores each chunk as the sum, over the lists that hold it, of
1 / (`RRF_K` + rank), rank counted from 1. It returns `(chunk_id, score)` pairs, best first. Ties
keep the order in which chunks first appear when the lists are read rank by rank: rank 1 of
every list in turn, then rank 2, and so on. The lists are passed in the order keyword, vector,
document. All lists weigh the same. `RRF_K` 60, `CANDIDATES` 50 and the equal weights are
starting values, changed only through a recorded experiment (#8).

## The k hits

1. **Reference slots.** One per resolved article reference, in question order. Its chunk is:
   - for a named clause of a split article, that clause's chunk;
   - for an article that is not split, the article chunk, whether or not a clause is named;
   - for a split article with no clause named, its chunk ranked best in the fused list, or its
     first chunk in `chunks.jsonl` if none of its chunks is in the fused list.

   A chunk already in a slot does not take a second one. Context assembly (#14) adds the whole
   parent article, so one slot brings in the article.
2. **Fused hits.** The fused list, in order, skipping chunks already in a slot, until there are
   k hits.

When more than k articles are referenced, the first k take the slots. The same question against
the same index always gives the same result.

## Acceptance

**AC-007.** For each eval-set question and conversation turn with `form: reference`, every
article it names is among the parents of its hits. This is the article the question names,
which is not always the expected provision: some questions name the wrong one on purpose. The
corpus test checks it two ways:

- independently of the resolver: when the text holds exactly one corpus document number and
  some `Điều <n>` that exists in that document, that article is among the hits' parents;
- through the resolver: on an answerable question or turn, every reference is resolved, or is
  reported `unknown_document` because it names a document outside the corpus.

**AC-012.** The median `retrieve` time over every question and conversation turn of the eval
set is under 2 s on the dev laptop, with the model loaded beforehand and no network. The test
prints the median and the 95th percentile, and both are recorded here with the machine.

## Measured

On the dev laptop (i7-10610U, 16 GB RAM, CPU only; torch 2.15.0+cpu, sentence-transformers
6.3.0), eval set v1, the index of 1,923 chunks, the code that closes #8, 2026-11-13:

- **AC-012.** 66 questions and turns, one warm-up call not timed: median 0.448 s, 95th
  percentile 0.775 s. Nearly all of it is embedding the question.
- **AC-007.** 13 items have `form: reference`. 4 name an article of a corpus document by number,
  and all 4 articles are retrieved. The other 9 name a document without an article and get a
  document list. No reference in an answerable item is unresolved.

## Cut diagnosis

Of the expected articles missing from the top 8, how many are retrieved but ranked below the
cut, and how many no list retrieves at all? The question is #24. The approach is the approved
comment on #24. ADR-0002 reopens the reranker question only if the misses are ranked below the cut.

```bash
python -m src.eval.diagnose      # eval/questions.yaml, data/, writes to eval/results/diagnostics/
```

Its options are `--set`, `--data`, `--enriched`, `--index` and `--out`, as for
`python -m src.eval.run` ([eval-results.md](eval-results.md#running-it)). `--out` defaults to
`eval/results/diagnostics`.

**What it does.** It loads the eval set and the retriever as the runner does, then calls
`rankings` once for every standalone question and every conversation turn, in file order, each
turn as written (`rewrite: none`). `TOP_K` stays 8. The measurement only reads further down
`final`. Nothing is timed.

**Scored items.** The items EVAL-001 and EVAL-005 score: answerable standalone questions
(`standalone`), and answerable follow-up turns (`follow_up`). They are reported apart.

**Recall at each cut.** For k = 8, 12, 16, 20, 30 and 50 (`CUTS`), recall@k on the parent
articles of the first k of `final`, as defined in [acceptance.md](../product/acceptance.md#measurement-definitions),
with the bootstrap interval of the runner. Recall cannot drop as k grows, since each cut holds
the smaller ones. recall@8 equals the runner's EVAL-001 and EVAL-005 on the same index.

**Misses.** A miss is an expected article of a scored item that is not among the parents of the
first 8 of `final`. For each miss:

| Field | Meaning |
|---|---|
| `article` | the article id |
| `final_rank` | the rank, from 1, of its best chunk in `final`; null if no chunk of it is in `final` |
| `keyword_rank` | the rank of its best chunk in `Rankings.keyword`; null if no chunk of it scores above 0 |
| `vector_rank` | the rank of its best chunk in `Rankings.vector` |
| `place` | `below_cut` if `final_rank` is 9 to 50; `beyond_50` if it is above 50; `not_in_pool` if it is null |
| `lists` | the lists whose first `CANDIDATES` hold a chunk of it, out of `keyword` and `vector`, in that order |
| `split` | true if the article has more than one chunk |

An item with an unresolved reference keeps its reasons, as in the runner's items, and its misses
are counted apart as `unresolved`, since such a miss may come from reference lookup rather than
from the ranking.

**Decision rule** (approved on #24). Over the misses of the standalone questions: if at least
half are `below_cut`, the verdict is `ranking`, and the next issue tunes the fusion. Otherwise
it is `retrieval`, and the next issue changes the embedding, BM25 or the chunks. The verdict is
`borderline` when moving two misses across the line would change it, and is then reported, not
acted on. With no misses there is no verdict: `result` is null. The follow-up turns are reported
but do not decide.

**The file.** One JSON file per run, named and never overwritten as the runner's results file
is ([eval-results.md](eval-results.md#the-results-file)), committed under the same rule. It holds
ids and numbers only.

```json
{
  "format": 1,
  "run": {"started": "…", "command": "python -m src.eval.diagnose", "seconds": 30.1},
  "configuration": {…},
  "recall": {"standalone": {"8": {"value": …, "n": …, "interval": […]}, "12": {…}}, "follow_up": {…}},
  "misses": {"standalone": {…}, "follow_up": {…}},
  "verdict": {"result": "ranking", "below_cut": …, "misses": …, "borderline": false},
  "items": [{…}]
}
```

- `configuration` is the runner's, with `pipeline` holding `top_k` 8, `rrf_k`, `candidates`,
  `rewrite: none`, `depth` 50 and `cuts`.
- `misses` gives, per group, `articles` (the number of misses), `below_cut`, `beyond_50`,
  `not_in_pool`, the share `below_cut` / `articles` as `share_below_cut`, `lists` as counts of
  `both`, `keyword`, `vector` and `neither`, `split` and `unresolved`.
- `items` holds one entry per scored item, in run order, with `id`, `kind`, `conversation`,
  `turn`, `expected`, `recall` (per cut), `misses` (the table above) and `unresolved` (reasons only).

**The summary.** Printed after the file is written: the path, and `DIRTY` as the runner prints
it; recall at each cut per group; the miss counts per group; the verdict.

Not run yet.
