"""AC-003: every chunk gets a context header, apart from its text. Approach approved on #3.

The header form and its rules are in `docs/reference/chunk-schema.md`
(`data/enriched/chunks.jsonl`). Fixtures are small documents in the shape of
`data/processed/<slug>.json`; tokens are counted as words, so no tokenizer is needed. The corpus
test at the end runs over the local `data/processed/` (gitignored): `pytest -m corpus`.
"""

import json
from pathlib import Path

import pytest

from src.chunking import build as build_chunks
from src.chunking import chunk_document
from src.enrich import build, enrich_document, indexed_text

ROOT = Path(__file__).resolve().parent.parent
DOC_ID = "439827"
CIRCULAR = "[Thông tư 90/2026/TT-BTC — Quy định về đăng ký thuế]"
SIGNATURE = "Nơi nhận: - Lưu: VT, CT. | KT. BỘ TRƯỞNG THỨ TRƯỞNG Cao Anh Tuấn"


def words(text: str) -> int:
    return len(text.split())


def make_doc(*texts: str, doc_id: str = DOC_ID, kind: str = "Thông tư", number: str = "90/2026/TT-BTC",
             title: str = "Quy định về đăng ký thuế") -> dict:
    return {
        "source_url": f"https://luatvietnam.vn/thue/van-ban-{doc_id}-d1.html",
        "crawled_at": "2026-11-04T00:00:00+00:00",
        "metadata": {"so_hieu": number, "loai_van_ban": kind, "trich_yeu": title},
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
        "Điều 3. Hiệu lực thi hành\nThông tư này có hiệu lực từ ngày ký.",
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
    assert all(e == {**c, "header": e["header"]} for e, c in zip(enriched, chunks))
    assert enriched[0]["header"] == f"{CIRCULAR} [Chương I. QUY ĐỊNH CHUNG > Điều 1. Phạm vi điều chỉnh]"
    assert "indexed_text" not in enriched[0]


def test_build_is_deterministic(tmp_path):
    first, second = built(tmp_path, "a"), built(tmp_path, "b")

    assert first.read_bytes() == second.read_bytes()


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
