"""FR-CORE-010/011 cited answers. Approach approved on #15.
AC-009: every citation id in an answer resolves to a passage that was in the context; an id that
does not is flagged in the output.

The rules are `docs/reference/answer.md`, *The answer*. Unit tests assemble a small context as in
`tests/test_context.py`, with tokens counted as words, and a fake model that returns a fixed reply,
so nothing goes to the network. The live test calls the real model once: `pytest -m live`.
"""

import json
import socket
from pathlib import Path
from urllib.parse import quote

import pytest

from src.answer import NOT_FOUND, Answerer, AnswerOutput, Document
from src.context import Assembler
from src.llm import Call
from src.retrieval import Hit, Retrieval

ROOT = Path(__file__).resolve().parent.parent
PROMPT = ROOT / "src" / "prompts" / "answer.md"

VAT_URL = "https://luatvietnam.vn/thue/luat-thue-gia-tri-gia-tang-2024-so-48-2024-qh15-379409-d1.html"
AMENDING_URL = "https://luatvietnam.vn/thue/luat-thue-gia-tri-gia-tang-sua-doi-2025-so-149-2025-qh15-421739-d1.html"
PIT_URL = "https://luatvietnam.vn/thue/luat-thue-thu-nhap-ca-nhan-2025-so-109-2025-qh15-422733-d1.html"
DOCUMENTS = {
    "379409": ("Luật", "48/2024/QH15", "Thuế giá trị gia tăng", VAT_URL),
    "421739": ("Luật", "149/2025/QH15", "Sửa đổi, bổ sung một số điều của Luật Thuế giá trị gia tăng", AMENDING_URL),
    "422733": ("Luật", "109/2025/QH15", "Thuế thu nhập cá nhân", PIT_URL),
}
ARTICLES = [  # id, title, text
    ("379409:D5", "Đối tượng không chịu thuế",
     "Các hàng hóa, dịch vụ sau đây không chịu thuế giá trị gia tăng:\n"
     "1. Sản phẩm trồng trọt chưa chế biến.\n"
     "25. Hàng hóa, dịch vụ của hộ kinh doanh có doanh thu năm từ 500 triệu đồng trở xuống."),
    ("379409:D7", "Thuế suất - mức thu", "Mức thuế suất do Chính phủ quy định."),
    ("379409:D11", "Khấu trừ thuế",
     "1. Khấu trừ thuế theo hóa đơn.\n2. Khấu trừ thuế theo chứng từ.\n2. Khấu trừ thuế theo bảng kê."),
    ("421739:D1", "Sửa đổi, bổ sung một số điều của Luật Thuế giá trị gia tăng",
     "1. Sửa đổi, bổ sung khoản 1 Điều 4 như sau: “1. Người nộp thuế là tổ chức.”\n"
     "2. Sửa đổi, bổ sung khoản 25 Điều 5 như sau: “25. Hàng hóa của hộ kinh doanh có doanh thu năm "
     "từ 1 tỷ đồng trở xuống.”"),
    ("422733:D3", "", "Thu nhập từ tiền lương, tiền công."),
    ("379409:D9", "Thuế suất 5%", "Mức thuế suất 5% áp dụng đối với nước sạch."),
]
CHUNKS = [  # id, clause, text (none: the whole article), amended_by
    ("379409:D5:K1", "1", "1. Sản phẩm trồng trọt chưa chế biến.", []),
    ("379409:D5:K25", "25",
     "25. Hàng hóa, dịch vụ của hộ kinh doanh có doanh thu năm từ 500 triệu đồng trở xuống.",
     [{"type": "amends", "source": "421739:D1:K2"}]),
    ("379409:D7", None, None, []),
    ("379409:D11", None, None, []),
    ("421739:D1:K1", "1", "1. Sửa đổi, bổ sung khoản 1 Điều 4 như sau: “1. Người nộp thuế là tổ chức.”", []),
    ("421739:D1:K2", "2",
     "2. Sửa đổi, bổ sung khoản 25 Điều 5 như sau: “25. Hàng hóa của hộ kinh doanh có doanh thu năm "
     "từ 1 tỷ đồng trở xuống.”", []),
    ("422733:D3", None, None, []),
    ("379409:D9", None, None, [{"type": "repeals", "source": "421739:D1:K1"}]),
]


