"""Build both indexes. Run `python -m src.enrich` first, then `python -m src.index`.

`--tokenizer` and `--out` build a variant for an experiment (#10); the vector cache stays in
`data/index/embeddings/`, so a variant embeds nothing new.
"""

import argparse
from pathlib import Path

from src.index.builder import build, load_embedder
from src.index.tokenizers import TOKENIZERS

ENRICHED_DIR = Path("data/enriched")
INDEX_DIR = Path("data/index")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m src.index", description="Build both indexes.")
    parser.add_argument("--tokenizer", choices=TOKENIZERS, default="syllable", help="the BM25 tokenizer")
    parser.add_argument("--out", help="the index folder; default data/index")
    args = parser.parse_args(argv)
    out = Path(args.out) if args.out else INDEX_DIR

    manifest = build(ENRICHED_DIR, out, load_embedder(), tokenizer=args.tokenizer, cache_dir=INDEX_DIR / "embeddings")
    print(f"{manifest['chunk_count']} chunks -> {out} (vector + BM25)")
    print(f"{manifest['embedded']} texts embedded, the rest from the cache; {manifest['seconds']} s "
          f"({manifest['bm25_seconds']} s for BM25)")
    print(f"{manifest['model']}@{manifest['revision'][:7]}, {manifest['dimension']} dimensions, "
          f"BM25 tokens: {manifest['bm25_tokenizer']}")


if __name__ == "__main__":
    main()
