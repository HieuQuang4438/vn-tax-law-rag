"""Compare the runs of two configurations, each item averaged over its side's runs (#37, step 3B).

The rules are `docs/reference/eval-results.md`, *Comparing several runs*.
"""

import argparse
import json
from collections.abc import Callable
from pathlib import Path

from src.eval.metrics import (
    BOOTSTRAP_LEVEL,
    BOOTSTRAP_RESAMPLES,
    paired_bootstrap_interval,
    paired_nanmean_bootstrap_interval,
    paired_ratio_bootstrap_interval,
)
from src.eval.run import BONFERRONI_RESAMPLES

def _standalone(item: dict) -> bool:
    return item["kind"] == "question"


def _answerable(item: dict) -> bool:
    return _standalone(item) and item["answerable"]


def _follow_up(item: dict) -> bool:
    return item["kind"] == "turn" and (item.get("turn") or 0) > 1


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _judged(item: dict) -> bool:
    return item.get("cited_supported") is not None


def _of(runs: list[dict[str, dict]], item_id: str) -> list[dict]:
    return [items[item_id] for items in runs if item_id in items]


def _plain(selects: Callable[[dict], bool], value: Callable[[dict], float | None]):
    """The mean over runs of one value, none when no run has it."""
    def per_item(entries: list[dict]) -> float | None:
        return _mean([v for v in (value(e) for e in entries if selects(e)) if v is not None])
    return per_item


def _correct(item: dict) -> float | None:
    return None if item.get("correct") is None else float(bool(item["correct"]))


def _not_found(item: dict) -> float | None:
    if _standalone(item) and not item["answerable"] and item.get("generated"):
        return float(bool(item["not_found"]))
    return None


def _coverage(item: dict) -> float | None:
    """EVAL-009 of one item (#39): 0 when not found or contradicting, else the share of its key facts stated."""
    if not item.get("key_facts"):
        return None
    if item.get("not_found") or item.get("contradicts"):
        return 0.0
    return item["facts_stated"] / item["key_facts"]


def _faithful(item: dict) -> float | None:
    return item["supported"] / item["sentences"] if _judged(item) and item.get("sentences") else None


PLAIN = {
    "EVAL-001": _plain(_standalone, lambda i: i.get("recall")),
    "EVAL-004": _plain(_standalone, _not_found),
    "EVAL-005": _plain(_follow_up, lambda i: i.get("recall")),
    "EVAL-006": _plain(_answerable, _correct),
    "EVAL-007": _plain(_standalone, lambda i: i.get("context_precision")),
    "EVAL-009": _plain(_answerable, _coverage),
}


def _citations(entries: list[dict]) -> tuple[float, float] | None:
    judged = [e for e in entries if _answerable(e) and _judged(e)]
    if not judged:
        return None
    return float(sum(e["cited_supported"] for e in judged)), float(sum(e["cited_sentences"] for e in judged))


def _check(old: list[dict], new: list[dict]) -> None:
    shas = {r["configuration"]["eval_set"]["sha256"] for r in old + new}
    if len(shas) != 1:
        raise ValueError("different eval sets: scores are not comparable")
    def unseeded(results: dict) -> dict:  # the runs of one side differ by their seeds and nothing else (#37)
        return {k: v for k, v in results["configuration"]["pipeline"].items() if k != "seed"}

    for side in (old, new):
        if any(unseeded(r) != unseeded(side[0]) for r in side):
            raise ValueError("the runs of one side differ in configuration")


def _interval(text: str, low: float, high: float, name: str = "paired") -> str:
    return f"{text}  {name} [{low:+.3f}, {high:+.3f}]"


