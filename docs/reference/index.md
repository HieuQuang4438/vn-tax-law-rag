---
status: approved
updated: 2026-11-21
owner: HieuQuang4438
approved-by: peer
---

# Index format

What `python -m src.index` writes to `data/index/`, from the enriched chunks in
`data/enriched/chunks.jsonl` ([chunk-schema.md](chunk-schema.md)). The rules behind it are
FR-CORE-006, NFR-001, NFR-005 and [ADR-0002](../adr/0002-hybrid-retrieval-without-rerank.md); the
approach is the approved comments on #6, and on #11 for the choice of embedding model.

Two indexes over the same chunk ids: a vector index (bge-m3 by default, in a local Chroma collection) and a
keyword index (`bm25s`). Each holds only chunk ids and what it needs to search. Everything else
about a chunk — header, text, dates, `amended_by` — is read back by id from
`data/enriched/chunks.jsonl`, which stays the one source of truth.

```text
data/index/
  manifest.json     what the indexes were built from; written last
  chroma/           vector index: Chroma persistent client, collection "chunks"
  bm25/             keyword index: bm25s files + ids.json
  embeddings/       vector cache, so a rebuild embeds only new or changed text
```

`data/index/` is gitignored, like everything under `data/` (NFR-003).

## What both indexes read

Every record of `data/enriched/chunks.jsonl`, in file order, as `header + "\n" + text` — the
indexed text specified on #3. A chunk's text alone is what a citation shows; it is never
indexed without its header.

**AC-006.** After a build, the set of ids in the Chroma collection, the set of ids in
`bm25/ids.json` and the set of ids in `data/enriched/chunks.jsonl` are the same set, and none of
the three holds an id twice.

## Vector index — `chroma/`

