"""Run the eval set through the pipeline and write a results file (#9, FR-CORE-015).

Format and rules: `docs/reference/eval-results.md`.
"""

import argparse
import hashlib
import json
import os
import platform
import statistics
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Protocol

from src.eval.dataset import EvalSet, Item, load_eval_set
from src.eval.metrics import (
    BOOTSTRAP_LEVEL,
    BOOTSTRAP_RESAMPLES,
    BOOTSTRAP_SEED,
    bootstrap_interval,
    context_precision_at_k,
    paired_bootstrap_interval,
    recall_at_k,
)
from src.retrieval import TOP_K, Hit, Unresolved

FORMAT = 1
TARGETS = {"EVAL-001": 0.80, "EVAL-002": 0.90, "EVAL-003": 0.90, "EVAL-004": 0.80,
           "EVAL-005": 0.70, "EVAL-006": 0.80, "EVAL-007": 0.60, "EVAL-008": None}
NAMES = {
    "EVAL-001": "recall@k, answerable standalone questions",
    "EVAL-002": "citation correctness",
    "EVAL-003": "faithfulness",
    "EVAL-004": "not-found accuracy, unanswerable questions",
    "EVAL-005": "recall@k, answerable follow-up turns",
    "EVAL-006": "answer correctness",
    "EVAL-007": "context precision@k, answerable standalone questions",
    "EVAL-008": "answer relevancy",
}
NOT_RUN = "no generation stage"
NFR006 = {"median_s": 10, "p95_s": 20}
NFR007 = {"average_usd": 0.01}
VERSIONED = ("bm25s", "chromadb", "numpy", "pyvi", "sentence-transformers", "torch", "underthesea")
INDEX_FIELDS = ("model", "revision", "chunks_sha256", "chunk_count", "bm25_tokenizer", "chunking", "input_limit",
                "truncated")


@dataclass
class Outcome:
    hits: list[Hit]
    unresolved: list[Unresolved] = field(default_factory=list)
    latency: dict[str, float] = field(default_factory=dict)  # seconds per stage
    tokens: dict[str, int] = field(default_factory=lambda: {"input": 0, "output": 0})
    cost_usd: float = 0.0


class Pipeline(Protocol):
    config: dict  # recorded under configuration.pipeline

    def answer(self, question: str) -> Outcome:
        ...


class RetrievalPipeline:
    """Today's pipeline: one stage, retrieval, each question as written (`rewrite: none`)."""

    def __init__(self, retriever, k: int = TOP_K):
        from src.retrieval import hybrid

        self._retriever, self._k = retriever, k
        self.config = {"stages": ["retrieval"], "rewrite": "none", "top_k": k,
                       "rrf_k": hybrid.RRF_K, "candidates": hybrid.CANDIDATES}

    def answer(self, question: str) -> Outcome:
        started = time.perf_counter()
        result = self._retriever.retrieve(question, k=self._k)
        return Outcome(result.hits, result.unresolved, {"retrieval": time.perf_counter() - started})


# --- Scoring ------------------------------------------------------------------------------------

def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _score(eval_id: str, values: list[float]) -> dict:
    value, target = _mean(values), TARGETS[eval_id]
    return {
        "name": NAMES[eval_id],
        "value": value,
        "n": len(values),
        "interval": list(bootstrap_interval(values)) if values else None,
        "target": target,
        "passes": None if value is None or target is None else value >= target,
    }


def _not_run(eval_id: str) -> dict:
    return {"name": NAMES[eval_id], "value": None, "n": 0, "interval": None, "target": TARGETS[eval_id],
            "passes": None, "reason": NOT_RUN}


def _item(item: Item, kind: str, conversation: str | None, turn: int | None, outcome: Outcome,
          parents: dict[str, str], k: int) -> dict:
    articles = [parents[hit.chunk_id] for hit in outcome.hits]
    expected = list(dict.fromkeys(p.article for p in item.provisions))
    scored = item.unanswerable is None and bool(expected)
    return {
        "id": item.id,
        "kind": kind,
        "conversation": conversation,
        "turn": turn,
        "tax_type": item.tax_type,
        "form": item.form,
        "answerable": item.unanswerable is None,
        "expected": expected,
        "hits": [{"chunk_id": hit.chunk_id, "article": article, "found_by": list(hit.found_by), "score": hit.score}
                 for hit, article in zip(outcome.hits, articles)],
        "unresolved": [u.reason for u in outcome.unresolved],
        "recall": recall_at_k(articles, expected, k) if scored else None,
        "context_precision": context_precision_at_k(articles, expected, k) if scored else None,
        "latency_s": dict(outcome.latency),
        "tokens": dict(outcome.tokens),
        "cost_usd": outcome.cost_usd,
    }


