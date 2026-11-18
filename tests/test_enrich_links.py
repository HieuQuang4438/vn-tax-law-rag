"""AC-005: amendment links, from the amending side, inverted onto the amended chunks. Approach
approved on #5.

The rules are in `docs/reference/chunk-schema.md` (*Amendment links*, `data/enriched/links.jsonl`).
Fixtures are small documents in the shape of `data/processed/<slug>.json`; tokens are counted as
words. The corpus test at the end compares the real build with the hand-checked list in
`tests/fixtures/amendment_links.csv`: `pytest -m corpus`.
"""

import csv
import json
from pathlib import Path

import pytest

from src.chunking import build as build_chunks
from src.chunking import chunk_document
from src.enrich import amendment_links, build

ROOT = Path(__file__).resolve().parent.parent
SIGNATURE = "Nơi nhận: - Lưu: VT. | CHỦ TỊCH"
VAT_LAW, VAT_NUMBER = "500001", "48/2024/QH15"
EFFECT_2026 = "Điều {n}. Hiệu lực thi hành\n{kind} này có hiệu lực thi hành từ ngày 01 tháng 01 năm 2026."


def words(text: str) -> int:
    return len(text.split())


def make_doc(doc_id: str, kind: str, number: str, title: str, *articles: str) -> dict:
    return {
        "source_url": f"https://luatvietnam.vn/thue/van-ban-{doc_id}-d1.html",
        "crawled_at": "2026-11-04T00:00:00+00:00",
        "metadata": {"so_hieu": number, "loai_van_ban": kind, "trich_yeu": title, "ngay_ban_hanh": "01/12/2025"},
        "blocks": [{"id": f"demuc{i}", "kind": "docitem-11", "text": t} for i, t in enumerate([*articles, SIGNATURE])],
    }


def clauses(*numbers: int, size: int = 10) -> str:
    return "\n".join(f"{n}. " + " ".join(["nội-dung"] * size) for n in numbers)


def vat_law() -> dict:
    """The amended law: Article 5 is split into clauses 1-3, Article 9 is one chunk."""
    return make_doc(
        VAT_LAW, "Luật", VAT_NUMBER, "Thuế giá trị gia tăng",
        "Điều 1. Phạm vi điều chỉnh\nLuật này quy định về thuế giá trị gia tăng.",
        "Điều 5. Đối tượng không chịu thuế\n" + clauses(1, 2, 3),
        "Điều 9. Thuế suất\n1. Mức thuế suất 0%.",
        EFFECT_2026.format(n=10, kind="Luật"),
    )


def amending_law(*lines: str, doc_id: str = "500002", number: str = "149/2025/QH15",
                 title: str = "Sửa đổi, bổ sung một số điều của Luật Thuế giá trị gia tăng",
                 article_title: str = "Sửa đổi, bổ sung một số điều của Luật Thuế giá trị gia tăng",
                 effect: str = "Luật này có hiệu lực thi hành từ ngày 01 tháng 01 năm 2026.") -> dict:
    return make_doc(doc_id, "Luật", number, title,
                    f"Điều 1. {article_title}\n" + "\n".join(lines),
                    f"Điều 2. Hiệu lực thi hành\n{effect}")


def circular(*effect_lines: str, doc_id: str = "500003", body: str = "Thông tư này quy định về hóa đơn.") -> dict:
    """A document that is not an amending one: only its effectiveness article is read."""
    return make_doc(doc_id, "Thông tư", "90/2026/TT-BTC", "Quy định về hóa đơn",
                    f"Điều 1. Phạm vi điều chỉnh\n{body}",
                    "Điều 2. Hiệu lực thi hành\n1. Thông tư này có hiệu lực thi hành từ ngày 01 tháng 7 năm 2026.\n"
                    + "\n".join(effect_lines))


def chunked(doc: dict):
    # Only the amended law's long article is split; directives stay whole-article chunks.
    max_tokens = 20 if doc["metadata"]["trich_yeu"] == "Thuế giá trị gia tăng" else 1000
    return doc, chunk_document(doc, count_tokens=words, max_tokens=max_tokens)


def links_of(*docs: dict):
    return amendment_links([chunked(d) for d in docs])


def rows(result) -> list[tuple]:
    return [(l.type, l.source, l.target_number, l.target_article, l.target_clause, l.target_point,
             l.target_part, l.target_chunks, l.in_corpus) for l in result.links]


