"""AC-006: the vector index and the keyword index hold the same chunk ids. Approach approved on #6.
AC-013 / NFR-005: two builds from the same chunks give identical keyword-index files.

The format is `docs/reference/index.md`. Unit tests build from a few chunks in the shape of
`data/enriched/chunks.jsonl` with a fake embedder that gives deterministic vectors, so no model is
loaded and nothing goes to the network. The corpus tests at the end read the local
`data/enriched/` and `data/index/` (gitignored): `pytest -m corpus`.
"""

import hashlib
import json
import math
import os
import socket
import subprocess
import sys
import unicodedata
from contextlib import contextmanager
from pathlib import Path

import bm25s
import chromadb
import pytest
from chromadb.api.client import SharedSystemClient
from chromadb.config import Settings

from src.index import (
    BM25_TOKENIZER,
    EMBEDDING_MODEL,
    EMBEDDING_REVISION,
    ModelNotCachedError,
    build,
    load_embedder,
    tokenize,
)

ROOT = Path(__file__).resolve().parent.parent
DIM = 8
BM25_FILES = ("params.index.json", "vocab.index.json", "data.csc.index.npy", "indices.csc.index.npy",
              "indptr.csc.index.npy", "ids.json")


def fake_vector(text: str) -> list[float]:
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    vector = [b - 127.5 for b in digest[:DIM]]
    norm = math.sqrt(sum(x * x for x in vector))
    return [x / norm for x in vector]


class FakeEmbedder:
    model = EMBEDDING_MODEL

    def __init__(self, revision: str = EMBEDDING_REVISION, fail: bool = False):
        self.revision = revision
        self.fail = fail
        self.calls: list[str] = []

    def embed(self, texts: list[str]) -> list[list[float]]:
        if self.fail:
            raise RuntimeError("embedding stopped")
        self.calls.extend(texts)
        return [fake_vector(t) for t in texts]


CIRCULAR = "[Thông tư 90/2026/TT-BTC — Quy định về đăng ký thuế]"
LAW = "[Luật 149/2025/QH15 — Luật sửa đổi, bổ sung một số điều của Luật Thuế giá trị gia tăng]"
RECORDS = [
    ("439827:D1", f"{CIRCULAR} [Chương I. QUY ĐỊNH CHUNG > Điều 1. Phạm vi điều chỉnh]",
     "Thông tư này quy định về đăng ký thuế."),
    ("439827:D5:K1", f"{CIRCULAR} [Chương I. QUY ĐỊNH CHUNG > Điều 5. Cấu trúc mã số thuế > Khoản 1]",
     "1. Mã số thuế thực hiện theo quy định tại khoản 1, 2, 3 và 4 Điều 11 Luật số 108/2025/QH15."),
    ("439827:D5:K2", f"{CIRCULAR} [Chương I. QUY ĐỊNH CHUNG > Điều 5. Cấu trúc mã số thuế > Khoản 2]",
     "2. Hộ kinh doanh, cá nhân kinh doanh được cấp mã số thuế."),
    ("421739:D1", f"{LAW} [Điều 1. Sửa đổi, bổ sung một số điều của Luật Thuế giá trị gia tăng]",
     "Sửa đổi, bổ sung khoản 25 Điều 5 Luật Thuế giá trị gia tăng số 48/2024/QH15 như sau:"),
]


def record(chunk_id: str, header: str, text: str) -> dict:
    doc_id, article, *rest = chunk_id.split(":")
    return {
        "id": chunk_id, "doc_id": doc_id, "chapter": None, "chapter_title": None,
        "article": article[1:], "clause": rest[0][1:] if rest else None,
        "parent_id": f"{doc_id}:{article}", "text": text, "header": header,
        "effective_date": "2026-07-01", "amended_by": [],
    }


def write_chunks(enriched_dir: Path, records=RECORDS) -> list[dict]:
    rows = [record(*r) for r in records]
    enriched_dir.mkdir(parents=True, exist_ok=True)
    with (enriched_dir / "chunks.jsonl").open("w", encoding="utf-8", newline="\n") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return rows


