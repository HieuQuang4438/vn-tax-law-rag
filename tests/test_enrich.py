"""AC-003: every chunk gets a context header, apart from its text. Approach approved on #3.
AC-004: every chunk gets an effective date, or its document is reported. Approach approved on #4.

The header form, the effective-date rules and their reports are in
`docs/reference/chunk-schema.md` (`data/enriched/`). Fixtures are small documents in the shape of
`data/processed/<slug>.json`; tokens are counted as words, so no tokenizer is needed. The corpus
test at the end runs over the local `data/processed/` (gitignored): `pytest -m corpus`.
"""

import json
from pathlib import Path

import pytest

from src.chunking import build as build_chunks
from src.chunking import chunk_document
from src.enrich import build, effective_dates, enrich_document, indexed_text

ROOT = Path(__file__).resolve().parent.parent
DOC_ID = "439827"
CIRCULAR = "[Thông tư 90/2026/TT-BTC — Quy định về đăng ký thuế]"
SIGNATURE = "Nơi nhận: - Lưu: VT, CT. | KT. BỘ TRƯỞNG THỨ TRƯỞNG Cao Anh Tuấn"


def words(text: str) -> int:
    return len(text.split())


def make_doc(*texts: str, doc_id: str = DOC_ID, kind: str = "Thông tư", number: str = "90/2026/TT-BTC",
             title: str = "Quy định về đăng ký thuế", issued: str = "30/06/2026") -> dict:
    return {
        "source_url": f"https://luatvietnam.vn/thue/van-ban-{doc_id}-d1.html",
        "crawled_at": "2026-11-04T00:00:00+00:00",
        "metadata": {"so_hieu": number, "loai_van_ban": kind, "trich_yeu": title, "ngay_ban_hanh": issued},
        "blocks": [{"id": f"demuc{i}", "kind": "docitem-11", "text": t} for i, t in enumerate(texts)],
    }


def clause(n: int, size: int = 10) -> str:
    return f"{n}. " + " ".join(["nội-dung"] * size)


def circular() -> dict:
    return make_doc(
        "Chương I\nQUY ĐỊNH CHUNG",
        "Điều 1. Phạm vi điều chỉnh\nThông tư này quy định về đăng ký thuế.",
        "Chương II\nTHỦ TỤC ĐĂNG KÝ THUẾ",
        "Mục 1\nĐĂNG KÝ THUẾ LẦN ĐẦU",
        "Điều 2. Cấu trúc mã số thuế\n" + "\n".join(clause(i) for i in (1, 2, 3)),
        "Điều 3. Hiệu lực thi hành\nThông tư này có hiệu lực thi hành kể từ ngày 01 tháng 7 năm 2026.",
        SIGNATURE,
    )


def enrich(doc: dict, max_tokens: int = 20, **kwargs):
    return enrich_document(doc, chunk_document(doc, count_tokens=words, max_tokens=max_tokens, **kwargs))


def by_id(chunks) -> dict:
    return {c.id: c for c in chunks}


# --- The header ----------------------------------------------------------------------------


def test_whole_article_header_names_document_chapter_and_article():
    first = by_id(enrich(circular()))[f"{DOC_ID}:D1"]

    assert first.header == f"{CIRCULAR} [Chương I. QUY ĐỊNH CHUNG > Điều 1. Phạm vi điều chỉnh]"


def test_clause_chunk_header_adds_the_clause():
    second = by_id(enrich(circular()))[f"{DOC_ID}:D2:K2"]

    assert second.header == f"{CIRCULAR} [Chương II. THỦ TỤC ĐĂNG KÝ THUẾ > Điều 2. Cấu trúc mã số thuế > Khoản 2]"


def test_section_is_not_in_the_header():
    headers = [c.header for c in enrich(circular())]

    assert not any("Mục" in h or "ĐĂNG KÝ THUẾ LẦN ĐẦU" in h for h in headers)