def targets(result) -> list[tuple]:
    return [(l.type, l.target_number, l.target_article, l.target_clause, l.target_point, l.target_part)
            for l in result.links]


# --- Amending documents --------------------------------------------------------------------


def test_amending_law_links_the_clauses_it_names_in_the_law_its_title_names():
    result = links_of(vat_law(), amending_law(
        "1. Sửa đổi, bổ sung một số khoản của Điều 5 như sau:",
        "a) Sửa đổi, bổ sung khoản 1 như sau:",
        "“1. Hàng hóa nhập khẩu.”;",
        "2. Bãi bỏ khoản 3 Điều 5 và khoản 1 Điều 9.",
    ))

    assert rows(result) == [
        ("amends", "500002:D1", VAT_NUMBER, "5", "1", None, None, [f"{VAT_LAW}:D5:K1"], True),
        ("repeals", "500002:D1", VAT_NUMBER, "5", "3", None, None, [f"{VAT_LAW}:D5:K3"], True),
        ("repeals", "500002:D1", VAT_NUMBER, "9", "1", None, None, [f"{VAT_LAW}:D9"], True),
    ]


def test_every_in_corpus_target_chunk_lists_the_link_in_amended_by():
    result = links_of(vat_law(), amending_law("1. Bãi bỏ khoản 3 Điều 5."))

    assert result.amended_by == {f"{VAT_LAW}:D5:K3": [{"type": "repeals", "source": "500002:D1"}]}


def test_quoted_new_wording_is_never_read_as_a_directive():
    result = links_of(vat_law(), amending_law(
        "1. Sửa đổi, bổ sung khoản 2 Điều 5 như sau:",
        "“2. Bãi bỏ khoản 1 Điều 9 đối với hàng hóa",
        "Sửa đổi, bổ sung khoản 3 Điều 5 khi cần.”",
        "2. Sửa đổi cụm từ “bãi bỏ khoản 1 Điều 5” thành “hủy” tại khoản 3 Điều 5.",
    ))

    assert targets(result) == [("amends", VAT_NUMBER, "5", "2", None, None),
                               ("amends", VAT_NUMBER, "5", "3", None, None)]


def test_directive_in_the_article_title_links_from_the_articles_first_chunk():
    amending = amending_law("“2. Nội dung mới.”",
                            article_title="Sửa đổi, bổ sung khoản 2 Điều 5 của Luật Thuế giá trị gia tăng")

    assert rows(links_of(vat_law(), amending)) == [
        ("amends", "500002:D1", VAT_NUMBER, "5", "2", None, None, [f"{VAT_LAW}:D5:K2"], True),
    ]


def test_law_named_without_number_resolves_to_the_corpus_law_of_that_name():
    pit = make_doc("500004", "Luật", "109/2025/QH15", "Thuế thu nhập cá nhân",
                   "Điều 7. Thuế đối với thu nhập từ kinh doanh\n1. Nội dung.",
                   EFFECT_2026.format(n=8, kind="Luật"))
    amending = amending_law("“1. Mới.”",
                            title="Sửa đổi, bổ sung một số điều của Luật Thuế thu nhập cá nhân, Luật Thuế giá trị gia tăng",
                            article_title="Sửa đổi, bổ sung khoản 1 Điều 7 của Luật Thuế thu nhập cá nhân")

    assert rows(links_of(vat_law(), pit, amending)) == [
        ("amends", "500002:D1", "109/2025/QH15", "7", "1", None, None, ["500004:D7"], True),
    ]


def test_document_comes_from_the_trich_yeu_and_the_point_from_the_enclosing_title():
    decree = make_doc("500005", "Nghị định", "181/2025/NĐ-CP", "Quy định chi tiết Luật Thuế giá trị gia tăng",
                      "Điều 23. Khấu trừ\n1. Nội dung.\n2. Điểm:\na) một.\nb) hai.",
                      EFFECT_2026.format(n=24, kind="Nghị định"))
    amending = make_doc("500006", "Nghị định", "144/2026/NĐ-CP",
                        "Sửa đổi, bổ sung một số điều của Nghị định 181/2025/NĐ-CP ngày 01/7/2025 của Chính phủ",
                        "Điều 1. Sửa đổi, bổ sung một số điểm của khoản 2 Điều 23\n"
                        "1. Sửa đổi, bổ sung điểm a như sau:\n“a) một mới.”\n"
                        "2. Bổ sung điểm c vào sau điểm b như sau:\n“c) ba.”",
                        EFFECT_2026.format(n=2, kind="Nghị định"))

    assert rows(links_of(decree, amending)) == [
        ("amends", "500006:D1", "181/2025/NĐ-CP", "23", "2", "a", None, ["500005:D23"], True),
        ("amends", "500006:D1", "181/2025/NĐ-CP", "23", "2", "c", None, ["500005:D23"], True),
    ]


