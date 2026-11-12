---
status: draft
updated: 2026-11-12
owner: HieuQuang4438
---

# Chunk schema

What `python -m src.chunking` writes to `data/chunks/`, from the parsed documents in
`data/processed/`. The rules behind it are FR-CORE-002 and
[ADR-0001](../adr/0001-chunk-by-legal-structure.md); the approach is the approved comment on #2.

Every file is JSON Lines, UTF-8, `\n` line endings, ordered by document id (numeric) and then by
position in the document. Nothing in it depends on when it was built: two builds from the same
`data/processed/` are byte-identical (NFR-005).

## `chunks.jsonl` — the chunker's chunks

One record per chunk. The enrich step (below) adds to these records; its output is what gets
indexed.

| Field | Type | Example | Meaning |
|---|---|---|---|
| `id` | string | `439827:D5:K1` | `<doc_id>:D<article>` for a whole article, `:K<clause>` appended for a clause, `:K0` for the intro of a split article |
| `doc_id` | string | `439827` | luatvietnam.vn numeric id, from the source URL (`-<id>-d1.html`) |
| `chapter` | string or null | `Chương I` | latest chapter heading before the article; null when the document has no chapters |
| `chapter_title` | string or null | `QUY ĐỊNH CHUNG` | the all-caps title line right after that chapter heading, as written in the source; null when there is no chapter or the line after the heading is not all caps (reported as `missing_chapter_title`) |
| `article` | string | `5` | article (Điều) number |
| `clause` | string or null | `1` | clause (Khoản) number; `"0"` for an intro chunk; null for a whole article |
| `parent_id` | string | `439827:D5` | id of the article in `articles.jsonl`; equals `id` for a whole-article chunk |
| `text` | string | `1. Mã số thuế thực hiện theo …` | the chunk's own text, without the `Điều N. …` heading line |

The context header (#3), effective date (#4) and amendment links (#5) are added to this record
by the enrich step.

## `data/enriched/chunks.jsonl` — what gets indexed

The approach is the approved comment on #3. Written by `python -m src.enrich`
from `data/chunks/chunks.jsonl`, `data/chunks/articles.jsonl` and the documents' metadata in
`data/processed/`. One record per chunk, same order and same ids as `data/chunks/chunks.jsonl`,
byte-identical across two builds from the same inputs (NFR-005).

| Field | Type | Example | Meaning |
|---|---|---|---|
| every field of `chunks.jsonl` | | | unchanged; `text` is still the chunk's own text, with no header |
| `header` | string | see below | where the chunk sits, built from metadata only — FR-CORE-003 |

**Header form.** Two bracketed groups, separated by one space:

```text
[<loai_van_ban> <so_hieu> — <trich_yeu>] [Chương <n>. <chapter_title> > Điều <n>. <title> > Khoản <n>]
```

- The first group names the document. `loai_van_ban`, `so_hieu` and `trich_yeu` come from the
  document's metadata, `trich_yeu` in full and unchanged. A document missing any of the three
  is an error naming its `doc_id`, not a header with a gap.
- The second group names the position, its parts joined by ` > `:
  - `Chương <n>. <chapter_title>` — left out when `chapter` is null; `Chương <n>` alone when
    `chapter_title` is null.
  - `Điều <n>. <title>` — `title` from the article record; `Điều <n>` alone when it is empty.
  - `Khoản <n>` — only on a clause chunk, with the source's clause number: a repeated number
    (id suffix `.2`) shows the number as written. A `:K0` intro chunk and a whole-article
    chunk have no `Khoản` part.
- Sections (Mục) are not in the header.

Examples, from Circular 90/2026/TT-BTC and Law 09/2026/QH16 (no chapters):

```text
[Thông tư 90/2026/TT-BTC — Quy định về đăng ký thuế] [Chương I. QUY ĐỊNH CHUNG > Điều 5. Cấu trúc mã số thuế > Khoản 1]
[Luật 09/2026/QH16 — Sửa đổi, bổ sung một số điều của Luật Thuế thu nhập cá nhân, …] [Điều 4. Sửa đổi, bổ sung quy định về xe có gắn động cơ dưới 24 chỗ chạy bằng pin …]
```

(`…` marks text shortened here only; the header carries both in full.)

**Indexed text** is `header + "\n" + text`, returned by `src.enrich.indexed_text(chunk)`. It is
not stored: the indexes call that function, and a citation shows `text` alone.

**Token limit.** The split threshold (`MAX_TOKENS`, 800) counts the chunk text only, not header +
text, so the header changes no split. `python -m src.enrich` prints the largest header and the
largest header + text in bge-m3 tokens, against bge-m3's 8,192-token input limit. On the
corpus (2026-11-12): largest header 234 tokens (`440483:D93:K1`, a long article title), largest
header + text 3,363 (`404357:D27:K3`).

## `articles.jsonl` — full articles for context assembly

One record per article, split or not. Not indexed; read by context assembly (#14) to show a
clause's whole parent article.

| Field | Type | Meaning |
|---|---|---|
| `id` | string | `<doc_id>:D<article>`, the `parent_id` of its chunks |
| `doc_id`, `chapter`, `chapter_title`, `article` | | as in `chunks.jsonl` |
| `title` | string | the heading text after `Điều N.`, e.g. `Cấu trúc mã số thuế` |
| `text` | string | the whole article body, heading line excluded |

## `issues.jsonl` — what the chunker could not settle

One record per problem found in a source document. The chunker never repairs silently; it
reports here and on the console.

| Field | Meaning |
|---|---|
| `doc_id`, `article` | where |
| `kind` | `duplicate_heading` — the same article heading twice in a row; the longer copy is kept · `article_gap` — article numbers not 1, 2, 3, … · `clause_numbering` — a split article's clauses not 1, 2, 3, … · `unbalanced_quotes` — a “ never closed, or opened mid-line and not closed on its line; `article` is where it opened · `mismatched_quotes` — a “ closed with a straight `"` on its line; treated as closed, reported because the source is mistyped · `hidden_heading` — a `Điều N.` line read as quoted, numbered above the last kept article: a quotation probably swallowed the end of the document · `unexpected_last_article` — the last kept article's title has none of `hiệu lực`, `thi hành`, `chuyển tiếp`, `tổ chức thực hiện` · `missing_chapter_title` — the line after a chapter heading is not all caps, so the chapter has no title; `article` is the first article of that chapter, or empty if it has none |
| `detail` | human-readable specifics |

## Rules, in the order they apply

- **Article text** starts at the first `Điều N.` heading and ends at the first of: `Nơi nhận:`,
  a line of underscores, `Luật này được Quốc hội…`, a `Phụ lục` heading, or a `Mẫu số …` form
  heading. Heading block, preamble and everything after the end are not chunked.
- **Chapter and section headings** (`Chương I`, `Mục 1`) and the all-caps title line after them
  are left out of article text; the chapter label and its title line are kept
  on every following article.
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
