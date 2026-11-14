"""Enrich the chunked corpus. Run `python -m src.chunking` first, then `python -m src.enrich`.

`--processed`, `--chunks` and `--out` build a variant for an experiment (#12).
"""

import argparse
import json
from collections import Counter
from pathlib import Path

from src.chunking.tokens import bge_m3_token_counter
from src.enrich.header import build, indexed_text

PROCESSED_DIR = Path("data/processed")
CHUNKS_DIR = Path("data/chunks")
ENRICHED_DIR = Path("data/enriched")
EMBEDDING_INPUT_LIMIT = 8192  # bge-m3 maximum input, in tokens


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m src.enrich", description="Enrich the chunked corpus.")
    parser.add_argument("--processed", help="the parsed documents; default data/processed")  # stub
    parser.add_argument("--chunks", help="the chunker's output; default data/chunks")  # stub
    parser.add_argument("--out", help="the output folder; default data/enriched")  # stub
    parser.parse_args(argv)
    chunks, issues = build(PROCESSED_DIR, CHUNKS_DIR, ENRICHED_DIR)
    print(f"{len(chunks)} chunks -> {ENRICHED_DIR}")
    undated = sum(chunk.effective_date is None for chunk in chunks)
    print(f"{len(chunks) - undated} chunks with an effective date, {undated} without")
    links = [json.loads(line) for line in (ENRICHED_DIR / "links.jsonl").read_text(encoding="utf-8").splitlines()]
    print(f"{len(links)} amendment links: {dict(Counter(link['type'] for link in links))}, "
          f"{sum(link['in_corpus'] for link in links)} in the corpus; "
          f"{sum(bool(chunk.amended_by) for chunk in chunks)} chunks with amended_by")
    print(f"{len(issues)} issues: {dict(Counter(issue.kind for issue in issues))}")
    for issue in issues:
        print(f"  {issue.doc_id} Điều {issue.article} {issue.kind}: {issue.detail[:100]}")
    count = bge_m3_token_counter()
    header = max(chunks, key=lambda c: count(c.header))
    indexed = max(chunks, key=lambda c: count(indexed_text(c)))
    print(f"largest header: {count(header.header)} tokens ({header.id})")
    print(f"largest header + text: {count(indexed_text(indexed))} tokens ({indexed.id}), "
          f"limit {EMBEDDING_INPUT_LIMIT}")


if __name__ == "__main__":
    main()