def test_added_clause_maps_to_the_clause_it_is_placed_after():
    result = links_of(vat_law(), amending_law("1. Bổ sung khoản 1b sau khoản 1 Điều 5 như sau:", "“1b. Mới.”"))

    assert rows(result) == [("amends", "500002:D1", VAT_NUMBER, "5", "1b", None, None, [f"{VAT_LAW}:D5:K1"], True)]


def test_added_clause_without_after_maps_to_the_highest_clause_below_it():
    result = links_of(vat_law(), amending_law("1. Bổ sung khoản 4 Điều 5 như sau:", "“4. Mới.”"))

    assert result.links[0].target_clause == "4"
    assert result.links[0].target_chunks == [f"{VAT_LAW}:D5:K3"]


def test_phrase_change_gives_one_link_per_provision_named():
    result = links_of(vat_law(), amending_law(
        "1. Sửa đổi cụm từ “500 triệu đồng” thành “01 tỷ đồng” tại Điều 1, khoản 1 và khoản 2 Điều 5 Luật số 48/2024/QH15.",
    ))

    assert [(l.target_article, l.target_clause, l.target_chunks) for l in result.links] == [
        ("1", None, [f"{VAT_LAW}:D1"]),
        ("5", "1", [f"{VAT_LAW}:D5:K1"]),
        ("5", "2", [f"{VAT_LAW}:D5:K2"]),
    ]


def test_article_target_maps_to_every_chunk_of_the_article():
    result = links_of(vat_law(), amending_law("1. Sửa đổi, bổ sung Điều 5 như sau:", "“Điều 5. Mới.”"))

    assert result.links[0].target_chunks == [f"{VAT_LAW}:D5:K1", f"{VAT_LAW}:D5:K2", f"{VAT_LAW}:D5:K3"]


def test_annexes_and_forms_are_parts_with_no_chunks():
    result = links_of(vat_law(), amending_law(
        "1. Thay thế Danh mục (Phụ lục I, Phụ lục II) ban hành kèm theo Luật số 48/2024/QH15 thành Danh mục "
        "(Phụ lục I, Phụ lục II) ban hành kèm theo Luật này.",
        "2. Thay thế Mẫu số 01/CNKD, Mẫu số 01/BĐS theo danh mục mẫu biểu ban hành kèm theo Luật số 48/2024/QH15 "
        "bằng Mẫu số 01/CNKD, Mẫu số 01/BĐS ban hành kèm theo Luật này.",
    ))

    assert [(l.type, l.target_part, l.target_article, l.target_chunks) for l in result.links] == [
        ("replaces", "Phụ lục I", None, []),
        ("replaces", "Phụ lục II", None, []),
        ("replaces", "Mẫu số 01/CNKD", None, []),
        ("replaces", "Mẫu số 01/BĐS", None, []),
    ]
    assert result.amended_by == {}


def test_two_targets_of_one_source_in_one_chunk_give_one_entry():
    result = links_of(vat_law(), amending_law("1. Sửa đổi cụm từ “a” thành “b” tại khoản 1 và khoản 2 Điều 9."))

    assert len(result.links) == 2
    assert result.amended_by == {f"{VAT_LAW}:D9": [{"type": "amends", "source": "500002:D1"}]}


def test_two_amenders_of_one_clause_are_ordered_by_their_effective_date():
    later = amending_law("1. Sửa đổi, bổ sung khoản 2 Điều 5 như sau:", "“2. Mới.”")
    earlier = amending_law("1. Sửa đổi, bổ sung khoản 2 Điều 5 như sau:", "“2. Cũ.”", doc_id="500007",
                           number="09/2026/QH16", effect="Luật này có hiệu lực thi hành từ ngày 01 tháng 7 năm 2025.")

    assert links_of(vat_law(), later, earlier).amended_by[f"{VAT_LAW}:D5:K2"] == [
        {"type": "amends", "source": "500007:D1"},
        {"type": "amends", "source": "500002:D1"},
    ]