def indexed(row: dict) -> str:
    return row["header"] + "\n" + row["text"]


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@contextmanager
def chroma(index_dir: Path):
    path = index_dir / "chroma"
    assert path.is_dir(), f"no vector index at {path}"
    client = chromadb.PersistentClient(path=str(path), settings=Settings(anonymized_telemetry=False))
    try:
        yield client.get_collection("chunks")
    finally:
        SharedSystemClient.clear_system_cache()  # release the files, so a rebuild can delete them


def chroma_ids(index_dir: Path) -> list[str]:
    with chroma(index_dir) as collection:
        return collection.get()["ids"]


def bm25_file(index_dir: Path, name: str) -> Path:
    path = index_dir / "bm25" / name
    assert path.is_file(), f"no {name} in the keyword index"
    return path


def bm25_ids(index_dir: Path) -> list[str]:
    return json.loads(bm25_file(index_dir, "ids.json").read_text(encoding="utf-8"))


def manifest(index_dir: Path) -> dict:
    path = index_dir / "manifest.json"
    assert path.is_file(), "no manifest"
    return json.loads(path.read_text(encoding="utf-8"))


def cache_keys(index_dir: Path, revision: str = EMBEDDING_REVISION) -> list[str]:
    path = index_dir / "embeddings" / f"BAAI--bge-m3@{revision}" / "keys.json"
    assert path.is_file(), f"no vector cache for revision {revision}"
    return json.loads(path.read_text(encoding="utf-8"))


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
def built(tmp_path, connections):
    enriched, index = tmp_path / "enriched", tmp_path / "index"
    rows = write_chunks(enriched)
    embedder = FakeEmbedder()
    result = build(enriched, index, embedder)
    return rows, enriched, index, embedder, result


# --- Tokens (BM25 default until #10) --------------------------------------------------------


@pytest.mark.parametrize("text, tokens", [
    ("Luật số 48/2024/QH15,", ["luật", "số", "48/2024/qh15"]),
    ("khoản 25 Điều 5.", ["khoản", "25", "điều", "5"]),
    ("đ) Hộ kinh doanh", ["đ", "hộ", "kinh", "doanh"]),
    ("– (trừ", ["trừ"]),
    ("a, b và c", ["a", "b", "và", "c"]),
    ("Thuế\ngiá  trị\tgia tăng", ["thuế", "giá", "trị", "gia", "tăng"]),
])
def test_syllable_tokens(text, tokens):
    assert tokenize(text) == tokens


def test_decomposed_text_gives_the_same_tokens_as_composed():
    assert tokenize(unicodedata.normalize("NFD", "Thuế GIÁ TRỊ")) == ["thuế", "giá", "trị"]


# --- Both indexes over the same ids (AC-006) ------------------------------------------------


def test_both_indexes_hold_exactly_the_chunk_ids(built):
    rows, _, index, _, _ = built
    ids = [row["id"] for row in rows]
    vector_ids, keyword_ids = chroma_ids(index), bm25_ids(index)
    assert len(vector_ids) == len(set(vector_ids)) == len(ids)
    assert len(keyword_ids) == len(set(keyword_ids)) == len(ids)
    assert set(vector_ids) == set(keyword_ids) == set(ids)


def test_keyword_index_rows_follow_the_chunk_file_order(built):
    rows, _, index, _, _ = built
    assert bm25_ids(index) == [row["id"] for row in rows]
    assert bm25s.BM25.load(str(index / "bm25")).scores["num_docs"] == len(rows)


def test_a_rebuild_drops_a_removed_chunk_from_both_indexes(built):
    rows, enriched, index, _, _ = built
    write_chunks(enriched, RECORDS[:-1])
    build(enriched, index, FakeEmbedder())
    kept = {row["id"] for row in rows[:-1]}
    assert set(chroma_ids(index)) == set(bm25_ids(index)) == kept


# --- Vector index ---------------------------------------------------------------------------


def test_each_vector_is_the_embedding_of_header_and_text(built):
    rows, _, index, _, _ = built
    with chroma(index) as collection:
        for row in rows:
            found = collection.query(query_embeddings=[fake_vector(indexed(row))], n_results=1)
            assert found["ids"] == [[row["id"]]]
            assert found["distances"][0][0] < 1e-5


