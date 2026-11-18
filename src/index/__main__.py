"""Build both indexes. Run `python -m src.enrich` first, then `python -m src.index`.

`--tokenizer` and `--out` build a variant for an experiment (#10); the vector cache stays in
`data/index/embeddings/`, so a variant embeds nothing new. `--enriched` indexes other chunks and
`--cache` gives such a variant its own copy of the cache (#12). `--model` and `--input-limit`
choose the embedding model and how much of each text it reads (#11).
"""

import argparse
from pathlib import Path

from src.index.builder import EMBEDDING_MODEL, EMBEDDING_MODELS, build, load_embedder
from src.index.tokenizers import TOKENIZERS

ENRICHED_DIR = Path("data/enriched")
INDEX_DIR = Path("data/index")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m src.index", description="Build both indexes.")
    parser.add_argument("--tokenizer", choices=TOKENIZERS, default="syllable", help="the BM25 tokenizer")
    parser.add_argument("--enriched", help="the enriched chunks; default data/enriched")
    parser.add_argument("--out", help="the index folder; default data/index")
    parser.add_argument("--cache", help="the vector cache; default data/index/embeddings")
    parser.add_argument("--model", choices=list(EMBEDDING_MODELS), default=EMBEDDING_MODEL,
                        help="the embedding model; default BAAI/bge-m3")
    parser.add_argument("--input-limit", type=int, help="the input limit in tokens; default the model's maximum")
    args = parser.parse_args(argv)
    enriched = Path(args.enriched) if args.enriched else ENRICHED_DIR
    out = Path(args.out) if args.out else INDEX_DIR
    cache = Path(args.cache) if args.cache else INDEX_DIR / "embeddings"

    embedder = load_embedder(model=args.model, input_limit=args.input_limit)
    manifest = build(enriched, out, embedder, tokenizer=args.tokenizer, cache_dir=cache)
    print(f"{manifest['chunk_count']} chunks -> {out} (vector + BM25)")
    print(f"{manifest['embedded']} texts embedded, the rest from the cache; {manifest['seconds']} s "
          f"({manifest['bm25_seconds']} s for BM25)")
    print(f"{manifest['model']}@{manifest['revision'][:7]}, {manifest['dimension']} dimensions, "
          f"input limit {manifest['input_limit']} ({manifest['truncated']} texts cut), "
          f"BM25 tokens: {manifest['bm25_tokenizer']}")


if __name__ == "__main__":
    main()
