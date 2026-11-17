"""Run the eval set through the pipeline and write a results file (#9, FR-CORE-015);
with `--generate`, also generate and judge the answers (#15).

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
from typing import Any, Protocol

from src.eval.dataset import EvalSet, Item, load_eval_set
from src.eval.metrics import (
    BOOTSTRAP_LEVEL,
    BOOTSTRAP_RESAMPLES,
    BOOTSTRAP_SEED,
    bootstrap_interval,
    context_precision_at_k,
    paired_bootstrap_interval,
    ratio_bootstrap_interval,
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
    answer: Any = None  # a src.answer.Answer when the item was generated (#15)


class Pipeline(Protocol):
    config: dict  # recorded under configuration.pipeline

    def answer(self, question: str) -> Outcome:
        ...


class RetrievalPipeline:
    """Today's pipeline: one stage, retrieval, each question as written (`rewrite: none`)."""

    def __init__(self, retriever, k: int = TOP_K):
        self._retriever, self._k = retriever, k
        self.config = {"stages": ["retrieval"], "rewrite": "none", "top_k": k, **retriever.fusion.config()}

    def answer(self, question: str) -> Outcome:
        started = time.perf_counter()
        result = self._retriever.retrieve(question, k=self._k)
        return Outcome(result.hits, result.unresolved, {"retrieval": time.perf_counter() - started})


class AnswerPipeline:
    """Retrieval, context assembly and generation (#15): `answer` does all three, `retrieve` the first."""

    generates = True

    def __init__(self, retriever, answerer, judge_model: str | None = None, k: int = TOP_K):
        from src.answer.answerer import PROMPT as ANSWER_PROMPT
        from src.eval.judge import PROMPT as JUDGE_PROMPT
        from src.llm import PRICES, PRICES_READ

        self._retriever, self._answerer, self._k = retriever, answerer, k
        model = answerer.llm.model
        price_in, price_out = PRICES[model]
        self.config = {"stages": ["retrieval", "assembly", "generation"], "rewrite": "none", "top_k": k,
                       **retriever.fusion.config(), "model": model,
                       "prices": {"read": PRICES_READ, "input": price_in, "output": price_out},
                       "prompts": {"answer": hashlib.sha256(ANSWER_PROMPT.read_bytes()).hexdigest(),
                                   "judge": hashlib.sha256(JUDGE_PROMPT.read_bytes()).hexdigest()},
                       "judge_model": judge_model or model, "context_budget": answerer.assembler.budget,
                       "google_genai": _version("google-genai")}

    def _retrieval(self, question: str):
        started = time.perf_counter()
        result = self._retriever.retrieve(question, k=self._k)
        return result, time.perf_counter() - started

    def retrieve(self, question: str) -> Outcome:
        result, seconds = self._retrieval(question)
        return Outcome(result.hits, result.unresolved, {"retrieval": seconds})

    def answer(self, question: str) -> Outcome:
        result, seconds = self._retrieval(question)
        answer = self._answerer.answer(question, result)
        call = answer.call
        tokens = {"input": call.input_tokens, "output": call.output_tokens} if call else {"input": 0, "output": 0}
        return Outcome(result.hits, result.unresolved, {"retrieval": seconds, **answer.latency_s}, tokens,
                       call.cost_usd if call else 0.0, answer)


class ProgressMismatch(RuntimeError):
    """The progress file belongs to another run."""


class Progress:
    """Generated items of an interrupted `--generate` run (#15): a first line naming the run, then one
    line per item, `{"item": <results item>, "answer": <answers-file record>}`."""

    def __init__(self, path: Path, header: dict, items: dict[str, dict]):
        self.path, self.header, self.items = path, header, items

    @classmethod
    def open(cls, path: Path, header: dict) -> "Progress":
        header = json.loads(json.dumps(header))
        if path.exists():
            lines = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
            if not lines or lines[0] != header:
                raise ProgressMismatch(f"{path} is from another run; remove it to start again")
            return cls(path, header, {line["item"]["id"]: line for line in lines[1:]})
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes((json.dumps(header, ensure_ascii=False) + "\n").encode("utf-8"))
        return cls(path, header, {})

    def add(self, item: dict, answer: dict) -> None:
        line = {"item": item, "answer": answer}
        with self.path.open("ab") as file:
            file.write((json.dumps(line, ensure_ascii=False) + "\n").encode("utf-8"))
        self.items[item["id"]] = line

    def remove(self) -> None:
        self.path.unlink(missing_ok=True)


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


