"""BM25 tokenizers (#6, #10). Rules: `docs/reference/index.md`, *Keyword index*.

`syllable` needs nothing. The word segmenters are imported only when used; they are pinned in
`requirements-experiments.txt`.
"""

import unicodedata
from collections.abc import Callable
from functools import cache

TOKENIZERS = ("syllable", "underthesea", "pyvi")


def _strip(word: str) -> str:
    """The word without the characters at either end that are neither a letter nor a digit."""
    start, end = 0, len(word)
    while start < end and not word[start].isalnum():
        start += 1
    while end > start and not word[end - 1].isalnum():
        end -= 1
    return word[start:end]


def tokenize(text: str) -> list[str]:
    """The `syllable` tokens of a chunk or a question."""
    tokens = []
    for word in unicodedata.normalize("NFC", text).lower().split():
        word = _strip(word)
        if word:
            tokens.append(word)
    return tokens


def _segmenter(name: str) -> Callable[[str], list[str]]:
    """The words of a text, each one string with its syllables separated by spaces or `_`."""
    if name == "underthesea":
        from underthesea import word_tokenize

        return word_tokenize
    from pyvi import ViTokenizer

    return lambda text: ViTokenizer.tokenize(text).split()


def _word_tokenizer(name: str) -> Callable[[str], list[str]]:
    segment = _segmenter(name)

    def tokenize_words(text: str) -> list[str]:
        tokens: list[str] = []
        run: list[str] = []

        def flush() -> None:
            if run:
                for word in segment(" ".join(run)):
                    joined = "_".join(word.replace("_", " ").split())
                    token = _strip(unicodedata.normalize("NFC", joined).lower())
                    if token:
                        tokens.append(token)
                run.clear()

        for piece in unicodedata.normalize("NFC", text).split():
            stripped = _strip(piece.lower())
            if "/" in stripped:  # a document number or a date: one token, as syllable makes it
                flush()
                tokens.append(stripped)
            else:
                run.append(piece)
        flush()
        return tokens

    return tokenize_words


@cache
def get_tokenizer(name: str) -> Callable[[str], list[str]]:
    """The tokenizer called `name`; ValueError for an unknown name."""
    if name not in TOKENIZERS:
        raise ValueError(f"unknown BM25 tokenizer {name!r}; one of {', '.join(TOKENIZERS)}")
    return tokenize if name == "syllable" else _word_tokenizer(name)
