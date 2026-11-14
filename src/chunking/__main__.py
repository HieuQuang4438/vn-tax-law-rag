"""Chunk the parsed corpus. Run with `python -m src.chunking`.

`--max-tokens`, `--processed` and `--out` build a variant for an experiment (#12).
"""

import argparse
from collections import Counter
from pathlib import Path

from src.chunking.chunker import MAX_TOKENS, build
from src.chunking.tokens import bge_m3_token_counter

PROCESSED_DIR = Path("data/processed")
CHUNKS_DIR = Path("data/chunks")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m src.chunking", description="Chunk the parsed corpus.")
    parser.add_argument("--max-tokens", type=int, default=MAX_TOKENS, help=f"the split threshold; default {MAX_TOKENS}")
    parser.add_argument("--processed", help="the parsed documents; default data/processed")
    parser.add_argument("--out", help="the output folder; default data/chunks")
    args = parser.parse_args(argv)
    if args.max_tokens < 1:
        parser.error(f"--max-tokens must be at least 1, not {args.max_tokens}")
    processed = Path(args.processed) if args.processed else PROCESSED_DIR
    out = Path(args.out) if args.out else CHUNKS_DIR

    issues = build(processed, out, bge_m3_token_counter(), max_tokens=args.max_tokens)
    chunks = (out / "chunks.jsonl").read_text(encoding="utf-8").count("\n")
    articles = (out / "articles.jsonl").read_text(encoding="utf-8").count("\n")
    print(f"{articles} articles, {chunks} chunks -> {out} (split over {args.max_tokens} tokens)")
    print(f"{len(issues)} issues: {dict(Counter(issue.kind for issue in issues))}")
    for issue in issues:
        print(f"  {issue.doc_id} Điều {issue.article} {issue.kind}: {issue.detail}")


if __name__ == "__main__":
    main()
