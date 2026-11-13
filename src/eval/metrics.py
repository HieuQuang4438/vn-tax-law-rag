"""Retrieval metrics on ids (#9). Definitions: `docs/reference/eval-results.md`, *Scores*.

Interface stub: not implemented yet.
"""

BOOTSTRAP_RESAMPLES = 1000
BOOTSTRAP_SEED = 0
BOOTSTRAP_LEVEL = 0.95


def recall_at_k(articles: list[str], expected: list[str], k: int) -> float:
    """Share of the expected articles among the parent articles of the first k hits."""
    return 0.0


def context_precision_at_k(articles: list[str], expected: list[str], k: int) -> float:
    """Mean precision@i over the ranks i <= k whose hit belongs to an expected article; 0 if none."""
    return 0.0


def bootstrap_interval(values: list[float], resamples: int = BOOTSTRAP_RESAMPLES,
                       seed: int = BOOTSTRAP_SEED, level: float = BOOTSTRAP_LEVEL) -> tuple[float, float]:
    """Percentile bootstrap interval of the mean."""
    return (0.0, 0.0)
