"""FR-CORE-007 reference lookup and FR-CORE-008 hybrid retrieval. Approach approved on #8.
AC-007: a named article is retrieved. AC-012 / NFR-002: median retrieval under 2 s.

The rules are `docs/reference/retrieval.md`. Unit tests build a small index from chunks in the
shape of `data/enriched/chunks.jsonl`, with documents in the shape of `data/processed/`, and an
embedder whose vectors follow a few topic words, so no model is loaded and nothing goes to the
network. The corpus tests at the end read the local `data/` and the eval set: `pytest -m corpus`.
"""

import json
import math
import re
import socket
import statistics
import time
import unicodedata
from pathlib import Path

import pytest

import src.retrieval.hybrid as hybrid
from src.index import EMBEDDING_MODEL, EMBEDDING_REVISION, build
from src.retrieval import (
    CANDIDATES,
    RRF_K,
    TOP_K,
    IndexNotReadyError,
    Retriever,
    find_references,
    rrf,
)

ROOT = Path(__file__).resolve().parent.parent
FOUND_BY = ("reference", "keyword", "vector", "document")

# --- A small corpus ------------------------------------------------------------------------------

DOCUMENTS = {  # doc_id: (loai_van_ban, so_hieu, trich_yeu)
    "379409": ("Luật", "48/2024/QH15", "Thuế giá trị gia tăng"),
    "421739": ("Luật", "149/2025/QH15", "Sửa đổi, bổ sung một số điều của Luật Thuế giá trị gia tăng"),
    "422733": ("Luật", "109/2025/QH15", "Thuế thu nhập cá nhân"),
    "427630": ("Nghị định", "68/2026/NĐ-CP", "Quy định về chính sách thuế và quản lý thuế đối với hộ kinh doanh"),
    "439827": ("Thông tư", "90/2026/TT-BTC", "Quy định về đăng ký thuế"),
    "427777": ("Thông tư", "18/2026/TT-BTC", "Quy định về hồ sơ, thủ tục quản lý thuế đối với hộ kinh doanh"),
    "999001": ("Thông tư", "18/2026/TT-NHNN", "Quy định về thanh toán không dùng tiền mặt"),
}

CHUNKS = [  # id, position in the header, text
    ("379409:D5:K1", "Điều 5. Đối tượng không chịu thuế > Khoản 1", "1. Sản phẩm trồng trọt chưa chế biến."),
    ("379409:D5:K2", "Điều 5. Đối tượng không chịu thuế > Khoản 2", "2. Sản phẩm là giống vật nuôi."),
    ("379409:D5:K25", "Điều 5. Đối tượng không chịu thuế > Khoản 25",
     "25. Hàng hóa, dịch vụ của hộ kinh doanh có doanh thu năm từ 500 triệu đồng trở xuống."),
    ("379409:D9", "Điều 9. Thuế suất", "1. Mức thuế suất 0% áp dụng đối với hàng hóa xuất khẩu."),
    ("379409:D10:K1", "Điều 10. Hoàn thuế > Khoản 1", "1. Cơ sở kinh doanh được khấu trừ thuế."),
    ("379409:D10:K2", "Điều 10. Hoàn thuế > Khoản 2", "2. Hoàn thuế đối với dự án đầu tư."),
    ("421739:D1", "Điều 1. Sửa đổi, bổ sung một số điều của Luật Thuế giá trị gia tăng",
     "Sửa đổi, bổ sung khoản 25 Điều 5 Luật Thuế giá trị gia tăng số 48/2024/QH15 như sau:"),
    ("421739:D2", "Điều 2. Hiệu lực thi hành", "Luật này có hiệu lực thi hành từ ngày 01 tháng 01 năm 2026."),
    ("422733:D3", "Điều 3. Thu nhập chịu thuế", "Thu nhập từ tiền lương, tiền công."),
    ("422733:D9", "Điều 9. Giảm trừ gia cảnh", "Mức giảm trừ đối với đối tượng nộp thuế."),
    ("427630:D4", "Điều 4. Đối tượng nộp thuế", "Hộ kinh doanh, cá nhân kinh doanh nộp thuế."),
    ("427630:D5:K1", "Điều 5. Khai thuế > Khoản 1", "1. Hộ kinh doanh khai thuế theo quý."),
    ("427630:D5:K2", "Điều 5. Khai thuế > Khoản 2", "2. Hộ kinh doanh khai thuế theo năm."),
    ("439827:D1", "Điều 1. Phạm vi điều chỉnh", "Thông tư này quy định về đăng ký thuế."),
    ("439827:D5:K1", "Điều 5. Cấu trúc mã số thuế > Khoản 1", "1. Mã số thuế có 10 chữ số."),
    ("439827:D5:K2", "Điều 5. Cấu trúc mã số thuế > Khoản 2", "2. Mã số thuế có 13 chữ số."),
    ("427777:D2", "Điều 2. Hồ sơ khai thuế", "Hồ sơ khai thuế của hộ kinh doanh."),
    ("999001:D2", "Điều 2. Thanh toán", "Thanh toán qua ngân hàng."),
]

