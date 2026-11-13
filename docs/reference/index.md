---
status: draft
updated: 2026-11-13
owner: HieuQuang4438
---

# Index format

What `python -m src.index` writes to `data/index/`, from the enriched chunks in
`data/enriched/chunks.jsonl` ([chunk-schema.md](chunk-schema.md)). The rules behind it are
FR-CORE-006, NFR-001, NFR-005 and [ADR-0002](../adr/0002-hybrid-retrieval-without-rerank.md); the
approach is the approved comments on #6.

Two indexes over the same chunk ids: a vector index (bge-m3 in a local Chroma collection) and a
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

- **Model.** `BAAI/bge-m3` through `sentence-transformers`, revision
  `5617a9f61b028005a4858fdac845db406aefb181`, on CPU (NFR-001). `max_seq_length` 8192, so no
  chunk is cut: the largest indexed text in the corpus is 3,363 tokens. Vectors are normalized
  to unit length (1,024 dimensions).
- **Offline.** The model is loaded from the local Hugging Face cache only, so a build makes no
  network request (approved on #6). The snapshot folder of the pinned revision is resolved with
  `local_files_only=True` and the model is loaded from that folder. Setting `HF_HUB_OFFLINE=1` is
  not enough on its own: `huggingface_hub` reads it once, at import, and in a test run where an
  earlier test had imported it, loading by model name still opened 12 connections to the Hub.
  If the cache lacks that revision, the build stops with `ModelNotCachedError`, whose message
  names the one-time download command:
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

- One folder per model and revision: `embeddings/BAAI--bge-m3@<revision>/`, holding
  `keys.json` (a JSON list of `sha256` hex digests of the indexed text, sorted ascending) and
  `vectors.npy` (`float32`, one row per key, same order).
- A build embeds only the indexed texts whose digest is not in the cache, in the order they first
  appear in `chunks.jsonl`. An unchanged corpus embeds nothing; one changed chunk embeds one text;
  a different revision has its own folder and embeds everything.
- After a build the cache holds exactly the digests of the current indexed texts: vectors of text
  no longer in the corpus are dropped. Two chunks with the same indexed text share one vector.

## Keyword index — `bm25/`

- **Tokens.** One of three tokenizers, chosen at build time with `--tokenizer` and recorded
  in the manifest as `bm25_tokenizer`; questions are tokenized by the same one (approved on
  #10). `syllable` is the default, kept after #10 measured the two segmenters against it
  (*Tokenizer experiment*, below).
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
| `chunks_sha256` | `9c1e…` | `sha256` of the bytes of `data/enriched/chunks.jsonl` |
| `chunk_count` | `1923` | records indexed, in each index |
| `bm25_tokenizer` | `syllable` | the tokenizer above: `syllable`, `underthesea` or `pyvi` |
| `bm25_seconds` | `3.2` | wall time to tokenize the corpus and write the keyword index |
| `embedded` | `0` | indexed texts embedded by this build; the rest came from the cache |
| `seconds` | `41.7` | wall time of the whole build |
| `versions` | `{"bm25s": "0.3.16", …}` | installed versions of `bm25s`, `chromadb`, `sentence-transformers` and `torch`, and of the segmenter when `bm25_tokenizer` is one |

## Variants of the index

For an experiment, `python -m src.index` can write elsewhere:

```bash
python -m src.index --tokenizer pyvi --out data/index-pyvi
```

| Option | Default | Meaning |
|---|---|---|
| `--tokenizer` | `syllable` | the BM25 tokenizer, as above |
| `--out` | `data/index` | the index folder: `manifest.json`, `chroma/`, `bm25/` |

The vector cache stays in `data/index/embeddings/` whatever `--out` is, so a variant embeds
nothing new. `build(enriched_dir, index_dir, embedder, tokenizer="syllable", cache_dir=None)`
takes the same choices; with no `cache_dir`, the cache is `index_dir/embeddings`. An unknown
tokenizer stops the build with `ValueError` before anything is written.

## Tokenizer experiment

Does word segmentation raise recall@8 over syllable tokens? Measured on #10, with the decision
rule fixed before the run: a segmenter replaces `syllable` only if the paired 95% bootstrap
interval of its EVAL-001 change lies entirely above 0 and AC-012 still holds.

Setup, the same for every run: commit `0e6024c`, eval set v1 (`d33b390e4894…`), bge-m3
`5617a9f6`, chunk threshold 800, k = 8, RRF 60, 50 candidates, `rewrite: none`, the dev laptop
(i7-10610U, 16 GB RAM, CPU only). Each variant was built with `--out data/index-<tokenizer>`
from the shared vector cache and scored with `python -m src.eval.run --index`.

| Tokenizer | Version | EVAL-001 | Paired change vs syllable | EVAL-005 | EVAL-007 | BM25 build | Retrieval median / p95 | Results file |
|---|---|---|---|---|---|---|---|---|
| `syllable` | — | 0.633 [0.539, 0.727] | — | 0.575 [0.333, 0.817] | 0.676 [0.571, 0.773] | 0.6 s | 0.40 / 0.78 s | `2026-11-13-0e6024c.json` |
| `underthesea` | 9.5.0 | 0.627 [0.519, 0.731] | −0.006 [−0.058, +0.038] | 0.542 [0.275, 0.808] | 0.674 [0.571, 0.765] | 44.0 s | 0.24 / 0.35 s | `2026-11-13-0e6024c-2.json` |
| `pyvi` | 0.1.1 | 0.601 [0.499, 0.702] | −0.032 [−0.083, +0.013] | 0.542 [0.275, 0.808] | 0.658 [0.557, 0.754] | 13.7 s | 0.43 / 0.56 s | `2026-11-13-0e6024c-3.json` |

- Neither segmenter meets the rule: both paired intervals include 0, and both means are lower.
  `syllable` stays, and no dependency is added to `requirements.txt`.
- Per question, underthesea raised recall on 3 questions and lowered it on 4; pyvi on 2 and 5.
- On `plain` questions underthesea gains slightly (0.581 against 0.572) and pyvi loses (0.544);
  on `reference` questions both lose (0.729 against 0.771).
- Retrieval latency varies by about 0.2 s between runs on this laptop, more than between
  tokenizers, so it does not separate them; every variant keeps AC-012.
- The segmenters stay available, so the experiment can be run again on a later eval set.

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