def article_records() -> list[dict]:
    return [{"id": a, "doc_id": a.split(":D")[0], "chapter": None, "chapter_title": None, "article": a.split(":D")[1],
             "title": title, "text": text} for a, title, text in ARTICLES]


def chunk_records() -> list[dict]:
    titles = {a: (title, text) for a, title, text in ARTICLES}
    records = []
    for chunk_id, clause, text, amended_by in CHUNKS:
        parent = ":".join(chunk_id.split(":")[:2])
        doc_id, number = parent.split(":D")
        kind, so_hieu, trich_yeu, _ = DOCUMENTS[doc_id]
        title = titles[parent][0]
        position = f"Điều {number}. {title}" if title else f"Điều {number}"
        header = f"[{kind} {so_hieu} — {trich_yeu}] [{position}" + (f" > Khoản {clause}]" if clause else "]")
        records.append({"id": chunk_id, "doc_id": doc_id, "chapter": None, "chapter_title": None,
                        "article": number, "clause": clause, "parent_id": parent,
                        "text": text if text is not None else titles[parent][1], "header": header,
                        "effective_date": "2026-01-01", "amended_by": amended_by})
    return records


def words(text: str) -> int:
    return len(text.split())


def documents() -> dict[str, Document]:
    return {doc_id: Document(f"{kind} {so_hieu}", url) for doc_id, (kind, so_hieu, _, url) in DOCUMENTS.items()}


class FakeLLM:
    """Returns the given reply for every call and records each request."""

    def __init__(self, sentences):
        self.sentences = sentences
        self.requests: list[tuple] = []

    def generate(self, prompt, system, user, schema, validate=None):
        self.requests.append((prompt, system, user, schema))
        parsed = AnswerOutput.model_validate({"sentences": self.sentences})
        return Call(parsed, "gemini-3.5-flash-lite", prompt, 9000, 120, 1.25, 0.0030, 1)


def retrieval(*chunk_ids: str) -> Retrieval:
    return Retrieval([Hit(chunk_id, ("vector",), 1.0) for chunk_id in chunk_ids], [])


def assembler() -> Assembler:
    return Assembler(chunk_records(), article_records(), words)


def ask(sentences, *chunk_ids: str, question: str = "Hộ kinh doanh có phải chịu thuế giá trị gia tăng không?"):
    llm = FakeLLM(sentences)
    answer = Answerer(assembler(), llm, documents()).answer(question, retrieval(*chunk_ids))
    return answer, llm


def fragment(text: str) -> str:
    return "#:~:text=" + quote(text, safe="").replace("-", "%2D")


# --- The request ---------------------------------------------------------------------------------

def test_the_model_gets_the_prompt_file_and_the_assembled_context():
    question = "Hộ kinh doanh có phải chịu thuế giá trị gia tăng không?"
    _, llm = ask([{"text": "Câu một.", "citations": ["1"]}], "379409:D5:K25", question=question)
    context = assembler().assemble(retrieval("379409:D5:K25"))
    assert llm.requests == [("answer", PROMPT.read_text(encoding="utf-8"),
                             f"Passages:\n\n{context.text}\n\nQuestion: {question}", AnswerOutput)]


def test_the_prompt_holds_the_not_found_sentence_and_the_link_line_rule():
    prompt = PROMPT.read_text(encoding="utf-8")
    assert NOT_FOUND == "Không tìm thấy quy định trả lời câu hỏi này trong các văn bản hiện có."
    assert NOT_FOUND in prompt
    assert "[1.25] được sửa đổi, bổ sung bởi [3]." in prompt


def test_the_answer_carries_its_context_call_and_latency():
    answer, _ = ask([{"text": "Câu một.", "citations": ["1"]}], "379409:D5:K25")
    assert answer.context == assembler().assemble(retrieval("379409:D5:K25"))
    assert answer.call is not None and answer.call.input_tokens == 9000
    assert answer.latency_s.get("generation") == pytest.approx(1.25)
    assert "assembly" in answer.latency_s