def test_vector_records_carry_doc_id_and_no_text(built):
    rows, _, index, _, _ = built
    with chroma(index) as collection:
        stored = collection.get(include=["metadatas", "documents"])
        assert collection.configuration_json["hnsw"]["space"] == "cosine"
    doc_ids = dict(zip(stored["ids"], stored["metadatas"]))
    assert doc_ids == {row["id"]: {"doc_id": row["doc_id"]} for row in rows}
    assert stored["documents"] == [None] * len(rows)


def test_texts_are_embedded_in_chunk_file_order(built):
    rows, _, _, embedder, _ = built
    assert embedder.calls == [indexed(row) for row in rows]


# --- Vector cache ---------------------------------------------------------------------------


def test_an_unchanged_rebuild_embeds_nothing(built):
    _, enriched, index, _, _ = built
    again = FakeEmbedder()
    assert build(enriched, index, again).get("embedded") == 0
    assert again.calls == []


def test_a_changed_chunk_is_the_only_text_embedded_again(built):
    _, enriched, index, _, _ = built
    changed = [*RECORDS[:2], (RECORDS[2][0], RECORDS[2][1], "2. Nội dung mới."), *RECORDS[3:]]
    rows = write_chunks(enriched, changed)
    again = FakeEmbedder()
    assert build(enriched, index, again).get("embedded") == 1
    assert again.calls == [indexed(rows[2])]
    with chroma(index) as collection:
        assert collection.query(query_embeddings=[fake_vector(indexed(rows[2]))], n_results=1)["ids"] == [[rows[2]["id"]]]


def test_another_model_revision_embeds_everything(built):
    rows, enriched, index, _, _ = built
    other = FakeEmbedder(revision="0" * 40)
    assert build(enriched, index, other).get("embedded") == len(rows)
    assert other.calls == [indexed(row) for row in rows]


def test_the_cache_holds_exactly_the_current_texts(built):
    rows, enriched, index, _, _ = built
    assert cache_keys(index) == sorted(sha256(indexed(row)) for row in rows)
    write_chunks(enriched, RECORDS[:-1])
    build(enriched, index, FakeEmbedder())
    assert cache_keys(index) == sorted(sha256(indexed(row)) for row in rows[:-1])


def test_two_chunks_with_the_same_indexed_text_share_one_vector(tmp_path, connections):
    enriched, index = tmp_path / "enriched", tmp_path / "index"
    duplicate = ("439827:D6", RECORDS[0][1], RECORDS[0][2])
    rows = write_chunks(enriched, [*RECORDS, duplicate])
    embedder = FakeEmbedder()
    assert build(enriched, index, embedder).get("embedded") == len(RECORDS)
    assert embedder.calls.count(indexed(rows[0])) == 1
    assert cache_keys(index) == sorted({sha256(indexed(row)) for row in rows})


# --- Keyword index --------------------------------------------------------------------------


def test_vocabulary_is_every_corpus_token_sorted_with_numbers_whole(built):
    rows, _, index, _, _ = built
    vocab = json.loads(bm25_file(index, "vocab.index.json").read_text(encoding="utf-8"))
    tokens = sorted({t for row in rows for t in tokenize(indexed(row))})
    assert [t for t, _ in sorted(vocab.items(), key=lambda item: item[1]) if t != ""] == tokens
    assert "48/2024/qh15" in vocab and "108/2025/qh15" in vocab
    assert "48" not in vocab


def test_keyword_index_finds_a_chunk_by_its_document_number(built):
    _, _, index, _, _ = built
    retriever = bm25s.BM25.load(str(bm25_file(index, "params.index.json").parent))
    found, _ = retriever.retrieve([tokenize("Luật số 48/2024/QH15")], k=1, show_progress=False)
    assert bm25_ids(index)[found[0][0]] == "421739:D1"


def test_keyword_index_files_are_the_bm25s_files_and_the_ids(built):
    _, _, index, _, _ = built
    folder = index / "bm25"
    assert folder.is_dir(), "no keyword index"
    assert sorted(p.name for p in folder.iterdir()) == sorted(BM25_FILES)


def run_build(enriched: Path, index: Path, seed: str) -> None:
    code = ("import sys; from pathlib import Path; from tests.test_index import FakeEmbedder; "
            "from src.index import build; build(Path(sys.argv[1]), Path(sys.argv[2]), FakeEmbedder())")
    env = {**os.environ, "PYTHONHASHSEED": seed}
    subprocess.run([sys.executable, "-c", code, str(enriched), str(index)], cwd=ROOT, env=env, check=True)


