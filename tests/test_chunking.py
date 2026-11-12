"""AC-002: chunk by legal structure. Approach approved on #2.

Fixture documents are small excerpts in the shape of `data/processed/<slug>.json`, abridged
from the corpus (Circular 90/2026, Decree 253/2026, Law 09/2026). Tokens are counted as words
so the tests need neither the bge-m3 tokenizer nor the network.
"""

import json
from pathlib import Path

import pytest

from src.chunking import MAX_TOKENS, MIN_INTRO_TOKENS, build, chunk_document

DOC_ID = "439827"


def words(text: str) -> int:
    return len(text.split())


def make_doc(*texts: str, doc_id: str = DOC_ID) -> dict:
    """One block per text; a block may hold several lines, as the parser emits them."""
    return {
        "source_url": f"https://luatvietnam.vn/thue/thong-tu-90-2026-tt-btc-{doc_id}-d1.html",
        "crawled_at": "2026-11-04T00:00:00+00:00",
        "metadata": {"so_hieu": "90/2026/TT-BTC", "trich_yeu": "Quy định về đăng ký thuế"},
        "blocks": [{"id": f"demuc{i}", "kind": "docitem-11", "text": t} for i, t in enumerate(texts)],
    }


HEADING = "BỘ TÀI CHÍNH _______ Số: 90/2026/TT-BTC | CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM Độc lập - Tự do - Hạnh phúc"
TITLE = "THÔNG TƯ\nQuy định về đăng ký thuế"
PREAMBLE = "Căn cứ Luật Quản lý thuế số 108/2025/QH15;\nBộ trưởng Bộ Tài chính ban hành Thông tư quy định về đăng ký thuế."
SIGNATURE = (
    "Nơi nhận: - Ban Bí thư Trung ương Đảng; - Thủ tướng, các Phó Thủ tướng Chính phủ; - Lưu: VT, CT. | "
    "KT. BỘ TRƯỞNG THỨ TRƯỞNG Cao Anh Tuấn"
)


def clause(n: int, size: int = 10) -> str:
    return f"{n}. " + " ".join(["nội-dung"] * size)


def short_doc() -> dict:
    return make_doc(
        HEADING, TITLE, PREAMBLE,
        "Chương I\nQUY ĐỊNH CHUNG",
        "Điều 1. Phạm vi điều chỉnh\nThông tư này quy định về đăng ký thuế.",
        "Điều 2. Đối tượng áp dụng",
        "Người nộp thuế theo quy định tại Điều 4 Luật Quản lý thuế.",
        "Chương II\nTHỦ TỤC ĐĂNG KÝ THUẾ",
        "Mục 1\nĐĂNG KÝ THUẾ LẦN ĐẦU",
        "Điều 3. Hiệu lực thi hành\nNgười nộp thuế nộp hồ sơ tại cơ quan thuế quản lý trực tiếp.",
        SIGNATURE,
    )


def chunk(doc: dict, **kwargs):
    return chunk_document(doc, count_tokens=words, **kwargs)


# --- Defaults ------------------------------------------------------------------------------


def test_split_threshold_defaults_to_800_tokens():
    assert MAX_TOKENS == 800


def test_intro_chunk_threshold_defaults_to_100_tokens():
    assert MIN_INTRO_TOKENS == 100


# --- What is chunked -----------------------------------------------------------------------


def test_one_chunk_per_article_at_or_under_threshold():
    result = chunk(short_doc())

    assert [c.id for c in result.chunks] == [f"{DOC_ID}:D1", f"{DOC_ID}:D2", f"{DOC_ID}:D3"]


def test_chunk_carries_document_chapter_article_clause_and_parent():
    first = chunk(short_doc()).chunks[0]

    assert first.doc_id == DOC_ID
    assert first.chapter == "Chương I"
    assert first.article == "1"
    assert first.clause is None
    assert first.parent_id == f"{DOC_ID}:D1"


def test_chapter_follows_the_latest_chapter_heading():
    chapters = [c.chapter for c in chunk(short_doc()).chunks]

    assert chapters == ["Chương I", "Chương I", "Chương II"]


def test_document_without_chapters_has_no_chapter():
    doc = make_doc(HEADING, "Điều 1. Phạm vi\nNội dung.", "Điều 2. Hiệu lực\nNội dung.", SIGNATURE)

    assert [c.chapter for c in chunk(doc).chunks] == [None, None]


# AC-003 needs the chapter title for the context header; the chunker records it (approach on #3).


