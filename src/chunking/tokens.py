from collections.abc import Callable

from tokenizers import Tokenizer

EMBEDDING_MODEL = "BAAI/bge-m3"  # ADR-0002; the split threshold is counted in its tokens


def bge_m3_token_counter() -> Callable[[str], int]:
    """Downloads the tokenizer once into the Hugging Face cache, then runs offline."""
    tokenizer = Tokenizer.from_pretrained(EMBEDDING_MODEL)
    return lambda text: len(tokenizer.encode(text, add_special_tokens=False).ids)