def test_document_without_chapters_has_no_chapter_part():
    doc = make_doc("Điều 1. Phạm vi\nNội dung.", "Điều 2. Hiệu lực thi hành\nNội dung.", SIGNATURE)

    assert enrich(doc)[0].header == f"{CIRCULAR} [Điều 1. Phạm vi]"


def test_chapter_without_title_shows_its_number_only():
    doc = make_doc("Chương I", "Điều 1. Hiệu lực thi hành\nNội dung.", SIGNATURE)

    assert enrich(doc)[0].header == f"{CIRCULAR} [Chương I > Điều 1. Hiệu lực thi hành]"


def test_article_without_title_shows_its_number_only():
    doc = make_doc("Điều 1.\nNội dung.", "Điều 2. Hiệu lực thi hành\nNội dung.", SIGNATURE)

    assert enrich(doc)[0].header == f"{CIRCULAR} [Điều 1]"


def test_intro_chunk_has_no_clause_part():
    intro = " ".join(["mở-đầu"] * 101)
    doc = make_doc("Điều 1. Hiệu lực thi hành\n" + intro + "\n" + clause(1) + "\n" + clause(2), SIGNATURE)
    intro_chunk = by_id(enrich(doc, min_intro_tokens=100))[f"{DOC_ID}:D1:K0"]

    assert intro_chunk.header == f"{CIRCULAR} [Điều 1. Hiệu lực thi hành]"


def test_repeated_clause_number_shows_the_number_as_written():
    doc = make_doc("Điều 1. Hiệu lực thi hành\n" + "\n".join(clause(i) for i in (1, 2, 2)), SIGNATURE)
    repeated = by_id(enrich(doc))[f"{DOC_ID}:D1:K2.2"]

    assert repeated.header.endswith("> Khoản 2]")


def test_law_header_names_the_law_by_its_kind_number_and_full_trich_yeu():
    title = ("Sửa đổi, bổ sung một số điều của Luật Thuế thu nhập cá nhân, Luật Thuế giá trị gia tăng, "
             "Luật Thuế thu nhập doanh nghiệp và Luật Thuế tiêu thụ đặc biệt")
    doc = make_doc("Điều 1. Hiệu lực thi hành\nNội dung.", SIGNATURE, doc_id="434729",
                   kind="Luật", number="09/2026/QH16", title=title)

    assert enrich(doc)[0].header == f"[Luật 09/2026/QH16 — {title}] [Điều 1. Hiệu lực thi hành]"


@pytest.mark.parametrize("field", ["loai_van_ban", "so_hieu", "trich_yeu"])
def test_document_missing_a_header_field_is_rejected_by_doc_id(field):
    doc = circular()
    del doc["metadata"][field]

    with pytest.raises(ValueError, match=DOC_ID):
        enrich(doc)


# --- Header and text stay apart ------------------------------------------------------------


def test_text_and_every_chunker_field_are_unchanged():
    doc = circular()
    chunked = chunk_document(doc, count_tokens=words, max_tokens=20)
    enriched = enrich_document(doc, chunked)

    assert [c.id for c in enriched] == [c.id for c in chunked.chunks]
    for before, after in zip(chunked.chunks, enriched):
        assert (after.doc_id, after.chapter, after.chapter_title, after.article, after.clause,
                after.parent_id, after.text) == (before.doc_id, before.chapter, before.chapter_title,
                                                 before.article, before.clause, before.parent_id, before.text)


def test_text_shown_for_a_citation_contains_no_header():
    for c in enrich(circular()):
        assert c.header not in c.text
        assert not c.text.startswith("[")


def test_indexed_text_is_header_then_text():
    first = enrich(circular())[0]

    assert indexed_text(first) == first.header + "\n" + first.text


# --- Effective date (AC-004) ---------------------------------------------------------------


# Splits split_article() and none of the effectiveness articles below (at most about 70 words).
SPLIT_AT = 100