def bm25_bytes(index: Path) -> dict[str, bytes]:
    return {name: bm25_file(index, name).read_bytes() for name in BM25_FILES}


def test_two_builds_write_identical_keyword_index_files_whatever_the_hash_seed(tmp_path):
    enriched = tmp_path / "enriched"
    write_chunks(enriched)
    run_build(enriched, tmp_path / "one", "1")
    run_build(enriched, tmp_path / "two", "2")
    assert bm25_bytes(tmp_path / "one") == bm25_bytes(tmp_path / "two")


# --- Manifest -------------------------------------------------------------------------------


def test_manifest_records_what_the_index_was_built_from(built):
    rows, enriched, index, _, result = built
    written = manifest(index)
    assert written == result
    assert written["model"] == EMBEDDING_MODEL
    assert written["revision"] == EMBEDDING_REVISION
    assert written["dimension"] == DIM
    assert written["chunks_sha256"] == hashlib.sha256((enriched / "chunks.jsonl").read_bytes()).hexdigest()
    assert written["chunk_count"] == len(rows)
    assert written["bm25_tokenizer"] == BM25_TOKENIZER == "syllable"
    assert written["embedded"] == len(rows)
    assert isinstance(written["seconds"], (int, float)) and written["seconds"] >= 0
    assert set(written["versions"]) == {"bm25s", "chromadb", "sentence-transformers", "torch"}


def test_a_build_that_stops_early_leaves_no_manifest(built):
    _, enriched, index, _, _ = built
    assert (index / "manifest.json").is_file()
    write_chunks(enriched, [*RECORDS[:-1], (RECORDS[-1][0], RECORDS[-1][1], "Nội dung đã sửa.")])
    with pytest.raises(RuntimeError, match="embedding stopped"):
        build(enriched, index, FakeEmbedder(fail=True))
    assert not (index / "manifest.json").exists()


# --- Model loading --------------------------------------------------------------------------


def test_a_missing_model_cache_stops_with_the_download_command_and_no_request(tmp_path, connections):
    with pytest.raises(ModelNotCachedError) as error:
        load_embedder(cache_dir=tmp_path)
    assert f"hf download {EMBEDDING_MODEL} --revision {EMBEDDING_REVISION}" in str(error.value)
    assert connections == []


# --- The real model and corpus (AC-006, AC-013) -----------------------------------------------

ENRICHED_DIR = ROOT / "data" / "enriched"
INDEX_DIR = ROOT / "data" / "index"


@pytest.mark.corpus
def test_cached_model_loads_offline_at_the_pinned_revision(connections):
    embedder = load_embedder()
    assert (getattr(embedder, "model", None), getattr(embedder, "revision", None)) == (EMBEDDING_MODEL, EMBEDDING_REVISION)
    [vector] = embedder.embed(["Thuế giá trị gia tăng"])
    assert len(vector) == 1024
    assert abs(sum(x * x for x in vector) - 1) < 1e-4
    assert connections == []


@pytest.mark.corpus
def test_the_built_index_matches_the_enriched_chunks():
    """Run `python -m src.index` first."""
    chunks = (ENRICHED_DIR / "chunks.jsonl").read_bytes()
    ids = [json.loads(line)["id"] for line in chunks.decode("utf-8").splitlines()]
    written = manifest(INDEX_DIR)
    assert written["chunks_sha256"] == hashlib.sha256(chunks).hexdigest(), "index is older than the chunks"
    assert (written["model"], written["revision"], written["dimension"]) == (EMBEDDING_MODEL, EMBEDDING_REVISION, 1024)
    assert written["chunk_count"] == len(ids) == len(set(ids))
    vector_ids = chroma_ids(INDEX_DIR)
    assert len(vector_ids) == len(ids)
    assert set(vector_ids) == set(bm25_ids(INDEX_DIR)) == set(ids)
    assert bm25_ids(INDEX_DIR) == ids


@pytest.mark.corpus
def test_two_builds_of_the_corpus_write_identical_keyword_index_files(tmp_path):
    run_build(ENRICHED_DIR, tmp_path / "one", "1")
    run_build(ENRICHED_DIR, tmp_path / "two", "2")
    assert bm25_bytes(tmp_path / "one") == bm25_bytes(tmp_path / "two")