def _breakdown(standalone: list[dict], key: str) -> dict:
    groups: dict[str, list[dict]] = {}
    for entry in standalone:
        groups.setdefault(entry[key], []).append(entry)
    return {group: {"n": len(entries),
                    "EVAL-001": _mean([e["recall"] for e in entries]),
                    "EVAL-007": _mean([e["context_precision"] for e in entries])}
            for group, entries in sorted(groups.items())}


def evaluate(eval_set: EvalSet, pipeline: Pipeline, parents: dict[str, str], k: int = TOP_K) -> dict:
    """scores, breakdown, latency, cost and items for one run."""
    runs = [(q, "question", None, None) for q in eval_set.questions]
    runs += [(t, "turn", c.id, n) for c in eval_set.conversations for n, t in enumerate(c.turns, start=1)]
    if runs:
        pipeline.answer(runs[0][0].question)  # warm-up, not recorded
    items = [_item(item, kind, conversation, turn, pipeline.answer(item.question), parents, k)
             for item, kind, conversation, turn in runs]

    standalone = [i for i in items if i["kind"] == "question" and i["recall"] is not None]
    follow_ups = [i for i in items if i["kind"] == "turn" and i["turn"] > 1 and i["recall"] is not None]
    retrieval = {
        "EVAL-001": _score("EVAL-001", [i["recall"] for i in standalone]),
        "EVAL-005": _score("EVAL-005", [i["recall"] for i in follow_ups]),
        "EVAL-007": _score("EVAL-007", [i["context_precision"] for i in standalone]),
    }
    scores = {eval_id: retrieval.get(eval_id) or _not_run(eval_id) for eval_id in sorted(TARGETS)}

    totals = [sum(i["latency_s"].values()) for i in items]
    stages = list(pipeline.config.get("stages", []))
    latency = {
        "n": len(totals),
        "median_s": statistics.median(totals) if totals else None,
        "p95_s": statistics.quantiles(totals, n=20)[-1] if len(totals) > 1 else (totals[0] if totals else None),
        "stages": stages,
        "scope": f"{'retrieval only' if stages == ['retrieval'] else 'full pipeline'}, dev laptop",
        "nfr006": dict(NFR006),
    }
    no_llm = all(i["tokens"].get("input", 0) == 0 and i["tokens"].get("output", 0) == 0 for i in items)
    cost = {
        "average_usd": _mean([i["cost_usd"] for i in items]) or 0.0,
        "note": "no LLM in the pipeline" if no_llm else "",
        "nfr007": dict(NFR007),
    }
    return {
        "scores": scores,
        "breakdown": {"form": _breakdown(standalone, "form"), "tax_type": _breakdown(standalone, "tax_type")},
        "latency": latency,
        "cost": cost,
        "items": items,
    }


# --- Configuration ------------------------------------------------------------------------------

def _git(root: Path, *args: str) -> bytes:
    return subprocess.run(["git", *args], cwd=root, capture_output=True, check=True).stdout


def _ram_gb() -> float | None:
    try:
        if os.name == "nt":
            import ctypes

            class MemoryStatus(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                            ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                            ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                            ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                            ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]

            status = MemoryStatus()
            status.dwLength = ctypes.sizeof(MemoryStatus)
            if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
                return None
            total = status.ullTotalPhys
        else:
            total = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
        return round(total / 1024 ** 3, 1)
    except (AttributeError, OSError, ValueError):
        return None


def _version(name: str) -> str | None:
    try:
        return version(name)
    except PackageNotFoundError:
        return None