def dates(doc: dict, max_tokens: int = SPLIT_AT) -> dict[str, str | None]:
    return {c.id: c.effective_date for c in enrich(doc, max_tokens=max_tokens)}


def date_issues(doc: dict, max_tokens: int = SPLIT_AT) -> list[tuple[str, str]]:
    chunked = chunk_document(doc, count_tokens=words, max_tokens=max_tokens)
    return [(i.kind, i.article) for i in effective_dates(doc, chunked).issues]


def doc_with(effect: str, *articles: str, title: str = "Hiệu lực thi hành", **kwargs) -> dict:
    """Articles 1..n from `articles`, then the effectiveness article holding `effect`."""
    n = len(articles) + 1
    texts = [f"Điều {i}. Quy định {i}\n{body}" for i, body in enumerate(articles, start=1)]
    return make_doc(*texts, f"Điều {n}. {title}\n{effect}", SIGNATURE, **kwargs)


def split_article() -> str:
    return "\n".join(clause(i, size=40) for i in (1, 2, 3))  # 123 words: split at SPLIT_AT


def test_every_chunk_takes_the_documents_date():
    doc = doc_with("Thông tư này có hiệu lực thi hành từ ngày 01 tháng 7 năm 2026.", "Nội dung.", split_article())

    assert set(dates(doc).values()) == {"2026-07-01"}
    assert len(dates(doc)) == 5  # D1, D2:K1..K3, D3


@pytest.mark.parametrize("effect, expected", [
    ("1. Thông tư này có hiệu lực thi hành kể từ ngày 30 tháng 7 năm 2025.", "2025-07-30"),
    ("1. Thông tư này có hiệu lực kể từ ngày 01 tháng 7 năm 2026.", "2026-07-01"),
    ("Thông tư này có hiệu lực thi hành từ ngày 1/7/2026.", "2026-07-01"),
    ("1. Thông tư này có hiệu lực thi hành kể từ ngày ký ban hành.", "2026-06-30"),
    ("1. Thông tư này có hiệu lực thi hành kể từ ngày 01 tháng 7 năm 2026, thay thế Thông tư số 86/2024/TT-BTC.",
     "2026-07-01"),
])
def test_documents_date_forms(effect, expected):
    assert set(dates(doc_with(effect, "Nội dung.")).values()) == {expected}


def test_adoption_date_of_a_law_is_its_issue_date():
    doc = doc_with("Luật này có hiệu lực thi hành từ ngày được thông qua.", "Nội dung.",
                   kind="Luật", number="09/2026/QH16", issued="24/04/2026")

    assert set(dates(doc).values()) == {"2026-04-24"}


def test_effectiveness_article_titled_dieu_khoan_thi_hanh_is_found():
    doc = doc_with("1. Nghị định này có hiệu lực thi hành từ ngày 01 tháng 01 năm 2026.", "Nội dung.",
                   title="Điều khoản thi hành", kind="Nghị định")

    assert set(dates(doc).values()) == {"2026-01-01"}


def test_the_last_effectiveness_article_is_used():
    doc = doc_with("Thông tư này có hiệu lực thi hành từ ngày 01 tháng 7 năm 2026.",
                   "Thông tư này có hiệu lực thi hành từ ngày 01 tháng 01 năm 2020.")
    doc["blocks"][0]["text"] = "Điều 1. Hiệu lực thi hành của thông báo\nThông tư này có hiệu lực thi hành từ ngày 01 tháng 01 năm 2020."

    assert set(dates(doc).values()) == {"2026-07-01"}


def test_article_on_ending_a_tax_code_is_not_the_effectiveness_article():
    doc = make_doc("Điều 1. Các trường hợp chấm dứt hiệu lực mã số thuế\nThông tư này có hiệu lực thi hành từ ngày 01 tháng 01 năm 2020.",
                   "Điều 2. Tổ chức thực hiện\nNội dung.", SIGNATURE)

    assert set(dates(doc).values()) == {None}
    assert date_issues(doc) == [("no_effective_date", "")]


