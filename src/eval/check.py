"""Check the eval set against its format and the local corpus (#7). Run `python -m src.eval.check`.

Rules and messages: `docs/reference/eval-set.md`. Exits 1 when there is any error; warnings do
not change the exit code.
"""

import sys
from collections import Counter
from pathlib import Path

from src.eval.dataset import TAX_TYPES, Corpus, Report, analyse

EVAL_SET = Path("eval/questions.yaml")
PROCESSED_DIR = Path("data/processed")
ENRICHED_DIR = Path("data/enriched")
CORPUS_MD = Path("docs/reference/corpus.md")

__all__ = ["Report", "check", "main"]


def check(path: Path, processed_dir: Path, enriched_dir: Path, corpus_md: Path) -> Report:
    """Every error and warning in the set, in file order, then those about the set as a whole."""
    return analyse(path, Corpus(processed_dir, enriched_dir, corpus_md))[1]


def main(argv: list[str] | None = None, processed_dir: Path = PROCESSED_DIR, enriched_dir: Path = ENRICHED_DIR,
         corpus_md: Path = CORPUS_MD) -> int:
    argv = sys.argv[1:] if argv is None else argv
    path = Path(argv[0]) if argv else EVAL_SET
    corpus = Corpus(processed_dir, enriched_dir, corpus_md)
    eval_set, report = analyse(path, corpus)
    for message in report.errors:
        print(f"error: {message}")
    for message in report.warnings:
        print(f"warning: {message}")
    answerable = sum(q.unanswerable is None for q in eval_set.questions)
    types = Counter(q.tax_type for q in eval_set.questions)
    print(f"{path}: version {eval_set.version}, {len(eval_set.questions)} questions "
          f"({answerable} answerable, {len(eval_set.questions) - answerable} unanswerable), "
          f"{len(eval_set.conversations)} conversations; "
          + ", ".join(f"{t} {types[t]}" for t in TAX_TYPES))
    print(f"{len(report.errors)} errors, {len(report.warnings)} warnings")
    return 1 if report.errors else 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