def test_chapter_title_is_the_all_caps_line_after_the_chapter_heading():
    result = chunk(short_doc())

    assert [c.chapter_title for c in result.chunks] == ["QUY ĐỊNH CHUNG", "QUY ĐỊNH CHUNG", "THỦ TỤC ĐĂNG KÝ THUẾ"]
    assert [a.chapter_title for a in result.articles] == ["QUY ĐỊNH CHUNG", "QUY ĐỊNH CHUNG", "THỦ TỤC ĐĂNG KÝ THUẾ"]


def test_section_title_does_not_replace_the_chapter_title():
    # short_doc's Điều 3 sits under "Mục 1 / ĐĂNG KÝ THUẾ LẦN ĐẦU" inside Chương II.
    assert chunk(short_doc()).chunks[2].chapter_title == "THỦ TỤC ĐĂNG KÝ THUẾ"


def test_document_without_chapters_has_no_chapter_title():
    doc = make_doc(HEADING, "Điều 1. Phạm vi\nNội dung.", "Điều 2. Hiệu lực\nNội dung.", SIGNATURE)

    assert [c.chapter_title for c in chunk(doc).chunks] == [None, None]


def test_chapter_without_all_caps_title_line_has_no_title_and_is_reported():
    doc = make_doc(
        "Chương I", "Điều 1. Phạm vi\nNội dung.",
        "Chương II\nTHỦ TỤC", "Điều 2. Hiệu lực thi hành\nNội dung.",
        SIGNATURE,
    )
    result = chunk(doc)

    assert [c.chapter_title for c in result.chunks] == [None, "THỦ TỤC"]
    assert [(i.kind, i.article) for i in result.issues] == [("missing_chapter_title", "1")]


def test_chapter_title_is_kept_as_written_in_the_source():
    doc = make_doc("CHƯƠNG I\nNHỮNG QUY ĐỊNH CHUNG", "Điều 1. Hiệu lực thi hành\nNội dung.", SIGNATURE)
    first = chunk(doc).chunks[0]

    assert (first.chapter, first.chapter_title) == ("Chương I", "NHỮNG QUY ĐỊNH CHUNG")


def test_chunk_text_is_article_body_without_heading_line():
    chunks = chunk(short_doc()).chunks

    assert chunks[0].text == "Thông tư này quy định về đăng ký thuế."
    assert chunks[1].text == "Người nộp thuế theo quy định tại Điều 4 Luật Quản lý thuế."


def test_article_title_is_kept_on_the_article():
    articles = chunk(short_doc()).articles

    assert [a.title for a in articles] == ["Phạm vi điều chỉnh", "Đối tượng áp dụng", "Hiệu lực thi hành"]


def test_heading_with_space_before_dot_is_an_article():
    doc = make_doc("Điều 1 . Phạm vi\nNội dung một.", "Điều 2. Hiệu lực\nNội dung hai.", SIGNATURE)

    assert [a.article for a in chunk(doc).articles] == ["1", "2"]


def test_heading_block_preamble_chapter_titles_and_section_titles_are_not_chunked():
    texts = "\n".join(c.text for c in chunk(short_doc()).chunks)

    for excluded in ["CỘNG HÒA", "THÔNG TƯ", "Căn cứ", "QUY ĐỊNH CHUNG", "Chương", "Mục 1", "ĐĂNG KÝ THUẾ LẦN ĐẦU"]:
        assert excluded not in texts


def test_signature_block_after_last_article_is_not_chunked():
    last = chunk(short_doc()).chunks[-1]

    assert last.text == "Người nộp thuế nộp hồ sơ tại cơ quan thuế quản lý trực tiếp."


def test_law_adoption_statement_and_signer_are_not_chunked():
    doc = make_doc(
        "Điều 1. Sửa đổi khoản 1 Điều 7\nNội dung sửa đổi.",
        "Điều 2. Hiệu lực thi hành\nLuật này có hiệu lực từ ngày 01 tháng 01 năm 2026.",
        "_________________________________\nLuật này được Quốc hội nước Cộng hòa xã hội chủ nghĩa Việt Nam "
        "khóa XVI, Kỳ họp thứ Nhất thông qua ngày 24 tháng 4 năm 2026.",
        "CHỦ TỊCH QUỐC HỘI Trần Thanh Mẫn",
    )

    assert chunk(doc).chunks[-1].text == "Luật này có hiệu lực từ ngày 01 tháng 01 năm 2026."


