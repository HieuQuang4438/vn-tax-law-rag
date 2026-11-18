"""Retrieval metrics on ids (#9). Definitions: `docs/reference/eval-results.md`, *Scores*."""

import numpy as np

BOOTSTRAP_RESAMPLES = 1000
BOOTSTRAP_SEED = 0
BOOTSTRAP_LEVEL = 0.95


def recall_at_k(articles: list[str], expected: list[str], k: int) -> float:
    """Share of the expected articles among the parent articles of the first k hits."""
    wanted = set(expected)
    if not wanted:
        raise ValueError("recall needs at least one expected article")
    return len(wanted & set(articles[:k])) / len(wanted)


def context_precision_at_k(articles: list[str], expected: list[str], k: int) -> float:
    """Mean precision@i over the ranks i <= k whose hit belongs to an expected article; 0 if none."""
    wanted = set(expected)
    relevant, precisions = 0, []
    for rank, article in enumerate(articles[:k], start=1):
        if article in wanted:
            relevant += 1
            precisions.append(relevant / rank)
    return sum(precisions) / len(precisions) if precisions else 0.0


def bootstrap_interval(values: list[float], resamples: int = BOOTSTRAP_RESAMPLES,
                       seed: int = BOOTSTRAP_SEED, level: float = BOOTSTRAP_LEVEL) -> tuple[float, float]:
    """Percentile bootstrap interval of the mean: resamples of the values with replacement."""
    data = np.asarray(values, dtype=np.float64)
    if data.size == 0:
        raise ValueError("no values to resample")
    rng = np.random.default_rng(seed)
    means = data[rng.integers(0, data.size, size=(resamples, data.size))].mean(axis=1)
    tail = round((1 - level) / 2 * 100, 10)
    return float(np.percentile(means, tail)), float(np.percentile(means, 100 - tail))


def ratio_bootstrap_interval(numerators: list[float], denominators: list[float],
                             resamples: int = BOOTSTRAP_RESAMPLES, seed: int = BOOTSTRAP_SEED,
                             level: float = BOOTSTRAP_LEVEL) -> tuple[float, float]:
    """Percentile bootstrap interval of sum(numerators) / sum(denominators), resampling the items:
    claims of one answer are not independent, so the answer is the unit (#15)."""
    top, bottom = np.asarray(numerators, dtype=np.float64), np.asarray(denominators, dtype=np.float64)
    if top.size == 0 or top.size != bottom.size:
        raise ValueError(f"numerators and denominators: {top.size} and {bottom.size} values")
    rng = np.random.default_rng(seed)
    draws = rng.integers(0, top.size, size=(resamples, top.size))
    ratios = top[draws].sum(axis=1) / bottom[draws].sum(axis=1)
    tail = round((1 - level) / 2 * 100, 10)
    return float(np.percentile(ratios, tail)), float(np.percentile(ratios, 100 - tail))


def paired_bootstrap_interval(old: list[float], new: list[float], resamples: int = BOOTSTRAP_RESAMPLES,
                              seed: int = BOOTSTRAP_SEED, level: float = BOOTSTRAP_LEVEL) -> tuple[float, float]:
    """Bootstrap interval of the mean per-item difference new - old, item by item (#10)."""
    if len(old) != len(new):
        raise ValueError(f"paired values differ in length: {len(old)} and {len(new)}")
    return bootstrap_interval([n - o for o, n in zip(old, new)], resamples, seed, level)