@pytest.mark.parametrize("effect", [
    "Thông tư này có hiệu lực từ ngày ký.",
    "Thông tư này có hiệu lực thi hành sau 45 ngày.",
    "Các Bộ trưởng chịu trách nhiệm thi hành Thông tư này.",
])
def test_unreadable_date_leaves_dates_null_and_is_reported(effect):
    doc = doc_with(effect, "Nội dung.")

    assert set(dates(doc).values()) == {None}
    assert date_issues(doc) == [("no_effective_date", "2")]


def test_check_case_law_09_2026():
    # AC-004: articles 1-3 carry 01/01/2026, the other articles the adoption date 24/04/2026.
    doc = doc_with(
        "1. Luật này có hiệu lực thi hành từ ngày được thông qua, trừ quy định tại khoản 2 Điều này.\n"
        "2. Quy định tại các điều 1, 2 và 3 của Luật này có hiệu lực thi hành từ ngày 01 tháng 01 năm 2026.",
        "Sửa đổi khoản 1 Điều 7.", "Sửa đổi Điều 9.", "Sửa đổi Điều 11.", "Sửa đổi biểu thuế.",
        kind="Luật", number="09/2026/QH16", issued="24/04/2026", doc_id="434729",
    )

    assert dates(doc) == {"434729:D1": "2026-01-01", "434729:D2": "2026-01-01", "434729:D3": "2026-01-01",
                          "434729:D4": "2026-04-24", "434729:D5": "2026-04-24"}
    assert date_issues(doc) == []


def test_whole_article_exception_covers_every_chunk_of_a_split_article():
    doc = doc_with(
        "1. Thông tư này có hiệu lực thi hành từ ngày 01 tháng 7 năm 2026, trừ quy định tại khoản 2 Điều này.\n"
        "2. Quy định tại Điều 2 của Thông tư này có hiệu lực thi hành từ ngày 01 tháng 01 năm 2026.",
        "Nội dung.", split_article(),
    )

    assert dates(doc) == {f"{DOC_ID}:D1": "2026-07-01", f"{DOC_ID}:D2:K1": "2026-01-01",
                          f"{DOC_ID}:D2:K2": "2026-01-01", f"{DOC_ID}:D2:K3": "2026-01-01",
                          f"{DOC_ID}:D3": "2026-07-01"}


def test_clause_exception_covers_that_clause_chunk_of_a_split_article():
    doc = doc_with(
        "1. Thông tư này có hiệu lực thi hành từ ngày 01 tháng 7 năm 2026.\n"
        "2. Quy định tại khoản 2 Điều 1 của Thông tư này có hiệu lực thi hành từ ngày 01 tháng 01 năm 2026.",
        split_article(),
    )

    assert dates(doc) == {f"{DOC_ID}:D1:K1": "2026-07-01", f"{DOC_ID}:D1:K2": "2026-01-01",
                          f"{DOC_ID}:D1:K3": "2026-07-01", f"{DOC_ID}:D2": "2026-07-01"}
    assert date_issues(doc) == []


def test_clause_exception_inside_an_unsplit_article_is_partial():
    doc = doc_with(
        "1. Thông tư này có hiệu lực thi hành từ ngày 01 tháng 7 năm 2026.\n"
        "2. Quy định tại khoản 2 Điều 1 của Thông tư này có hiệu lực thi hành từ ngày 01 tháng 01 năm 2026.",
        split_article(),
    )

    assert set(dates(doc, max_tokens=800).values()) == {"2026-07-01"}
    assert date_issues(doc, max_tokens=800) == [("partial_effective_date", "1")]