def test_appendix_and_forms_after_signature_are_not_chunked():
    doc = make_doc(
        "Điều 1. Phạm vi\nNội dung.",
        SIGNATURE,
        "Phụ lục I",
        "Mẫu số: 01-ĐKT (Kèm theo Thông tư số 90/2026/TT-BTC ngày 30 tháng 6 năm 2026 của Bộ trưởng Bộ Tài chính)",
        "TỜ KHAI ĐĂNG KÝ THUẾ\n1. Tên người nộp thuế: ……",
    )
    result = chunk(doc)

    assert [c.id for c in result.chunks] == [f"{DOC_ID}:D1"]
    assert result.chunks[0].text == "Nội dung."


def test_form_quoting_an_article_heading_does_not_create_an_article():
    # Circulars 86/2026 and 89/2026: decision forms in the appendix contain "Điều 1." lines.
    doc = make_doc(
        "Điều 1. Phạm vi\nNội dung.",
        "Điều 2. Hiệu lực\nNội dung.",
        SIGNATURE,
        "Mẫu số 69",
        "QUYẾT ĐỊNH\nĐiều 1. Giao cho ông/bà … thực hiện nhiệm vụ.\nĐiều 2. Quyết định này có hiệu lực kể từ ngày ký.",
    )

    assert [a.article for a in chunk(doc).articles] == ["1", "2"]


def test_appendix_without_signature_block_still_ends_article_text():
    # Circular 89/2026: the forms follow the last article with no "Nơi nhận:" in between.
    doc = make_doc(
        "Điều 1. Phạm vi\nNội dung.",
        "Mẫu số: 02/UNT (Kèm theo Thông tư số 89/2026/TT-BTC ngày 30 tháng 6 năm 2026 của Bộ trưởng Bộ Tài chính)",
        "GIẤY ỦY NHIỆM THU THUẾ\nĐiều 1. Bên A ủy nhiệm cho bên B thu thuế.",
    )
    result = chunk(doc)

    assert [a.article for a in result.articles] == ["1"]
    assert result.chunks[0].text == "Nội dung."


# --- Splitting into clauses ----------------------------------------------------------------


def long_article(n_clauses: int = 3, intro: str = "") -> str:
    lines = ["Điều 1. Cấu trúc mã số thuế"] + ([intro] if intro else [])
    return "\n".join(lines + [clause(i) for i in range(1, n_clauses + 1)])


def test_article_over_threshold_is_split_into_its_clauses():
    doc = make_doc(long_article(3), SIGNATURE)  # 3 clauses x 11 words
    result = chunk(doc, max_tokens=20)

    assert [c.id for c in result.chunks] == [f"{DOC_ID}:D1:K1", f"{DOC_ID}:D1:K2", f"{DOC_ID}:D1:K3"]
    assert [c.clause for c in result.chunks] == ["1", "2", "3"]
    assert all(c.parent_id == f"{DOC_ID}:D1" for c in result.chunks)
    assert result.chunks[1].text == clause(2)


def test_article_exactly_at_threshold_is_not_split():
    doc = make_doc(long_article(3), SIGNATURE)
    body_tokens = 3 * 11

    assert [c.id for c in chunk(doc, max_tokens=body_tokens).chunks] == [f"{DOC_ID}:D1"]
    assert len(chunk(doc, max_tokens=body_tokens - 1).chunks) == 3


def test_article_over_threshold_without_clauses_stays_one_chunk():
    body = " ".join(["nội-dung"] * 50)
    doc = make_doc(f"Điều 1. Cấu trúc mã số thuế\n{body}", SIGNATURE)
    result = chunk(doc, max_tokens=20)

    assert [c.id for c in result.chunks] == [f"{DOC_ID}:D1"]
    assert result.chunks[0].text == body


def test_clause_keeps_its_points_and_following_paragraphs():
    doc = make_doc(
        "Điều 1. Cấu trúc mã số thuế\n" + clause(1) + "\na) điểm a;\nb) điểm b.\nTrường hợp khác thì áp dụng điểm a.",
        clause(2),
        SIGNATURE,
    )
    first = chunk(doc, max_tokens=10).chunks[0]

    assert first.text == clause(1) + "\na) điểm a;\nb) điểm b.\nTrường hợp khác thì áp dụng điểm a."


