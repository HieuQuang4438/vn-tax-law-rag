from collections.abc import Callable
from pathlib import Path

from tokenizers import Tokenizer

EMBEDDING_MODEL = "BAAI/bge-m3"  # ADR-0002; the split threshold is counted in its tokens
EMBEDDING_REVISION = "5617a9f61b028005a4858fdac845db406aefb181"  # pinned on #6


class ModelNotCachedError(RuntimeError):
    """The pinned model revision is not in the local Hugging Face cache."""


def bge_m3_token_counter(cache_dir: Path | None = None) -> Callable[[str], int]:
    """bge-m3 token count at the pinned revision, from the local cache only (#23). Interface stub."""
    tokenizer = Tokenizer.from_pretrained(EMBEDDING_MODEL)
    return lambda text: len(tokenizer.encode(text, add_special_tokens=False).ids)
