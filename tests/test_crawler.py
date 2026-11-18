"""AC-001 and NFR-004 / AC-013 (no network on a full cache) for the crawler in `scripts/`.

Unit tests run on abridged HTML fixtures in `tests/fixtures/crawler/`, never on the network.
The corpus test at the end runs the real crawl over the local cache in `data/raw/`, which is
gitignored: opt in with `pytest -m corpus`; it is skipped on a checkout without the cache.
"""

import json
import shutil
import sys
from pathlib import Path

import pytest
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))  # crawl_index imports crawl_one as a sibling script

import crawl_index  # noqa: E402
import crawl_one  # noqa: E402

from src.chunking import chunk_document  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures" / "crawler"
SITE = "https://luatvietnam.vn"
TAX_INDEX = f"{SITE}/thue-phi-le-phi/tong-hop-danh-sach-luat-thue-565-110892-article.html"
PIT_INDEX = f"{SITE}/thue-phi-le-phi/tong-hop-van-ban-thue-tncn-565-96172-article.html"
VAT_LAW = f"{SITE}/thue/luat-thue-gia-tri-gia-tang-2024-so-48-2024-qh15-379409-d1.html"
AMENDING_LAW = f"{SITE}/thue/luat-thue-sua-doi-2026-so-09-2026-qh16-434729-d1.html"
PIT_LAW = f"{SITE}/thue/luat-thue-thu-nhap-ca-nhan-2025-so-109-2025-qh15-422733-d1.html"
DOCUMENTS = [VAT_LAW, AMENDING_LAW, PIT_LAW]


class NetworkCalled(AssertionError):
    pass


@pytest.fixture
def no_network(monkeypatch):
    def refuse(*args, **kwargs):
        raise NetworkCalled(f"network request: {args[0] if args else kwargs}")

    monkeypatch.setattr(crawl_one.requests, "get", refuse)


@pytest.fixture
def sleeps(monkeypatch) -> list[float]:
    calls: list[float] = []
    monkeypatch.setattr(crawl_index.time, "sleep", calls.append)
    return calls


@pytest.fixture
def dirs(tmp_path, monkeypatch) -> tuple[Path, Path]:
    raw, out = tmp_path / "raw", tmp_path / "processed"
    raw.mkdir()
    for module in (crawl_one, crawl_index):
        monkeypatch.setattr(module, "RAW_DIR", raw)
        monkeypatch.setattr(module, "OUT_DIR", out)
    return raw, out


def cache(raw: Path, url: str, fixture: str) -> None:
    shutil.copy(FIXTURES / fixture, raw / f"{crawl_one.slug_from_url(url)}.html")


@pytest.fixture
def full_cache(dirs) -> tuple[Path, Path]:
    raw, out = dirs
    cache(raw, TAX_INDEX, "index_tax.html")
    cache(raw, PIT_INDEX, "index_pit.html")
    for url in DOCUMENTS:
        cache(raw, url, "document.html")
    return raw, out


def manifest(out: Path) -> dict:
    return json.loads((out / "_index.json").read_text(encoding="utf-8"))


# --- The document list ---------------------------------------------------------------------


def test_every_listed_document_is_crawled_exactly_once(full_cache, no_network, sleeps):
    crawl_index.main([TAX_INDEX, PIT_INDEX])

    docs = manifest(full_cache[1])["documents"]
    assert [d["url"] for d in docs] == DOCUMENTS
    assert [d["status"] for d in docs] == ["ok", "ok", "ok"]


def test_document_listed_in_both_articles_records_both(full_cache, no_network, sleeps):
    crawl_index.main([TAX_INDEX, PIT_INDEX])

    listed_in = {d["doc_id"]: d["listed_in"] for d in manifest(full_cache[1])["documents"]}
    assert listed_in["434729"] == [TAX_INDEX, PIT_INDEX]
    assert listed_in["379409"] == [TAX_INDEX]
    assert listed_in["422733"] == [PIT_INDEX]


def test_only_document_links_inside_the_article_table_are_taken(full_cache, no_network):
    ids = [d["doc_id"] for d in crawl_index.document_links([TAX_INDEX])]

    # Not taken: the link outside the table, the trial link, the news link, sidebar and footer.
    assert ids == ["379409", "434729"]


def test_relative_links_are_resolved_against_the_article(full_cache, no_network):
    urls = [d["url"] for d in crawl_index.document_links([TAX_INDEX])]

    assert urls == [VAT_LAW, AMENDING_LAW]


def test_manifest_records_the_summary_articles_it_was_built_from(full_cache, no_network, sleeps):
    crawl_index.main([TAX_INDEX, PIT_INDEX])

    assert manifest(full_cache[1])["index_urls"] == [TAX_INDEX, PIT_INDEX]


