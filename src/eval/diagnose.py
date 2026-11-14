"""Where the expected articles missing from the top 8 sit (#24).

Rules and file format: `docs/reference/retrieval.md`, *Cut diagnosis*.
"""

import argparse
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

from src.eval.dataset import EvalSet, Item, load_eval_set
from src.eval.metrics import bootstrap_interval, recall_at_k
from src.eval.run import _parents, configuration, write_results
from src.retrieval import TOP_K, Rankings
from src.retrieval import hybrid

FORMAT = 1
CUTS = (8, 12, 16, 20, 30, 50)
DEPTH = 50  # the deepest cut; a miss ranked deeper is `beyond_50`
LISTS = ("both", "keyword", "vector", "neither")


def verdict(below_cut: int, misses: int) -> dict:
    """`ranking` if at least half the misses are below the cut, else `retrieval`; null with no misses.

    Borderline when moving two misses across the line would change the result (approved on #24).
    """
    if misses == 0:
        result, borderline = None, False
    elif 2 * below_cut >= misses:
        result, borderline = "ranking", 2 * (below_cut - 2) < misses
    else:
        result, borderline = "retrieval", 2 * (below_cut + 2) >= misses
    return {"result": result, "below_cut": below_cut, "misses": misses, "borderline": borderline}


def _best_rank(ranking: list[str], article: str, parents: dict[str, str]) -> int | None:
    """The rank, from 1, of the article's first chunk in the ranking; None if no chunk of it is there."""
    return next((rank for rank, chunk_id in enumerate(ranking, start=1) if parents.get(chunk_id) == article), None)


def _miss(article: str, rankings: Rankings, parents: dict[str, str], chunk_counts: Counter) -> dict:
    final_rank = _best_rank(rankings.final, article, parents)
    keyword_rank = _best_rank(rankings.keyword, article, parents)
    vector_rank = _best_rank(rankings.vector, article, parents)
    place = "not_in_pool" if final_rank is None else "below_cut" if final_rank <= DEPTH else "beyond_50"
    candidates = hybrid.CANDIDATES  # read at call time, as the retriever does
    lists = [name for name, rank in (("keyword", keyword_rank), ("vector", vector_rank))
             if rank is not None and rank <= candidates]
    return {"article": article, "final_rank": final_rank, "keyword_rank": keyword_rank, "vector_rank": vector_rank,
            "place": place, "lists": lists, "split": chunk_counts[article] > 1}


def _item(item: Item, kind: str, conversation: str | None, turn: int | None, rankings: Rankings,
          parents: dict[str, str], chunk_counts: Counter) -> dict:
    expected = list(dict.fromkeys(p.article for p in item.provisions))
    articles = [parents[chunk_id] for chunk_id in rankings.final[:DEPTH]]
    top = set(articles[:TOP_K])
    return {
        "id": item.id,
        "kind": kind,
        "conversation": conversation,
        "turn": turn,
        "expected": expected,
        "recall": {str(k): recall_at_k(articles, expected, k) for k in CUTS},
        "misses": [_miss(a, rankings, parents, chunk_counts) for a in expected if a not in top],
        "unresolved": [u.reason for u in rankings.unresolved],
    }


def _recall(entries: list[dict]) -> dict:
    scores = {}
    for k in CUTS:
        values = [entry["recall"][str(k)] for entry in entries]
        scores[str(k)] = {"value": sum(values) / len(values) if values else None, "n": len(values),
                          "interval": list(bootstrap_interval(values)) if values else None}
    return scores


def _misses(entries: list[dict]) -> dict:
    misses = [miss for entry in entries for miss in entry["misses"]]
    places = Counter(miss["place"] for miss in misses)
    lists = Counter("both" if len(m["lists"]) == 2 else m["lists"][0] if m["lists"] else "neither" for m in misses)
    return {
        "articles": len(misses),
        "below_cut": places["below_cut"],
        "beyond_50": places["beyond_50"],
        "not_in_pool": places["not_in_pool"],
        "share_below_cut": places["below_cut"] / len(misses) if misses else None,
        "lists": {name: lists[name] for name in LISTS},
        "split": sum(miss["split"] for miss in misses),
        "unresolved": sum(len(entry["misses"]) for entry in entries if entry["unresolved"]),
    }