def test_subject_inside_a_clause_is_partial_and_a_bare_article_after_it_is_whole():
    # Law 48/2024, Article 18 clause 2.
    doc = doc_with(
        "1. Luật này có hiệu lực thi hành từ ngày 01 tháng 7 năm 2025, trừ trường hợp quy định tại khoản 2 Điều này.\n"
        "2. Quy định về mức doanh thu của hộ, cá nhân sản xuất, kinh doanh thuộc đối tượng không chịu thuế tại "
        "khoản 2 Điều 1 của Luật này và Điều 2 của Luật này có hiệu lực thi hành từ ngày 01 tháng 01 năm 2026.",
        split_article(), "Nội dung.", kind="Luật", number="48/2024/QH15",
    )

    assert dates(doc) == {f"{DOC_ID}:D1:K1": "2025-07-01", f"{DOC_ID}:D1:K2": "2025-07-01",
                          f"{DOC_ID}:D1:K3": "2025-07-01", f"{DOC_ID}:D2": "2026-01-01",
                          f"{DOC_ID}:D3": "2025-07-01"}
    assert date_issues(doc) == [("partial_effective_date", "1")]


def test_bare_article_then_subject_inside_an_article():
    # Law 108/2025, Article 52 clause 2.
    doc = doc_with(
        "1. Luật này có hiệu lực thi hành từ ngày 01 tháng 7 năm 2026, trừ quy định tại khoản 2 Điều này.\n"
        "2. Quy định tại Điều 1 và việc sử dụng hóa đơn điện tử của hộ kinh doanh, cá nhân kinh doanh quy định "
        "tại Điều 2 của Luật này có hiệu lực thi hành từ ngày 01 tháng 01 năm 2026.",
        "Nội dung.", split_article(), kind="Luật", number="108/2025/QH15",
    )

    assert dates(doc) == {f"{DOC_ID}:D1": "2026-01-01", f"{DOC_ID}:D2:K1": "2026-07-01",
                          f"{DOC_ID}:D2:K2": "2026-07-01", f"{DOC_ID}:D2:K3": "2026-07-01",
                          f"{DOC_ID}:D3": "2026-07-01"}
    assert date_issues(doc) == [("partial_effective_date", "2")]


def test_point_exception_is_partial():
    doc = doc_with(
        "1. Nghị định này có hiệu lực thi hành từ ngày 01 tháng 7 năm 2026.\n"
        "2. Quy định tại điểm a khoản 2 Điều 1 của Nghị định này có hiệu lực thi hành từ ngày 01 tháng 01 năm 2027.",
        split_article(), kind="Nghị định",
    )

    assert set(dates(doc).values()) == {"2026-07-01"}
    assert date_issues(doc) == [("partial_effective_date", "1")]


@pytest.mark.parametrize("line", [
    # Decree 252/2026: another document stays in force.
    "4. Nghị định số 125/2020/NĐ-CP ngày 19 tháng 10 năm 2020 của Chính phủ tiếp tục có hiệu lực thi hành "
    "kể từ ngày 01 tháng 7 năm 2026 cho đến khi có văn bản thay thế.",
    # Law 108/2025: a provision of another document ceases to apply.
    "3. Luật Quản lý thuế số 38/2019/QH14 hết hiệu lực thi hành kể từ ngày Luật này có hiệu lực thi hành; riêng "
    "quy định tại Điều 51 của Luật Quản lý thuế số 38/2019/QH14 hết hiệu lực thi hành kể từ ngày 01 tháng 01 năm 2026.",
])
def test_line_about_another_document_is_not_an_exception(line):
    doc = doc_with("1. Nghị định này có hiệu lực thi hành từ ngày 01 tháng 7 năm 2026.\n" + line, "Nội dung.",
                   kind="Nghị định")

    assert set(dates(doc).values()) == {"2026-07-01"}
    assert date_issues(doc) == []