def test_ordinary_document_body_is_not_read_for_directives():
    result = links_of(vat_law(), circular(body="5. Sửa đổi, bổ sung khoản 1 Điều 5 Luật số 48/2024/QH15 khi cần."))

    assert result.links == [] and result.issues == []


# --- Effectiveness articles ----------------------------------------------------------------


def test_replaced_document_outside_the_corpus_is_kept_and_marked():
    result = links_of(circular("2. Thông tư này thay thế Thông tư số 40/2021/TT-BTC ngày 01 tháng 6 năm 2021 "
                               "của Bộ trưởng Bộ Tài chính hướng dẫn thuế."))

    assert rows(result) == [("replaces", "500003:D2", "40/2021/TT-BTC", None, None, None, None, [], False)]
    assert result.links[0].target_doc is None


def test_list_items_take_the_type_of_the_line_that_opens_the_list():
    result = links_of(circular(
        "2. Thông tư này thay thế:",
        "a) Thông tư số 219/2013/TT-BTC ngày 31 tháng 12 năm 2013 hướng dẫn thi hành Luật Thuế giá trị gia tăng "
        "và Nghị định số 209/2013/NĐ-CP ngày 18 tháng 12 năm 2013 của Chính phủ.",
        "b) Thông tư số 193/2015/TT-BTC sửa đổi, bổ sung Thông tư số 219/2013/TT-BTC.",
        "3. Bãi bỏ quy định tại:",
        "a) Điều 2 Nghị định số 91/2014/NĐ-CP sửa đổi, bổ sung một số điều tại các Nghị định quy định về thuế.",
        "b) Điều 1, Điều 2 Thông tư số 25/2018/TT-BTC hướng dẫn Nghị định số 146/2017/NĐ-CP và sửa đổi, bổ sung "
        "một số điều của Thông tư số 78/2014/TT-BTC, Thông tư số 111/2013/TT-BTC.",
        "c) Bỏ cụm từ “hạch toán” tại điểm a khoản 3 Điều 11 Thông tư số 328/2016/TT-BTC.",
    ))

    assert targets(result) == [
        ("replaces", "219/2013/TT-BTC", None, None, None, None),
        ("replaces", "193/2015/TT-BTC", None, None, None, None),
        ("repeals", "91/2014/NĐ-CP", "2", None, None, None),
        ("repeals", "25/2018/TT-BTC", "1", None, None, None),
        ("repeals", "25/2018/TT-BTC", "2", None, None, None),
        ("amends", "328/2016/TT-BTC", "11", "3", "a", None),
    ]


def test_line_on_how_to_read_amended_references_is_not_a_directive():
    result = links_of(circular("3. Trường hợp các văn bản quy phạm pháp luật viện dẫn tại Thông tư này được sửa đổi, "
                               "bổ sung hoặc thay thế thì thực hiện theo văn bản được sửa đổi, bổ sung hoặc thay thế đó."))

    assert result.links == [] and result.issues == []


def test_documents_named_in_a_targets_history_are_not_targets():
    result = links_of(circular(
        "2. Luật Thuế giá trị gia tăng số 13/2008/QH12 đã được sửa đổi, bổ sung một số điều theo Luật số "
        "31/2013/QH13, Luật số 71/2014/QH13 và Luật số 106/2016/QH13 hết hiệu lực kể từ ngày Thông tư này có hiệu lực thi hành.",
    ))

    assert targets(result) == [("repeals", "13/2008/QH12", None, None, None, None)]


def test_second_document_of_the_same_kind_after_va_is_a_target():
    result = links_of(circular(
        "2. Nghị định số 132/2020/NĐ-CP ngày 05 tháng 11 năm 2020 quy định về giao dịch liên kết và Nghị định số "
        "20/2025/NĐ-CP ngày 10 tháng 02 năm 2025 của Chính phủ hết hiệu lực kể từ ngày Thông tư này có hiệu lực thi hành.",
        "3. Thông tư này thay thế Thông tư số 40/2021/TT-BTC hướng dẫn thuế; Thông tư số 100/2021/TT-BTC sửa đổi, "
        "bổ sung một số điều của Thông tư số 40/2021/TT-BTC.",
    ))

    assert targets(result) == [
        ("repeals", "132/2020/NĐ-CP", None, None, None, None),
        ("repeals", "20/2025/NĐ-CP", None, None, None, None),
        ("replaces", "40/2021/TT-BTC", None, None, None, None),
        ("replaces", "100/2021/TT-BTC", None, None, None, None),
    ]


