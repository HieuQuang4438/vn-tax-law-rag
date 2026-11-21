"""FR-CORE-013/014 web app, its JSON API (#30). Approach approved on #30.
AC-010: the web interface answers a question end to end, shows citations as links to the
source, and shows the not-advice notice.

The rules are `docs/reference/web.md`, *The API*. FastAPI's TestClient runs the app with a `load`
that returns a fake retriever and a fake answerer, so nothing loads the index and nothing goes
to the network.
"""

import threading
import time

import pytest
from fastapi.testclient import TestClient

from src.answer import NOT_FOUND, Answer, Citation, Document, Sentence
from src.context import Link
from src.llm import LLMError
from src.retrieval import Hit, Retrieval
from src.web import MAX_CHARS, MAX_EARLIER, create_app

Q1 = "Thuế suất thuế giá trị gia tăng đối với cửa hàng tạp hóa là bao nhiêu?"
Q2 = "Còn hộ kinh doanh thì sao?"
VAT_URL = "https://luatvietnam.vn/thue/luat-thue-gia-tri-gia-tang-2024-so-48-2024-qh15-379409-d1.html"
AMENDING_URL = "https://luatvietnam.vn/thue/luat-thue-gia-tri-gia-tang-sua-doi-2025-so-149-2025-qh15-421739-d1.html"
DOCUMENTS = {
    "379409": Document("Luật 48/2024/QH15", VAT_URL, "Luật", "48/2024/QH15", "Thuế giá trị gia tăng", "2024-11-26"),
    "421739": Document("Luật 149/2025/QH15", AMENDING_URL, "Luật", "149/2025/QH15",
                       "Sửa đổi, bổ sung một số điều của Luật Thuế giá trị gia tăng", "2025-12-11"),
}
SENTENCE = "Hộ kinh doanh có doanh thu năm từ 500 triệu đồng trở xuống không chịu thuế giá trị gia tăng."
NOTICE_SENTENCE = ("Khoản 25 Điều 5 Luật 48/2024/QH15 được sửa đổi, bổ sung bởi khoản 2 Điều 1 "
                   "Luật 149/2025/QH15.")
CLAUSE_TEXT = "25. Hàng hóa, dịch vụ của hộ kinh doanh có doanh thu năm từ 500 triệu đồng trở xuống."
AMENDING_TEXT = "2. Sửa đổi khoản 25 Điều 5 như sau: ..."
LINK = Link("1.25", "amends", "2")


def cited() -> Answer:
    clause = Citation("1.25", True, "1", "Luật 48/2024/QH15", "5", "25", VAT_URL + "#:~:text=%C4%90i%E1%BB%81u%205.",
                      "379409", "Điều 5. Đối tượng không chịu thuế", CLAUSE_TEXT, "2026-01-01", (LINK,))
    amending = Citation("2", True, "2", "Luật 149/2025/QH15", "1", "2", AMENDING_URL + "#:~:text=%C4%90i%E1%BB%81u%201.",
                        "421739", "Điều 1. Sửa đổi, bổ sung một số điều của Luật Thuế giá trị gia tăng",
                        AMENDING_TEXT, "2026-07-01")
    sentences = [Sentence(SENTENCE, ("1.25", "7")), Sentence(NOTICE_SENTENCE, ("1.25", "2"))]
    return Answer(sentences, [clause, Citation("7", False), amending], ["7"], False, "the rendered text",
                  notices=1)


def not_found() -> Answer:
    return Answer([Sentence(NOT_FOUND, ())], [], [], True, NOT_FOUND)


class FakeRetriever:
    def __init__(self):
        self.queries: list[str] = []

    def retrieve(self, query, k=8):
        self.queries.append(query)
        return Retrieval([Hit("379409:D5:K25", ("vector",), 0.1)])

    def fuse(self, queries, k=8):
        self.queries.extend(queries)
        return Retrieval([Hit("379409:D5:K25", ("vector",), 0.1)])


class FakeAnswerer:
    """Returns the given answers in order; raises an exception given in their place."""

    def __init__(self, *answers):
        self.answers = list(answers)
        self.questions: list[str] = []
        self.documents = dict(DOCUMENTS)

    def answer(self, question, retrieval):
        self.questions.append(question)
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer


