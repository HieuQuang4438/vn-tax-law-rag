"""Chunk the parsed corpus. Run with `python -m src.chunking`."""

from collections import Counter
from pathlib import Path

from src.chunking.chunker import build
from src.chunking.tokens import bge_m3_token_counter

PROCESSED_DIR = Path("data/processed")
CHUNKS_DIR = Path("data/chunks")


def main() -> None:
    issues = build(PROCESSED_DIR, CHUNKS_DIR, bge_m3_token_counter())
    chunks = (CHUNKS_DIR / "chunks.jsonl").read_text(encoding="utf-8").count("\n")
    articles = (CHUNKS_DIR / "articles.jsonl").read_text(encoding="utf-8").count("\n")
    print(f"{articles} articles, {chunks} chunks -> {CHUNKS_DIR}")
    print(f"{len(issues)} issues: {dict(Counter(issue.kind for issue in issues))}")
    for issue in issues:
        print(f"  {issue.doc_id} Điều {issue.article} {issue.kind}: {issue.detail}")


if __name__ == "__main__":
    main()