def test_one_failing_page_does_not_stop_the_batch(full_cache, no_network, sleeps):
    raw, out = full_cache
    (raw / f"{crawl_one.slug_from_url(VAT_LAW)}.html").write_text("<html><body></body></html>", encoding="utf-8")

    crawl_index.main([TAX_INDEX, PIT_INDEX])

    assert [d["status"] for d in manifest(out)["documents"]] == ["error", "ok", "ok"]


# --- One document ----------------------------------------------------------------------------


def parsed() -> dict:
    soup = BeautifulSoup((FIXTURES / "document.html").read_text(encoding="utf-8"), "lxml")
    return {"metadata": crawl_one.parse_metadata(soup), "blocks": crawl_one.parse_body(soup)}


def test_metadata_has_number_type_issuer_and_issue_date():
    meta = parsed()["metadata"]

    assert meta["so_hieu"] == "09/2026/QH16"
    assert meta["loai_van_ban"] == "Luật"
    assert meta["co_quan_ban_hanh"] == "Quốc hội"
    assert meta["ngay_ban_hanh"] == "24/04/2026"
    assert meta["trich_yeu"] == "Sửa đổi, bổ sung một số điều của Luật Thuế thu nhập cá nhân"


def test_paid_only_fields_are_left_out_rather_than_stored_as_placeholder():
    meta = parsed()["metadata"]

    assert "ngay_hieu_luc" not in meta
    assert "Đã biết" not in json.dumps(meta, ensure_ascii=False)


def test_body_comes_from_the_document_text_not_the_summary_tab():
    texts = "\n".join(b["text"] for b in parsed()["blocks"])

    assert "Miễn thuế cho doanh nghiệp" not in texts
    assert [b["id"] for b in parsed()["blocks"]][0] == "demuc3663453"


def test_blocks_keep_document_order_id_and_kind():
    blocks = parsed()["blocks"]

    assert [b["id"] for b in blocks] == [
        "demuc3663453", "demuc3663455", "demuc3663457", "demuc3663460", "demuc3663461", "demuc3663462",
    ]
    assert blocks[2]["kind"] == "docitem-5"


def test_site_widgets_and_empty_blocks_are_dropped():
    blocks = parsed()["blocks"]

    assert "Theo dõi" not in "\n".join(b["text"] for b in blocks)
    assert "demuc3663499" not in [b["id"] for b in blocks]


def amended_clause_lines() -> list[str]:
    soup = BeautifulSoup((FIXTURES / "amended_clause.html").read_text(encoding="utf-8"), "lxml")
    return "\n".join(b["text"] for b in crawl_one.parse_body(soup)).split("\n")


def test_amendment_label_is_dropped_but_the_amended_clause_is_kept():
    # Decree 181/2025, Article 4 (#21): the site's "Bổ sung" label became a line of the text.
    lines = amended_clause_lines()

    assert "Bổ sung" not in lines
    assert lines[:3] == [
        "Điều 4. Đối tượng không chịu thuế",
        "1. Sản phẩm cây trồng, rừng trồng, chăn nuôi, thủy sản nuôi trồng, đánh bắt chưa chế biến thành các sản phẩm khác.",
        "2. Nhà ở thuộc tài sản công do Nhà nước bán cho người đang thuê.",
    ]


def test_site_comment_block_is_dropped():
    # Law 48/2024, Article 9 (#21): the site's note on the 2% VAT cut was read as a provision.
    lines = amended_clause_lines()

    assert not any("giảm 2% thuế suất" in line for line in lines)
    assert lines[-2:] == [
        "2. Nhà ở thuộc tài sản công do Nhà nước bán cho người đang thuê.",
        "3. Chuyển quyền sử dụng đất theo quy định của pháp luật về đất đai.",
    ]


def test_line_breaks_and_paragraphs_become_lines():
    heading_block = parsed()["blocks"][0]["text"]

    assert heading_block.split("\n")[0] == "QUỐC HỘI _______ Luật số: 09/2026/QH16 | CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM"


def test_article_heading_as_bare_text_next_to_a_table_is_kept():
    # Law 09/2026, Article 4: the heading is a text node beside a table, not a <p>; it was once lost.
    lines = parsed()["blocks"][3]["text"].split("\n")

    assert lines[0] == "Điều 4. Sửa đổi, bổ sung quy định về xe chạy bằng pin"
    assert lines[2] == "- Xe ô tô chở người từ 9 chỗ trở xuống | - Từ 01/01/2026: 3 - Từ 01/01/2031: 11"


def test_crawl_writes_json_and_markdown_for_the_document(full_cache, no_network):
    raw, out = full_cache
    crawl_one.crawl(AMENDING_LAW)

    slug = crawl_one.slug_from_url(AMENDING_LAW)
    doc = json.loads((out / f"{slug}.json").read_text(encoding="utf-8"))
    assert doc["source_url"] == AMENDING_LAW
    assert (out / f"{slug}.md").read_text(encoding="utf-8").startswith("QUỐC HỘI")