def test_provision_runs_skip_parentheses_and_continue_after_a_comma():
    result = links_of(circular(
        "2. Thông tư này bãi bỏ các quy định tại:",
        "a) Điều 1, Điều 13 (trừ điểm b.11 khoản 1 Điều 13) và Điều 16 Thông tư số 103/2014/TT-BTC hướng dẫn thuế;",
        "b) Quy định tại điểm a khoản 1 Điều 11 Nghị định số 134/2016/NĐ-CP ngày 01 tháng 9 năm 2016 của Chính phủ "
        "(đã được sửa đổi, bổ sung tại Nghị định số 18/2021/NĐ-CP), điểm b khoản 2 Điều 4 và Mẫu số 14, Phụ lục II "
        "ban hành kèm theo Nghị định số 26/2023/NĐ-CP.",
        "c) Các điểm b, c và điểm d khoản 1; khoản 2 Điều 7 Thông tư số 328/2016/TT-BTC.",
    ))

    assert targets(result) == [
        ("repeals", "103/2014/TT-BTC", "1", None, None, None),
        ("repeals", "103/2014/TT-BTC", "13", None, None, None),
        ("repeals", "103/2014/TT-BTC", "16", None, None, None),
        ("repeals", "134/2016/NĐ-CP", "11", "1", "a", None),
        ("repeals", "26/2023/NĐ-CP", "4", "2", "b", None),
        ("repeals", "26/2023/NĐ-CP", None, None, None, "Mẫu số 14, Phụ lục II"),
        ("repeals", "328/2016/TT-BTC", "7", "1", "b", None),
        ("repeals", "328/2016/TT-BTC", "7", "1", "c", None),
        ("repeals", "328/2016/TT-BTC", "7", "1", "d", None),
        ("repeals", "328/2016/TT-BTC", "7", "2", None, None),
    ]


def test_each_part_with_het_hieu_luc_is_a_directive_and_one_without_a_target_is_reported():
    line = ("3. Luật Quản lý thuế số 38/2019/QH14 hết hiệu lực thi hành kể từ ngày Thông tư này có hiệu lực thi "
            "hành, trừ quy định tại khoản 1 Điều 53 của Thông tư này; riêng quy định tại Điều 51 của Luật Quản lý thuế "
            "số 38/2019/QH14 hết hiệu lực thi hành kể từ ngày 01 tháng 01 năm 2026; riêng các quy định liên quan "
            "đến thu nhập từ tiền lương hết hiệu lực thi hành từ kỳ tính thuế năm 2026.")
    result = links_of(circular(line))

    assert targets(result) == [("repeals", "38/2019/QH14", None, None, None, None),
                               ("repeals", "38/2019/QH14", "51", None, None, None)]
    assert [(i.doc_id, i.kind, i.article) for i in result.issues] == [("500003", "unresolved_link", "2")]
    assert "riêng các quy định liên quan" in result.issues[0].detail


def test_in_corpus_whole_document_target_maps_to_every_chunk():
    result = links_of(vat_law(), circular("2. Thông tư này bãi bỏ Luật số 48/2024/QH15."))

    assert result.links[0].target_chunks == [f"{VAT_LAW}:D1", f"{VAT_LAW}:D5:K1", f"{VAT_LAW}:D5:K2",
                                             f"{VAT_LAW}:D5:K3", f"{VAT_LAW}:D9", f"{VAT_LAW}:D10"]


# --- The build -----------------------------------------------------------------------------


def write_processed(directory: Path, *docs: dict) -> None:
    directory.mkdir(parents=True)
    for doc in docs:
        doc_id = doc["source_url"].split("-")[-2]
        (directory / f"doc-{doc_id}-d1.json").write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def built(tmp_path: Path, out: str = "enriched") -> Path:
    processed, chunks = tmp_path / "processed", tmp_path / "chunks"
    if not processed.exists():
        write_processed(processed, vat_law(), amending_law("1. Bãi bỏ khoản 3 Điều 5 và Điều 9."),
                        circular("2. Thông tư này thay thế Thông tư số 40/2021/TT-BTC."))
        build_chunks(processed, chunks, count_tokens=words, max_tokens=20)
    build(processed, chunks, tmp_path / out)
    return tmp_path / out