class Loader:
    """A `load` that counts its calls, can wait for a signal, and can fail."""

    def __init__(self, *answers, fail: int = 0, wait: bool = False):
        self.retriever, self.answerer = FakeRetriever(), FakeAnswerer(*answers)
        self.calls, self.fail = 0, fail
        self.go = threading.Event()
        if not wait:
            self.go.set()

    def __call__(self):
        self.calls += 1
        assert self.go.wait(5)
        if self.calls <= self.fail:
            raise RuntimeError("the index is not built")
        return self.retriever, self.answerer


def settled(client: TestClient) -> str:
    """The status once loading is over."""
    for _ in range(500):
        status = client.get("/api/status").json()["status"]
        if status != "loading":
            return status
        time.sleep(0.01)
    raise AssertionError("still loading")


@pytest.fixture
def serve():
    clients = []

    def started(loader: Loader) -> TestClient:
        client = TestClient(create_app(loader))
        client.__enter__()
        clients.append(client)
        return client

    yield started
    for client in clients:
        client.__exit__(None, None, None)


# --- Loading -------------------------------------------------------------------------------------

def test_the_status_is_loading_until_the_load_returns_then_ready(serve):
    loader = Loader(wait=True)
    client = serve(loader)
    assert client.get("/api/status").json() == {"status": "loading"}
    loader.go.set()
    assert settled(client) == "ready"


def test_a_load_that_raises_leaves_the_app_in_error(serve, caplog):
    client = serve(Loader(fail=1))
    assert settled(client) == "error"
    assert "RuntimeError" in caplog.text


def test_post_load_retries_a_failed_load(serve):
    loader = Loader(fail=1)
    client = serve(loader)
    assert settled(client) == "error"
    assert client.post("/api/load").json()["status"] in ("loading", "ready")
    assert settled(client) == "ready"
    assert loader.calls == 2


def test_post_load_does_nothing_once_loaded(serve):
    loader = Loader()
    client = serve(loader)
    assert settled(client) == "ready"
    assert client.post("/api/load").json() == {"status": "ready"}
    assert loader.calls == 1


def test_the_load_runs_once_for_every_request(serve):
    loader = Loader(cited(), cited())
    client = serve(loader)
    settled(client)
    client.post("/api/ask", json={"question": Q1})
    client.post("/api/ask", json={"question": Q2, "earlier": [Q1]})
    assert loader.calls == 1


def test_asking_while_loading_is_503_loading(serve):
    loader = Loader(wait=True)
    client = serve(loader)
    response = client.post("/api/ask", json={"question": Q1})
    assert (response.status_code, response.json()) == (503, {"error": "loading"})
    assert client.get("/api/documents").status_code == 503
    loader.go.set()


def test_asking_after_a_failed_load_is_503_load_error(serve):
    client = serve(Loader(fail=1))
    settled(client)
    for response in (client.post("/api/ask", json={"question": Q1}), client.get("/api/documents")):
        assert (response.status_code, response.json()) == (503, {"error": "load_error"})


# --- Asking --------------------------------------------------------------------------------------

def test_an_answer_carries_its_sentences_sources_and_flagged_ids(serve):
    client = serve(Loader(cited()))
    settled(client)
    body = client.post("/api/ask", json={"question": f"  {Q1} "}).json()
    assert body["question"] == Q1
    assert body["sentences"] == [{"text": SENTENCE, "citations": ["1.25", "7"]},
                                 {"text": NOTICE_SENTENCE, "citations": ["1.25", "2"]}]
    assert (body["notices"], body["not_found"], body["flagged"]) == (1, False, ["7"])
    assert [source.get("ids") for source in body["sources"]] == [["1.25"], ["2"]]
    assert isinstance(body["seconds"], float) and body["seconds"] >= 0
    assert "text" not in body  # the page renders the sentences and the sources, not Answer.text


def test_a_source_joins_its_citation_to_its_document(serve):
    client = serve(Loader(cited()))
    settled(client)
    source = client.post("/api/ask", json={"question": Q1}).json()["sources"][0]
    assert source == {
        "ids": ["1.25"], "document": "Luật 48/2024/QH15", "kind": "Luật", "number": "48/2024/QH15",
        "title": "Thuế giá trị gia tăng", "issued": "2024-11-26", "article": "5", "clauses": ["25"],
        "heading": "Điều 5. Đối tượng không chịu thuế", "url": VAT_URL + "#:~:text=%C4%90i%E1%BB%81u%205.",
        "text": CLAUSE_TEXT, "effective": "2026-01-01",
        "amended_by": [{"target": "1.25", "type": "amends", "source": "2"}],
    }