def compare_runs(old: list[dict], new: list[dict], comparisons: int = 1) -> str:
    """One line per EVAL id with a value on both sides; raises ValueError as `_check` says."""
    _check(old, new)
    before = [{i["id"]: i for i in r["items"]} for r in old]
    after = [{i["id"]: i for i in r["items"]} for r in new]
    order = [i["id"] for i in new[0]["items"]]
    commits = lambda side: ", ".join(r["configuration"]["commit"][:7] for r in side)
    lines = [f"Compared {commits(old)} ({len(old)} runs) with {commits(new)} ({len(new)} runs)"]
    corrected = 1 - (1 - BOOTSTRAP_LEVEL) / comparisons

    def line(eval_id: str, old_value: float, new_value: float, interval) -> str:
        text = f"  {eval_id}  {old_value:.3f} -> {new_value:.3f}  ({new_value - old_value:+.3f})"
        text = _interval(text, *interval())
        if comparisons > 1:
            text = _interval(text, *interval(BONFERRONI_RESAMPLES, corrected), "bonferroni")
        return text

    for eval_id in sorted(set(PLAIN) | {"EVAL-002", "EVAL-003"}):
        if eval_id == "EVAL-002":
            pairs = [(_citations(_of(before, i)), _citations(_of(after, i))) for i in order]
            pairs = [(o, n) for o, n in pairs if o is not None and n is not None]
            old_top, old_bottom = [o[0] for o, _ in pairs], [o[1] for o, _ in pairs]
            new_top, new_bottom = [n[0] for _, n in pairs], [n[1] for _, n in pairs]
            if not pairs or not sum(old_bottom) or not sum(new_bottom):
                continue
            lines.append(line(eval_id, sum(old_top) / sum(old_bottom), sum(new_top) / sum(new_bottom),
                              lambda resamples=BOOTSTRAP_RESAMPLES, level=BOOTSTRAP_LEVEL: paired_ratio_bootstrap_interval(
                                  old_top, old_bottom, new_top, new_bottom, resamples, level=level)))
        elif eval_id == "EVAL-003":
            population = [i for i in order if any(_answerable(e) for e in _of(after, i) + _of(before, i))]
            faithful = _plain(_answerable, _faithful)
            old_values = [faithful(_of(before, i)) for i in population]
            new_values = [faithful(_of(after, i)) for i in population]
            known_old, known_new = [v for v in old_values if v is not None], [v for v in new_values if v is not None]
            if not known_old or not known_new:
                continue
            lines.append(line(eval_id, _mean(known_old), _mean(known_new),
                              lambda resamples=BOOTSTRAP_RESAMPLES, level=BOOTSTRAP_LEVEL: paired_nanmean_bootstrap_interval(
                                  old_values, new_values, resamples, level=level)))
        else:
            per_item = PLAIN[eval_id]
            pairs = [(per_item(_of(before, i)), per_item(_of(after, i))) for i in order]
            pairs = [(o, n) for o, n in pairs if o is not None and n is not None]
            if not pairs:
                continue
            old_values, new_values = [o for o, _ in pairs], [n for _, n in pairs]
            lines.append(line(eval_id, _mean(old_values), _mean(new_values),
                              lambda resamples=BOOTSTRAP_RESAMPLES, level=BOOTSTRAP_LEVEL: paired_bootstrap_interval(
                                  old_values, new_values, resamples, level=level)))
    return "\n".join(lines)


def _read(paths: str) -> list[dict]:
    return [json.loads(Path(p).read_text(encoding="utf-8")) for p in paths.split(",") if p]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m src.eval.compare",
                                     description="Compare the runs of two configurations, item by item.")
    parser.add_argument("--old", required=True, help="results files of the old configuration, comma-separated")
    parser.add_argument("--new", required=True, help="results files of the new configuration, comma-separated")
    parser.add_argument("--comparisons", type=int, default=1,
                        help="variants compared with the same baseline; above 1, also the Bonferroni interval")
    args = parser.parse_args(argv)
    if args.comparisons < 1:
        parser.error(f"--comparisons must be at least 1, not {args.comparisons}")
    try:
        text = compare_runs(_read(args.old), _read(args.new), args.comparisons)
    except ValueError as error:
        print(error)
        return 2
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