def test_build_writes_links_and_amended_by(tmp_path):
    out = built(tmp_path)
    links = read_jsonl(out / "links.jsonl")
    enriched = {c["id"]: c for c in read_jsonl(out / "chunks.jsonl")}

    assert [(l["source"], l["target_number"], l["target_article"], l["in_corpus"]) for l in links] == [
        ("500002:D1", VAT_NUMBER, "5", True),
        ("500002:D1", VAT_NUMBER, "9", True),
        ("500003:D2:K2", "40/2021/TT-BTC", None, False),  # the article is split at 20 words
    ]
    assert set(links[0]) == {"type", "source", "target_number", "target_doc", "target_article", "target_clause",
                              "target_point", "target_part", "target_chunks", "in_corpus"}
    assert enriched[f"{VAT_LAW}:D5:K3"]["amended_by"] == [{"type": "repeals", "source": "500002:D1"}]
    assert enriched[f"{VAT_LAW}:D5:K1"]["amended_by"] == []


def test_build_of_links_is_deterministic(tmp_path):
    first, second = built(tmp_path, "a"), built(tmp_path, "b")

    for name in ("links.jsonl", "chunks.jsonl", "issues.jsonl"):
        assert (first / name).read_bytes() == (second / name).read_bytes()


# --- The real corpus (AC-005) --------------------------------------------------------------

REAL_PROCESSED = ROOT / "data" / "processed"
REAL_CHUNKS = ROOT / "data" / "chunks"
FIXTURE = ROOT / "tests" / "fixtures" / "amendment_links.csv"


def expected_links() -> list[dict]:
    with FIXTURE.open(encoding="utf-8", newline="") as f:
        return [{**{k: (v or None) for k, v in row.items() if k != "target_chunks"},
                 "target_chunks": row["target_chunks"].split(";") if row["target_chunks"] else []}
                for row in csv.DictReader(f)]


@pytest.fixture(scope="module")
def corpus_build(tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("enriched")
    build(REAL_PROCESSED, REAL_CHUNKS, out)
    return out


needs_corpus = pytest.mark.skipif(not (REAL_CHUNKS / "chunks.jsonl").exists(), reason="needs data/chunks/")


@pytest.mark.corpus
@needs_corpus
def test_corpus_every_hand_checked_directive_produces_its_link(corpus_build):
    fields = ("source", "type", "target_number", "target_article", "target_clause", "target_point",
              "target_part", "target_chunks")
    built_links = [{k: link[k] for k in fields} for link in read_jsonl(corpus_build / "links.jsonl")]

    assert built_links == expected_links()


@pytest.mark.corpus
@needs_corpus
def test_corpus_in_corpus_links_have_their_inverse_and_others_are_marked(corpus_build):
    links = read_jsonl(corpus_build / "links.jsonl")
    chunks = {c["id"]: c for c in read_jsonl(corpus_build / "chunks.jsonl")}
    doc_numbers = {json.loads(p.read_text(encoding="utf-8"))["metadata"]["so_hieu"]
                   for p in REAL_PROCESSED.glob("*-d1.json")}

    for link in links:
        assert link["in_corpus"] == (link["target_number"] in doc_numbers), link
        assert link["in_corpus"] == (link["target_doc"] is not None), link
        for target in link["target_chunks"]:
            assert {"type": link["type"], "source": link["source"]} in chunks[target]["amended_by"], link
    inverse = sum(len(c["amended_by"]) for c in chunks.values())
    assert inverse == len({(t, l["type"], l["source"]) for l in links for t in l["target_chunks"]})
    assert all(len(c["amended_by"]) == len({(e["type"], e["source"]) for e in c["amended_by"]}) for c in chunks.values())


@pytest.mark.corpus
@needs_corpus
def test_corpus_only_the_subject_only_repeal_is_unresolved(corpus_build):
    issues = [i for i in read_jsonl(corpus_build / "issues.jsonl") if i["kind"] == "unresolved_link"]

    assert [(i["doc_id"], i["article"]) for i in issues] == [("422733", "29")]