def test_application_rules_change_no_date_and_are_reported_per_line():
    # Decree 253/2026, Article 69 clause 1.
    doc = doc_with(
        "1. Nghị định này có hiệu lực thi hành từ ngày 01 tháng 7 năm 2026. Việc xác định thời gian áp dụng "
        "trong một số trường hợp cụ thể như sau:\n"
        "a) Các quy định liên quan đến thu nhập từ kinh doanh của cá nhân cư trú áp dụng từ kỳ tính thuế năm 2026;\n"
        "b) Quy định về tiền ăn giữa ca tại điểm g khoản 2 Điều 1 của Nghị định này áp dụng từ ngày 01 tháng 7 năm 2026.",
        "Nội dung.", kind="Nghị định",
    )

    assert set(dates(doc).values()) == {"2026-07-01"}
    assert date_issues(doc) == [("application_period", "2"), ("application_period", "2")]


def test_application_rule_on_the_documents_own_line_is_reported():
    # Law 67/2025, Article 19 clause 1.
    doc = doc_with("1. Luật này có hiệu lực thi hành từ ngày 01 tháng 10 năm 2025 và áp dụng từ kỳ tính thuế "
                   "thu nhập doanh nghiệp năm 2025.", "Nội dung.", kind="Luật")

    assert set(dates(doc).values()) == {"2025-10-01"}
    assert date_issues(doc) == [("application_period", "2")]


def test_end_date_is_reported_and_not_modelled():
    # Decree 252/2026, Article 74 clause 2.
    doc = doc_with(
        "1. Nghị định này có hiệu lực thi hành kể từ ngày 01 tháng 7 năm 2026.\n"
        "2. Quy định về phân bổ thuế tại điểm a.2 khoản 2 Điều 1 Nghị định này thực hiện đến hết ngày 31 tháng 12 năm 2026.",
        split_article(), kind="Nghị định",
    )

    assert set(dates(doc).values()) == {"2026-07-01"}
    assert date_issues(doc) == [("effective_until", "2")]


def test_retroactive_date_is_kept_as_written():
    # Decree 141/2026: issued 29/04/2026, in force from 01/01/2026.
    doc = doc_with("Nghị định này có hiệu lực thi hành từ ngày 01 tháng 01 năm 2026.", "Nội dung.",
                   kind="Nghị định", issued="29/04/2026")

    assert set(dates(doc).values()) == {"2026-01-01"}
    assert date_issues(doc) == []


# --- Building the enriched file ------------------------------------------------------------


def write_processed(directory: Path) -> None:
    directory.mkdir()
    (directory / "_index.json").write_text(json.dumps({"documents": []}), encoding="utf-8")
    for doc_id in ("500002", "500001"):
        doc = circular()
        doc["source_url"] = doc["source_url"].replace(DOC_ID, doc_id)
        (directory / f"doc-{doc_id}-d1.json").write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def built(tmp_path: Path, out: str = "enriched") -> Path:
    processed, chunks = tmp_path / "processed", tmp_path / "chunks"
    if not processed.exists():
        write_processed(processed)
        build_chunks(processed, chunks, count_tokens=words, max_tokens=20)
    build(processed, chunks, tmp_path / out)
    return tmp_path / out / "chunks.jsonl"


def test_build_writes_every_chunk_in_chunker_order_with_its_header(tmp_path):
    enriched = read_jsonl(built(tmp_path))
    chunks = read_jsonl(tmp_path / "chunks" / "chunks.jsonl")

    assert [c["id"] for c in enriched] == [c["id"] for c in chunks]
    assert all(e == {**c, "header": e["header"], "effective_date": "2026-07-01"} for e, c in zip(enriched, chunks))
    assert enriched[0]["header"] == f"{CIRCULAR} [Chương I. QUY ĐỊNH CHUNG > Điều 1. Phạm vi điều chỉnh]"
    assert "indexed_text" not in enriched[0]


