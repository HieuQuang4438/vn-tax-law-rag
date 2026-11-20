"""Run-to-run noise in EVAL-006 (#37, step 0A): how much a rerun of one configuration moves it.

The rules are `docs/reference/eval-results.md`, *Run-to-run noise*. Reads results files and their
answers files, structured fields only; prints counts and numbers, never question or answer text.

    python scripts/noise.py --runs a.json,b.json,c.json [--pairs old.json:new.json,...] [--answers data/eval-answers]
"""

import argparse
import itertools
import json
import math
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.eval.metrics import paired_bootstrap_interval  # noqa: E402

Z = 1.96
KS = range(1, 6)


def normalised(texts: list[str]) -> tuple[str, ...]:
    """Each sentence with every punctuation character dropped and whitespace collapsed, trimmed."""
    def one(text: str) -> str:
        kept = "".join(c for c in text if not unicodedata.category(c).startswith("P"))
        return " ".join(kept.split())
    return tuple(one(t) for t in texts)


def _scored(items: list[dict]) -> dict[str, dict]:
    """The answerable standalone questions with a `correct`, by id, in run order."""
    return {i["id"]: i for i in items
            if i["kind"] == "question" and i["answerable"] and i.get("correct") is not None}


def _texts(records: list[dict]) -> dict[str, list[str]]:
    return {r["id"]: [s["text"] for s in r["sentences"]] for r in records}


def pair_split(a_items: list[dict], b_items: list[dict], a_records: list[dict], b_records: list[dict]) -> dict:
    """Verdict changes between two runs, split by same text; the half-width of their paired EVAL-006 interval."""
    a, b = _scored(a_items), _scored(b_items)
    ids = [i for i in a if i in b]
    a_texts, b_texts = _texts(a_records), _texts(b_records)
    same = {i for i in ids if i in a_texts and i in b_texts and a_texts[i] == b_texts[i]}
    same_normalised = {i for i in ids if i in a_texts and i in b_texts
                       and normalised(a_texts[i]) == normalised(b_texts[i])}
    changed = {i for i in ids if bool(a[i]["correct"]) != bool(b[i]["correct"])}
    old, new = [float(bool(a[i]["correct"])) for i in ids], [float(bool(b[i]["correct"])) for i in ids]
    low, high = paired_bootstrap_interval(old, new) if ids else (math.nan, math.nan)
    return {"n": len(ids), "same_text": len(same), "same_normalised": len(same_normalised), "changed": len(changed),
            "changed_same_text": len(changed & same), "changed_same_normalised": len(changed & same_normalised),
            "half_width": (high - low) / 2}


def projection(runs: list[list[dict]]) -> dict:
    """σ̄², the mean per-item sample variance of `correct` across the runs, and the projected half-width of a
    paired EVAL-006 change for each k runs per arm."""
    if len(runs) < 3:
        raise ValueError(f"the projection needs three or more runs, not {len(runs)}")
    scored = [_scored(items) for items in runs]
    ids = [i for i in scored[0] if all(i in s for s in scored[1:])]
    if not ids:
        raise ValueError("no item has a correct in every run")
    variances = []
    for i in ids:
        values = [float(bool(s[i]["correct"])) for s in scored]
        mean = sum(values) / len(values)
        variances.append(sum((v - mean) ** 2 for v in values) / (len(values) - 1))
    variance = sum(variances) / len(variances)
    return {"n": len(ids), "variance": variance,
            "half_width": {k: Z * math.sqrt(2 * variance / (k * len(ids))) for k in KS}}


def facts_share(item: dict, record: dict | None) -> float | None:
    """The share of key facts stated: the mean of the verdict's facts, 0 when not found, none without a verdict."""
    if item["kind"] != "question" or not item["answerable"]:
        return None
    if item.get("not_found"):
        return 0.0
    verdict = (record or {}).get("verdict")
    if not verdict or not verdict.get("facts"):
        return None
    return sum(1 for fact in verdict["facts"] if fact) / len(verdict["facts"])


