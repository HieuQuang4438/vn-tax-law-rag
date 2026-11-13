---
status: draft
updated: 2026-11-13
owner: HieuQuang4438
---

# Corpus

The 30 documents the system answers from: where they come from, what they are, how they relate
and what is unusual in them. Terms are defined in [glossary.md](glossary.md); the chunk format
is in [chunk-schema.md](chunk-schema.md).

Counts were measured on 2026-11-11 from the crawl of 2026-11-04, with the chunker at commit
`df328fc` (`python -m src.chunking`). A change to the crawler or the chunker can change them.

## Source

Two summary articles on luatvietnam.vn list the documents; the crawler reads them from
`INDEX_URLS` in `scripts/crawl_index.py`.

| List | Article | Documents |
|---|---|---|
| A | [Tổng hợp danh sách luật thuế và nghị định, thông tư thuế mới nhất 2026](https://luatvietnam.vn/thue-phi-le-phi/tong-hop-danh-sach-luat-thue-va-nghi-dinh-thong-tu-thue-moi-nhat-2026-565-110892-article.html) | 27 |
| B | [Luật Thuế TNCN mới nhất 2026 và văn bản hướng dẫn](https://luatvietnam.vn/thue-phi-le-phi/tong-hop-van-ban-huong-dan-ve-thue-tncn-moi-nhat-565-96172-article.html) | 6, of which 3 are also in A |

Each document is one page, `…-<doc_id>-d1.html`. `doc_id` is the site's numeric id and the
prefix of every chunk id. The crawled pages and parsed text stay in `data/`, which is gitignored.

## In numbers

| | Laws | Decrees | Circulars | Total |
|---|---|---|---|---|
| Documents | 7 | 11 | 12 | 30 |
| of which amending documents | 2 | 3 | 1 | 6 |
| Articles | 138 | 325 | 281 | 744 |
| Chunks | 349 | 823 | 751 | 1,923 |

- Issue dates run from 26/11/2024 (`48/2024/QH15`) to 01/07/2026 (`94/2026/TT-BTC`).
- 17 documents have chapters, 6 of them also sections; 13 have neither.
- 15 documents have an appendix or forms after the body; none of it is chunked.
- 125 chunks are over 800 tokens: a clause, or an article with no clauses, that is over the
  limit on its own. The longest is 3,289 tokens.

## Documents

Grouped by tax. *Title* is the trích yếu as the document gives it, with "Luật" put in front
of a law's, whose trích yếu is only its subject. *Subject* is a short English rendering of it. *Amends* marks an
amending document. *Art.* and *Chunks* are counts.

### Tax administration

| doc_id | Number | Title | Issued | Subject | Art. | Chunks | List |
|---|---|---|---|---|---|---|---|
| 421539 | 108/2025/QH15 | Luật Quản lý thuế | 10/12/2025 | Law on Tax Administration | 53 | 151 | A |
| 439382 | 252/2026/NĐ-CP | Quy định chi tiết một số điều và biện pháp để tổ chức, hướng dẫn thi hành Luật Quản lý thuế | 30/06/2026 | details the Law on Tax Administration | 76 | 267 | A |
| 439381 | 254/2026/NĐ-CP | Quy định chi tiết một số điều và biện pháp để tổ chức hướng dẫn thi hành Luật Quản lý thuế 2025 số 108/2025/QH15 về hóa đơn điện tử, chứng từ điện tử | 30/06/2026 | details the Law on Tax Administration: e-invoices and e-documents | 45 | 87 | A |
| 439613 | 255/2026/NĐ-CP | Quy định về quản lý thuế đối với các giao dịch liên kết của những doanh nghiệp có quan hệ liên kết | 30/06/2026 | tax administration of related-party transactions | 24 | 62 | A |
| 440483 | 89/2026/TT-BTC | Quy định chi tiết một số điều của Luật Quản lý thuế và Nghị định 252/2026/NĐ-CP của Chính phủ quy định chi tiết một số điều và biện pháp để tổ chức, hướng dẫn thi hành Luật Quản lý thuế | 30/06/2026 | details the Law on Tax Administration and Decree 252/2026 | 101 | 293 | A |
| 439780 | 91/2026/TT-BTC | Quy định một số điều của Luật Quản lý thuế và Nghị định 254/2026/NĐ-CP của Chính phủ quy định chi tiết một số điều và biện pháp để tổ chức, hướng dẫn thi hành Luật Quản lý thuế số 108/2025/QH15 về hóa đơn điện tử, chứng từ điện tử | 30/06/2026 | details the Law on Tax Administration and Decree 254/2026: e-invoices and e-documents | 25 | 42 | A |
| 439827 | 90/2026/TT-BTC | Quy định về đăng ký thuế | 30/06/2026 | tax registration | 38 | 114 | A |
| 439781 | 94/2026/TT-BTC | Quy định về quản lý tuân thủ, quản lý rủi ro trong quản lý thuế | 01/07/2026 | compliance and risk management in tax administration | 23 | 57 | A |
| 439660 | 86/2026/TT-BTC | Quy định về quản lý thuế đối với hàng hóa xuất khẩu, nhập khẩu | 30/06/2026 | tax administration of exports and imports | 45 | 144 | A |

### Value-added tax (VAT)

| doc_id | Number | Title | Issued | Subject | Art. | Chunks | List |
|---|---|---|---|---|---|---|---|
| 379409 | 48/2024/QH15 | Luật Thuế giá trị gia tăng | 26/11/2024 | Law on Value-Added Tax | 18 | 65 | A |
| 421739 | 149/2025/QH15 | Sửa đổi, bổ sung một số điều của Luật Thuế giá trị gia tăng | 11/12/2025 | *Amends* the Law on Value-Added Tax | 2 | 2 | A |
| 404357 | 181/2025/NĐ-CP | Quy định chi tiết thi hành một số điều của Luật Thuế giá trị gia tăng | 01/07/2025 | details the Law on Value-Added Tax | 40 | 120 | A |
| 422898 | 359/2025/NĐ-CP | Sửa đổi, bổ sung một số điều của Nghị định 181/2025/NĐ-CP ngày 01/7/2025 của Chính phủ quy định chi tiết thi hành một số điều của Luật Thuế giá trị gia tăng | 31/12/2025 | *Amends* Decree 181/2025 | 2 | 2 | A |
| 433921 | 144/2026/NĐ-CP | Sửa đổi, bổ sung một số điều của Nghị định 181/2025/NĐ-CP ngày 01/7/2025 của Chính phủ quy định chi tiết thi hành một số điều của Luật Thuế giá trị gia tăng đã được sửa đổi, bổ sung một số điều bởi Nghị định 359/2025/NĐ-CP ngày 31/12/2025 của Chính phủ | 05/05/2026 | *Amends* Decree 181/2025, as amended by Decree 359/2025 | 6 | 6 | A |
| 404453 | 69/2025/TT-BTC | Quy định chi tiết một số điều của Luật Thuế giá trị gia tăng và hướng dẫn thực hiện Nghị định 181/2025/NĐ-CP ngày 01/07/2025 của Chính phủ quy định chi tiết thi hành một số điều của Luật Thuế giá trị gia tăng | 01/07/2025 | details the Law on Value-Added Tax and Decree 181/2025 | 10 | 21 | A |
| 406967 | 77/2025/TT-BTC | Quy định chi tiết các dịch vụ kinh doanh chứng khoán và chuyển nhượng chứng khoán theo Nghị định 181/2025/NĐ-CP ngày 01/7/2025 của Chính phủ quy định chi tiết thi hành một số điều của Luật Thuế giá trị gia tăng | 30/07/2025 | securities business services and securities transfers under Decree 181/2025 | 5 | 5 | A |

### Personal income tax (PIT)

| doc_id | Number | Title | Issued | Subject | Art. | Chunks | List |
|---|---|---|---|---|---|---|---|
| 422733 | 109/2025/QH15 | Luật Thuế thu nhập cá nhân | 10/12/2025 | Law on Personal Income Tax | 29 | 60 | B |
| 439303 | 253/2026/NĐ-CP | Quy định chi tiết một số điều và biện pháp để tổ chức, hướng dẫn thi hành Luật Thuế thu nhập cá nhân | 30/06/2026 | details the Law on Personal Income Tax | 71 | 94 | B |
| 439434 | 87/2026/TT-BTC | Quy định chi tiết một số điều của Luật Thuế thu nhập cá nhân và Nghị định 253/2026/NĐ-CP của Chính phủ quy định chi tiết một số điều và biện pháp để tổ chức, hướng dẫn thi hành Luật Thuế thu nhập cá nhân | 30/06/2026 | details the Law on Personal Income Tax and Decree 253/2026 | 6 | 14 | B |

### Corporate income tax (CIT)

| doc_id | Number | Title | Issued | Subject | Art. | Chunks | List |
|---|---|---|---|---|---|---|---|
| 404386 | 67/2025/QH15 | Luật Thuế thu nhập doanh nghiệp | 14/06/2025 | Law on Corporate Income Tax | 20 | 51 | A |
| 421582 | 320/2025/NĐ-CP | Quy định chi tiết một số điều và biện pháp để tổ chức, hướng dẫn thi hành Luật Thuế thu nhập doanh nghiệp | 15/12/2025 | details the Law on Corporate Income Tax | 26 | 108 | A |
| 428454 | 20/2026/TT-BTC | Quy định chi tiết một số điều của Luật Thuế thu nhập doanh nghiệp và Nghị định 320/2025/NĐ-CP ngày 15/12/2025 của Chính phủ quy định chi tiết một số điều và biện pháp để tổ chức, hướng dẫn thi hành Luật Thuế thu nhập doanh nghiệp | 12/03/2026 | details the Law on Corporate Income Tax and Decree 320/2025 | 10 | 34 | A |

### Special consumption tax (SCT)

| doc_id | Number | Title | Issued | Subject | Art. | Chunks | List |
|---|---|---|---|---|---|---|---|
| 405694 | 66/2025/QH15 | Luật Thuế tiêu thụ đặc biệt | 14/06/2025 | Law on Special Consumption Tax | 11 | 15 | A |
| 422910 | 360/2025/NĐ-CP | Quy định chi tiết thi hành một số điều của Luật Thuế tiêu thụ đặc biệt | 31/12/2025 | details the Law on Special Consumption Tax | 11 | 42 | A |
| 422908 | 158/2025/TT-BTC | Quy định chi tiết một số điều của Nghị định 360/2025/NĐ-CP ngày 31/12/2025 của Chính phủ quy định chi tiết thi hành một số điều của Luật Thuế tiêu thụ đặc biệt | 31/12/2025 | details Decree 360/2025 | 5 | 11 | A |

### Household and individual businesses

| doc_id | Number | Title | Issued | Subject | Art. | Chunks | List |
|---|---|---|---|---|---|---|---|
| 427630 | 68/2026/NĐ-CP | Quy định về chính sách thuế và quản lý thuế đối với hộ kinh doanh, cá nhân kinh doanh | 05/03/2026 | tax policy and administration for household and individual businesses | 19 | 30 | A, B |
| 433387 | 141/2026/NĐ-CP | Sửa đổi, bổ sung một số điều của Nghị định 68/2026/NĐ-CP quy định về chính sách thuế đối với hộ kinh doanh, cá nhân kinh doanh và Nghị định 320/2025/NĐ-CP quy định chi tiết một số điều và biện pháp để tổ chức, hướng dẫn thi hành Luật Thuế thu nhập doanh nghiệp | 29/04/2026 | *Amends* Decree 68/2026 and Decree 320/2025 | 5 | 5 | A, B |
| 427777 | 18/2026/TT-BTC | Quy định về hồ sơ, thủ tục quản lý thuế đối với hộ kinh doanh, cá nhân kinh doanh | 05/03/2026 | dossiers and procedures for household and individual businesses | 9 | 12 | A |
| 434628 | 50/2026/TT-BTC | Sửa đổi, bổ sung một số điều của Thông tư 18/2026/TT-BTC ngày 05/3/2026 của Bộ trưởng Bộ Tài chính quy định về hồ sơ, thủ tục quản lý thuế đối với hộ kinh doanh, cá nhân kinh doanh | 13/05/2026 | *Amends* Circular 18/2026 | 4 | 4 | A |

### Across several taxes

| doc_id | Number | Title | Issued | Subject | Art. | Chunks | List |
|---|---|---|---|---|---|---|---|
| 434729 | 09/2026/QH16 | Sửa đổi, bổ sung một số điều của Luật Thuế thu nhập cá nhân, Luật Thuế giá trị gia tăng, Luật Thuế thu nhập doanh nghiệp và Luật Thuế tiêu thụ đặc biệt | 24/04/2026 | *Amends* the laws on PIT, VAT, CIT and SCT | 5 | 5 | A, B |

## How the documents relate

Each tax has a law, a decree detailing it and a circular detailing the decree; amending
documents sit beside the document they change. Read top-down: a decree is valid only within its
law, a circular only within its decree.

- **Tax administration:** Law 108/2025 › Decrees 252/2026, 254/2026, 255/2026 › Circulars
  89/2026, 90/2026, 86/2026 (from 252), 91/2026 (from 254), 94/2026 (from 252 and 254).
  Decree 255/2026 also rests on the CIT Law 67/2025; Circular 86/2026 also on the customs and
  export–import tax laws, which are not in the corpus.
- **VAT:** Law 48/2024 › Decree 181/2025 › Circulars 69/2025, 77/2025. The law is amended by
  Law 149/2025 and Law 09/2026; the decree by Decree 359/2025, then Decree 144/2026.
- **PIT:** Law 109/2025 › Decree 253/2026 › Circular 87/2026. Amended by Law 09/2026.
- **CIT:** Law 67/2025 › Decree 320/2025 › Circular 20/2026. The law is amended by Law 09/2026,
  the decree by Decree 141/2026.
- **SCT:** Law 66/2025 › Decree 360/2025 › Circular 158/2025. Amended by Law 09/2026.
- **Household businesses:** Decree 68/2026 › Circular 18/2026. Amended by Decree 141/2026 and
  Circular 50/2026.

These are document-level links taken from the trích yếu and the "Căn cứ" lines. Links at article
and clause level are FR-CORE-005, not built yet.

An amending document is short: 2 to 6 articles, each quoting the new wording of many
provisions in “ ”. Quoted text is never split into its own chunks, so these documents yield one
chunk per article, often over 800 tokens.

## Known irregularities

What the source text does wrong, as reported in `data/chunks/issues.jsonl`. The chunker reports
and does not repair them.

| doc_id | Article | Issue | What is in the source |
|---|---|---|---|
| 439303 | 66 | `duplicate_heading` | the Điều 66 heading appears twice in a row; the longer is kept |
| 439660 | 39 | `clause_numbering` | clauses run 1–7, then 9: clause 8 is missing |
| 439780 | 9, 9, 18, 24 | `mismatched_quotes` | a quotation opened with “ is closed with a straight `"` |

Not reported as an issue, but handled: article headings written `Điều 1 .` with a space before
the dot, and a heading sitting as bare text beside a table (`09/2026/QH16`, Article 4).

## Amendments from outside the corpus

Amendment links are read from the amending text, so a provision changed by a document that is
not in the corpus has no `amended_by` link, and retrieval can return its superseded wording.
The site's notes name 19 such changes (as of 2026-11-12); they are listed here, not modelled:

| Amended | Provisions | Amended by |
|---|---|---|
| 379409 (Law 48/2024) | point a, clause 1, Article 9 | Law 90/2025/QH15, Article 4 |
| 404357 (Decree 181/2025) | Annex III | Decree 273/2026/NĐ-CP |
| 404386 (Law 67/2025) | clauses 11a and 11b, Article 4 | Law 141/2025/QH15, Article 2 clause 2 |
| 404386 (Law 67/2025) | clause 6, Article 4 | Law 127/2025/QH15, Article 178 |
| 404386 (Law 67/2025) | points a, e, e1, e2 of clause 2, Article 12; clause 1a, point d of clause 4 and clause 7, Article 13; point a of clause 1 and clause 4, Article 14; clause 1a, Article 20 | Law 133/2025/QH15, Article 25 clause 7 (10 provisions) |
| 404386 (Law 67/2025) | point h, clause 2, Article 12 | Law 143/2025/QH15, Article 50 clause 2 |
| 421539 (Law 108/2025) | points g and n of clause 1, Articles 38 and 37 | Law 15/2026/QH16, Article 2 clause 2 |
| 422908 (Circular 158/2025) | clause 2, Article 3 | Circular 136/2026/TT-BTC, Article 1 |

Adding these documents to the corpus would let the links be read; that is a corpus change, not
part of FR-CORE-005.

## Annexes are not indexed

Annexes and forms are parsed into `data/processed/` but never chunked
([chunk-schema.md](chunk-schema.md), ADR-0001), so what only an annex says cannot be retrieved.
Some of it answers everyday questions. Known case: Annex I of Circular 69/2025/TT-BTC (404453)
lists which activities fall into each VAT percentage group for household businesses (1%, 2%,
3%, 5%); Article 5 only refers to it. Eval set turn c02.2 keeps a question about it on purpose,
to measure this gap (#7).