def test_build_is_deterministic(tmp_path):
    first, second = built(tmp_path, "a"), built(tmp_path, "b")

    assert first.read_bytes() == second.read_bytes()
    assert (tmp_path / "a" / "issues.jsonl").read_bytes() == (tmp_path / "b" / "issues.jsonl").read_bytes()


def test_build_writes_effective_date_issues_ordered_by_doc_id(tmp_path):
    processed, chunks = tmp_path / "processed", tmp_path / "chunks"
    processed.mkdir()
    for doc_id in ("500002", "500001"):
        doc = make_doc("Điều 1. Phạm vi\nNội dung.", "Điều 2. Hiệu lực thi hành\nThông tư này có hiệu lực sớm.",
                       SIGNATURE, doc_id=doc_id)
        (processed / f"doc-{doc_id}-d1.json").write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    build_chunks(processed, chunks, count_tokens=words)
    build(processed, chunks, tmp_path / "enriched")

    issues = read_jsonl(tmp_path / "enriched" / "issues.jsonl")
    assert [(i["doc_id"], i["kind"]) for i in issues] == [("500001", "no_effective_date"),
                                                          ("500002", "no_effective_date")]
    assert set(issues[0]) == {"doc_id", "kind", "article", "detail"}
    assert all(c["effective_date"] is None for c in read_jsonl(tmp_path / "enriched" / "chunks.jsonl"))


# --- The real corpus (AC-003) --------------------------------------------------------------

REAL_PROCESSED = ROOT / "data" / "processed"


def corpus_docs() -> list[dict]:
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(REAL_PROCESSED.glob("*-d1.json"))]


@pytest.mark.corpus
@pytest.mark.skipif(not list(REAL_PROCESSED.glob("*-d1.json")), reason="needs data/processed/")
def test_corpus_every_chunk_has_a_complete_header_apart_from_its_text():
    problems = []
    for doc in corpus_docs():
        chunked = chunk_document(doc, count_tokens=words)
        problems += [(i.doc_id, i.kind, i.article) for i in chunked.issues if i.kind == "missing_chapter_title"]
        meta = doc["metadata"]
        for c in enrich_document(doc, chunked):
            expected_start = f"[{meta['loai_van_ban']} {meta['so_hieu']} — {meta['trich_yeu']}] ["
            if not c.header.startswith(expected_start):
                problems.append((c.id, "document part", c.header[:80]))
            if c.chapter and f"{c.chapter}. {c.chapter_title} > " not in c.header:
                problems.append((c.id, "chapter part", c.header[-80:]))
            if f"Điều {c.article}" not in c.header:
                problems.append((c.id, "article part", c.header[-80:]))
            if (c.clause not in (None, "0")) != c.header.endswith(f"> Khoản {c.clause}]"):
                problems.append((c.id, "clause part", c.header[-80:]))
            if c.text.startswith(c.header) or c.header in c.text:
                problems.append((c.id, "header in text", None))
    assert problems == []