TOPICS = ("hoàn thuế", "mã số thuế", "hộ kinh doanh", "giảm trừ", "thuế suất", "khấu trừ", "thanh toán")


def topic_vector(text: str) -> list[float]:
    """One axis per topic word, counted in the text, plus a small constant axis; unit length."""
    lowered = unicodedata.normalize("NFC", text).lower()
    vector = [float(lowered.count(topic)) for topic in TOPICS] + [0.1]
    norm = math.sqrt(sum(x * x for x in vector))
    return [x / norm for x in vector]


class TopicEmbedder:
    model = EMBEDDING_MODEL

    def __init__(self, revision: str = EMBEDDING_REVISION):
        self.revision = revision
        self.calls: list[str] = []

    def embed(self, texts: list[str]) -> list[list[float]]:
        self.calls.extend(texts)
        return [topic_vector(t) for t in texts]


def chunk_record(chunk_id: str, position: str, text: str) -> dict:
    doc_id, article, *rest = chunk_id.split(":")
    kind, number, title = DOCUMENTS[doc_id]
    return {
        "id": chunk_id, "doc_id": doc_id, "chapter": None, "chapter_title": None,
        "article": article[1:], "clause": rest[0][1:] if rest else None,
        "parent_id": f"{doc_id}:{article}", "text": text,
        "header": f"[{kind} {number} — {title}] [{position}]",
        "effective_date": "2026-07-01", "amended_by": [],
    }


def write_corpus(data_dir: Path) -> None:
    processed, enriched = data_dir / "processed", data_dir / "enriched"
    processed.mkdir(parents=True)
    enriched.mkdir(parents=True)
    for doc_id, (kind, number, title) in DOCUMENTS.items():
        document = {
            "source_url": f"https://luatvietnam.vn/thue/van-ban-{doc_id}-d1.html",
            "metadata": {"so_hieu": number, "loai_van_ban": kind, "trich_yeu": title},
            "blocks": [],
        }
        (processed / f"van-ban-{doc_id}-d1.json").write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
    (processed / "_index.json").write_text("[]", encoding="utf-8")
    with (enriched / "chunks.jsonl").open("w", encoding="utf-8", newline="\n") as f:
        for chunk in CHUNKS:
            f.write(json.dumps(chunk_record(*chunk), ensure_ascii=False) + "\n")


@pytest.fixture
def connections(monkeypatch) -> list:
    """Every outgoing connection attempt; each one fails."""
    attempts = []

    def refuse(sock, address):
        attempts.append(address)
        raise OSError("network blocked in unit tests")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    return attempts


@pytest.fixture
def data_dir(tmp_path, connections) -> Path:
    data = tmp_path / "data"
    write_corpus(data)
    build(data / "enriched", data / "index", TopicEmbedder())
    return data


