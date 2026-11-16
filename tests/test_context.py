"""FR-CORE-009 context assembly. Approach approved on #14.
AC-008: for a fixed set of retrieved chunks, assembly is deterministic, contains no duplicate
passage, includes the parent article of every clause and the amending text of every amended
chunk, and stays within the token budget.

The rules are `docs/reference/context.md`. Unit tests use chunks and articles in the shape of
`data/enriched/chunks.jsonl` and `articles.jsonl`, and count tokens as words, so no model is
loaded and nothing goes to the network. The corpus test at the end reads the local `data/` and
the eval set: `pytest -m corpus`.
"""

import json
import re
import socket
from pathlib import Path

import pytest

from src.context import BUDGET, Assembler, Context
from src.retrieval import Hit, Retrieval, Unresolved

ROOT = Path(__file__).resolve().parent.parent
MARK = re.compile(r"^\[\d+(?:\.\d+)*\] ")

# --- A small corpus ------------------------------------------------------------------------------

DOCUMENTS = {  # doc_id: the document group of the header
    "379409": "[Luật 48/2024/QH15 — Thuế giá trị gia tăng]",
    "421739": "[Luật 149/2025/QH15 — Sửa đổi, bổ sung một số điều của Luật Thuế giá trị gia tăng]",
    "422733": "[Luật 109/2025/QH15 — Thuế thu nhập cá nhân]",
    "427630": "[Nghị định 68/2026/NĐ-CP — Quy định về chính sách thuế và quản lý thuế đối với hộ kinh doanh]",
}

ARTICLES = [  # id, title, text
    ("379409:D5", "Đối tượng không chịu thuế",
     "Các hàng hóa, dịch vụ sau đây không chịu thuế giá trị gia tăng:\n"
     "1. Sản phẩm trồng trọt chưa chế biến.\n"
     "2. Sản phẩm là giống vật nuôi.\n"
     "25. Hàng hóa, dịch vụ của hộ kinh doanh có doanh thu năm từ 500 triệu đồng trở xuống."),
    ("379409:D9", "Thuế suất",
     "1. Mức thuế suất 0% áp dụng đối với hàng hóa xuất khẩu.\n"
     "2. Mức thuế suất 5% áp dụng đối với nước sạch."),
    ("379409:D11", "Khấu trừ thuế",
     "1. Khấu trừ thuế theo hóa đơn.\n"
     "2. Khấu trừ thuế theo chứng từ.\n"
     "2. Khấu trừ thuế theo bảng kê."),
    ("379409:D12", "Sửa đổi mẫu biểu",
     "1. Sửa đổi mẫu biểu như sau:\n"
     "“Mẫu biểu mới gồm:\n"
     "2. Tờ khai thuế.”\n"
     "2. Bộ Tài chính hướng dẫn mẫu biểu."),
    ("421739:D1", "Sửa đổi, bổ sung một số điều của Luật Thuế giá trị gia tăng",
     "1. Sửa đổi, bổ sung khoản 1 Điều 4 như sau: “1. Người nộp thuế là tổ chức.”\n"
     "2. Sửa đổi, bổ sung khoản 25 Điều 5 như sau: “25. Hàng hóa của hộ kinh doanh có doanh thu năm "
     "từ 1 tỷ đồng trở xuống.”"),
    ("421739:D3", "Hiệu lực thi hành",
     "Luật này có hiệu lực từ ngày 01 tháng 01 năm 2026. Bãi bỏ Điều 9 và Điều 11 Luật Thuế giá trị gia tăng."),
    ("422733:D3", "Thu nhập chịu thuế", "Thu nhập từ tiền lương, tiền công."),
    ("422733:D4", "Thu nhập được miễn thuế", " ".join(["Thu nhập từ chuyển nhượng bất động sản."] * 40)),
    ("427630:D4", "Đối tượng nộp thuế", "Thu nhập từ tiền lương, tiền công."),
    ("427630:D6", "Khai thuế", "Hộ kinh doanh khai thuế theo năm."),
]