# Hand-checked from each document's effectiveness article (2026-11-12), not from the code; the rows
# that differ from a plain default date (379409, 421539, 434729, 421582, 439382) were re-read against
# the source by a second person:
# doc_id: (default date, {(article, clause or None): date} whole exceptions,
#          [articles with a partial exception], application_period lines, effective_until lines).
EXPECTED_DATES = {
    "379409": ("2025-07-01", {("17", None): "2026-01-01"}, ["5"], 0, 0),  # 48/2024/QH15
    "404357": ("2025-07-01", {}, [], 0, 0),  # 181/2025/NĐ-CP
    "404386": ("2025-10-01", {}, [], 1, 0),  # 67/2025/QH15
    "404453": ("2025-07-01", {}, [], 0, 0),  # 69/2025/TT-BTC
    "405694": ("2026-01-01", {}, [], 0, 0),  # 66/2025/QH15
    "406967": ("2025-07-30", {}, [], 0, 0),  # 77/2025/TT-BTC
    "421539": ("2026-07-01", {("13", None): "2026-01-01"}, ["26"], 0, 0),  # 108/2025/QH15
    "421582": ("2025-12-15", {}, [], 3, 0),  # 320/2025/NĐ-CP, from its signing
    "421739": ("2026-01-01", {}, [], 0, 0),  # 149/2025/QH15
    "422733": ("2026-07-01", {}, [], 1, 0),  # 109/2025/QH15
    "422898": ("2026-01-01", {}, [], 0, 0),  # 359/2025/NĐ-CP
    "422908": ("2026-01-01", {}, [], 0, 0),  # 158/2025/TT-BTC
    "422910": ("2026-01-01", {}, [], 0, 0),  # 360/2025/NĐ-CP
    "427630": ("2026-03-05", {}, [], 0, 0),  # 68/2026/NĐ-CP, from its signing
    "427777": ("2026-03-05", {}, [], 0, 0),  # 18/2026/TT-BTC, from its signing
    "428454": ("2026-03-12", {}, [], 2, 0),  # 20/2026/TT-BTC
    "433387": ("2026-01-01", {}, [], 0, 0),  # 141/2026/NĐ-CP, retroactive
    "433921": ("2026-06-20", {}, [], 0, 0),  # 144/2026/NĐ-CP
    "434628": ("2026-05-13", {}, [], 0, 0),  # 50/2026/TT-BTC, from its signing
    "434729": ("2026-04-24", {("1", None): "2026-01-01", ("2", None): "2026-01-01",
                              ("3", None): "2026-01-01"}, [], 0, 0),  # 09/2026/QH16, AC-004 check case
    "439303": ("2026-07-01", {}, [], 2, 0),  # 253/2026/NĐ-CP
    "439381": ("2026-07-01", {}, [], 0, 0),  # 254/2026/NĐ-CP
    "439382": ("2026-07-01", {}, [], 0, 1),  # 252/2026/NĐ-CP
    "439434": ("2026-07-01", {}, [], 1, 0),  # 87/2026/TT-BTC
    "439613": ("2026-07-01", {}, [], 1, 0),  # 255/2026/NĐ-CP
    "439660": ("2026-07-01", {}, [], 0, 0),  # 86/2026/TT-BTC
    "439780": ("2026-07-01", {}, [], 0, 0),  # 91/2026/TT-BTC
    "439781": ("2026-07-01", {}, [], 0, 0),  # 94/2026/TT-BTC
    "439827": ("2026-07-01", {}, [], 0, 0),  # 90/2026/TT-BTC
    "440483": ("2026-07-01", {}, [], 0, 0),  # 89/2026/TT-BTC
}


@pytest.mark.corpus
@pytest.mark.skipif(not list(REAL_PROCESSED.glob("*-d1.json")), reason="needs data/processed/")
def test_corpus_effective_dates_match_the_hand_checked_table():
    from src.chunking.tokens import bge_m3_token_counter  # real splits: exceptions name clause chunks

    count = bge_m3_token_counter()
    seen = set()
    problems = []
    for doc in corpus_docs():
        chunked = chunk_document(doc, count_tokens=count)
        doc_id = chunked.articles[0].doc_id
        seen.add(doc_id)
        default, whole, partial, applications, until = EXPECTED_DATES[doc_id]
        for c in enrich_document(doc, chunked):
            expected = whole.get((c.article, c.clause), whole.get((c.article, None), default))
            if c.effective_date != expected:
                problems.append((c.id, c.effective_date, expected))
        issues = effective_dates(doc, chunked).issues
        got = ([i.article for i in issues if i.kind == "partial_effective_date"],
               sum(i.kind == "application_period" for i in issues),
               sum(i.kind == "effective_until" for i in issues),
               [i.kind for i in issues if i.kind == "no_effective_date"])
        if got != (partial, applications, until, []):
            problems.append((doc_id, got, (partial, applications, until, [])))
    assert seen == set(EXPECTED_DATES)
    assert problems == []