@pytest.fixture
def retriever(data_dir) -> Retriever:
    return Retriever(data_dir / "index", data_dir / "enriched", data_dir / "processed", TopicEmbedder())


def ids(result) -> list[str]:
    return [hit.chunk_id for hit in result.hits]


def reasons(result) -> list[tuple[str, str]]:
    return [(u.text, u.reason) for u in result.unresolved]


def parsed(question: str) -> list[tuple]:
    return [(r.kind, r.number, r.article, r.clause) for r in find_references(question)]


# --- Finding references (no corpus) -------------------------------------------------------------

def test_a_full_number_with_an_article_is_one_reference():
    assert parsed("Điều 9 48/2024/QH15 quy định gì?") == [(None, "48/2024/QH15", "9", None)]


@pytest.mark.parametrize("written, kind, number", [
    ("Luật 48/2024", "Luật", "48/2024"),
    ("Luật số 48/2024", "Luật", "48/2024"),
    ("Nghị định 68/2026", "Nghị định", "68/2026"),
    ("NĐ 68/2026", "Nghị định", "68/2026"),
    ("nghị định số 68/2026/NĐ-CP", "Nghị định", "68/2026/NĐ-CP"),
    ("Thông tư số 90/2026/TT-BTC", "Thông tư", "90/2026/TT-BTC"),
    ("TT 90/2026", "Thông tư", "90/2026"),
])
def test_a_kind_word_with_a_number_is_a_document_reference(written, kind, number):
    assert parsed(f"{written} quy định gì về hộ kinh doanh?") == [(kind, number, None, None)]


@pytest.mark.parametrize("question", [
    "Doanh thu tháng 12/2025 có phải nộp thuế không?",
    "Hóa đơn lập ngày 15/12/2025 thì kê khai kỳ nào?",
    "Mức 68/2026 là bao nhiêu?",
])
def test_a_number_without_a_kind_word_or_suffix_is_not_a_reference(question):
    assert parsed(question) == []


@pytest.mark.parametrize("written", [
    "khoản 2 Điều 9 Luật 48/2024",
    "Điều 9 khoản 2 Luật 48/2024",
    "điểm a khoản 2 Điều 9 Luật 48/2024",
    "khoản 2 Điều 9 của Luật 48/2024",
])
def test_a_clause_is_read_with_its_article(written):
    assert parsed(f"{written} quy định gì?") == [("Luật", "48/2024", "9", "2")]


def test_article_and_clause_numbers_may_carry_a_letter():
    assert parsed("khoản 1a Điều 5a Nghị định 68/2026 quy định gì?") == [("Nghị định", "68/2026", "5a", "1a")]


@pytest.mark.parametrize("written, number", [
    ("Luật Thuế GTGT", "48/2024/QH15"),
    ("luật thuế giá trị gia tăng", "48/2024/QH15"),
    ("Luật GTGT", "48/2024/QH15"),
    ("Luật TNCN", "109/2025/QH15"),
    ("Luật Thuế thu nhập cá nhân", "109/2025/QH15"),
    ("luật thuế thu nhập doanh nghiệp", "67/2025/QH15"),
    ("Luật Thuế TNDN", "67/2025/QH15"),
    ("Luật Thuế TTĐB", "66/2025/QH15"),
    ("Luật thuế tiêu thụ đặc biệt", "66/2025/QH15"),
    ("Luật Quản lý thuế", "108/2025/QH15"),
])
def test_a_base_law_name_resolves_through_the_alias_list(written, number):
    assert parsed(f"Điều 9 {written} quy định gì?") == [("Luật", number, "9", None)]


def test_a_law_name_followed_by_its_number_is_one_reference():
    assert parsed("Điều 9 Luật Thuế GTGT số 48/2024/QH15 quy định gì?") == [("Luật", "48/2024/QH15", "9", None)]


def test_a_law_name_not_in_the_alias_list_is_not_a_reference():
    assert parsed("Luật Doanh nghiệp quy định gì về vốn điều lệ?") == []