CHUNKS = [  # id, clause, text, amended_by
    ("379409:D5:K1", "1", "1. Sản phẩm trồng trọt chưa chế biến.", []),
    ("379409:D5:K2", "2", "2. Sản phẩm là giống vật nuôi.", [{"type": "replaces", "source": "427630:D6"}]),
    ("379409:D5:K25", "25",
     "25. Hàng hóa, dịch vụ của hộ kinh doanh có doanh thu năm từ 500 triệu đồng trở xuống.",
     [{"type": "amends", "source": "421739:D1:K2"}]),
    ("379409:D9", None, None, [{"type": "repeals", "source": "421739:D3"}]),
    ("379409:D11", None, None, [{"type": "repeals", "source": "421739:D3"}]),
    ("379409:D12", None, None, []),
    ("421739:D1:K1", "1", "1. Sửa đổi, bổ sung khoản 1 Điều 4 như sau: “1. Người nộp thuế là tổ chức.”", []),
    ("421739:D1:K2", "2",
     "2. Sửa đổi, bổ sung khoản 25 Điều 5 như sau: “25. Hàng hóa của hộ kinh doanh có doanh thu năm "
     "từ 1 tỷ đồng trở xuống.”", []),
    ("421739:D3", None, None, []),
    ("422733:D3", None, None, []),
    ("422733:D4", None, None, []),
    ("427630:D4", None, None, []),
    ("427630:D6", None, None, []),
]


def article_records() -> list[dict]:
    records = []
    for article_id, title, text in ARTICLES:
        doc_id, number = article_id.split(":D")
        records.append({"id": article_id, "doc_id": doc_id, "chapter": None, "chapter_title": None,
                        "article": number, "title": title, "text": text})
    return records


def article_header(article_id: str) -> str:
    doc_id, number = article_id.split(":D")
    title = next(title for a, title, _ in ARTICLES if a == article_id)
    return f"{DOCUMENTS[doc_id]} [Điều {number}. {title}]"


def article_text(article_id: str) -> str:
    return next(text for a, _, text in ARTICLES if a == article_id)


def chunk_records() -> list[dict]:
    records = []
    for chunk_id, clause, text, amended_by in CHUNKS:
        parent = ":".join(chunk_id.split(":")[:2])
        doc_id, number = parent.split(":D")
        header = article_header(parent)
        if clause is not None:
            header = header[:-1] + f" > Khoản {clause}]"
        records.append({"id": chunk_id, "doc_id": doc_id, "chapter": None, "chapter_title": None,
                        "article": number, "clause": clause, "parent_id": parent,
                        "text": text if text is not None else article_text(parent), "header": header,
                        "effective_date": "2026-01-01", "amended_by": amended_by})
    return records


def chunk(chunk_id: str) -> dict:
    return next(record for record in chunk_records() if record["id"] == chunk_id)


def words(text: str) -> int:
    return len(text.split())


def assembler(budget: int = BUDGET) -> Assembler:
    return Assembler(chunk_records(), article_records(), words, budget=budget)


def retrieval(*chunk_ids: str, unresolved: list[Unresolved] | None = None) -> Retrieval:
    hits = [Hit(chunk_id, ("vector",), 1.0 / rank) for rank, chunk_id in enumerate(chunk_ids, 1)]
    return Retrieval(hits, unresolved or [])


def assemble(*chunk_ids: str, budget: int = BUDGET) -> Context:
    return assembler(budget).assemble(retrieval(*chunk_ids))


def articles_of(context: Context) -> list[str]:
    return [f"{p.doc_id}:D{p.article}" for p in context.passages if p.kind == "article"]


def passage_of(context: Context, article_id: str):
    matches = [p for p in context.passages if p.kind == "article" and f"{p.doc_id}:D{p.article}" == article_id]
    assert len(matches) == 1, f"{article_id}: {len(matches)} article passages"
    return matches[0]


def body(passage) -> list[str]:
    """The article text lines of a passage, marks removed: every line but the first and the link lines."""
    lines = passage.text.split("\n")[1:]
    return [MARK.sub("", line) for line in lines if not LINK.match(line)]


LINK = re.compile(r"^\[\d+(?:\.\d+)*\] (được sửa đổi, bổ sung bởi|được thay thế bởi|bị bãi bỏ bởi) "
                  r"\[\d+(?:\.\d+)*\]\.$")


# --- Article passages ----------------------------------------------------------------------------

