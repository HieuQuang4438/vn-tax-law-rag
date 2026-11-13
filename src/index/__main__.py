"""Build both indexes. Run `python -m src.enrich` first, then `python -m src.index`."""

from pathlib import Path

from src.index.builder import build, load_embedder

ENRICHED_DIR = Path("data/enriched")
INDEX_DIR = Path("data/index")


def main(argv: list[str] | None = None) -> None:
    manifest = build(ENRICHED_DIR, INDEX_DIR, load_embedder())
    print(f"{manifest['chunk_count']} chunks -> {INDEX_DIR} (vector + BM25)")
    print(f"{manifest['embedded']} texts embedded, the rest from the cache; {manifest['seconds']} s")
    print(f"{manifest['model']}@{manifest['revision'][:7]}, {manifest['dimension']} dimensions, "
          f"BM25 tokens: {manifest['bm25_tokenizer']}")


if __name__ == "__main__":
    main()