def test_every_source_links_to_its_source_page(serve):
    client = serve(Loader(cited()))
    settled(client)
    sources = client.post("/api/ask", json={"question": Q1}).json()["sources"]
    assert [source["url"].split("#")[0] for source in sources] == [VAT_URL, AMENDING_URL]


def test_a_not_found_answer_has_no_source(serve):
    client = serve(Loader(not_found()))
    settled(client)
    body = client.post("/api/ask", json={"question": Q1}).json()
    assert (body["not_found"], body["sources"], body["flagged"]) == (True, [], [])
    assert body["sentences"] == [{"text": NOT_FOUND, "citations": []}]


def test_the_earlier_questions_go_through_the_default_rewriter(serve):
    loader = Loader(cited())
    client = serve(loader)
    settled(client)
    client.post("/api/ask", json={"question": Q2, "earlier": [Q1]})
    assert loader.retriever.queries == [f"{Q1} {Q2}"]
    assert loader.answerer.questions == [f"{Q1} {Q2}"]


def test_a_first_question_goes_through_unchanged(serve):
    loader = Loader(cited())
    client = serve(loader)
    settled(client)
    client.post("/api/ask", json={"question": Q1})
    assert loader.retriever.queries == [Q1]


def test_the_app_keeps_nothing_between_questions(serve):
    loader = Loader(cited(), cited())
    client = serve(loader)
    settled(client)
    client.post("/api/ask", json={"question": Q1})
    client.post("/api/ask", json={"question": Q2})
    assert loader.retriever.queries == [Q1, Q2]


def test_a_spent_quota_is_429_quota(serve):
    client = serve(Loader(LLMError("no usable reply", quota=True)))
    settled(client)
    response = client.post("/api/ask", json={"question": Q1})
    assert (response.status_code, response.json()) == (429, {"error": "quota"})


@pytest.mark.parametrize("failure", [LLMError("no usable reply"), RuntimeError("the store is gone")],
                         ids=["llm", "retrieval"])
def test_any_other_failure_is_500_error_and_logged(serve, caplog, failure):
    client = serve(Loader(failure))
    settled(client)
    response = client.post("/api/ask", json={"question": Q1})
    assert (response.status_code, response.json()) == (500, {"error": "error"})
    assert type(failure).__name__ in caplog.text


@pytest.mark.parametrize("body", [
    {},
    {"question": ""},
    {"question": "   "},
    {"question": "x" * (MAX_CHARS + 1)},
    {"question": Q1, "earlier": [Q1] * (MAX_EARLIER + 1)},
    {"question": Q1, "earlier": ["x" * (MAX_CHARS + 1)]},
    {"question": 3},
], ids=["missing", "empty", "blank", "too-long", "too-many-earlier", "earlier-too-long", "not-a-string"])
def test_a_body_that_does_not_fit_is_422(serve, body):
    loader = Loader(cited())
    client = serve(loader)
    settled(client)
    assert client.post("/api/ask", json=body).status_code == 422
    assert loader.answerer.questions == []


def test_the_limits_themselves_are_accepted(serve):
    client = serve(Loader(cited()))
    settled(client)
    body = {"question": "x" * MAX_CHARS, "earlier": ["y" * MAX_CHARS] * MAX_EARLIER}
    assert client.post("/api/ask", json=body).status_code == 200


# --- Documents -----------------------------------------------------------------------------------

def test_the_documents_are_those_the_answerer_loaded_in_its_order(serve):
    client = serve(Loader())
    settled(client)
    assert client.get("/api/documents").json() == {"documents": [
        {"id": "379409", "kind": "Luật", "number": "48/2024/QH15", "title": "Thuế giá trị gia tăng",
         "url": VAT_URL, "issued": "2024-11-26"},
        {"id": "421739", "kind": "Luật", "number": "149/2025/QH15",
         "title": "Sửa đổi, bổ sung một số điều của Luật Thuế giá trị gia tăng", "url": AMENDING_URL,
         "issued": "2025-12-11"},
    ]}


# --- One source per article (#41) ----------------------------------------------------------------

ARTICLE_TEXT = "Điều 5. Đối tượng không chịu thuế\n1. Sản phẩm trồng trọt.\n3. Sản phẩm là giống vật nuôi.\n" + CLAUSE_TEXT
CLAUSE_3_TEXT = "3. Sản phẩm là giống vật nuôi."
ARTICLE_LINK = Link("1", "amends", "2")


