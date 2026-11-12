"""Check the eval set against its format and the local corpus (#7). Run `python -m src.eval.check`.

Rules and messages: `docs/reference/eval-set.md`.
"""

import sys
from dataclasses import dataclass, field
from pathlib import Path

EVAL_SET = Path("eval/questions.yaml")
PROCESSED_DIR = Path("data/processed")
ENRICHED_DIR = Path("data/enriched")
CORPUS_MD = Path("docs/reference/corpus.md")


@dataclass
class Report:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def check(path: Path, processed_dir: Path, enriched_dir: Path, corpus_md: Path) -> Report:
    """Every error and warning in the set, in file order, then those about the set as a whole."""
    return Report()


def main(argv: list[str] | None = None, processed_dir: Path = PROCESSED_DIR, enriched_dir: Path = ENRICHED_DIR,
         corpus_md: Path = CORPUS_MD) -> int:
    return 0


if __name__ == "__main__":
    sys.exit(main())