def test_short_intro_before_clause_1_is_not_a_chunk_but_stays_in_the_article():
    intro = "Thông tư này quy định các nội dung sau:"
    doc = make_doc(long_article(3, intro=intro), SIGNATURE)
    result = chunk(doc, max_tokens=20)

    assert [c.clause for c in result.chunks] == ["1", "2", "3"]
    assert result.articles[0].text.startswith(intro + "\n1. ")


def test_long_intro_before_clause_1_becomes_clause_0_chunk():
    intro = " ".join(["mở-đầu"] * (MIN_INTRO_TOKENS + 1))
    doc = make_doc(long_article(3, intro=intro), SIGNATURE)
    result = chunk(doc, max_tokens=20)

    assert result.chunks[0].id == f"{DOC_ID}:D1:K0"
    assert result.chunks[0].clause == "0"
    assert result.chunks[0].text == intro
    assert [c.clause for c in result.chunks[1:]] == ["1", "2", "3"]


def test_intro_exactly_at_intro_threshold_is_not_a_chunk():
    intro = " ".join(["mở-đầu"] * MIN_INTRO_TOKENS)
    doc = make_doc(long_article(3, intro=intro), SIGNATURE)

    assert [c.clause for c in chunk(doc, max_tokens=20).chunks] == ["1", "2", "3"]


# --- Quoted amending text ------------------------------------------------------------------


def amending_doc() -> dict:
    # Law 09/2026 style: the amended clause is quoted, numbered lines inside the quote are its own.
    return make_doc(
        "Điều 1. Sửa đổi, bổ sung Điều 7 của Luật Thuế thu nhập cá nhân\n" + clause(1),
        "2. Sửa đổi Điều 7 như sau:\n“Điều 7. Kỳ tính thuế\n1. Kỳ tính thuế theo năm.\n2. Kỳ tính thuế theo từng lần.”",
        clause(3),
        "Điều 2. Hiệu lực thi hành\nLuật này có hiệu lực từ ngày ký.",
        SIGNATURE,
    )


def test_numbered_lines_inside_a_quotation_are_not_clauses():
    result = chunk(amending_doc(), max_tokens=10)
    article_1 = [c for c in result.chunks if c.article == "1"]

    assert [c.clause for c in article_1] == ["1", "2", "3"]
    assert article_1[1].text.endswith("2. Kỳ tính thuế theo từng lần.”")


def test_article_heading_inside_a_quotation_is_not_an_article():
    multiline_quote = make_doc(
        "Điều 1. Sửa đổi Nghị định 181\n1. Sửa đổi Điều 5 như sau:\n“Điều 5. Đối tượng\nNội dung.",
        "Điều 6. Thời điểm\nNội dung.”",
        "Điều 2. Hiệu lực thi hành\nNội dung.",
        SIGNATURE,
    )

    assert [a.article for a in chunk(multiline_quote).articles] == ["1", "2"]


# --- Malformed sources are reported, not silently fixed --------------------------------------


def test_heading_repeated_in_a_row_keeps_the_longer_occurrence_and_reports_it():
    # Modelled on Decree 253/2026, Article 66: the heading and clause 1 appear twice, the second time complete.
    doc = make_doc(
        "Điều 1. Kỳ tính thuế\n1. Đối với cá nhân cư trú kỳ tính thuế được xác định như sau:",
        "Điều 1. Kỳ tính thuế\n1. Đối với cá nhân cư trú kỳ tính thuế được xác định như sau:\na) Theo năm dương lịch.",
        "Điều 2. Hiệu lực thi hành\nNội dung.",
        SIGNATURE,
    )
    result = chunk(doc)

    assert [a.article for a in result.articles] == ["1", "2"]
    assert result.articles[0].text.endswith("a) Theo năm dương lịch.")
    assert [(i.kind, i.article) for i in result.issues] == [("duplicate_heading", "1")]


def test_gap_in_article_numbering_is_reported():
    doc = make_doc("Điều 1. A\nX.", "Điều 2. B\nX.", "Điều 4. Hiệu lực thi hành\nX.", SIGNATURE)

    assert [(i.kind, i.article) for i in chunk(doc).issues] == [("article_gap", "4")]


def test_document_not_starting_at_article_1_is_reported():
    doc = make_doc("Điều 2. B\nX.", "Điều 3. Hiệu lực thi hành\nX.", SIGNATURE)

    assert [(i.kind, i.article) for i in chunk(doc).issues] == [("article_gap", "2")]


def test_gap_in_clause_numbering_of_a_split_article_is_reported():
    doc = make_doc("Điều 1. Hiệu lực thi hành\n" + clause(1), clause(3), SIGNATURE)

    assert [(i.kind, i.article) for i in chunk(doc, max_tokens=10).issues] == [("clause_numbering", "1")]