# --- Ids -----------------------------------------------------------------------------------------

def test_ids_as_written_are_trimmed_unbracketed_and_kept_once_per_sentence():
    answer, _ = ask([{"text": "Câu một.", "citations": [" [1.25] ", "2", "2"]}], "379409:D5:K25")
    assert [(s.text, s.citations) for s in answer.sentences] == [("Câu một.", ("1.25", "2"))]


def test_ids_resolve_against_the_passages_and_the_rest_are_flagged():
    sentences = [{"text": "Câu một.", "citations": ["1", "1.25", "2", "1.99", "9", "2.1", "abc"]}]
    answer, _ = ask(sentences, "379409:D5:K25")
    by_id = {c.id: c for c in answer.citations}
    assert [c.id for c in answer.citations] == ["1", "1.25", "2", "1.99", "9", "2.1", "abc"]
    assert answer.flagged == ["1.99", "9", "2.1", "abc"]
    assert [by_id[i].in_context for i in ("1", "1.25", "2")] == [True, True, True]
    assert (by_id["1"].passage, by_id["1"].document, by_id["1"].article, by_id["1"].clause) == \
        ("1", "Luật 48/2024/QH15", "5", None)
    assert (by_id["1.25"].passage, by_id["1.25"].article, by_id["1.25"].clause) == ("1", "5", "25")
    assert (by_id["2"].passage, by_id["2"].document, by_id["2"].article, by_id["2"].clause) == \
        ("2", "Luật 149/2025/QH15", "1", "2")
    assert all(by_id[i].in_context is False and by_id[i].url is None for i in answer.flagged)


def test_citations_are_distinct_in_first_use_order_across_sentences():
    sentences = [{"text": "Câu một.", "citations": ["1.25", "7"]}, {"text": "Câu hai.", "citations": ["2", "1.25"]}]
    answer, _ = ask(sentences, "379409:D5:K25")
    assert [c.id for c in answer.citations] == ["1.25", "7", "2"]
    assert answer.flagged == ["7"]


def test_a_repeated_clause_number_is_shown_by_its_number():
    answer, _ = ask([{"text": "Câu một.", "citations": ["1.2.2"]}], "379409:D11")
    assert answer.citations and answer.citations[0].in_context
    assert answer.citations[0].clause == "2"
    assert "[Luật 48/2024/QH15, Điều 11, khoản 2](" in answer.text


# --- Rendering -----------------------------------------------------------------------------------

def test_the_text_is_the_sentences_with_their_ids_then_the_sources():
    sentences = [{"text": "Câu một.", "citations": ["1.25", "2"]}, {"text": "Câu hai.", "citations": []}]
    answer, _ = ask(sentences, "379409:D5:K25")
    vat = VAT_URL + fragment("Điều 5. Đối tượng không chịu thuế")
    amending = AMENDING_URL + fragment("Điều 1. Sửa đổi, bổ sung một số điều của Luật Thuế giá trị gia tăng")
    assert answer.text == (
        "Câu một. [1.25][2] Câu hai.\n\n"
        "Nguồn:\n"
        f"- [1.25] [Luật 48/2024/QH15, Điều 5, khoản 25]({vat})\n"
        f"- [2] [Luật 149/2025/QH15, Điều 1, khoản 2]({amending})"
    )


def test_a_flagged_id_is_listed_apart_and_is_never_a_source():
    answer, _ = ask([{"text": "Câu một.", "citations": ["1", "7", "1.99"]}], "379409:D7")
    vat = VAT_URL + fragment("Điều 7. Thuế suất - mức thu")
    assert answer.text == (
        "Câu một. [1][7][1.99]\n\n"
        "Nguồn:\n"
        f"- [1] [Luật 48/2024/QH15, Điều 7]({vat})\n\n"
        "Trích dẫn không có trong nguồn được cung cấp: [7] [1.99]"
    )


def test_a_link_fragment_encodes_the_hyphen():
    answer, _ = ask([{"text": "Câu một.", "citations": ["1"]}], "379409:D7")
    assert answer.citations and answer.citations[0].url == VAT_URL + fragment("Điều 7. Thuế suất - mức thu")
    assert "-" not in answer.citations[0].url.split("#:~:text=")[1]


