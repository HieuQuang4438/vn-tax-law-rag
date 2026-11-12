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

The approach is the approved comments on #3 (header), #4 (effective date) and #5 (amendment
links). Written by `python -m src.enrich` from `data/chunks/chunks.jsonl`,
`data/chunks/articles.jsonl` and the documents' metadata in `data/processed/`. One record per
chunk, same order and same ids as `data/chunks/chunks.jsonl`, byte-identical across two builds
from the same inputs (NFR-005). Next to it, `data/enriched/links.jsonl` holds every amendment
link and `data/enriched/issues.jsonl` reports what the enrich step could not settle.

| Field | Type | Example | Meaning |
|---|---|---|---|
| every field of `chunks.jsonl` | | | unchanged; `text` is still the chunk's own text, with no header |
| `header` | string | see below | where the chunk sits, built from metadata only — FR-CORE-003 |
| `effective_date` | string or null | `2026-01-01` | the date the chunk's provision takes effect, `YYYY-MM-DD`; null only when its document is reported as `no_effective_date` — FR-CORE-004 |
| `amended_by` | list | `[{"type": "amends", "source": "421739:D1"}]` | the in-corpus links whose target chunks include this chunk, one entry per `type` and `source` chunk id (two targets of one source inside this chunk give one entry; approved on #5), ordered by the source chunk's `effective_date`, then by source id; empty when nothing in the corpus changes the chunk — FR-CORE-005 |

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

### Effective date

Read from the document's own text, because the site keeps it behind a paywall.
Every chunk gets a date of its own document, amending documents included. An amended chunk
keeps its own date, because its text is still the original wording; the date of the new
wording is the amending chunk's own, reached through `amended_by` (#5, choice 6).

All of it is read from one article, the **effectiveness article**: the last article whose title
contains `hiệu lực thi hành` or `điều khoản thi hành`, ignoring case. A document with none is
reported as `no_effective_date`.

**The document's date.** The first line of that article stating
`<Luật|Nghị định|Thông tư> này có hiệu lực [thi hành] [kể] từ ngày <D>` gives the whole
document one date — "Luật này có hiệu lực thi hành từ ngày 01 tháng 7 năm 2026". Every chunk
takes it by default. `<D>` is:

- `<dd> tháng <mm> năm <yyyy>` or `<dd>/<mm>/<yyyy>` — that date;
- `ký ban hành` or `được thông qua` — the document's `ngay_ban_hanh`.

No such line, or `<D>` in another form: `no_effective_date`, and every chunk of the document
has `effective_date` null.

**Exception.** Another line of the same article that sets its own date for some provisions *of
this document*. It needs both:

- `có hiệu lực [thi hành] [kể] từ ngày <D>`;
- a reference to this document's provisions — `Điều <m>`, `khoản <n> Điều <m>`,
  `điểm <x> khoản <n> Điều <m>`, or a list `các điều <m>, <m> và <m>`. At least one reference
  in the line is followed by `[của] <Luật|Nghị định|Thông tư> này`; a bare reference beside it
  counts too ("Quy định tại Điều 13 và … Điều 26 của Luật này"), one followed by another
  document's name does not.

Not exceptions: a line about another document, even with a date ("Nghị định số 125/2020/NĐ-CP
… tiếp tục có hiệu lực thi hành kể từ ngày …"), and a line on a provision ceasing to apply
(`hết hiệu lực`).

An exception is **whole** or **partial**, depending on whether the line names the provision
itself or only part of what it says.

- **Whole** — the line names the provision, with nothing narrowing it: "Quy định tại Điều 13…"
  (108/2025), "Quy định tại các điều 1, 2 và 3 của Luật này…" (09/2026), "… và Điều 17 của Luật
  này…" (48/2024). All of that provision's text changes date, so every chunk of it takes `<D>`:
  - `Điều <m>` — every chunk of the article, whether or not it is split;
  - `khoản <n> Điều <m>` in a split article — that clause's chunk(s), `K<n>` (and `K<n>.2`).
- **Partial** — `<D>` holds for only part of a chunk's text, so no single date is right for the
  chunk:
  1. the line names a subject inside the provision: "Quy định **về mức doanh thu** … tại khoản
     25 Điều 5" (48/2024; clause 25 also covers assets, national reserve goods, fees and
     charges), "**việc sử dụng hóa đơn điện tử** của hộ kinh doanh … tại Điều 26" (108/2025;
     Article 26 covers e-invoices in general);
  2. the line names a clause of an article that is one chunk: `khoản 3 Điều 10`, with Article
     10 unsplit, leaves `D10` holding clause 3 and the others;
  3. the line names a point (`điểm`): a point is always smaller than a chunk, the smallest
     being a clause.

  The chunks keep the document's date, and the exception is reported as
  `partial_effective_date` with the line quoted, once per referenced provision. Giving them
  `<D>` would put a wrong date on the rest of their text; keeping the document's date and
  reporting it guesses nothing.

One line can hold both kinds. Law 48/2024, Article 18 clause 2: "Quy định về mức doanh thu …
tại khoản 25 Điều 5 của Luật này và Điều 17 của Luật này có hiệu lực thi hành từ ngày 01 tháng
01 năm 2026" — clause 25 of Article 5 is partial (`K25` keeps `2025-07-01`, reported); Article
17 is whole (`2026-01-01`).

Other lines of the article:

- **Application rules** — a line with `áp dụng [kể] từ kỳ tính thuế` or `áp dụng [kể] từ ngày`
  — set which tax period or case a rule applies to, not when it takes effect. No date changes;
  each line is reported as `application_period`.
- **End dates** — a line with `đến hết ngày <D>` — are not modelled (validity status is out of
  scope); each is reported as `effective_until`.

A date earlier than `ngay_ban_hanh` is kept as written: documents do take effect retroactively
(Decree 141/2026: 01/01/2026, issued 29/04/2026).

Check case (AC-004): Law 09/2026/QH16, issued 24/04/2026 — `Luật này có hiệu lực thi hành từ
ngày được thông qua, trừ quy định tại khoản 2` and `Quy định tại các điều 1, 2 và 3 của Luật này
có hiệu lực thi hành từ ngày 01 tháng 01 năm 2026`: Articles 1–3 carry `2026-01-01`, Articles 4
and 5 carry `2026-04-24`.

### Amendment links

A **directive** is a provision telling the reader to amend, replace or repeal another one. Each
directive gives one link per provision it names, from the chunk that holds it (the **source**)
to the provision named (the **target**); the target's chunks then list the link in
`amended_by`. Links are read from the amending side only: the amended text does not say it was
amended. The site's own notes on amended provisions are not read (#5, choice 7; #21).

**Where directives are read.** Two places, and nowhere else:

- every article of an **amending document** — one whose `trich_yeu` starts with
  `Sửa đổi, bổ sung` (6 in the corpus) — other than its effectiveness article: the article title
  and each line that starts, after its list marker (`1.`, `a)`), with a **directive verb**;
- the **effectiveness article** of every document (as defined under *Effective date*): each line
  that replaces or repeals, in the forms below, and the items of the lists such a line opens.

Text inside a quotation is the new wording, never a directive: lines are skipped while a `“`
opened on an earlier line is still open (tracked as the chunker does), and text between `“` and
`”` on a line is dropped before reading. A mention such as "… được sửa đổi, bổ sung bởi Nghị
định số 18/2021/NĐ-CP" describes another document's history and is never a link.

**Type.** From the directive's verb:

| Verb | `type` |
|---|---|
| `Sửa đổi, bổ sung`, `Sửa đổi`, `Bổ sung`, `Sửa đổi cụm từ … thành …`, `Bỏ cụm từ` | `amends` |
| `Thay thế`, `<kind> này thay thế` | `replaces` |
| `Bãi bỏ`, `<kind> này bãi bỏ`, `… hết hiệu lực [thi hành]` | `repeals` |

In the effectiveness article, `thay thế` and `bãi bỏ` count only when a document, a provision,
`quy định tại`, `nội dung tại`, `các quy định` or a closing `:` follows them, and not after
`được`, `bị` or `hoặc` — so "Trường hợp các văn bản … được sửa đổi, bổ sung hoặc thay thế thì
thực hiện theo văn bản … thay thế đó" is not a directive. A line with `hết hiệu lực` is cut at
`;` and each part holding `hết hiệu lực` is a directive whose targets stand before those words.

**Lists.** A replace or repeal line that names no target of its own and ends with `:` ("2. Nghị
định này thay thế:", "3. Bãi bỏ quy định tại:", "… các Nghị định sau đây hết hiệu lực thi
hành:") opens a list: each following letter item (`a)`, `b)`, …) up to the next numbered clause
is a directive of the same type. An item that starts with its own verb ("g) Bỏ cụm từ …") takes
that verb's type.

**Targets.** Read left to right through the directive, after dropping every parenthesis that
names a document or starts with `trừ`:

- a **provision** is `[điểm <p>] [khoản <c>] Điều <a>`; a run like `Điều 6, Điều 9 và Điều 15`
  or `điểm a và điểm c khoản 2; khoản 3 Điều 4` gives one target per provision, each taking the
  next `khoản` and `Điều` to its right. A run holds only `,`, `;`, `và`, `của`, `tại` and
  `[ban hành] kèm theo` between its parts; other text ends it, and a point or clause left without
  an article there takes one from the context below, or is dropped ("điểm g mục 4 phần I của
  Biểu thuế … tại khoản 1 Điều 8" names clause 1 of Article 8, not a point of it);
- a **part** is `Chương <n>`, `Phụ lục <n>` or `Mẫu số <code>` (case ignored, written
  `Mẫu số`); a form followed by its annex (`Mẫu số 14, Phụ lục II`) is one part;
- a **document** is `<kind> [liên tịch] [số] <number>`, a law named with its number (`Luật Thuế
  giá trị gia tăng số 13/2008/QH12`), or a law named without one, resolved to the corpus law
  whose `Luật <trich_yeu>` is that name (`của Luật Thuế giá trị gia tăng` → 48/2024/QH15). A
  `<kind> này` reference is the document itself and is never a target.

Provisions and parts belong to the first document to their right; with none, to the **inherited
document**: the one named in the article title, else the first document in the `trich_yeu`
(Decree 144/2026 → "Nghị định 181/2025/NĐ-CP"). A provision or point that names no article or
clause takes it from the line that encloses it, then from the article title
(`1. Sửa đổi, bổ sung một số khoản của Điều 5 như sau:` › `a) Sửa đổi, bổ sung khoản 1` →
clause 1 of Article 5). A directive whose object is `một số điều|khoản|điểm` only sets this
context and gives no link of its own.

Which documents in a directive are targets:

- the first document, with whatever provisions or parts belong to it;
- a later document of the **same kind** placed directly after `và` or `;` with no other document
  between it and the previous target ("Nghị định số 132/2020/NĐ-CP … và Nghị định số
  20/2025/NĐ-CP … hết hiệu lực");
- when the first target has provisions or parts, a later provision group that follows `,` or
  `và` directly ("…, điểm b khoản 2 Điều 4 và Mẫu số 14, Phụ lục II ban hành kèm theo Nghị định
  số 26/2023/NĐ-CP");
- anything else is the description of a target ("Thông tư số 193/2015/TT-BTC … sửa đổi, bổ sung
  Thông tư số 219/2013/TT-BTC …" replaces 193/2015 only). In a `Thay thế X bằng|thành Y`
  directive, Y is the replacement, not a target, when Y starts with `Danh mục`, `Mẫu số`,
  `Phụ lục`, `quy định` or `các` ("giá thành sản phẩm" is not a replacement);
  `[vào] sau <provision>` says where an added provision goes and is not a target.

A directive with a verb but no target it can resolve is reported as `unresolved_link`, with the
line quoted. An article title with no target ("Điều 3. Thay thế mẫu biểu") is a heading, not a
directive, and is not reported. When the title and a line of its body name the same target, the
link is recorded once.

**Target chunks.** A target in the corpus maps to chunks of its document:

| Target | Chunks |
|---|---|
| a whole document | every chunk of it |
| an article | every chunk of the article |
| a clause or a point | the clause's chunk if the article is split, else the article's chunk |
| a clause or point the directive adds (`Bổ sung khoản 1b sau khoản 1`) | the chunk of the provision it is placed after; with no `sau`, of the highest existing clause numbered below it (`Bổ sung khoản 15 Điều 4` → clause 14) |
| a part | none: annexes and forms are not chunked |

A target outside the corpus is kept, named by its number and provision, with `in_corpus`
false and no chunks (FR-CORE-005).

**Check cases** (AC-005):

- Law 149/2025, Article 1: clause 1 and clause 25 of Article 5, clause 5 of Article 9 of Law
  48/2024 amended; clause 3 of Article 12 and point c of clause 9 of Article 15 repealed.
- Law 09/2026, Article 4: "… tại điểm g mục 4 phần I của Biểu thuế tiêu thụ đặc biệt quy định
  tại khoản 1 Điều 8 của Luật Thuế tiêu thụ đặc biệt" amends clause 1 of Article 8 of Law
  66/2025. (#5's comment listed this as a target regex could not place; the title does name
  the clause.)
- Law 109/2025, Article 29, clause 3: "Luật Thuế thu nhập cá nhân số 04/2007/QH12 đã được sửa
  đổi, bổ sung … theo … Luật số 48/2024/QH15 … hết hiệu lực" repeals Law 04/2007 only. The laws
  after `theo` are its history. The site notes it as repealing Article 17 of Law 48/2024, and
  #5's comment repeated that as an example; the text does not say it. The part after `;` names
  provisions by subject only and is reported as `unresolved_link`.

The full hand-checked list is `tests/fixtures/amendment_links.csv`: one row per link,
`target_chunks` filled for in-corpus targets.

## `data/enriched/links.jsonl` — every amendment link

One record per link, ordered by the source chunk's position in `data/chunks/chunks.jsonl`,
then by the target's position in the directive. Byte-identical across two builds (NFR-005).

| Field | Type | Example | Meaning |
|---|---|---|---|
| `type` | string | `amends` | `amends`, `replaces` or `repeals` |
| `source` | string | `421739:D1` | id of the chunk holding the directive; for a directive in an article title, the article's first chunk |
| `target_number` | string | `48/2024/QH15` | the target document's number, as written in the corpus (`so_hieu`) or in the directive |
| `target_doc` | string or null | `379409` | the target document's `doc_id`; null outside the corpus |
| `target_article` | string or null | `5` | null for a whole document or a part |
| `target_clause` | string or null | `25` | as written, so an added clause is `1b` |
| `target_point` | string or null | `c` | as written, e.g. `a.4` |
| `target_part` | string or null | `Phụ lục I` | a chapter, annex or form; null otherwise |
| `target_chunks` | list | `["379409:D5:K25"]` | the target's chunks, by the table above; empty outside the corpus and for a part |
| `in_corpus` | bool | `true` | whether the target document is in the corpus |

## `data/enriched/issues.jsonl` — what the enrich step could not settle

Same fields as the chunker's `issues.jsonl`, ordered by document id; within a document, the
effective-date issues come first, then `unresolved_link`, each in text order.

| `kind` | `article` | Meaning |
|---|---|---|
| `no_effective_date` | the effectiveness article, or empty | the document's date could not be read; its chunks have `effective_date` null. This is AC-004's report |
| `partial_effective_date` | the referenced article | an exception narrower than the chunks it falls in; `detail` quotes the line |
| `application_period` | the effectiveness article | an application rule; `detail` quotes the line |
| `effective_until` | the effectiveness article | an end date; `detail` quotes the line |
| `unresolved_link` | the article holding the directive | a directive with no target that could be resolved; `detail` quotes the line |

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