- **Model.** One of the pinned models below, through `sentence-transformers`, on CPU (NFR-001),
  chosen with `--model`; `BAAI/bge-m3` by default (approved on #11), kept after the
  [embedding experiment](../experiments/2026-11-14-embedding-model.md) and its
  [re-run on eval set v2](../experiments/2026-11-15-embedding-model-eval-set-v2.md). The table is
  `EMBEDDING_MODELS` in `src/chunking/tokens.py`. Vectors are normalized to unit length.

  | Model | Revision | Maximum input, tokens | Dimensions |
  |---|---|---|---|
  | `BAAI/bge-m3` | `5617a9f61b028005a4858fdac845db406aefb181` | 8,192 | 1,024 |
  | `AITeamVN/Vietnamese_Embedding` | `dea33aa1ab339f38d66ae0a40e6c40e0a9249568` | 2,048 | 1,024 |

- **Input limit.** `max_seq_length` is the model's maximum input, unless `--input-limit` sets a
  lower one. A text over the limit is cut by `sentence-transformers` to that many tokens, special
  tokens included, and only the cut text is embedded. At bge-m3's 8,192 no chunk is cut: the
  largest indexed text in the corpus is 3,363 tokens. A model not in the table, or a limit
  below 1 or above the model's maximum, stops with `ValueError` before anything is loaded or
  written.
- **Offline.** The model is loaded from the local Hugging Face cache only, so a build makes no
  network request (approved on #6). The snapshot folder of the pinned revision is resolved with
  `local_files_only=True` and the model is loaded from that folder. Setting `HF_HUB_OFFLINE=1` is
  not enough on its own: `huggingface_hub` reads it once, at import, and in a test run where an
  earlier test had imported it, loading by model name still opened 12 connections to the Hub.
  The revision is the model's entry in `EMBEDDING_MODELS`; bge-m3's is `EMBEDDING_REVISION`, the
  one the chunk splits are counted at ([chunk-schema.md](chunk-schema.md), *Tokens*), so both
  read the same snapshot. If the cache lacks that revision, loading stops with
  `ModelNotCachedError`, whose message names the one-time download command:
  `hf download <model> --revision <revision>`, for example
  `hf download BAAI/bge-m3 --revision 5617a9f61b028005a4858fdac845db406aefb181`.
- **Collection.** One collection, `chunks`, with cosine distance. One record per chunk:
  `id` = chunk id, the embedding of its indexed text, metadata `{"doc_id": <doc_id>}`. No
  document text is stored. Chroma's anonymized telemetry is turned off.
- **Rebuilt from scratch.** Every build deletes `chroma/` and writes the collection again from
  the vector cache, so its content depends only on the chunk file, never on earlier builds.

## Vector cache — `embeddings/`

Embedding the whole corpus takes most of the build, so vectors are cached by what was embedded.
Measured on the dev laptop (i7-10610U, 16 GB RAM, CPU only; torch 2.15.0+cpu,
sentence-transformers 6.3.0, batch size 4, the code that closes #6): the first build of 1,923 chunks
embedded 1,923 texts in 4,912.5 s (82 min); a rebuild with nothing changed took 2.0 s. ADR-0002
estimated about 95 minutes for 1,824 chunks.

- One folder per model and revision, `/` written as `--`: `embeddings/BAAI--bge-m3@<revision>/`,
  holding `keys.json` (a JSON list of keys, sorted ascending) and `vectors.npy` (`float32`, one
  row per key, same order).
- **Key.** The `sha256` hex digest of the indexed text, when the text fits the input limit. A
  text over the limit has the key `<digest>@<input limit>`, for example `9c1e…@2048`, because
  its vector depends on where it was cut. A text fits when the model's own tokenizer, special
  tokens included, gives it no more tokens than the limit. A text that fits gives the same vector
  at any limit, so changing the limit re-embeds only the texts over it (approved on #11).
- A build embeds only the indexed texts whose key is not in the cache, in the order they first
  appear in `chunks.jsonl`. An unchanged corpus embeds nothing; one changed chunk embeds one text;
  a different model or revision has its own folder and embeds everything.
- After a build the cache holds exactly the keys of the current indexed texts: vectors of text
  no longer in the corpus are dropped. Two chunks with the same indexed text share one vector.

## Keyword index — `bm25/`

- **Tokens.** One of three tokenizers, chosen at build time with `--tokenizer` and recorded
  in the manifest as `bm25_tokenizer`; questions are tokenized by the same one (approved on
  #10). `syllable` is the default, kept after #10 measured the two segmenters against it
  ([tokenizer experiment](../experiments/2026-11-13-bm25-tokenizer.md)).
  - `syllable`: Unicode NFC, lowercase, split on whitespace, then strip from both ends of each
    token every character that is neither a letter nor a digit (`str.isalnum`); empty tokens
    are dropped. No stopword list. Diacritics stay, one-letter syllables stay, and a document
    number stays whole.
  - `underthesea` and `pyvi`: word tokens from that Vietnamese word segmenter
    (`underthesea.word_tokenize`, `pyvi.ViTokenizer.tokenize`). The text is put in NFC and
    split on whitespace. A piece that holds a `/` once stripped as above, such as a document
    number or a date, is **protected**: it becomes one token exactly as `syllable` makes it,
    because both segmenters split `48/2024/QH15` into pieces. Each run of pieces between
    protected ones is joined with spaces and given to the segmenter, in its original case.
    Each word it returns is lowercased, its syllables joined with `_` (`kinh_doanh`), and
    stripped at both ends as above; empty words are dropped. Tokens keep the order of the
    text. Neither segmenter makes a network request; both are imported only when used and are
    pinned in `requirements-experiments.txt`.

  | Text | `syllable` tokens |
  |---|---|
  | `Luật số 48/2024/QH15,` | `luật` `số` `48/2024/qh15` |
  | `khoản 25 Điều 5.` | `khoản` `25` `điều` `5` |
  | `đ) Hộ kinh doanh` | `đ` `hộ` `kinh` `doanh` |
  | `– (trừ` | `trừ` |

- **Scoring.** `bm25s` defaults: method `lucene`, `k1` 1.5, `b` 0.75, as recorded in
  `params.index.json`.
- **Vocabulary.** Every distinct token of the corpus, sorted by code point, numbered from 0;
  `bm25s` appends its empty token last. The vocabulary is built here and passed to `bm25s`,
  because `bm25s` numbers its own vocabulary in set order, which changes with `PYTHONHASHSEED`:
  three runs on the same two documents gave three different `vocab.index.json`.
- **Files.** What `bm25s` saves (`params.index.json`, `vocab.index.json`,
  `data.csc.index.npy`, `indices.csc.index.npy`, `indptr.csc.index.npy`) plus `ids.json`, a JSON
  list of chunk ids: row *i* of the index is `ids.json[i]`, in `chunks.jsonl` order. No corpus
  copy is saved.
- **Deterministic.** Two builds from the same `chunks.jsonl` write byte-identical files in `bm25/`,
  whatever the hash seed (NFR-005). With the chunk and enrich steps already byte-identical across
  builds ([chunk-schema.md](chunk-schema.md)), this is the AC-013 check for the index.

## `manifest.json`

Written last: a build that stops early leaves no manifest, so a manifest means a complete index.

| Field | Example | Meaning |
|---|---|---|
| `model` | `BAAI/bge-m3` | embedding model |
| `revision` | `5617a9f6…` | model revision, in full |
| `dimension` | `1024` | vector length |
| `input_limit` | `8192` | the input limit the texts were embedded with (approved on #11) |
| `truncated` | `0` | indexed texts over the input limit, so cut when embedded |
| `chunks_sha256` | `9c1e…` | `sha256` of the bytes of `data/enriched/chunks.jsonl` |
| `chunk_count` | `1286` | records indexed, in each index |
| `bm25_tokenizer` | `syllable` | the tokenizer above: `syllable`, `underthesea` or `pyvi` |
| `bm25_seconds` | `3.2` | wall time to tokenize the corpus and write the keyword index |
| `embedded` | `0` | indexed texts embedded by this build; the rest came from the cache |
| `seconds` | `41.7` | wall time of the whole build |
| `versions` | `{"bm25s": "0.3.16", …}` | installed versions of `bm25s`, `chromadb`, `sentence-transformers` and `torch`, and of the segmenter when `bm25_tokenizer` is one |
| `chunking` | `{"max_tokens": 1600, "min_intro_tokens": 100}` | the split the chunks were cut with: the content of `params.json` in the enriched folder ([chunk-schema.md](chunk-schema.md)), or null when it has none (approved on #12) |

## Variants of the index

For an experiment, `python -m src.index` can read and write elsewhere:

```bash
python -m src.index --tokenizer pyvi --out data/index-pyvi
```

| Option | Default | Meaning |
|---|---|---|
| `--tokenizer` | `syllable` | the BM25 tokenizer, as above |
| `--model` | `BAAI/bge-m3` | the embedding model, one of `EMBEDDING_MODELS` (#11) |
| `--input-limit` | the model's maximum | the input limit, from 1 to the model's maximum (#11) |
| `--enriched` | `data/enriched` | the enriched chunks to index, for a variant chunked another way (#12) |
| `--out` | `data/index` | the index folder: `manifest.json`, `chroma/`, `bm25/` |
| `--cache` | `data/index/embeddings` | the vector cache |

The vector cache stays in `data/index/embeddings/` whatever `--out` is, unless `--cache` names
another one, so a tokenizer variant embeds nothing new. A variant with other chunks gets its
own copy of the cache instead, because a build prunes the cache to its own texts
([threshold experiment](../experiments/2026-11-14-chunk-threshold.md)). `build(enriched_dir, index_dir, embedder, tokenizer="syllable", cache_dir=None)`
takes the same choices; with no `cache_dir`, the cache is `index_dir/embeddings`. An unknown
tokenizer stops the build with `ValueError` before anything is written.

The model and the input limit come with the embedder:
`load_embedder(cache_dir=None, model=EMBEDDING_MODEL, input_limit=None)` loads a model of the
table offline, with the given limit or, when it is `None`, the model's maximum. An embedder has
`model`, `revision`, `input_limit`, `embed(texts)`, which returns one unit-length vector per
text, and `count_tokens(text)`, the model's token count of a text, special tokens included and
nothing cut, which decides whether a text fits the limit.

## Rebuilding from the cached pages

One command rebuilds everything from the pages cached in `data/raw/` (NFR-005, approved on #6):

```bash
python scripts/rebuild.py
```

It runs four steps in this order, each as its own process, from the repository root:

| Step | Command | Writes |
|---|---|---|
| parse | `python scripts/crawl_index.py` | `data/processed/` |
| chunk | `python -m src.chunking` | `data/chunks/` |
| enrich | `python -m src.enrich` | `data/enriched/` |
| index | `python -m src.index` | `data/index/` |

- A step that exits with an error stops the run; the later steps do not start, and the command
  exits with that step's code.
- The parse step records a failed document in `data/processed/_index.json` and goes on with
  the others. A rebuild must not quietly drop a document, so if any document's `status` there is
  not `ok`, the run stops before chunking, naming those documents, and exits with code 1.
- On a full cache the parse step makes no network request (AC-013). A page missing from the cache
  is fetched by the crawler, as in a normal crawl.
- Each step can still be run alone, with the command in the table.

The first build embeds every chunk; its time is recorded in the manifest. Later builds embed
only what changed.