def vat(id: str, clause: str | None, text: str, effective: str | None, links=()) -> Citation:
    return Citation(id, True, "1", "Luật 48/2024/QH15", "5", clause, VAT_URL + "#:~:text=%C4%90i%E1%BB%81u%205.",
                    "379409", "Điều 5. Đối tượng không chịu thuế", text, effective, tuple(links))


def amending() -> Citation:
    return Citation("2", True, "2", "Luật 149/2025/QH15", "1", "2", AMENDING_URL + "#:~:text=%C4%90i%E1%BB%81u%201.",
                    "421739", "Điều 1. Sửa đổi, bổ sung một số điều của Luật Thuế giá trị gia tăng",
                    AMENDING_TEXT, "2026-07-01")


def answer_citing(*citations: Citation) -> Answer:
    ids = tuple(c.id for c in citations)
    return Answer([Sentence(SENTENCE, ids)], list(citations), [], False, "the rendered text")


def sources_of(serve, answer: Answer) -> list[dict]:
    client = serve(Loader(answer))
    settled(client)
    return client.post("/api/ask", json={"question": Q1}).json()["sources"]


def test_an_article_cited_whole_and_by_a_clause_is_one_source(serve):
    """The case of #41: a clause cited by the answer, its whole article by the amendment notice."""
    sources = sources_of(serve, answer_citing(vat("1.25", "25", CLAUSE_TEXT, "2026-01-01", [LINK]), amending(),
                                              vat("1", None, ARTICLE_TEXT, "2025-07-01", [ARTICLE_LINK])))
    assert [source.get("ids") for source in sources] == [["1.25", "1"], ["2"]]
    article = sources[0]
    assert (article["article"], article.get("clauses")) == ("5", ["25"])
    assert (article["text"], article["effective"]) == (ARTICLE_TEXT, "2025-07-01")
    assert article["amended_by"] == [{"target": "1.25", "type": "amends", "source": "2"},
                                     {"target": "1", "type": "amends", "source": "2"}]


def test_the_clauses_of_one_article_are_one_source_in_clause_order(serve):
    sources = sources_of(serve, answer_citing(vat("1.25", "25", CLAUSE_TEXT, "2026-01-01"),
                                              vat("1.3", "3", CLAUSE_3_TEXT, "2026-01-01")))
    assert len(sources) == 1
    source = sources[0]
    assert (source.get("ids"), source.get("clauses")) == (["1.25", "1.3"], ["3", "25"])
    assert (source["text"], source["effective"]) == (CLAUSE_3_TEXT + "\n" + CLAUSE_TEXT, "2026-01-01")


def test_clauses_with_different_dates_give_no_date(serve):
    sources = sources_of(serve, answer_citing(vat("1.25", "25", CLAUSE_TEXT, "2026-01-01"),
                                              vat("1.3", "3", CLAUSE_3_TEXT, "2025-07-01")))
    assert sources[0]["effective"] is None


def test_an_article_cited_alone_has_no_clause(serve):
    source = sources_of(serve, answer_citing(vat("1", None, ARTICLE_TEXT, "2025-07-01")))[0]
    assert (source.get("ids"), source.get("clauses"), source["text"]) == (["1"], [], ARTICLE_TEXT)


def test_a_source_stands_where_its_first_id_is_first_used(serve):
    sources = sources_of(serve, answer_citing(amending(), vat("1.25", "25", CLAUSE_TEXT, "2026-01-01"),
                                              vat("1", None, ARTICLE_TEXT, "2025-07-01")))
    assert [source.get("ids") for source in sources] == [["2"], ["1.25", "1"]]


def test_a_link_two_ids_share_is_listed_once(serve):
    sources = sources_of(serve, answer_citing(vat("1", None, ARTICLE_TEXT, "2025-07-01", [ARTICLE_LINK]),
                                              vat("1.25", "25", CLAUSE_TEXT, "2026-01-01", [ARTICLE_LINK])))
    assert len(sources) == 1
    assert sources[0]["amended_by"] == [{"target": "1", "type": "amends", "source": "2"}]


def test_a_flagged_id_is_not_a_source(serve):
    answer = answer_citing(vat("1.25", "25", CLAUSE_TEXT, "2026-01-01"), Citation("1.9", False),
                           vat("1", None, ARTICLE_TEXT, "2025-07-01"))
    answer.flagged = ["1.9"]
    client = serve(Loader(answer))
    settled(client)
    body = client.post("/api/ask", json={"question": Q1}).json()
    assert ([source.get("ids") for source in body["sources"]], body["flagged"]) == ([["1.25", "1"]], ["1.9"])