def _not_run(eval_id: str, reason: str = NOT_RUN) -> dict:
    return {"name": NAMES[eval_id], "value": None, "n": 0, "interval": None, "target": TARGETS[eval_id],
            "passes": None, "reason": reason}


GENERATION_KEYS = ("generated", "context_tokens", "dropped", "not_found", "sentences", "cited_sentences", "citations",
                   "flagged", "notices", "cited_supported", "supported", "correct", "ac015", "judge_latency_s", "judge_tokens",
                   "judge_cost_usd")


def _item(item: Item, kind: str, conversation: str | None, turn: int | None, outcome: Outcome,
          parents: dict[str, str], k: int) -> dict:
    articles = [parents[hit.chunk_id] for hit in outcome.hits]
    expected = list(dict.fromkeys(p.article for p in item.provisions))
    scored = item.unanswerable is None and bool(expected)
    entry = {
        "id": item.id,
        "kind": kind,
        "conversation": conversation,
        "turn": turn,
        "tax_type": item.tax_type,
        "form": item.form,
        "added_in": item.added_in,
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
    entry.update({key: None for key in GENERATION_KEYS})
    entry["generated"] = False
    return entry


def _amended(item: Item, answer, chunks: dict[str, dict], chunks_of: dict[str, list[dict]]) -> dict | None:
    """AC-015 for one answer (eval-results.md, choice B2): none when no listed provision has an amended chunk;
    else whether one is in the context, the ids AC-015 asks about, and the chunk ids of their amending sources."""
    from src.context import cites

    amended: dict[str, bool] = {}  # amended chunk id -> listed as a clause
    for provision in item.provisions:
        chunk = chunks.get(provision.chunk)
        listed_clause = (provision.chunk != provision.article and chunk is not None
                         and chunk["clause"] not in (None, "0"))
        targets = [chunk] if listed_clause else chunks_of.get(provision.article, [])
        for target in targets:
            if target["amended_by"]:
                amended[target["id"]] = amended.get(target["id"], False) or listed_clause
    if not amended:
        return None
    cited = [c.id for c in answer.citations if c.in_context]
    in_context, asked, sources = False, [], set()
    for chunk_id, listed_clause in amended.items():
        chunk = chunks[chunk_id]
        for passage in answer.context.passages:
            if passage.kind == "article" and chunk_id in passage.chunk_ids:
                in_context = True
                own = passage.id if chunk["clause"] in (None, "0") else f"{passage.id}.{chunk_id.split(':K', 1)[1]}"
                if listed_clause or any(cites(i, own) for i in cited):
                    asked.append(own)
                    sources |= {link["source"] for link in chunk["amended_by"]}
    return {"in_context": in_context, "ids": tuple(dict.fromkeys(asked)), "sources": sources}


def _generated(entry: dict, item: Item, answer, judge, chunks: dict[str, dict], chunks_of: dict[str, list[dict]]):
    """Fill the item's generation keys; return the answers-file record and the verdict."""
    context = answer.context
    entry.update({
        "generated": True,
        "context_tokens": context.tokens,
        "dropped": list(context.dropped),
        "not_found": answer.not_found,
        "sentences": len(answer.sentences),
        "cited_sentences": sum(1 for s in answer.sentences if s.citations),
        "citations": [c.id for c in answer.citations],
        "flagged": list(answer.flagged),
        "notices": answer.notices,
    })
    answerable = item.unanswerable is None
    ac015 = _amended(item, answer, chunks, chunks_of) if answerable else None
    # an asked id that a notice covers says "amended" without the judge (choice 1 on #15)
    noticed_targets = {s.citations[0] for s in answer.sentences[len(answer.sentences) - answer.notices:]
                       if s.citations} if answer.notices else set()
    asked = ac015["ids"] if ac015 else ()
    noticed = [i for i in asked if i in noticed_targets]
    amended = tuple(i for i in asked if i not in noticed_targets)
    verdict = None
    if answerable and answer.not_found:
        entry["correct"] = False
    elif answerable and judge is not None:
        verdict = judge.judge(item.question, list(item.key_facts), answer, amended)
        entry.update({
            "cited_supported": sum(1 for value in verdict.cited if value),
            "supported": sum(1 for value in verdict.supported if value),
            "correct": verdict.correct,
            "judge_latency_s": verdict.call.latency_s if verdict.call else None,
            "judge_tokens": {"input": verdict.call.input_tokens, "output": verdict.call.output_tokens}
            if verdict.call else None,
            "judge_cost_usd": verdict.call.cost_usd if verdict.call else None,
        })
    if ac015 is not None:
        if not ac015["in_context"]:
            entry["ac015"] = {"in_context": False, "asked": None, "noticed": None, "cites_amending": None,
                              "says_amended": None, "passes": None}
        elif not ac015["ids"]:  # uncited: the answer cites no amended clause of a listed article
            entry["ac015"] = {"in_context": True, "asked": [], "noticed": None, "cites_amending": None,
                              "says_amended": None, "passes": None}
        else:
            passages = {p.id: p for p in context.passages}
            amending = any(c.in_context and ac015["sources"] & set(passages[c.id.split(".")[0]].chunk_ids)
                           for c in answer.citations if c.id.split(".")[0] in passages)
            says = True if not amended else (verdict.says_amended if verdict else None)
            entry["ac015"] = {"in_context": True, "asked": list(ac015["ids"]), "noticed": noticed,
                              "cites_amending": bool(amending), "says_amended": says,
                              "passes": bool(not answer.not_found and amending and says is True)}
    record = {
        "id": item.id,
        "passages": [{"id": p.id, "text": p.text} for p in context.passages],
        "sentences": [{"text": s.text, "citations": list(s.citations)} for s in answer.sentences],
        "flagged": list(answer.flagged),
        "not_found": answer.not_found,
        "amended": list(amended) if verdict is not None else [],
        "verdict": None if verdict is None else {
            "cited": list(verdict.cited), "supported": list(verdict.supported), "facts": list(verdict.facts),
            "contradicts": verdict.contradicts, "says_amended": verdict.says_amended, "correct": verdict.correct},
    }
    return record, verdict


def _breakdown(standalone: list[dict], key: str) -> dict:
    groups: dict[str, list[dict]] = {}
    for entry in standalone:
        groups.setdefault(str(entry[key]), []).append(entry)
    return {group: {"n": len(entries),
                    "EVAL-001": _mean([e["recall"] for e in entries]),
                    "EVAL-007": _mean([e["context_precision"] for e in entries])}
            for group, entries in sorted(groups.items())}


def _judged_scores(items: list[dict], judge_model: str | None) -> dict:
    answered = [i for i in items if i["kind"] == "question" and i["generated"] and i["answerable"]]
    judged = [i for i in answered if i["cited_supported"] is not None]
    cited = [i for i in judged if i["cited_sentences"]]
    scores = {}
    if cited:
        supported, total = [i["cited_supported"] for i in cited], [i["cited_sentences"] for i in cited]
        value = sum(supported) / sum(total)
        scores["EVAL-002"] = {"name": NAMES["EVAL-002"], "value": value, "n": sum(total),
                              "interval": list(ratio_bootstrap_interval(supported, total)),
                              "target": TARGETS["EVAL-002"], "passes": value >= TARGETS["EVAL-002"]}
    faithful = [i["supported"] / i["sentences"] for i in judged if i["sentences"]]
    if faithful:
        scores["EVAL-003"] = _score("EVAL-003", faithful)
    correct = [1.0 if i["correct"] else 0.0 for i in answered if i["correct"] is not None]
    if correct:
        scores["EVAL-006"] = _score("EVAL-006", correct)
    for entry in scores.values():
        entry["judge"] = judge_model
    return scores


def _generation(items: list[dict], judge_model: str | None) -> dict:
    generated = [i for i in items if i["generated"]]
    answerable = [i for i in generated if i["answerable"]]
    unanswerable = [i for i in generated if not i["answerable"]]
    judged = [i for i in generated if i["judge_tokens"] is not None]
    return {
        "answered": len(generated),
        "not_found": {"answerable": sum(1 for i in answerable if i["not_found"]), "answerable_of": len(answerable),
                      "unanswerable": sum(1 for i in unanswerable if i["not_found"]),
                      "unanswerable_of": len(unanswerable)},
        "flagged": {"ids": sum(len(i["flagged"]) for i in generated),
                    "items": sum(1 for i in generated if i["flagged"])},
        "judge": {"model": judge_model, "calls": len(judged),
                  "cost_usd": sum(i["judge_cost_usd"] or 0.0 for i in judged)},
    }


def _ac015(items: list[dict]) -> dict:
    present = [i for i in items if i["ac015"] is not None]
    applies = [i for i in present if i["ac015"]["asked"] != []]
    fails = [i["id"] for i in applies if i["ac015"]["passes"] is False]
    return {
        "applies": [i["id"] for i in applies],
        "retrieval_misses": [i["id"] for i in applies if not i["ac015"]["in_context"]],
        "uncited": [i["id"] for i in present if i["ac015"]["asked"] == []],
        "passes": [i["id"] for i in applies if i["ac015"]["passes"] is True],
        "fails": fails,
        "green": (not fails) if applies else None,
    }


def evaluate(eval_set: EvalSet, pipeline: Pipeline, parents: dict[str, str], k: int = TOP_K, judge=None,
             chunks: dict[str, dict] | None = None, progress: Progress | None = None,
             answers: list | None = None) -> dict:
    """scores, breakdown, latency, cost, generation, AC-015 and items for one run."""
    generating = bool(getattr(pipeline, "generates", False))
    retrieve = pipeline.retrieve if generating else pipeline.answer
    chunks = chunks or {}
    chunks_of: dict[str, list[dict]] = {}
    for chunk in chunks.values():
        chunks_of.setdefault(chunk["parent_id"], []).append(chunk)
    runs = [(q, "question", None, None) for q in eval_set.questions]
    runs += [(t, "turn", c.id, n) for c in eval_set.conversations for n, t in enumerate(c.turns, start=1)]
    if runs:
        retrieve(runs[0][0].question)  # warm-up, not recorded
    items, judge_model = [], getattr(getattr(judge, "llm", None), "model", None)
    for item, kind, conversation, turn in runs:
        if generating and kind == "question":
            stored = progress.items.get(item.id) if progress else None
            if stored:
                entry, record = stored["item"], stored["answer"]
            else:
                outcome = pipeline.answer(item.question)
                entry = _item(item, kind, conversation, turn, outcome, parents, k)
                record, verdict = _generated(entry, item, outcome.answer, judge, chunks, chunks_of)
                if verdict is not None and verdict.call is not None:
                    judge_model = verdict.call.model
                if progress:
                    progress.add(entry, record)
            if answers is not None:
                answers.append(record)
        else:
            entry = _item(item, kind, conversation, turn, retrieve(item.question), parents, k)
        items.append(entry)

    standalone = [i for i in items if i["kind"] == "question" and i["recall"] is not None]
    follow_ups = [i for i in items if i["kind"] == "turn" and i["turn"] > 1 and i["recall"] is not None]
    computed = {
        "EVAL-001": _score("EVAL-001", [i["recall"] for i in standalone]),
        "EVAL-005": _score("EVAL-005", [i["recall"] for i in follow_ups]),
        "EVAL-007": _score("EVAL-007", [i["context_precision"] for i in standalone]),
    }
    if generating:
        computed.update(_judged_scores(items, judge_model))
    reasons = {"EVAL-004": "scored by #16", "EVAL-008": "not scored"} if generating else {}
    default_reason = ("no judge" if judge is None else "no items") if generating else NOT_RUN
    scores = {eval_id: computed.get(eval_id) or _not_run(eval_id, reasons.get(eval_id, default_reason))
              for eval_id in sorted(TARGETS)}

    timed = [i for i in items if i["generated"]] if generating else items
    totals = [sum(i["latency_s"].values()) for i in timed]
    stages = list(pipeline.config.get("stages", []))
    latency = {
        "n": len(totals),
        "median_s": statistics.median(totals) if totals else None,
        "p95_s": statistics.quantiles(totals, n=20)[-1] if len(totals) > 1 else (totals[0] if totals else None),
        "stages": stages,
        "scope": f"{'retrieval only' if stages == ['retrieval'] else 'full pipeline'}, dev laptop",
        "nfr006": dict(NFR006),
    }
    no_llm = all(i["tokens"].get("input", 0) == 0 and i["tokens"].get("output", 0) == 0 for i in timed)
    cost = {
        "average_usd": _mean([i["cost_usd"] for i in timed]) or 0.0,
        "note": "no LLM in the pipeline" if no_llm else "",
        "nfr007": dict(NFR007),
    }
    return {
        "scores": scores,
        "breakdown": {key: _breakdown(standalone, key) for key in ("form", "tax_type", "added_in")},
        "latency": latency,
        "cost": cost,
        "generation": _generation(items, judge_model) if generating else None,
        "ac015": _ac015(items) if generating else None,
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
        judged = f"  judge {entry['judge']}, not hand-checked" if "judge" in entry else ""
        lines.append(f"  {eval_id}  {entry['name']}: {entry['value']:.3f}  n={entry['n']}  "
                     f"[{low:.3f}, {high:.3f}]  {target}  {verdict}".rstrip() + judged)
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
    generation, ac015 = results.get("generation"), results.get("ac015")
    if generation:
        found, flagged, judge = generation["not_found"], generation["flagged"], generation["judge"]
        lines.append(f"Generation: {generation['answered']} answered; not found on {found['answerable']} of "
                     f"{found['answerable_of']} answerable and {found['unanswerable']} of {found['unanswerable_of']} "
                     f"unanswerable; {flagged['ids']} ids not in the context, in {flagged['items']} items (AC-009); "
                     f"judge {judge['model']}: {judge['calls']} calls, {judge['cost_usd']:.4f} USD")
    if ac015:
        verdict = {True: "GREEN", False: "NOT GREEN", None: "nothing applies"}[ac015["green"]]
        lines.append(f"AC-015: {len(ac015['passes'])} pass, {len(ac015['fails'])} fail, "
                     f"{len(ac015['retrieval_misses'])} retrieval misses, of {len(ac015['applies'])}; "
                     f"{len(ac015.get('uncited', []))} uncited: {verdict}")
        if ac015["fails"]:
            lines.append(f"  fails: {', '.join(ac015['fails'])}")
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


BONFERRONI_RESAMPLES = 10_000  # the corrected interval reads a far tail, so it needs more resamples (#25)


def compare(old: dict, new: dict, comparisons: int = 1) -> str:
    """Score changes and recall drops; raises ValueError when the eval sets differ.

    With `comparisons` above 1, each paired interval is followed by its Bonferroni interval (#25).
    """
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
                    before_values, after_values = [o for o, _ in pairs], [n for _, n in pairs]
                    low, high = paired_bootstrap_interval(before_values, after_values)
                    line += f"  paired [{low:+.3f}, {high:+.3f}]"
                    if comparisons > 1:
                        low, high = paired_bootstrap_interval(before_values, after_values, BONFERRONI_RESAMPLES,
                                                              level=1 - (1 - BOOTSTRAP_LEVEL) / comparisons)
                        line += f"  bonferroni [{low:+.3f}, {high:+.3f}]"
            lines.append(line)
    previous = {i["id"]: i["recall"] for i in old["items"]}
    drops = [f"  {i['id']}  recall {previous[i['id']]:.3f} -> {i['recall']:.3f}" for i in new["items"]
             if i["recall"] is not None and previous.get(i["id"]) is not None and i["recall"] < previous[i["id"]]]
    lines.append("Recall dropped:" if drops else "Recall dropped: none")
    lines.extend(drops)
    return "\n".join(lines)


# --- Command ------------------------------------------------------------------------------------

def add_fusion_arguments(parser: argparse.ArgumentParser) -> None:
    """The fusion options, shared with `src.eval.diagnose` (#25)."""
    parser.add_argument("--rrf-k", type=int, help="the fusion's rrf_k; default RRF_K")
    parser.add_argument("--keyword-weight", type=float, help="the fusion's keyword_weight; default 1")
    parser.add_argument("--vector-weight", type=float, help="the fusion's vector_weight; default 1")
    parser.add_argument("--per-article", action=argparse.BooleanOptionalAction, default=None,
                        help="skip a chunk whose article is already above it; default on")
    parser.add_argument("--candidates", type=int, help="the fusion's candidates; default CANDIDATES")


def fusion_from(parser: argparse.ArgumentParser, args: argparse.Namespace):
    """The `Fusion` the options name; a value it refuses stops the command with exit code 2."""
    from src.retrieval import Fusion

    settings = {name: getattr(args, name) for name in ("rrf_k", "keyword_weight", "vector_weight", "per_article",
                                                       "candidates") if getattr(args, name) is not None}
    try:
        return Fusion(**settings)
    except ValueError as error:
        parser.error(str(error))


def _parents(enriched_dir: Path) -> dict[str, str]:
    lines = (enriched_dir / "chunks.jsonl").read_text(encoding="utf-8").splitlines()
    return {chunk["id"]: chunk["parent_id"] for chunk in map(json.loads, lines)}


def main(argv: list[str] | None = None, pipeline: Pipeline | None = None, judge=None) -> int:
    parser = argparse.ArgumentParser(prog="python -m src.eval.run", description="Score the eval set.")
    parser.add_argument("--set", default="eval/questions.yaml", help="the eval set")
    parser.add_argument("--data", default="data", help="folder holding processed/, enriched/ and index/")
    parser.add_argument("--enriched", help="the enriched chunks; default <data>/enriched")
    parser.add_argument("--index", help="the index folder; default <data>/index")
    parser.add_argument("--out", default="eval/results", help="where the results file is written")
    parser.add_argument("--generate", action="store_true",
                        help="also assemble, generate and judge; spends API quota (#15)")
    parser.add_argument("--compare", help="an earlier results file to compare with")
    parser.add_argument("--comparisons", type=int, default=1,
                        help="variants compared with the same baseline; above 1, also the Bonferroni interval")
    add_fusion_arguments(parser)
    args = parser.parse_args(argv)
    if args.comparisons < 1:
        parser.error(f"--comparisons must be at least 1, not {args.comparisons}")
    fusion = fusion_from(parser, args)
    set_path, data, out = Path(args.set), Path(args.data), Path(args.out)
    index_dir = Path(args.index) if args.index else data / "index"
    enriched = Path(args.enriched) if args.enriched else data / "enriched"

    started_at = datetime.now().astimezone().isoformat(timespec="seconds")
    started = time.perf_counter()
    eval_set = load_eval_set(set_path, data / "processed", enriched)
    llm = None
    if pipeline is None:
        from src.retrieval import Retriever

        retriever = Retriever.load(data, index_dir=index_dir, enriched_dir=enriched, fusion=fusion)
        if args.generate:
            from src.answer import Answerer
            from src.llm import LLM

            llm = LLM()  # one wrapper for answers and judge: one pacing over one key
            pipeline = AnswerPipeline(retriever, Answerer.load(data, llm=llm))
        else:
            pipeline = RetrievalPipeline(retriever)
    progress, records, chunks = None, None, None
    if args.generate:
        if judge is None:
            from src.eval.judge import Judge
            from src.llm import LLM

            judge = Judge(llm or LLM())
        header = {"commit": _git(Path("."), "rev-parse", "HEAD").decode().strip(),
                  "eval_set_sha256": eval_set.sha256, "pipeline": pipeline.config}
        try:
            progress = Progress.open(data / "eval-answers" / "progress.jsonl", header)
        except ProgressMismatch as error:
            print(error)
            return 2
        records = []
        chunks = {chunk["id"]: chunk for chunk in map(json.loads, (enriched / "chunks.jsonl").read_text(
            encoding="utf-8").splitlines())}
    resumed = len(progress.items) if progress else 0
    scored = evaluate(eval_set, pipeline, _parents(enriched), judge=judge, chunks=chunks, progress=progress,
                      answers=records)
    config = configuration(eval_set, set_path, index_dir, pipeline.config)
    command = " ".join(["python -m src.eval.run", *(argv if argv is not None else [])])
    run = {"started": started_at, "command": command, "seconds": round(time.perf_counter() - started, 1)}
    if args.generate:
        run["resumed_items"] = resumed
    results = {"format": FORMAT, "run": run, "configuration": config, **scored}
    path = write_results(results, out)
    if args.generate:
        answers_path = data / "eval-answers" / f"{path.stem}.jsonl"
        answers_path.write_bytes("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records).encode("utf-8"))
        progress.remove()
    print(summary(results, path))
    if args.compare:
        old = json.loads(Path(args.compare).read_text(encoding="utf-8"))
        try:
            text = compare(old, results, args.comparisons)
        except ValueError as error:
            print(error)
            return 2
        print()
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