def test_unbalanced_quotation_is_reported():
    doc = make_doc("Điều 1. Sửa đổi\n“1. Nội dung không có ngoặc đóng.", "Điều 2. Hiệu lực\nX.", SIGNATURE)

    assert ("unbalanced_quotes", "1") in [(i.kind, i.article) for i in chunk(doc).issues]


def test_quotation_opened_mid_line_and_left_open_ends_at_its_line():
    # A mid-line “ left open once hid 16 of 25 articles in document 439780. Approved on #2.
    doc = make_doc(
        "Điều 1. Hóa đơn\n" + clause(1) + "\nb.1) Đối với bên ủy nhiệm tại Phần 5 “Danh sách chứng thư số;",
        clause(2),
        clause(3),
        "Điều 2. Hiệu lực\nX.",
        SIGNATURE,
    )
    result = chunk(doc, max_tokens=10)

    assert [c.id for c in result.chunks] == [f"{DOC_ID}:D1:K1", f"{DOC_ID}:D1:K2", f"{DOC_ID}:D1:K3", f"{DOC_ID}:D2"]
    assert [(i.kind, i.article) for i in result.issues] == [("unbalanced_quotes", "1")]


def test_quotation_opened_mid_line_and_closed_by_a_later_stray_mark_is_reported():
    # Closed with ’ instead of ”: a later ” used to absorb it silently.
    doc = make_doc(
        "Điều 1. Chỉ tiêu\n- Chỉ tiêu “Tỷ suất lợi nhuận ’.",
        "Điều 2. Hiệu lực thi hành\n1. Sửa đổi như sau: “Nội dung.”” thừa.",
        SIGNATURE,
    )

    assert [(i.kind, i.article) for i in chunk(doc).issues] == [("unbalanced_quotes", "1")]


def test_curly_quotation_closed_with_straight_quote_on_its_line_is_closed_and_reported_softly():
    # Document 439780, Article 9: Phần 5 “Danh sách chứng thư số sử dụng". Approved on #2.
    doc = make_doc(
        "Điều 1. Hóa đơn\n" + clause(1) + '\nb.1) Tại Phần 5 “Danh sách chứng thư số sử dụng", điền đủ;',
        clause(2),
        "Điều 2. Hiệu lực\nX.",
        SIGNATURE,
    )
    result = chunk(doc, max_tokens=10)

    assert [c.id for c in result.chunks] == [f"{DOC_ID}:D1:K1", f"{DOC_ID}:D1:K2", f"{DOC_ID}:D2"]
    assert [(i.kind, i.article) for i in result.issues] == [("mismatched_quotes", "1")]


def test_straight_quote_does_not_close_a_quotation_from_an_earlier_line():
    doc = make_doc(
        "Điều 1. Sửa đổi\n1. Sửa đổi Điều 7 như sau:\n“Điều 7. Kỳ tính thuế",
        '1. Ghi "Kỳ tính thuế" trên tờ khai.',
        "2. Kỳ tính thuế theo từng lần.”",
        "Điều 2. Hiệu lực\nX.",
        SIGNATURE,
    )
    result = chunk(doc, max_tokens=5)

    assert [c.clause for c in result.chunks if c.article == "1"] == ["1"]
    assert result.issues == []


def test_quotation_opened_mid_line_and_closed_on_the_same_line_is_fine():
    doc = make_doc("Điều 1. Hiệu lực thi hành\nHóa đơn ghi dòng chữ “Điều chỉnh cho hóa đơn số…”.", SIGNATURE)

    assert chunk(doc).issues == []


def test_article_heading_hidden_by_an_open_quotation_is_reported():
    # Document 439780: an open quotation once hid Articles 10-25 with no gap to see. Approved on #2.
    doc = make_doc(
        "Điều 1. Sửa đổi\n“1. Nội dung không có ngoặc đóng.",
        "Điều 2. Hiệu lực thi hành\nX.",
        SIGNATURE,
    )
    kinds = [(i.kind, i.article) for i in chunk(doc).issues]

    assert ("hidden_heading", "2") in kinds


def test_quoted_heading_numbered_below_the_last_article_is_not_reported():
    doc = make_doc(
        "Điều 1. Sửa đổi\n1. Sửa đổi như sau:\n“Điều 1. Phạm vi\nNội dung.",
        "Điều 2. Đối tượng\nNội dung.”",
        "Điều 2. Bổ sung\nX.",
        "Điều 3. Hiệu lực thi hành\nX.",
        SIGNATURE,
    )

    assert chunk(doc).issues == []