def test_an_article_binds_to_the_document_before_it():
    assert parsed("Nghị định 68/2026, Điều 5 quy định gì?") == [("Nghị định", "68/2026", "5", None)]


def test_an_article_binds_to_the_only_document_named():
    question = "Theo Nghị định 68/2026 thì hộ kinh doanh khai thuế theo quy định tại Điều 5 là gì?"
    assert parsed(question) == [("Nghị định", "68/2026", "5", None)]


def test_references_are_in_question_order():
    assert parsed("Nghị định 68/2026 và Điều 9 Luật 48/2024 khác nhau thế nào?") == [
        ("Nghị định", "68/2026", None, None), ("Luật", "48/2024", "9", None)]


def test_an_article_with_no_document_to_bind_has_no_number():
    assert parsed("Điều 9 quy định gì?") == [(None, None, "9", None)]
    assert parsed("Luật 48/2024 và Nghị định 68/2026 khác nhau thế nào ở Điều 9?") == [
        ("Luật", "48/2024", None, None), ("Nghị định", "68/2026", None, None), (None, None, "9", None)]


def test_decomposed_unicode_reads_as_composed():
    question = "Khoản 2 Điều 9 Luật 48/2024 quy định gì?"
    assert parsed(unicodedata.normalize("NFD", question)) == parsed(question) == [("Luật", "48/2024", "9", "2")]


def test_a_reference_text_is_the_span_it_covers():
    references = find_references("Cho hỏi Điều 9 Luật 48/2024 quy định gì?")
    assert [r.text for r in references] == ["Điều 9 Luật 48/2024"]


# --- Fusion -------------------------------------------------------------------------------------

def test_starting_values():
    assert (TOP_K, RRF_K, CANDIDATES) == (8, 60, 50)


def test_rrf_sums_one_over_constant_plus_rank():
    fused = rrf([["a", "b", "c"], ["b", "d"]])
    assert [chunk for chunk, _ in fused] == ["b", "a", "d", "c"]
    expected = {"a": 1 / 61, "b": 1 / 62 + 1 / 61, "c": 1 / 63, "d": 1 / 62}
    assert all(math.isclose(score, expected[chunk]) for chunk, score in fused)


def test_rrf_ties_keep_first_appearance_rank_by_rank():
    assert [chunk for chunk, _ in rrf([["a", "b"], ["c", "d"]])] == ["a", "c", "b", "d"]


def test_rrf_takes_the_constant():
    assert rrf([["a"]], constant=0) == [("a", 1.0)]


# --- Reference slots ----------------------------------------------------------------------------

def test_a_referenced_article_takes_the_first_slot(retriever):
    result = retriever.retrieve("Điều 9 Luật 48/2024 áp dụng cho hộ kinh doanh không?")
    assert ids(result)[:1] == ["379409:D9"]
    assert result.hits[0].found_by[:1] == ("reference",)
    assert result.unresolved == []


def test_a_named_clause_of_a_split_article_takes_its_clause_chunk(retriever):
    assert ids(retriever.retrieve("Khoản 25 Điều 5 Luật 48/2024 quy định gì?"))[:1] == ["379409:D5:K25"]


def test_a_named_clause_of_an_unsplit_article_takes_the_article_chunk(retriever):
    assert ids(retriever.retrieve("Khoản 1 Điều 9 Luật 48/2024 quy định gì?"))[:1] == ["379409:D9"]


def test_a_clause_missing_from_a_split_article_resolves_as_the_article(retriever):
    result = retriever.retrieve("Khoản 7 Điều 10 Luật 48/2024 quy định gì?")
    assert ids(result)[:1] and ids(result)[0].startswith("379409:D10:")
    assert result.unresolved == []


def test_a_split_article_with_no_clause_takes_its_best_ranked_chunk(retriever):
    # Clause 2 matches the question's words and its topic; clause 1 does neither.
    assert ids(retriever.retrieve("Điều 10 Luật 48/2024 về hoàn thuế dự án đầu tư"))[:1] == ["379409:D10:K2"]