def diagnose(eval_set: EvalSet, retriever, parents: dict[str, str]) -> dict:
    """recall, misses, verdict and items for one run: `rankings` once per question and turn, in file order."""
    chunk_counts = Counter(parents.values())
    runs = [(q, "question", None, None) for q in eval_set.questions]
    runs += [(t, "turn", c.id, n) for c in eval_set.conversations for n, t in enumerate(c.turns, start=1)]
    items = []
    for item, kind, conversation, turn in runs:
        rankings = retriever.rankings(item.question)
        scored = item.unanswerable is None and bool(item.provisions) and (kind == "question" or turn > 1)
        if scored:
            items.append(_item(item, kind, conversation, turn, rankings, parents, chunk_counts))

    groups = {"standalone": [i for i in items if i["kind"] == "question"],
              "follow_up": [i for i in items if i["kind"] == "turn"]}
    misses = {group: _misses(entries) for group, entries in groups.items()}
    return {
        "recall": {group: _recall(entries) for group, entries in groups.items()},
        "misses": misses,
        "verdict": verdict(misses["standalone"]["below_cut"], misses["standalone"]["articles"]),
        "items": items,
    }


def _value(score: dict) -> str:
    return "—" if score["value"] is None else f"{score['value']:.3f} (n={score['n']})"


def summary(results: dict, path: Path) -> str:
    lines = [str(path)]
    if results.get("configuration", {}).get("dirty"):
        lines.append("DIRTY: uncommitted changes, not a baseline")
    lines.append("Recall at each cut: standalone, follow-up")
    for k in CUTS:
        lines.append(f"  @{k}: {_value(results['recall']['standalone'][str(k)])}, "
                     f"{_value(results['recall']['follow_up'][str(k)])}")
    lines.append(f"Misses, articles missing from the top {TOP_K}:")
    for group, counts in results["misses"].items():
        listed = ", ".join(f"{name} {counts['lists'][name]}" for name in LISTS)
        lines.append(f"  {group}: {counts['articles']}; below_cut {counts['below_cut']}, "
                     f"beyond_50 {counts['beyond_50']}, not_in_pool {counts['not_in_pool']}; "
                     f"lists: {listed}; split {counts['split']}; unresolved {counts['unresolved']}")
    v = results["verdict"]
    result = "none (no misses)" if v["result"] is None else v["result"]
    lines.append(f"Verdict: {result}, {v['below_cut']} of {v['misses']} below the cut; "
                 f"borderline: {'yes' if v['borderline'] else 'no'}")
    return "\n".join(lines)


def main(argv: list[str] | None = None, retriever=None) -> int:
    parser = argparse.ArgumentParser(prog="python -m src.eval.diagnose",
                                     description="Place the expected articles missing from the top 8.")
    parser.add_argument("--set", default="eval/questions.yaml", help="the eval set")
    parser.add_argument("--data", default="data", help="folder holding processed/, enriched/ and index/")
    parser.add_argument("--enriched", help="the enriched chunks; default <data>/enriched")
    parser.add_argument("--index", help="the index folder; default <data>/index")
    parser.add_argument("--out", default="eval/results/diagnostics", help="where the file is written")
    args = parser.parse_args(argv)
    set_path, data, out = Path(args.set), Path(args.data), Path(args.out)
    index_dir = Path(args.index) if args.index else data / "index"
    enriched = Path(args.enriched) if args.enriched else data / "enriched"

    started_at = datetime.now().astimezone().isoformat(timespec="seconds")
    started = time.perf_counter()
    eval_set = load_eval_set(set_path, data / "processed", enriched)
    if retriever is None:
        from src.retrieval import Retriever

        retriever = Retriever.load(data, index_dir=index_dir, enriched_dir=enriched)
    diagnosed = diagnose(eval_set, retriever, _parents(enriched))
    pipeline = {"stages": ["retrieval"], "rewrite": "none", "top_k": TOP_K, "rrf_k": hybrid.RRF_K,
                "candidates": hybrid.CANDIDATES, "depth": DEPTH, "cuts": list(CUTS)}
    command = " ".join(["python -m src.eval.diagnose", *(argv if argv is not None else [])])
    results = {"format": FORMAT,
               "run": {"started": started_at, "command": command, "seconds": round(time.perf_counter() - started, 1)},
               "configuration": configuration(eval_set, set_path, index_dir, pipeline), **diagnosed}
    path = write_results(results, out)
    print(summary(results, path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