# --- Cache and politeness (NFR-004, AC-013) ------------------------------------------------


def test_rerun_on_a_full_cache_makes_no_network_request_and_does_not_wait(full_cache, no_network, sleeps):
    crawl_index.main([TAX_INDEX, PIT_INDEX])

    assert sleeps == []  # no_network fails the test on any request


class FakeResponse:
    def __init__(self, text: str):
        self.text, self.encoding = text, None

    def raise_for_status(self) -> None:
        pass


def test_uncached_pages_are_fetched_once_cached_and_spaced_3_seconds_apart(dirs, monkeypatch, sleeps):
    raw, out = dirs
    cache(raw, TAX_INDEX, "index_tax.html")
    cache(raw, PIT_INDEX, "index_pit.html")
    cache(raw, VAT_LAW, "document.html")  # cached: no request, no wait
    fetched: list[str] = []

    def get(url, **kwargs):
        fetched.append(url)
        return FakeResponse((FIXTURES / "document.html").read_text(encoding="utf-8"))

    monkeypatch.setattr(crawl_one.requests, "get", get)
    crawl_index.main([TAX_INDEX, PIT_INDEX])

    assert fetched == [AMENDING_LAW, PIT_LAW]
    assert sleeps == [3]  # after the first live fetch; none after the last document
    assert (raw / f"{crawl_one.slug_from_url(PIT_LAW)}.html").exists()

    fetched.clear()
    crawl_index.main([TAX_INDEX, PIT_INDEX])
    assert fetched == []


def test_delay_between_live_requests_is_at_least_3_seconds():
    assert crawl_index.DELAY_SECONDS >= 3


# --- The real corpus (AC-001) --------------------------------------------------------------

REAL_RAW = ROOT / "data" / "raw"
CORPUS_SIZE = 30  # as of 2026-11-04, acceptance.md AC-001


# Phrases from the 22 site comment blocks (div.docitem-binhluan) in the corpus as of 2026-11-12.
SITE_COMMENTS = (
    "giảm 2% thuế suất thuế giá trị gia tăng",
    "Nghị quyết 66.18/2026/NQ-CP",
    "nêu tại khoản 1 Điều 8 được sửa đổi, bổ sung bởi",
    "được thay thế bởi Phụ lục",
    "thay thế bằng biểu Mẫu số",
    "được thay thế bởi Mẫu số",
    "được thay thế bởi khoản Mẫu số",
)


def corpus_cached() -> bool:
    return all(
        (REAL_RAW / f"{crawl_one.slug_from_url(url)}.html").exists() for url in crawl_index.INDEX_URLS
    )


@pytest.mark.corpus
@pytest.mark.skipif(not corpus_cached(), reason="needs the local crawl cache in data/raw/")
def test_corpus_crawl_from_cache_meets_ac_001(tmp_path, monkeypatch, no_network, sleeps):
    monkeypatch.setattr(crawl_one, "OUT_DIR", tmp_path)
    monkeypatch.setattr(crawl_index, "OUT_DIR", tmp_path)

    crawl_index.main(crawl_index.INDEX_URLS)

    docs = manifest(tmp_path)["documents"]
    assert len(docs) == CORPUS_SIZE
    assert len({d["doc_id"] for d in docs}) == CORPUS_SIZE
    assert all(d["status"] == "ok" for d in docs), [d for d in docs if d["status"] != "ok"]
    assert sleeps == []

    problems = []
    for d in docs:
        doc = json.loads((tmp_path / f"{crawl_one.slug_from_url(d['url'])}.json").read_text(encoding="utf-8"))
        missing = [k for k in ("so_hieu", "loai_van_ban", "co_quan_ban_hanh", "ngay_ban_hanh") if not doc["metadata"].get(k)]
        if missing:
            problems.append((d["doc_id"], "metadata", missing))
        # Articles 1..N with no gap and none lost at the end — the chunker's structural checks.
        result = chunk_document(doc, count_tokens=lambda text: len(text.split()))
        problems += [(d["doc_id"], i.kind, i.article) for i in result.issues
                     if i.kind in ("article_gap", "hidden_heading", "unexpected_last_article")]
        if not result.articles or result.articles[0].article != "1":
            problems.append((d["doc_id"], "no Điều 1", None))
        # The site's amendment label and comment blocks are not document text (#21).
        lines = [line for b in doc["blocks"] for line in b["text"].split("\n")]
        labels = sum(line == "Bổ sung" for line in lines)
        if labels:
            problems.append((d["doc_id"], "amendment label", labels))
        comments = sum(text in line for line in lines for text in SITE_COMMENTS)
        if comments:
            problems.append((d["doc_id"], "site comment", comments))
    assert problems == []
