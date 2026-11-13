"""BM25 tokenizers: syllable (#6) and the two word segmenters compared on #10. Approach approved on #10.

The rules are `docs/reference/index.md`, *Keyword index*. The segmenters are in
`requirements-experiments.txt`; a machine without them skips their tests.
"""

import socket
import unicodedata

import pytest

from src.index import TOKENIZERS, get_tokenizer, tokenize

SEGMENTERS = ("underthesea", "pyvi")


@pytest.fixture
def connections(monkeypatch) -> list:
    """Every outgoing connection attempt; each one fails."""
    attempts = []

    def refuse(sock, address):
        attempts.append(address)
        raise OSError("network blocked in unit tests")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    return attempts


@pytest.fixture(params=SEGMENTERS)
def segmenter(request, connections):
    pytest.importorskip(request.param)
    return get_tokenizer(request.param)


def test_the_three_tokenizers_by_name():
    assert TOKENIZERS == ("syllable", "underthesea", "pyvi")
    assert get_tokenizer("syllable") is tokenize


def test_an_unknown_tokenizer_name_is_refused():
    with pytest.raises(ValueError, match="nltk"):
        get_tokenizer("nltk")


def test_a_segmenter_joins_the_syllables_of_a_word(segmenter):
    tokens = segmenter("Hộ kinh doanh có doanh thu năm từ 500 triệu đồng trở xuống.")
    assert "kinh_doanh" in tokens and "doanh_thu" in tokens
    assert all(t == t.lower() and " " not in t and t for t in tokens), tokens


def test_document_numbers_and_dates_stay_one_token(segmenter):
    tokens = segmenter("Theo Luật 48/2024/QH15, hóa đơn lập ngày 15/12/2025 (Nghị định 68/2026/NĐ-CP).")
    assert {"48/2024/qh15", "15/12/2025", "68/2026/nđ-cp"} <= set(tokens), tokens
    assert "2024" not in tokens and "qh15" not in tokens


def test_word_tokens_keep_the_order_of_the_text(segmenter):
    tokens = segmenter("Luật 48/2024/QH15 quy định thuế giá trị gia tăng")
    assert tokens.index("48/2024/qh15") > tokens.index("luật")
    assert tokens.index("48/2024/qh15") < tokens.index("thuế") if "thuế" in tokens else True


def test_punctuation_is_stripped_and_no_token_is_empty(segmenter):
    tokens = segmenter("– (trừ) hàng hóa, dịch vụ; “xuất khẩu”.")
    assert tokens and all(t and t[0].isalnum() and t[-1].isalnum() for t in tokens), tokens


def test_decomposed_unicode_reads_as_composed(segmenter):
    text = "Hộ kinh doanh nộp thuế thu nhập cá nhân"
    assert segmenter(unicodedata.normalize("NFD", text)) == segmenter(text)


def test_a_segmenter_makes_no_network_request(segmenter, connections):
    assert segmenter("Cá nhân kinh doanh nộp thuế theo phương pháp kê khai.")
    assert connections == []
