"""BM25 tokenizers (#6, #10). Rules: `docs/reference/index.md`, *Keyword index*.

Interface stub for the word segmenters: not implemented yet.
"""

import unicodedata
from collections.abc import Callable

TOKENIZERS = ("syllable", "underthesea", "pyvi")


def tokenize(text: str) -> list[str]:
    """The `syllable` tokens of a chunk or a question."""
    tokens = []
    for word in unicodedata.normalize("NFC", text).lower().split():
        start, end = 0, len(word)
        while start < end and not word[start].isalnum():
            start += 1
        while end > start and not word[end - 1].isalnum():
            end -= 1
        if start < end:
            tokens.append(word[start:end])
    return tokens


def get_tokenizer(name: str) -> Callable[[str], list[str]]:
    """The tokenizer called `name`; ValueError for an unknown name."""
    return tokenize