def _paired(old: list[float], new: list[float]) -> tuple[float, float, float, float]:
    low, high = paired_bootstrap_interval(old, new)
    return sum(old) / len(old), sum(new) / len(new), low, high


def pair_scores(a_items: list[dict], b_items: list[dict], a_records: list[dict], b_records: list[dict]) -> dict:
    """Binary EVAL-006 and the share of key facts, each (old, new, low, high) over the items with both values."""
    a, b = _scored(a_items), _scored(b_items)
    ids = [i for i in a if i in b]
    binary = _paired([float(bool(a[i]["correct"])) for i in ids], [float(bool(b[i]["correct"])) for i in ids])
    a_records_by, b_records_by = {r["id"]: r for r in a_records}, {r["id"]: r for r in b_records}
    shares = [(facts_share(a[i], a_records_by.get(i)), facts_share(b[i], b_records_by.get(i))) for i in ids]
    shares = [(o, n) for o, n in shares if o is not None and n is not None]
    facts = _paired([o for o, _ in shares], [n for _, n in shares])
    return {"EVAL-006": binary, "facts": facts, "n": len(ids), "facts_n": len(shares)}


def _load(path: str, answers_dir: Path) -> tuple[str, list[dict], list[dict]]:
    stem = Path(path).stem
    items = json.loads(Path(path).read_text(encoding="utf-8"))["items"]
    answers = answers_dir / f"{stem}.jsonl"
    lines = answers.read_text(encoding="utf-8").splitlines() if answers.exists() else []
    return stem, items, [json.loads(line) for line in lines if line.strip()]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python scripts/noise.py", description="Run-to-run noise in EVAL-006.")
    parser.add_argument("--runs", required=True, help="results files of one configuration, comma-separated")
    parser.add_argument("--pairs", default="", help="old.json:new.json pairs to score, comma-separated")
    parser.add_argument("--answers", default="data/eval-answers", help="the folder of the answers files")
    args = parser.parse_args(argv)
    answers_dir = Path(args.answers)
    runs = [_load(p, answers_dir) for p in args.runs.split(",") if p]
    print("Runs: " + ", ".join(stem for stem, _, _ in runs))
    for (a_stem, a_items, a_records), (b_stem, b_items, b_records) in itertools.combinations(runs, 2):
        s = pair_split(a_items, b_items, a_records, b_records)
        print(f"  {a_stem} vs {b_stem}: n={s['n']}; same text {s['same_text']}, same normalised "
              f"{s['same_normalised']}; verdicts changed {s['changed']}, of them same text {s['changed_same_text']}, "
              f"same normalised {s['changed_same_normalised']}; EVAL-006 paired half-width ±{s['half_width']:.3f}")
    if len(runs) >= 3:
        p = projection([items for _, items, _ in runs])
        widths = ", ".join(f"k = {k} ±{w:.3f}" for k, w in p["half_width"].items())
        print(f"Projection over {p['n']} items, mean variance {p['variance']:.4f}: {widths}")
    for pair in (p for p in args.pairs.split(",") if p):
        cut = pair.find(".json:")  # not a plain split: a Windows path has a colon after its drive
        if cut < 0:
            parser.error(f"--pairs: {pair!r} is not old.json:new.json")
        old_path, new_path = pair[:cut + len(".json")], pair[cut + len(".json:"):]
        (a_stem, a_items, a_records), (b_stem, b_items, b_records) = (_load(old_path, answers_dir),
                                                                      _load(new_path, answers_dir))
        scores = pair_scores(a_items, b_items, a_records, b_records)
        line = []
        for name, key, n in (("EVAL-006", "EVAL-006", scores["n"]), ("key facts", "facts", scores["facts_n"])):
            old, new, low, high = scores[key]
            line.append(f"{name} {old:.3f} -> {new:.3f} ({new - old:+.3f}) paired [{low:+.3f}, {high:+.3f}] n={n}")
        print(f"  {a_stem} -> {b_stem}: " + "; ".join(line))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
