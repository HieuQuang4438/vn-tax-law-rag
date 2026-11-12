"""Enrich the chunked corpus. Run `python -m src.chunking` first, then `python -m src.enrich`."""

from pathlib import Path

from src.chunking.tokens import bge_m3_token_counter
from src.enrich.header import build, indexed_text

PROCESSED_DIR = Path("data/processed")
CHUNKS_DIR = Path("data/chunks")
ENRICHED_DIR = Path("data/enriched")
EMBEDDING_INPUT_LIMIT = 8192  # bge-m3 maximum input, in tokens


def main() -> None:
    chunks = build(PROCESSED_DIR, CHUNKS_DIR, ENRICHED_DIR)
    print(f"{len(chunks)} chunks -> {ENRICHED_DIR}")
    count = bge_m3_token_counter()
    header = max(chunks, key=lambda c: count(c.header))
    indexed = max(chunks, key=lambda c: count(indexed_text(c)))
    print(f"largest header: {count(header.header)} tokens ({header.id})")
    print(f"largest header + text: {count(indexed_text(indexed))} tokens ({indexed.id}), "
          f"limit {EMBEDDING_INPUT_LIMIT}")


if __name__ == "__main__":
    main()