def test_two_clauses_of_one_article_make_one_passage():
    context = assemble("379409:D5:K1", "379409:D5:K25")
    assert articles_of(context) == ["379409:D5"]
    passage = passage_of(context, "379409:D5")
    assert passage.chunk_ids == ("379409:D5:K1", "379409:D5:K2", "379409:D5:K25")


def test_a_clause_brings_its_whole_parent_article():
    context = assemble("379409:D5:K1")
    passage = passage_of(context, "379409:D5")
    assert body(passage) == article_text("379409:D5").split("\n")


def test_the_first_line_is_the_id_and_the_article_header_without_a_clause():
    context = assemble("379409:D5:K25")
    first = passage_of(context, "379409:D5").text.split("\n")[0]
    assert first == "[1] [Luật 48/2024/QH15 — Thuế giá trị gia tăng] [Điều 5. Đối tượng không chịu thuế]"


def test_articles_follow_the_rank_of_their_best_retrieved_chunk():
    context = assemble("422733:D3", "379409:D5:K25", "427630:D4", "379409:D5:K1")
    assert articles_of(context) == ["422733:D3", "379409:D5", "427630:D4"]


def test_identical_text_in_two_provisions_is_kept():
    context = assemble("422733:D3", "427630:D4")
    assert articles_of(context) == ["422733:D3", "427630:D4"]


# --- Citation ids --------------------------------------------------------------------------------

def test_passages_are_numbered_in_order():
    context = assemble("422733:D3", "379409:D5:K25", "427630:D4")
    assert [p.id for p in context.passages] == [str(n) for n in range(1, len(context.passages) + 1)]
    assert len(context.passages) == 5  # D3, D5, its two amending passages, D4
    assert all(p.text.startswith(f"[{p.id}] ") for p in context.passages)


def test_clause_lines_are_marked_in_a_split_article():
    context = assemble("379409:D5:K1")
    passage = passage_of(context, "379409:D5")
    assert passage.clauses == ("1", "2", "25")
    lines = passage.text.split("\n")
    assert lines[1] == "Các hàng hóa, dịch vụ sau đây không chịu thuế giá trị gia tăng:"
    assert lines[2] == "[1.1] 1. Sản phẩm trồng trọt chưa chế biến."
    assert lines[4].startswith("[1.25] 25. ")


def test_clause_lines_are_marked_in_a_whole_article_chunk():
    context = assemble("379409:D9")
    passage = passage_of(context, "379409:D9")
    assert passage.clauses == ("1", "2")
    assert passage.text.split("\n")[2] == "[1.2] 2. Mức thuế suất 5% áp dụng đối với nước sạch."


def test_a_line_inside_a_quotation_is_not_a_clause():
    context = assemble("379409:D12")
    passage = passage_of(context, "379409:D12")
    assert passage.clauses == ("1", "2")
    lines = passage.text.split("\n")
    assert lines[3] == "2. Tờ khai thuế.”"
    assert lines[4] == "[1.2] 2. Bộ Tài chính hướng dẫn mẫu biểu."


def test_a_repeated_clause_number_gets_a_suffix():
    context = assemble("379409:D11")
    passage = passage_of(context, "379409:D11")
    assert passage.clauses == ("1", "2", "2.2")
    assert passage.text.split("\n")[3] == "[1.2.2] 2. Khấu trừ thuế theo bảng kê."


# --- Amending text -------------------------------------------------------------------------------

def test_amending_passages_follow_the_article_they_change():
    context = assemble("379409:D5:K25", "422733:D3")
    assert [(p.id, p.kind, p.chunk_ids) for p in context.passages] == [
        ("1", "article", ("379409:D5:K1", "379409:D5:K2", "379409:D5:K25")),
        ("2", "amending", ("427630:D6",)),
        ("3", "amending", ("421739:D1:K2",)),
        ("4", "article", ("422733:D3",)),
    ]


def test_every_amended_chunk_of_the_article_gets_a_link_line():
    """K2 was not retrieved, but the model reads the whole article, so its link is there too."""
    context = assemble("379409:D5:K25")
    lines = passage_of(context, "379409:D5").text.split("\n")
    assert lines[-2:] == ["[1.2] được thay thế bởi [2].", "[1.25] được sửa đổi, bổ sung bởi [3]."]


