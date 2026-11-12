---
status: draft
updated: 2026-11-12
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
- **Offline.** The model is loaded from the local Hugging Face cache only (`HF_HUB_OFFLINE=1`,
  `local_files_only=True`), so a build makes no network request. If the cache lacks that
  revision, the build stops with `ModelNotCachedError`, whose message names the one-time
  download command: `hf download BAAI/bge-m3 --revision 5617a9f61b028005a4858fdac845db406aefb181`.
  Approved on #6.
- **Collection.** One collection, `chunks`, with cosine distance. One record per chunk:
  `id` = chunk id, the embedding of its indexed text, metadata `{"doc_id": <doc_id>}`. No
  document text is stored. Chroma's anonymized telemetry is turned off.
- **Rebuilt from scratch.** Every build deletes `chroma/` and writes the collection again from
  the vector cache, so its content depends only on the chunk file, never on earlier builds.

## Vector cache — `embeddings/`

Embedding the whole corpus takes about 95 minutes on the dev laptop (ADR-0002), so vectors are
cached by what was embedded:

- One folder per model and revision: `embeddings/BAAI--bge-m3@<revision>/`, holding
  `keys.json` (a JSON list of `sha256` hex digests of the indexed text, sorted ascending) and
  `vectors.npy` (`float32`, one row per key, same order).
- A build embeds only the indexed texts whose digest is not in the cache, in the order they first
  appear in `chunks.jsonl`. An unchanged corpus embeds nothing; one changed chunk embeds one text;
  a different revision has its own folder and embeds everything.
- After a build the cache holds exactly the digests of the current indexed texts: vectors of text
  no longer in the corpus are dropped. Two chunks with the same indexed text share one vector.

## Keyword index — `bm25/`

- **Tokens.** `syllable`, the default until #10 decides: Unicode NFC, lowercase, split on
  whitespace, then strip from both ends of each token every character that is neither a letter
  nor a digit (`str.isalnum`); empty tokens are dropped. No stopword list. Diacritics stay, one-
  letter syllables stay, and a document number stays whole. Questions are tokenized by the same
  function.

  | Text | Tokens |
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
| `bm25_tokenizer` | `syllable` | the token rule above |
| `embedded` | `0` | indexed texts embedded by this build; the rest came from the cache |
| `seconds` | `41.7` | wall time of the whole build |
| `versions` | `{"bm25s": "0.3.16", …}` | installed versions of `bm25s`, `chromadb`, `sentence-transformers` and `torch` |

## Running it

```bash
python -m src.chunking   # data/processed/ -> data/chunks/
python -m src.enrich     # data/chunks/    -> data/enriched/
python -m src.index      # data/enriched/  -> data/index/
```

The first build embeds every chunk; its time is recorded in the manifest. Later builds embed
only what changed.
