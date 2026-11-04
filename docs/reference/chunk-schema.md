---
status: draft
updated: 2026-11-04
owner: HieuQuang4438
---

# Chunk schema

What `python -m src.chunking` writes to `data/chunks/`, from the parsed documents in
`data/processed/`. The rules behind it are FR-CORE-002 and
[ADR-0001](../adr/0001-chunk-by-legal-structure.md); the approach is the approved comment on #2.

Every file is JSON Lines, UTF-8, `\n` line endings, ordered by document id (numeric) and then by
position in the document. Nothing in it depends on when it was built: two builds from the same
`data/processed/` are byte-identical (NFR-005).

## `chunks.jsonl` — what gets indexed

One record per chunk.

| Field | Type | Example | Meaning |
|---|---|---|---|
| `id` | string | `439827:D5:K1` | `<doc_id>:D<article>` for a whole article, `:K<clause>` appended for a clause, `:K0` for the intro of a split article |
| `doc_id` | string | `439827` | luatvietnam.vn numeric id, from the source URL (`-<id>-d1.html`) |
| `chapter` | string or null | `Chương I` | latest chapter heading before the article; null when the document has no chapters |
| `article` | string | `5` | article (Điều) number |
| `clause` | string or null | `1` | clause (Khoản) number; `"0"` for an intro chunk; null for a whole article |
| `parent_id` | string | `439827:D5` | id of the article in `articles.jsonl`; equals `id` for a whole-article chunk |
| `text` | string | `1. Mã số thuế thực hiện theo …` | the chunk's own text, without the `Điều N. …` heading line |

The context header (#3), effective date (#4) and amendment links (#5) are added to this record
by later steps.

## `articles.jsonl` — full articles for context assembly

One record per article, split or not. Not indexed; read by context assembly (#14) to show a
clause's whole parent article.

| Field | Type | Meaning |
|---|---|---|
| `id` | string | `<doc_id>:D<article>`, the `parent_id` of its chunks |
| `doc_id`, `chapter`, `article` | | as in `chunks.jsonl` |
| `title` | string | the heading text after `Điều N.`, e.g. `Cấu trúc mã số thuế` |
| `text` | string | the whole article body, heading line excluded |

## `issues.jsonl` — what the chunker could not settle

One record per problem found in a source document. The chunker never repairs silently; it
reports here and on the console.

| Field | Meaning |
|---|---|
| `doc_id`, `article` | where |
| `kind` | `duplicate_heading` — the same article heading twice in a row; the longer copy is kept · `article_gap` — article numbers not 1, 2, 3, … · `clause_numbering` — a split article's clauses not 1, 2, 3, … · `unbalanced_quotes` — a “ never closed, or opened mid-line and not closed on its line; `article` is where it opened · `mismatched_quotes` — a “ closed with a straight `"` on its line; treated as closed, reported because the source is mistyped · `hidden_heading` — a `Điều N.` line read as quoted, numbered above the last kept article: a quotation probably swallowed the end of the document · `unexpected_last_article` — the last kept article's title has none of `hiệu lực`, `thi hành`, `chuyển tiếp`, `tổ chức thực hiện` |
| `detail` | human-readable specifics |

## Rules, in the order they apply

- **Article text** starts at the first `Điều N.` heading and ends at the first of: `Nơi nhận:`,
  a line of underscores, `Luật này được Quốc hội…`, a `Phụ lục` heading, or a `Mẫu số …` form
  heading. Heading block, preamble and everything after the end are not chunked.
- **Chapter and section headings** (`Chương I`, `Mục 1`) and the all-caps title line after them
  are skipped; the chapter label is kept on every following article.
- **Quotations**: a line that starts inside “…” cannot open an article or a clause, so quoted
  amending text stays in the clause that quotes it. Only a quotation that opens at the start
  of a line runs on to later lines; one opened mid-line and not closed on its line ends there
  and is reported as `unbalanced_quotes` (decided on #2: such a quote in document 439780 had
  hidden 16 of its 25 articles). A straight `"` closes a `“` opened earlier on the same line
  (reported as `mismatched_quotes`), never one carried over from an earlier line.
- **Split**: an article whose body is over `MAX_TOKENS` (800) bge-m3 tokens is cut at its
  clause lines (`N. `). An article over the limit with no clause lines stays one chunk, so a
  chunk can be over 800 tokens. Text before clause 1 becomes a `:K0` chunk when it is over
  `MIN_INTRO_TOKENS` (100); otherwise it is only in the article record.
- **Repeated clause number** in one article: the second gets `:K<n>.2`, so ids stay unique;
  it is also reported as `clause_numbering`.
- **Tokens** are counted with the bge-m3 tokenizer, without special tokens, using the
  `tokenizers` library rather than `transformers` (same tokenizer file, no PyTorch).