def test_a_link_to_an_article_without_a_title_names_the_article_alone():
    answer, _ = ask([{"text": "Câu một.", "citations": ["1"]}], "422733:D3")
    assert answer.citations and answer.citations[0].url == PIT_URL + "#:~:text=" + quote("Điều 3.", safe="")


# --- Amendment notices (choices A2 and 2', approved on #15) ------------------------------------

NOTICE = "Khoản 25 Điều 5 Luật 48/2024/QH15 được sửa đổi, bổ sung bởi khoản 2 Điều 1 Luật 149/2025/QH15."


def said(answer) -> list[tuple]:
    return [(s.text, s.citations) for s in answer.sentences]


def test_an_amended_clause_cited_without_its_source_gets_a_notice():
    answer, _ = ask([{"text": "Câu một.", "citations": ["1.25"]}], "379409:D5:K25")
    assert said(answer) == [("Câu một.", ("1.25",)), (NOTICE, ("1.25", "2"))]
    assert answer.notices == 1


@pytest.mark.parametrize("sentences", [
    [{"text": "Câu một.", "citations": ["1.25", "2"]}],
    [{"text": "Câu một.", "citations": ["1.25"]}, {"text": "Câu hai.", "citations": ["2"]}],
], ids=["same-sentence", "another-sentence"])
def test_a_notice_is_added_even_when_the_answer_cites_the_source(sentences):
    """Choice 2': a sentence citing both may still not say the provision was amended (q16 at 4091435)."""
    answer, _ = ask(sentences, "379409:D5:K25")
    assert said(answer)[len(sentences):] == [(NOTICE, ("1.25", "2"))]
    assert answer.notices == 1


def test_citing_the_whole_article_counts_as_citing_its_amended_clause():
    answer, _ = ask([{"text": "Câu một.", "citations": ["1"]}], "379409:D5:K25")
    assert said(answer)[1:] == [(NOTICE, ("1.25", "2"))]
    assert answer.notices == 1


def test_citing_another_clause_of_the_article_gets_no_notice():
    answer, _ = ask([{"text": "Câu một.", "citations": ["1.1"]}], "379409:D5:K25")
    assert said(answer) == [("Câu một.", ("1.1",))]
    assert answer.notices == 0


def test_a_repealed_whole_article_gets_a_notice_naming_the_article():
    answer, _ = ask([{"text": "Câu một.", "citations": ["1"]}], "379409:D9")
    assert said(answer)[1:] == [
        ("Điều 9 Luật 48/2024/QH15 bị bãi bỏ bởi khoản 1 Điều 1 Luật 149/2025/QH15.", ("1", "2"))]


def test_a_source_whose_article_is_in_the_context_is_cited_by_its_clause():
    answer, _ = ask([{"text": "Câu một.", "citations": ["1.25"]}], "379409:D5:K25", "421739:D1:K2")
    assert said(answer)[1:] == [(NOTICE, ("1.25", "2.2"))]
    both, _ = ask([{"text": "Câu một.", "citations": ["1.25", "2"]}], "379409:D5:K25", "421739:D1:K2")
    assert said(both)[1:] == [(NOTICE, ("1.25", "2.2"))]


def test_a_notice_is_rendered_and_its_ids_are_sources():
    answer, _ = ask([{"text": "Câu một.", "citations": ["1.25"]}], "379409:D5:K25")
    vat = VAT_URL + fragment("Điều 5. Đối tượng không chịu thuế")
    amending = AMENDING_URL + fragment("Điều 1. Sửa đổi, bổ sung một số điều của Luật Thuế giá trị gia tăng")
    assert answer.text == (
        f"Câu một. [1.25] {NOTICE} [1.25][2]\n\n"
        "Nguồn:\n"
        f"- [1.25] [Luật 48/2024/QH15, Điều 5, khoản 25]({vat})\n"
        f"- [2] [Luật 149/2025/QH15, Điều 1, khoản 2]({amending})"
    )
    assert [c.id for c in answer.citations] == ["1.25", "2"]