def test_a_split_article_none_of_whose_chunks_is_found_takes_its_first_chunk(retriever, monkeypatch):
    monkeypatch.setattr(hybrid, "CANDIDATES", 0)  # every ranked list is empty
    result = retriever.retrieve("Điều 10 Luật 48/2024 quy định gì?")
    assert [(h.chunk_id, h.found_by, h.score) for h in result.hits] == [("379409:D10:K1", ("reference",), 0.0)]


def test_reference_slots_follow_question_order_without_duplicates(retriever):
    result = retriever.retrieve("Điều 9 Luật 48/2024 và khoản 1 Điều 5 Nghị định 68/2026, so với Điều 9 Luật 48/2024?")
    assert ids(result)[:2] == ["379409:D9", "427630:D5:K1"]
    assert [h.found_by[0] for h in result.hits].count("reference") == 2
    assert len(ids(result)) == len(set(ids(result))) == TOP_K


def test_more_references_than_k_keep_the_first_k(retriever):
    result = retriever.retrieve("Điều 9 Luật 48/2024, Điều 4 Nghị định 68/2026 và Điều 1 Thông tư 90/2026?", k=2)
    assert ids(result) == ["379409:D9", "427630:D4"]


def test_a_base_law_name_reaches_the_base_law(retriever):
    assert ids(retriever.retrieve("Điều 9 Luật Thuế GTGT quy định gì?"))[:1] == ["379409:D9"]


def test_a_base_law_name_never_reaches_the_law_that_amends_it(retriever):
    # Article 1 exists only in Law 149/2025, which amends the VAT Law.
    result = retriever.retrieve("Điều 1 Luật Thuế GTGT quy định gì?")
    assert reasons(result) == [("Điều 1 Luật Thuế GTGT", "no_article")]
    assert "421739:D1" not in [h.chunk_id for h in result.hits if "reference" in h.found_by]


# --- Unresolved references ----------------------------------------------------------------------

@pytest.mark.parametrize("question, text, reason", [
    ("Điều 9 Nghị định 117/2025 quy định gì?", "Điều 9 Nghị định 117/2025", "unknown_document"),
    ("Điều 99 Luật 48/2024 quy định gì?", "Điều 99 Luật 48/2024", "no_article"),
    ("Thông tư 68/2026 quy định gì?", "Thông tư 68/2026", "kind_mismatch"),
    ("Thông tư 18/2026 quy định gì?", "Thông tư 18/2026", "ambiguous"),
    ("Điều 9 quy định gì?", "Điều 9", "no_document"),
])
def test_an_unresolved_reference_is_reported_and_searched_as_absent(retriever, question, text, reason):
    result = retriever.retrieve(question)
    assert reasons(result) == [(text, reason)]
    assert not any({"reference", "document"} & set(h.found_by) for h in result.hits)
    assert len(result.hits) == TOP_K


def test_an_article_between_two_documents_is_reported_no_document(retriever):
    result = retriever.retrieve("Luật 48/2024 và Nghị định 68/2026 khác nhau thế nào ở Điều 9?")
    assert reasons(result) == [("Điều 9", "no_document")]


# --- Hybrid search ------------------------------------------------------------------------------

def test_a_document_without_an_article_adds_its_chunks_as_a_document_list(retriever):
    result = retriever.retrieve("Nghị định 68/2026 quy định gì về khai thuế?")
    named = {"427630:D4", "427630:D5:K1", "427630:D5:K2"}
    assert named <= set(ids(result))
    for hit in result.hits:
        if hit.chunk_id in named:
            # keyword: the full number 68/2026/nđ-cp is added to the keyword query
            assert {"keyword", "document"} <= set(hit.found_by), hit
        else:
            assert "document" not in hit.found_by, hit
    assert not any("reference" in h.found_by for h in result.hits)
    assert result.unresolved == []