def test_an_amending_passage_is_the_source_chunk_alone():
    context = assemble("379409:D5:K25")
    source = chunk("421739:D1:K2")
    assert len(context.passages) == 3
    passage = context.passages[2]
    assert passage.kind == "amending"
    assert passage.text == f"[3] {source['header']}\n{source['text']}"
    assert passage.clauses == ()
    assert "Người nộp thuế là tổ chức" not in context.text  # K1 of the amending article


def test_a_repealed_whole_article_chunk_is_cited_by_its_passage_id():
    context = assemble("379409:D9")
    assert passage_of(context, "379409:D9").text.split("\n")[-1] == "[1] bị bãi bỏ bởi [2]."
    assert len(context.passages) == 2
    assert context.passages[1].chunk_ids == ("421739:D3",)


def test_a_source_whose_article_is_in_the_context_is_not_repeated():
    context = assemble("379409:D5:K25", "421739:D1:K1")
    assert [p.chunk_ids[0] for p in context.passages if p.kind == "amending"] == ["427630:D6"]
    assert articles_of(context) == ["379409:D5", "421739:D1"]
    assert passage_of(context, "379409:D5").text.split("\n")[-1] == "[1.25] được sửa đổi, bổ sung bởi [3.2]."


def test_a_source_changing_two_articles_is_one_passage():
    context = assemble("379409:D9", "379409:D11")
    assert [(p.id, p.kind) for p in context.passages] == [("1", "article"), ("2", "amending"), ("3", "article")]
    assert passage_of(context, "379409:D11").text.split("\n")[-1] == "[3] bị bãi bỏ bởi [2]."


def test_no_passage_is_sent_twice():
    context = assemble("379409:D5:K25", "421739:D1:K2", "379409:D9", "379409:D11", "379409:D5:K1")
    keys = [(p.kind, p.chunk_ids) for p in context.passages]
    assert len(keys) == len(set(keys)) == 6  # D5, 427630:D6, D1, D9, 421739:D3, D11
    covered = [chunk_id for p in context.passages for chunk_id in p.chunk_ids]
    assert len(covered) == len(set(covered))


# --- The text and the budget ---------------------------------------------------------------------

def test_the_text_is_the_passages_joined_by_a_blank_line():
    context = assemble("379409:D9", "422733:D3")
    assert context.passages
    assert context.text == "\n\n".join(p.text for p in context.passages)
    assert context.tokens == words(context.text)


def test_the_default_budget_is_24000():
    assert BUDGET == 24_000
    assert Assembler(chunk_records(), article_records(), words).budget == BUDGET


def test_over_the_budget_whole_articles_are_dropped_from_the_lowest_ranked():
    """D9 with its amending passage fits in 100 words; D4 does not, and D3 goes with it: the
    context is the longest run of articles that fits."""
    context = assemble("379409:D9", "422733:D4", "422733:D3", budget=100)
    assert articles_of(context) == ["379409:D9"]
    assert [p.kind for p in context.passages] == ["article", "amending"]
    assert context.dropped == ["422733:D4", "422733:D3"]
    assert context.tokens <= 100
    assert body(context.passages[0]) == article_text("379409:D9").split("\n")


def test_an_article_is_dropped_with_its_amending_passages_and_ids_have_no_gaps():
    context = assemble("422733:D3", "379409:D9", budget=30)
    assert [(p.id, p.chunk_ids) for p in context.passages] == [("1", ("422733:D3",))]
    assert context.dropped == ["379409:D9"]
    assert "Bãi bỏ" not in context.text


def test_the_top_article_is_kept_even_over_the_budget():
    context = assemble("422733:D4", "422733:D3", budget=5)
    assert articles_of(context) == ["422733:D4"]
    assert context.dropped == ["422733:D3"]
    assert context.tokens > 5


def test_within_the_budget_nothing_is_dropped():
    context = assemble("379409:D5:K25", "379409:D9", "422733:D3")
    assert articles_of(context) == ["379409:D5", "379409:D9", "422733:D3"]
    assert context.dropped == []
    assert 0 < context.tokens <= BUDGET


# --- Determinism, pass-through, loading ----------------------------------------------------------

def test_assembly_is_deterministic():
    chunk_ids = ("379409:D5:K25", "379409:D9", "421739:D1:K1", "379409:D11")
    first = assemble(*chunk_ids)
    assert first.passages
    assert assemble(*chunk_ids) == first
    assert assembler().assemble(retrieval(*chunk_ids)).text.encode("utf-8") == first.text.encode("utf-8")