def configuration(eval_set: EvalSet, set_path: Path, index_dir: Path, pipeline_config: dict,
                  root: Path = Path(".")) -> dict:
    diff = _git(root, "diff", "HEAD")
    manifest = json.loads((index_dir / "manifest.json").read_text(encoding="utf-8"))
    return {
        "commit": _git(root, "rev-parse", "HEAD").decode().strip(),
        "dirty": diff != b"",
        "diff_sha256": hashlib.sha256(diff).hexdigest() if diff else None,
        "eval_set": {"path": Path(set_path).as_posix(), "version": eval_set.version, "sha256": eval_set.sha256},
        "index": {key: manifest.get(key) for key in INDEX_FIELDS},
        "pipeline": dict(pipeline_config),
        "bootstrap": {"resamples": BOOTSTRAP_RESAMPLES, "seed": BOOTSTRAP_SEED, "level": BOOTSTRAP_LEVEL},
        "versions": {"python": platform.python_version(), **{name: _version(name) for name in VERSIONED}},
        "machine": {"os": platform.platform(), "cpu": platform.processor() or platform.machine(),
                    "cpu_count": os.cpu_count(), "ram_gb": _ram_gb()},
    }


# --- File, summary, comparison ------------------------------------------------------------------

def write_results(results: dict, out_dir: Path) -> Path:
    """`<date>-<commit7>[-dirty][-n].json`; an existing file is never overwritten."""
    config = results["configuration"]
    stem = f"{results['run']['started'][:10]}-{config['commit'][:7]}" + ("-dirty" if config.get("dirty") else "")
    out_dir.mkdir(parents=True, exist_ok=True)
    path, n = out_dir / f"{stem}.json", 2
    while path.exists():
        path, n = out_dir / f"{stem}-{n}.json", n + 1
    path.write_text(json.dumps(results, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    return path


def _number(value: float | None, digits: int = 3) -> str:
    return "—" if value is None else f"{value:.{digits}f}"


def summary(results: dict, path: Path) -> str:
    config = results.get("configuration", {})
    eval_set = config.get("eval_set", {})
    lines = [f"Results: {path}"]
    if config.get("dirty"):
        lines.append("DIRTY: uncommitted changes, not a baseline")
    lines.append(f"Eval set v{eval_set.get('version')} ({str(eval_set.get('sha256'))[:12]}), "
                 f"commit {str(config.get('commit'))[:7]}")
    lines.append("")
    lines.append("Scores")
    for eval_id, entry in results["scores"].items():
        target = "no target" if entry["target"] is None else f"target ≥ {entry['target']:.2f}"
        if entry["value"] is None:
            reason = entry.get("reason") or "no items"
            lines.append(f"  {eval_id}  {entry['name']}: not run ({reason})  {target}")
            continue
        low, high = entry["interval"]
        verdict = "" if entry["passes"] is None else ("PASS" if entry["passes"] else "FAIL")
        lines.append(f"  {eval_id}  {entry['name']}: {entry['value']:.3f}  n={entry['n']}  "
                     f"[{low:.3f}, {high:.3f}]  {target}  {verdict}".rstrip())
    lines.append("")
    lines.append("Breakdown: recall@k, context precision@k")
    for key, groups in results["breakdown"].items():
        for group, entry in groups.items():
            lines.append(f"  {key} {group}: n={entry['n']}  {_number(entry['EVAL-001'])}  {_number(entry['EVAL-007'])}")
    latency, cost = results["latency"], results["cost"]
    lines.append("")
    lines.append(f"Latency ({latency['scope']}): median {_number(latency['median_s'])} s, "
                 f"p95 {_number(latency['p95_s'])} s over {latency['n']} items; "
                 f"NFR-006: median ≤ {latency['nfr006']['median_s']} s, p95 ≤ {latency['nfr006']['p95_s']} s")
    note = f" ({cost['note']})" if cost.get("note") else ""
    lines.append(f"Cost: average {cost['average_usd']:.4f} USD per item{note}; "
                 f"NFR-007: ≤ {cost['nfr007']['average_usd']} USD")
    return "\n".join(lines)


def _standalone(item: dict) -> bool:
    return item["kind"] == "question"


def _follow_up(item: dict) -> bool:
    return item["kind"] == "turn" and (item.get("turn") or 0) > 1


PAIRED = {"EVAL-001": (_standalone, "recall"), "EVAL-005": (_follow_up, "recall"),
          "EVAL-007": (_standalone, "context_precision")}


def _paired(old_items: list[dict], new_items: list[dict], selects, key: str) -> list[tuple[float, float]]:
    """(old, new) values of the items scored in both runs, in the new run's order."""
    before = {i["id"]: i[key] for i in old_items if selects(i) and i[key] is not None}
    return [(before[i["id"]], i[key]) for i in new_items if selects(i) and i[key] is not None and i["id"] in before]


def compare(old: dict, new: dict) -> str:
    """Score changes and recall drops; raises ValueError when the eval sets differ."""
    if old["configuration"]["eval_set"]["sha256"] != new["configuration"]["eval_set"]["sha256"]:
        raise ValueError("different eval sets: scores are not comparable")
    lines = [f"Compared with {old['configuration']['commit'][:7]} ({old['run']['started']})"]
    for eval_id, entry in new["scores"].items():
        before = old["scores"].get(eval_id, {}).get("value")
        if before is not None and entry["value"] is not None:
            line = f"  {eval_id}  {before:.3f} -> {entry['value']:.3f}  ({entry['value'] - before:+.3f})"
            if eval_id in PAIRED:
                pairs = _paired(old["items"], new["items"], *PAIRED[eval_id])
                if pairs:
                    low, high = paired_bootstrap_interval([o for o, _ in pairs], [n for _, n in pairs])
                    line += f"  paired [{low:+.3f}, {high:+.3f}]"
            lines.append(line)
    previous = {i["id"]: i["recall"] for i in old["items"]}
    drops = [f"  {i['id']}  recall {previous[i['id']]:.3f} -> {i['recall']:.3f}" for i in new["items"]
             if i["recall"] is not None and previous.get(i["id"]) is not None and i["recall"] < previous[i["id"]]]
    lines.append("Recall dropped:" if drops else "Recall dropped: none")
    lines.extend(drops)
    return "\n".join(lines)


# --- Command ------------------------------------------------------------------------------------

def _parents(enriched_dir: Path) -> dict[str, str]:
    lines = (enriched_dir / "chunks.jsonl").read_text(encoding="utf-8").splitlines()
    return {chunk["id"]: chunk["parent_id"] for chunk in map(json.loads, lines)}


def main(argv: list[str] | None = None, pipeline: Pipeline | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m src.eval.run", description="Score the eval set.")
    parser.add_argument("--set", default="eval/questions.yaml", help="the eval set")
    parser.add_argument("--data", default="data", help="folder holding processed/, enriched/ and index/")
    parser.add_argument("--enriched", help="the enriched chunks; default <data>/enriched")
    parser.add_argument("--index", help="the index folder; default <data>/index")
    parser.add_argument("--out", default="eval/results", help="where the results file is written")
    parser.add_argument("--compare", help="an earlier results file to compare with")
    args = parser.parse_args(argv)
    set_path, data, out = Path(args.set), Path(args.data), Path(args.out)
    index_dir = Path(args.index) if args.index else data / "index"
    enriched = Path(args.enriched) if args.enriched else data / "enriched"

    started_at = datetime.now().astimezone().isoformat(timespec="seconds")
    started = time.perf_counter()
    eval_set = load_eval_set(set_path, data / "processed", enriched)
    if pipeline is None:
        from src.retrieval import Retriever

        pipeline = RetrievalPipeline(Retriever.load(data, index_dir=index_dir, enriched_dir=enriched))
    scored = evaluate(eval_set, pipeline, _parents(enriched))
    config = configuration(eval_set, set_path, index_dir, pipeline.config)
    command = " ".join(["python -m src.eval.run", *(argv if argv is not None else [])])
    results = {"format": FORMAT,
               "run": {"started": started_at, "command": command, "seconds": round(time.perf_counter() - started, 1)},
               "configuration": config, **scored}
    path = write_results(results, out)
    print(summary(results, path))
    if args.compare:
        old = json.loads(Path(args.compare).read_text(encoding="utf-8"))
        try:
            text = compare(old, results)
        except ValueError as error:
            print(error)
            return 2
        print()
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