def test_hits_without_references_are_the_fused_list_in_order(retriever):
    result = retriever.retrieve("Hộ kinh doanh khai thuế theo quý hay theo năm?")
    assert len(result.hits) == TOP_K
    assert all(set(h.found_by) <= {"keyword", "vector"} and h.found_by for h in result.hits)
    scores = [h.score for h in result.hits]
    assert scores == sorted(scores, reverse=True) and scores[-1] > 0


def test_a_chunk_scoring_zero_is_not_in_the_keyword_list(retriever):
    result = retriever.retrieve("xyzabc qwerty")
    assert result.hits and not any("keyword" in h.found_by for h in result.hits)


def test_found_by_follows_the_fixed_order(retriever):
    for question in ("Điều 9 Luật 48/2024 thuế suất", "Nghị định 68/2026 hộ kinh doanh", "mã số thuế"):
        hits = retriever.retrieve(question).hits
        assert hits, question
        for hit in hits:
            assert list(hit.found_by) == [way for way in FOUND_BY if way in hit.found_by] and hit.found_by, hit


def test_the_same_question_gives_the_same_result(retriever):
    question = "Điều 10 Luật 48/2024 về hoàn thuế"
    first, second = retriever.retrieve(question), retriever.retrieve(question)
    assert first.hits and first == second


def test_retrieval_makes_no_network_request(retriever, connections):
    assert retriever.retrieve("Hộ kinh doanh khai thuế theo quý?").hits
    assert connections == []


def test_load_reads_the_data_folder(data_dir):
    retriever = Retriever.load(data_dir, embedder=TopicEmbedder())
    assert ids(retriever.retrieve("Điều 9 Luật 48/2024"))[:1] == ["379409:D9"]


# --- Loading ------------------------------------------------------------------------------------

def test_a_missing_manifest_stops_loading(data_dir):
    (data_dir / "index" / "manifest.json").unlink()
    with pytest.raises(IndexNotReadyError, match="python -m src.index"):
        Retriever.load(data_dir, embedder=TopicEmbedder())


