"""The bge-m3 token count that sets the chunk splits, read offline at the pinned revision (#23).

Format and rules: `docs/reference/chunk-schema.md`, *Tokens*.
"""

from collections.abc import Callable
from pathlib import Path

from tokenizers import Tokenizer

EMBEDDING_MODEL = "BAAI/bge-m3"  # ADR-0002; the split threshold is counted in its tokens
EMBEDDING_REVISION = "5617a9f61b028005a4858fdac845db406aefb181"  # pinned on #6


class ModelNotCachedError(RuntimeError):
    """The pinned model revision is not in the local Hugging Face cache."""


def pinned_snapshot(cache_dir: Path | None = None) -> Path:
    """The snapshot folder of bge-m3 at the pinned revision, from the local cache only.

    Resolved with `local_files_only`, so no Hub call is made and `main` is never read.
    """
    from huggingface_hub import snapshot_download

    try:
        return Path(snapshot_download(EMBEDDING_MODEL, revision=EMBEDDING_REVISION, local_files_only=True,
                                      cache_dir=str(cache_dir) if cache_dir else None))
    except OSError as error:
        raise ModelNotCachedError(
            f"{EMBEDDING_MODEL} revision {EMBEDDING_REVISION} is not in the local Hugging Face cache; "
            f"download it once with: hf download {EMBEDDING_MODEL} --revision {EMBEDDING_REVISION}"
        ) from error


def bge_m3_token_counter(cache_dir: Path | None = None) -> Callable[[str], int]:
    """Tokens in a text, without special tokens, by the pinned bge-m3 tokenizer."""
    tokenizer = Tokenizer.from_file(str(pinned_snapshot(cache_dir) / "tokenizer.json"))
    return lambda text: len(tokenizer.encode(text, add_special_tokens=False).ids)