@pytest.mark.parametrize("title", [
    "Hiệu lực thi hành", "Trách nhiệm thi hành", "Điều khoản chuyển tiếp", "Điều khoản thi hành",
    "Tổ chức thực hiện",
])
def test_last_article_that_closes_the_document_reports_nothing(title):
    doc = make_doc("Điều 1. Phạm vi\nX.", f"Điều 2. {title}\nX.", SIGNATURE)

    assert chunk(doc).issues == []


def test_last_article_that_does_not_close_the_document_is_reported():
    doc = make_doc("Điều 1. Phạm vi\nX.", "Điều 2. Đối tượng áp dụng\nX.", SIGNATURE)

    assert [(i.kind, i.article) for i in chunk(doc).issues] == [("unexpected_last_article", "2")]


def test_well_formed_document_reports_no_issue():
    assert chunk(short_doc()).issues == []
    assert chunk(amending_doc(), max_tokens=10).issues == []


# --- Full articles for context assembly ----------------------------------------------------


def test_every_article_is_kept_in_full_even_when_split():
    doc = make_doc(long_article(3, intro="Mở đầu:"), SIGNATURE)
    article = chunk(doc, max_tokens=20).articles[0]

    assert article.id == f"{DOC_ID}:D1"
    assert article.text == "\n".join(["Mở đầu:", clause(1), clause(2), clause(3)])


def test_clause_chunks_together_with_intro_cover_the_article_text():
    intro = " ".join(["mở-đầu"] * (MIN_INTRO_TOKENS + 1))
    result = chunk(make_doc(long_article(3, intro=intro), SIGNATURE), max_tokens=20)

    assert "\n".join(c.text for c in result.chunks) == result.articles[0].text


# --- Building the corpus files -------------------------------------------------------------


def write_processed(directory: Path) -> None:
    directory.mkdir()
    (directory / "_index.json").write_text(json.dumps({"documents": []}), encoding="utf-8")
    for doc_id, doc in [("500002", short_doc()), ("500001", amending_doc())]:
        doc["source_url"] = doc["source_url"].replace(DOC_ID, doc_id)
        (directory / f"doc-{doc_id}-d1.json").write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_build_writes_chunks_and_articles_for_every_document_sorted_by_doc_id(tmp_path):
    write_processed(tmp_path / "processed")
    build(tmp_path / "processed", tmp_path / "out", count_tokens=words)

    chunks = read_jsonl(tmp_path / "out" / "chunks.jsonl")
    articles = read_jsonl(tmp_path / "out" / "articles.jsonl")

    assert [c["doc_id"] for c in chunks] == sorted(c["doc_id"] for c in chunks)
    assert {c["doc_id"] for c in chunks} == {"500001", "500002"}
    assert [a["id"] for a in articles] == ["500001:D1", "500001:D2", "500002:D1", "500002:D2", "500002:D3"]
    assert set(chunks[0]) == {"id", "doc_id", "chapter", "chapter_title", "article", "clause", "parent_id", "text"}


def test_build_is_deterministic(tmp_path):
    write_processed(tmp_path / "processed")
    build(tmp_path / "processed", tmp_path / "a", count_tokens=words)
    build(tmp_path / "processed", tmp_path / "b", count_tokens=words)

    for name in ["chunks.jsonl", "articles.jsonl"]:
        assert (tmp_path / "a" / name).read_bytes() == (tmp_path / "b" / name).read_bytes()


def test_build_returns_issues_from_every_document(tmp_path):
    processed = tmp_path / "processed"
    processed.mkdir()
    gap = make_doc("Điều 1. A\nX.", "Điều 3. Hiệu lực thi hành\nX.", SIGNATURE, doc_id="500003")
    (processed / "doc-500003-d1.json").write_text(json.dumps(gap, ensure_ascii=False), encoding="utf-8")

    issues = build(processed, tmp_path / "out", count_tokens=words)

    assert [(i.doc_id, i.kind, i.article) for i in issues] == [("500003", "article_gap", "3")]


def test_document_without_site_id_in_url_is_rejected():
    doc = short_doc()
    doc["source_url"] = "https://luatvietnam.vn/thue/no-id.html"

    with pytest.raises(ValueError, match="document id"):
        chunk(doc)
