"""Where the expected articles missing from the top 8 sit (#24).

Rules and file format: `docs/reference/retrieval.md`, *Cut diagnosis*.
"""

from pathlib import Path

from src.eval.dataset import EvalSet

FORMAT = 1
CUTS = (8, 12, 16, 20, 30, 50)
DEPTH = 50


def verdict(below_cut: int, misses: int) -> dict:  # stub (#24)
    """`ranking` if at least half the misses are below the cut, else `retrieval`; null with no misses."""
    return {}


def diagnose(eval_set: EvalSet, retriever, parents: dict[str, str]) -> dict:  # stub (#24)
    """recall, misses, verdict and items for one run."""
    return {"recall": {}, "misses": {}, "verdict": {}, "items": []}


def summary(results: dict, path: Path) -> str:  # stub (#24)
    return ""


def main(argv: list[str] | None = None, retriever=None) -> int:  # stub (#24)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
