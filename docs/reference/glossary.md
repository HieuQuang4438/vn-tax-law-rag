---
status: approved
updated: 2026-11-21
owner: HieuQuang4438
approved-by: peer
---

# Glossary — Vietnamese legal documents

The Vietnamese terms this repo uses, what each means, and the name it carries in code. Read it
before [corpus.md](corpus.md) and [chunk-schema.md](chunk-schema.md). Examples are taken from the
corpus.

## Kinds of document

Every document in the corpus is a *văn bản quy phạm pháp luật* (legal normative document): a
generally binding rule, issued by a state body in a form set by law. Three kinds occur. A lower
kind details a higher one and may not contradict it.

| Term | English | Issued by | Number suffix | Example |
|---|---|---|---|---|
| Luật | Law | Quốc hội (National Assembly) | `QH<term>` | `48/2024/QH15` — Law on Value-Added Tax |
| Nghị định | Decree | Chính phủ (Government) | `NĐ-CP` | `181/2025/NĐ-CP` — details the VAT Law |
| Thông tư | Circular | a minister; here Bộ trưởng Bộ Tài chính (Minister of Finance) | `TT-BTC` | `69/2025/TT-BTC` — details the VAT Law and Decree 181 |

A chain from law down to circular is the normal case: the law states the rule, a decree
*quy định chi tiết* (details) the articles the law delegates, and a circular details the decree.
[corpus.md](corpus.md#how-the-documents-relate) shows the chains in the corpus.

## Metadata of a document

Read from the information table at the top of each page; field names are those in
`data/processed/<slug>.json` under `metadata`.

| Term | Field | Meaning | Example |
|---|---|---|---|
| Số hiệu | `so_hieu` | document number: sequence / year / issuer code. `QH15` is the 15th National Assembly | `90/2026/TT-BTC` |
| Loại văn bản | `loai_van_ban` | kind of document | `Thông tư` |
| Cơ quan ban hành | `co_quan_ban_hanh` | issuing body. For a circular the site gives the ministry, not the minister | `Bộ Tài chính` |
| Người ký | `nguoi_ky` | signatory | `Trần Thanh Mẫn` |
| Ngày ban hành | `ngay_ban_hanh` | issue date, `dd/mm/yyyy` | `30/06/2026` |
| Trích yếu | `trich_yeu` | the document's own title, after its kind. A law's is only its subject: Luật + `Quản lý thuế` reads "Luật Quản lý thuế" | `Quy định về đăng ký thuế` |
| Tiêu đề | `tieu_de` | the site's page title: editorial, abbreviated, not part of the document | `Thông tư 90/2026/TT-BTC quy định đăng ký thuế` |
| Ngày hiệu lực | — | effective date. Paid-only on the site, so not stored; FR-CORE-004 reads it from the document's own effectiveness article | — |

## Parts of a document, in order

| Part | Term | What it holds | Chunked? |
|---|---|---|---|
| Heading block | quốc hiệu, tiêu ngữ | issuer, number, place and date; "CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM — Độc lập - Tự do - Hạnh phúc" | no |
| Name | tên văn bản | kind in capitals (`THÔNG TƯ`), then the trích yếu | no |
| Legal basis | căn cứ | lines starting "Căn cứ …" naming the documents it rests on, then who proposed and who issues it | no |
| Body | nội dung | the provisions, divided as in the next section | yes |
| Signature block | nơi nhận, chữ ký | "Nơi nhận:" (recipient list) and the signatory | no |
| Appendix | phụ lục | tables and lists attached to the document: "Phụ lục I", "(Kèm theo Thông tư số …)" | no |
| Form | mẫu số | blank forms to fill in: "Mẫu số: 01-ĐKT" | no |

What the chunker treats as the end of the body is listed in
[chunk-schema.md](chunk-schema.md#rules-in-the-order-they-apply).

## Divisions of the body

From largest to smallest. Only Điều is always present; every level above it is optional, and a
level below it appears only when the text needs it.

| Term | English | Written as | In code | Notes |
|---|---|---|---|---|
| Phần | Part | `Phần thứ nhất` | — | not used in the body of any document in the corpus; "Phần" occurs only inside forms |
| Chương | Chapter | `Chương I` + an all-caps title line | `chapter` | Roman numerals. 17 of the 30 documents have chapters |
| Mục | Section | `Mục 1` + a title line | — | inside a chapter, Arabic numerals. 6 documents have sections. Not recorded on chunks |
| Điều | Article | `Điều 5. Cấu trúc mã số thuế` | `article` | numbered 1..N through the whole document, never restarting per chapter. The unit of citation |
| Khoản | Clause | `1. …` | `clause` | numbered from 1 within its article |
| Điểm | Point | `a) …` | — | lettered within its clause in Vietnamese alphabet order: a, b, c, d, đ, e, … Some documents go one level deeper: `a.1)`, `a.2)` |
| — | indent | `- …` | — | an unnumbered item under a point or clause |

## Changing other documents

| Term | English | Meaning |
|---|---|---|
| Sửa đổi, bổ sung | amend, supplement | rewrite or add to provisions of an earlier document. The amending document quotes the new wording in “ ”: `Sửa đổi, bổ sung khoản 1 Điều 7 như sau: “1. …”` |
| Văn bản sửa đổi | amending document | a document whose purpose is amending others: 6 in the corpus, e.g. `09/2026/QH16` |
| Thay thế | replace | a provision or document takes the place of another |
| Bãi bỏ | repeal | a provision or document stops having effect, with nothing in its place |
| Văn bản hợp nhất | consolidated text | the original with its amendments merged in. Not in the corpus: the corpus holds originals and amending documents separately, which is why FR-CORE-005 links them |
| Hiệu lực thi hành | entry into force | the article stating when the document takes effect; may set different dates for different articles |
| Quy định chuyển tiếp | transitional provisions | how cases that began under the old rules are handled |
| Tổ chức thực hiện / Trách nhiệm thi hành | implementation | who carries the document out. With the two above, the usual last articles of a document |

## Cross-references

Provisions point at each other from the smallest unit to the largest, in lower case except
Điều:

- `điểm b khoản 1 Điều 40 Nghị định số 252/2026/NĐ-CP` — point b of clause 1 of Article 40 of
  Decree 252/2026/NĐ-CP.
- `khoản 1, 2, 3 và 4 Điều 11` — clauses 1–4 of Article 11 of the same document.
- `Điều này`, `khoản này` — this article, this clause. Meaningless out of context, which is why
  every chunk gets a context header (FR-CORE-003).
- `Luật này`, `Nghị định này`, `Thông tư này` — this document.