def test_a_not_found_answer_gets_no_notice():
    answer, _ = ask([{"text": NOT_FOUND, "citations": []}], "379409:D5:K25")
    assert answer.not_found is True and answer.notices == 0
    assert answer.text == NOT_FOUND


# --- Not found -----------------------------------------------------------------------------------

def test_the_not_found_sentence_alone_is_a_not_found_answer():
    answer, _ = ask([{"text": f"  {NOT_FOUND} ", "citations": []}], "379409:D5:K25")
    assert answer.not_found is True
    assert answer.text == NOT_FOUND
    assert answer.citations == [] and answer.flagged == []


def test_no_sentence_is_a_not_found_answer():
    answer, llm = ask([], "379409:D5:K25")
    assert len(llm.requests) == 1
    assert answer.not_found is True
    assert answer.text == NOT_FOUND


@pytest.mark.parametrize("sentences", [
    [{"text": NOT_FOUND, "citations": ["1"]}],
    [{"text": NOT_FOUND, "citations": []}, {"text": "Câu hai.", "citations": ["1"]}],
    [{"text": "Câu một.", "citations": ["1"]}],
], ids=["with-an-id", "two-sentences", "an-answer"])
def test_anything_else_is_an_answer(sentences):
    answer, _ = ask(sentences, "379409:D5:K25")
    assert answer.sentences
    assert answer.not_found is False
    assert answer.text != NOT_FOUND


def test_an_empty_context_is_not_found_without_a_call():
    answer, llm = ask([{"text": "Câu một.", "citations": ["1"]}])
    assert llm.requests == []
    assert answer.not_found is True
    assert answer.text == NOT_FOUND
    assert answer.call is None
    assert answer.latency_s.get("generation") == 0


# --- Loading -------------------------------------------------------------------------------------

def test_load_reads_the_documents_under_the_processed_folder(tmp_path):
    for folder, records in (("enriched", chunk_records()), ("chunks", article_records())):
        (tmp_path / folder).mkdir()
        name = "chunks.jsonl" if folder == "enriched" else "articles.jsonl"
        (tmp_path / folder / name).write_bytes(
            "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records).encode("utf-8"))
    (tmp_path / "processed").mkdir()
    for doc_id, (kind, so_hieu, trich_yeu, url) in DOCUMENTS.items():
        page = {"source_url": url, "crawled_at": "2026-11-12T14:17:19+00:00",
                "metadata": {"loai_van_ban": kind, "so_hieu": so_hieu, "trich_yeu": trich_yeu}, "blocks": []}
        (tmp_path / "processed" / f"{url.rsplit('/', 1)[1][:-5]}.json").write_bytes(
            json.dumps(page, ensure_ascii=False).encode("utf-8"))
    (tmp_path / "processed" / "_index.json").write_bytes(b'{"documents": []}')  # the crawler's index, not a page
    llm = FakeLLM([{"text": "Câu một.", "citations": ["1"]}])
    answerer = Answerer.load(tmp_path, llm=llm)
    assert answerer.documents == documents()
    assert answerer.answer("Câu hỏi?", retrieval("379409:D7")).citations[0].document == "Luật 48/2024/QH15"


def test_answering_makes_no_network_request_with_a_fake_model(monkeypatch):
    attempts = []
    monkeypatch.setattr(socket.socket, "connect", lambda sock, address: attempts.append(address))
    answer, _ = ask([{"text": "Câu một.", "citations": ["1"]}], "379409:D5:K25")
    assert answer.sentences
    assert attempts == []


# --- Live ----------------------------------------------------------------------------------------

@pytest.mark.live
def test_live_the_model_answers_from_the_context_with_resolvable_ids():
    """One real call to LLM_MODEL with the first key. Run with: pytest -m live"""
    from src.llm import LLM

    answer = Answerer(assembler(), LLM(), documents()).answer(
        "Hàng hóa của hộ kinh doanh có doanh thu bao nhiêu thì không chịu thuế giá trị gia tăng?",
        retrieval("379409:D5:K25"))
    assert answer.call is not None and answer.call.attempts >= 1
    assert answer.sentences
    assert all(c.in_context or c.id in answer.flagged for c in answer.citations)