def test_unresolved_references_pass_through_unchanged():
    unresolved = [Unresolved("Thông tư 99/2026", "unknown_document")]
    context = assembler().assemble(retrieval("422733:D3", unresolved=unresolved))
    assert context.passages
    assert context.unresolved == unresolved


def test_an_empty_retrieval_gives_an_empty_context():
    context = assemble()
    assert (context.passages, context.text, context.tokens, context.dropped) == ([], "", 0, [])


def test_load_reads_the_chunks_and_articles_under_the_data_folder(tmp_path):
    (tmp_path / "enriched").mkdir()
    (tmp_path / "chunks").mkdir()
    for path, records in ((tmp_path / "enriched" / "chunks.jsonl", chunk_records()),
                          (tmp_path / "chunks" / "articles.jsonl", article_records())):
        path.write_bytes("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records).encode("utf-8"))
    loaded = Assembler.load(tmp_path, count_tokens=words, budget=1000)
    assert loaded.budget == 1000
    assert loaded.assemble(retrieval("379409:D5:K25")) == assemble("379409:D5:K25", budget=1000)
    assert loaded.assemble(retrieval("379409:D5:K25")).passages


def test_assembly_makes_no_network_request(monkeypatch):
    attempts = []

    def refuse(sock, address):
        attempts.append(address)
        raise OSError("network blocked in unit tests")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    context = assemble("379409:D5:K25", "379409:D9")
    assert context.passages
    assert attempts == []


# --- The corpus ----------------------------------------------------------------------------------

DATA_DIR = ROOT / "data"
EVAL_SET = ROOT / "eval" / "questions.yaml"


@pytest.mark.corpus
def test_ac008_on_the_eval_set():
    """Run `python -m src.index` first. Over every eval question and turn, top 8: within the
    budget, every retrieved chunk's article is a passage or dropped, every retrieved clause chunk
    is marked, every amended chunk of a passage has a link line. Prints the counts."""
    from src.eval.dataset import load_eval_set
    from src.retrieval import Retriever

    eval_set = load_eval_set(EVAL_SET, DATA_DIR / "processed", DATA_DIR / "enriched")
    questions = [q.question for q in eval_set.questions]
    questions += [turn.question for conversation in eval_set.conversations for turn in conversation.turns]
    retriever = Retriever.load(DATA_DIR)
    assembler = Assembler.load(DATA_DIR)
    chunks = {c["id"]: c for c in map(json.loads, (DATA_DIR / "enriched" / "chunks.jsonl").open(encoding="utf-8"))}
    failures, cut, tokens = [], 0, []
    for index, question in enumerate(questions):
        result = retriever.retrieve(question)
        context = assembler.assemble(result)
        if context != assembler.assemble(result):
            failures.append(f"{index}: not deterministic")
        tokens.append(context.tokens)
        cut += bool(context.dropped)
        articles = {f"{p.doc_id}:D{p.article}": p for p in context.passages if p.kind == "article"}
        if context.tokens > BUDGET and len(articles) > 1:
            failures.append(f"{index}: {context.tokens} tokens")
        for hit in result.hits:
            record = chunks[hit.chunk_id]
            passage = articles.get(record["parent_id"])
            if passage is None:
                if record["parent_id"] not in context.dropped:
                    failures.append(f"{index}: {record['parent_id']} neither a passage nor dropped")
            elif record["clause"] not in (None, "0") and hit.chunk_id.split(":K")[1] not in passage.clauses:
                failures.append(f"{index}: {hit.chunk_id} not marked")
        for passage in articles.values():
            links = [line for line in passage.text.split("\n") if LINK.match(line)]
            expected = sum(len(chunks[chunk_id]["amended_by"]) for chunk_id in passage.chunk_ids)
            if len(links) != expected:
                failures.append(f"{index}: {passage.doc_id}:D{passage.article} {len(links)} links, {expected} expected")
    tokens.sort()
    print(f"\nAC-008: {len(questions)} questions and turns, {cut} cut, tokens median "
          f"{tokens[len(tokens) // 2]}, max {tokens[-1]}")
    assert failures == []