def test_chunks_newer_than_the_index_stop_loading(data_dir):
    with (data_dir / "enriched" / "chunks.jsonl").open("a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(chunk_record("999001:D3", "Điều 3. Mới", "Nội dung mới."), ensure_ascii=False) + "\n")
    with pytest.raises(IndexNotReadyError, match="python -m src.index"):
        Retriever.load(data_dir, embedder=TopicEmbedder())


def test_an_embedder_of_another_revision_stops_loading(data_dir):
    with pytest.raises(IndexNotReadyError, match="python -m src.index"):
        Retriever.load(data_dir, embedder=TopicEmbedder(revision="0" * 40))


def test_an_unknown_tokenizer_in_the_manifest_stops_loading(data_dir):
    path = data_dir / "index" / "manifest.json"
    written = json.loads(path.read_text(encoding="utf-8"))
    path.write_text(json.dumps({**written, "bm25_tokenizer": "nltk"}), encoding="utf-8")
    with pytest.raises(IndexNotReadyError, match="python -m src.index"):
        Retriever.load(data_dir, embedder=TopicEmbedder())


# --- Tokenizer variants (#10) -------------------------------------------------------------------

def test_the_question_is_tokenized_like_the_index(tmp_path, connections):
    pytest.importorskip("pyvi")
    data = tmp_path / "data"
    write_corpus(data)
    build(data / "enriched", data / "index", TopicEmbedder(), tokenizer="pyvi")
    vocabulary = json.loads((data / "index" / "bm25" / "vocab.index.json").read_text(encoding="utf-8"))
    assert "kinh_doanh" in vocabulary and "kinh" not in vocabulary and "doanh" not in vocabulary
    result = Retriever.load(data, embedder=TopicEmbedder()).retrieve("kinh doanh")
    assert any("keyword" in h.found_by for h in result.hits)


def test_load_reads_the_index_folder_it_is_given(data_dir, tmp_path):
    pytest.importorskip("pyvi")
    variant = tmp_path / "variant"
    build(data_dir / "enriched", variant, TopicEmbedder(), tokenizer="pyvi", cache_dir=data_dir / "index" / "embeddings")
    result = Retriever.load(data_dir, embedder=TopicEmbedder(), index_dir=variant).retrieve("kinh doanh")
    assert any("keyword" in h.found_by for h in result.hits)
    default = Retriever.load(data_dir, embedder=TopicEmbedder()).retrieve("kinh doanh")
    assert not any("keyword" in h.found_by for h in default.hits)


# --- The real model, corpus and eval set (AC-007, AC-012) ---------------------------------------

DATA_DIR = ROOT / "data"
EVAL_SET = ROOT / "eval" / "questions.yaml"
NUMBER = re.compile(r"(?<![\d/])(\d{1,3}/\d{4})(?![\d])")
ARTICLE = re.compile(r"điều\s+(\d+[a-z]?)\b")
LAW_NAME = re.compile(r"luật\s+(thuế|quản lý|gtgt|tncn|tndn|ttđb)")


def eval_items():
    from src.eval.dataset import load_eval_set

    eval_set = load_eval_set(EVAL_SET, DATA_DIR / "processed", DATA_DIR / "enriched")
    items = list(eval_set.questions)
    for conversation in eval_set.conversations:
        items.extend(conversation.turns)
    return items


def item_id(item, index: int) -> str:
    return getattr(item, "id", None) or f"item {index}"


@pytest.mark.corpus
def test_ac007_every_named_article_is_retrieved(connections):
    """Run `python -m src.index` first."""
    from src.eval.dataset import Corpus

    corpus = Corpus(DATA_DIR / "processed", DATA_DIR / "enriched")
    parent = {chunk["id"]: article for article, chunks in corpus.chunks.items() for chunk in chunks}
    retriever = Retriever.load(DATA_DIR)
    failures, checked = [], 0
    for index, item in enumerate(eval_items()):
        if item.form != "reference":
            continue
        result = retriever.retrieve(item.question)
        parents = {parent[h.chunk_id] for h in result.hits}
        text = unicodedata.normalize("NFC", item.question).lower()
        documents = {doc_id for key, (doc_id, _) in corpus.documents.items()
                     for number in NUMBER.findall(text) if key == number or key.startswith(number + "/")}
        if len(documents) == 1 and not LAW_NAME.search(text):
            [doc_id] = documents
            for article in ARTICLE.findall(text):
                if f"{doc_id}:D{article}" in corpus.chunks:
                    checked += 1
                    if f"{doc_id}:D{article}" not in parents:
                        failures.append(f"{item_id(item, index)}: {doc_id}:D{article} not retrieved")
        if item.unanswerable is None:
            failures.extend(f"{item_id(item, index)}: {u.reason}" for u in result.unresolved
                            if u.reason != "unknown_document")
    print(f"\nAC-007: {checked} named articles checked")
    assert checked > 0
    assert failures == []
    assert connections == []


@pytest.mark.corpus
def test_ac012_median_retrieval_is_under_two_seconds(connections):
    """Run `python -m src.index` first. Prints the median and the 95th percentile."""
    retriever = Retriever.load(DATA_DIR)
    questions = [item.question for item in eval_items()]
    retriever.retrieve(questions[0])  # warm-up, not timed
    seconds, empty = [], 0
    for question in questions:
        started = time.perf_counter()
        result = retriever.retrieve(question)
        seconds.append(time.perf_counter() - started)
        empty += not result.hits
    median = statistics.median(seconds)
    p95 = statistics.quantiles(seconds, n=20)[-1]
    print(f"\nAC-012: {len(seconds)} questions, median {median:.3f} s, p95 {p95:.3f} s")
    assert empty == 0, f"{empty} questions retrieved nothing"
    assert median < 2.0
    assert connections == []
