"""FR-CORE-015 eval runner. Approach approved on #9.
AC-011: one command writes a results file with every EVAL score, the commit and the configuration.
AC-016: the file holds latency and token cost per question; the run reports median and p95
latency and the average cost against NFR-006 and NFR-007.

The format is `docs/reference/eval-results.md`. Unit tests score a small eval set through a fake
pipeline whose hits are fixed per question, so no index or model is needed and nothing goes to
the network. The corpus test at the end runs the real pipeline over `eval/questions.yaml`:
`pytest -m corpus`.
"""

import dataclasses
import hashlib
import json
import re
import socket
import subprocess
from datetime import date
from pathlib import Path

import numpy as np
import pytest
import yaml

from src.eval.dataset import TAX_TYPES, Conversation, EvalSet, Item, Provision
from src.eval.metrics import bootstrap_interval, context_precision_at_k, paired_bootstrap_interval, recall_at_k
from src.eval.run import (
    TARGETS,
    Outcome,
    RetrievalPipeline,
    compare,
    configuration,
    evaluate,
    main,
    summary,
    write_results,
)
from src.retrieval import TOP_K, Fusion, Hit, Retrieval, Retriever, Unresolved

ROOT = Path(__file__).resolve().parent.parent
EVAL_IDS = [f"EVAL-00{n}" for n in range(1, 9)]
GENERATION = ["EVAL-002", "EVAL-003", "EVAL-004", "EVAL-006", "EVAL-008"]
TOP_KEYS = ["format", "run", "configuration", "scores", "breakdown", "latency", "cost", "items"]


def at(data, *keys):
    """data[k1][k2]…, failing on an assertion, not a KeyError, when a key is missing."""
    for key in keys:
        assert isinstance(data, (dict, list)), f"{keys}: {key!r} reached a {type(data).__name__}"
        if isinstance(data, dict):
            assert key in data, f"{keys}: no {key!r}"
        else:
            assert isinstance(key, int) and key < len(data), f"{keys}: no item {key!r}"
        data = data[key]
    return data


@pytest.fixture
def connections(monkeypatch) -> list:
    """Every outgoing connection attempt; each one fails."""
    attempts = []

    def refuse(sock, address):
        attempts.append(address)
        raise OSError("network blocked in unit tests")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    return attempts


# --- Metrics ------------------------------------------------------------------------------------

def test_recall_is_the_share_of_expected_articles_in_the_first_k():
    assert recall_at_k(["A", "X", "A", "C"], ["A", "B"], k=8) == 0.5
    assert recall_at_k(["A", "B"], ["A", "B"], k=8) == 1.0


def test_recall_reads_only_the_first_k():
    assert recall_at_k(["X"] * 8 + ["B"], ["B"], k=8) == 0.0
    assert recall_at_k(["X", "B"], ["B"], k=1) == 0.0


def test_context_precision_averages_precision_at_each_relevant_rank():
    assert context_precision_at_k(["A", "X", "B"], ["A", "B"], k=8) == pytest.approx((1 + 2 / 3) / 2)
    assert context_precision_at_k(["X", "X", "C"], ["C"], k=8) == pytest.approx(1 / 3)
    assert context_precision_at_k(["A", "A", "X"], ["A"], k=8) == pytest.approx(1.0)


def test_context_precision_is_zero_with_no_relevant_rank_in_the_first_k():
    assert context_precision_at_k(["X", "Y"], ["A"], k=8) == 0.0
    assert context_precision_at_k(["X", "A"], ["A"], k=1) == 0.0


def test_bootstrap_interval_follows_the_specified_draw():
    values = [1.0, 0.0, 0.5, 1.0, 1.0, 0.0, 0.25]
    rng = np.random.default_rng(0)
    means = np.asarray(values)[rng.integers(0, len(values), size=(1000, len(values)))].mean(axis=1)
    expected = (float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5)))
    assert bootstrap_interval(values) == pytest.approx(expected)
    assert bootstrap_interval(values) == bootstrap_interval(values)


def test_paired_interval_is_the_bootstrap_of_the_per_item_differences():
    old, new = [1.0, 0.5, 0.0, 1.0, 0.5], [1.0, 1.0, 0.5, 1.0, 0.0]
    expected = bootstrap_interval([n - o for o, n in zip(old, new)])
    assert paired_bootstrap_interval(old, new) == pytest.approx(expected)
    assert paired_bootstrap_interval(old, old) == pytest.approx((0.0, 0.0))
    with pytest.raises(ValueError):
        paired_bootstrap_interval([1.0], [1.0, 0.0])


def test_bootstrap_interval_of_equal_values_is_that_value():
    assert bootstrap_interval([0.5, 0.5, 0.5]) == pytest.approx((0.5, 0.5))


# --- A small run --------------------------------------------------------------------------------

A, B, C, X = "379409:D5", "379409:D9", "421739:D1", "999001:D1"
PARENTS = {"379409:D5:K1": A, "379409:D5:K25": A, "379409:D9": B, "421739:D1": C, "999001:D1": X}


def provision(article: str) -> Provision:
    return Provision(text=f"provision of {article}", article=article, chunk=article)


def item(item_id, question, tax_type, form, expected=(), unanswerable=None) -> Item:
    return Item(id=item_id, line=1, question=question, tax_type=tax_type, form=form, answer="Câu trả lời.",
                key_facts=["một sự kiện"] if not unanswerable else [],
                provisions=[provision(a) for a in expected], unanswerable=unanswerable)


QUESTIONS = [
    item("q01", "Câu hỏi một về thuế giá trị gia tăng?", "vat", "plain", [A, B]),
    item("q02", "Điều 1 Luật 149/2025/QH15 quy định gì?", "pit", "reference", [C]),
    item("q03", "Câu hỏi ba về thuế giá trị gia tăng?", "vat", "plain", [A, B]),
    item("q04", "Câu hỏi bốn không có đáp án?", "vat", "plain", unanswerable="out_of_scope"),
]
TURNS = [
    item("c01.1", "Lượt một của hội thoại?", "vat", "plain", [A]),
    item("c01.2", "Còn lượt hai thì sao?", "vat", "plain", [B]),
    item("c01.3", "Còn lượt ba thì sao?", "pit", "plain", [C]),
]
HITS = {  # question -> retrieved chunk ids, best first
    QUESTIONS[0].question: ["379409:D5:K1", "999001:D1", "379409:D9", "999001:D1"],  # recall 1, CP (1 + 2/3) / 2
    QUESTIONS[1].question: ["999001:D1", "999001:D1", "421739:D1"],  # recall 1, CP 1/3
    QUESTIONS[2].question: ["379409:D5:K25", "999001:D1"],  # recall 0.5, CP 1
    QUESTIONS[3].question: ["999001:D1"],
    TURNS[0].question: ["999001:D1"],  # recall 0, not scored: a first turn
    TURNS[1].question: ["379409:D9"],  # recall 1
    TURNS[2].question: ["999001:D1"],  # recall 0
}


class FakePipeline:
    config = {"stages": ["retrieval"], "rewrite": "none", "top_k": 8, "rrf_k": 60, "candidates": 50}

    def __init__(self, hits=HITS, default=None):
        self.hits, self.default = hits, default
        self.calls: list[str] = []

    def answer(self, question: str) -> Outcome:
        self.calls.append(question)
        chunk_ids = self.hits.get(question, self.default or [])
        seconds = 100.0 if len(self.calls) == 1 else 0.1 * len(self.calls)  # the first call is the warm-up
        unresolved = [Unresolved("Nghị định 117/2025", "unknown_document")] if "149/2025" in question else []
        return Outcome(hits=[Hit(c, ("keyword",), 0.5) for c in chunk_ids], unresolved=unresolved,
                       latency={"retrieval": seconds})


def small_set() -> EvalSet:
    return EvalSet(version=1, as_of=date(2026, 11, 12), sha256="a" * 64, questions=list(QUESTIONS),
                   conversations=[Conversation("c01", 1, list(TURNS))])


@pytest.fixture
def results(connections) -> dict:
    return evaluate(small_set(), FakePipeline(), PARENTS)


def score(results, eval_id):
    return at(results, "scores", eval_id)


def test_eval001_is_mean_recall_over_answerable_standalone_questions(results):
    entry = score(results, "EVAL-001")
    assert at(entry, "value") == pytest.approx((1 + 1 + 0.5) / 3)
    assert at(entry, "n") == 3
    assert at(entry, "target") == 0.80 and at(entry, "passes") is True


def test_eval007_is_mean_context_precision_over_answerable_standalone_questions(results):
    entry = score(results, "EVAL-007")
    assert at(entry, "value") == pytest.approx(((1 + 2 / 3) / 2 + 1 / 3 + 1) / 3)
    assert at(entry, "n") == 3
    assert at(entry, "passes") is True


def test_eval005_is_mean_recall_over_follow_up_turns_only(results):
    entry = score(results, "EVAL-005")
    assert at(entry, "value") == pytest.approx(0.5)
    assert at(entry, "n") == 2
    assert at(entry, "target") == 0.70 and at(entry, "passes") is False


def test_scores_carry_name_and_bootstrap_interval(results):
    for eval_id in ("EVAL-001", "EVAL-005", "EVAL-007"):
        entry = score(results, eval_id)
        low, high = at(entry, "interval")
        assert low <= at(entry, "value") <= high
        assert at(entry, "name")
    recalls = [1.0, 1.0, 0.5]
    assert at(score(results, "EVAL-001"), "interval") == pytest.approx(list(bootstrap_interval(recalls)))


def test_metrics_that_need_an_answer_are_not_run(results):
    assert sorted(at(results, "scores")) == EVAL_IDS
    for eval_id in GENERATION:
        entry = score(results, eval_id)
        assert (at(entry, "value"), at(entry, "interval"), at(entry, "passes")) == (None, None, None)
        assert at(entry, "reason") == "no generation stage"
        assert at(entry, "target") == TARGETS[eval_id]


def test_targets_match_acceptance_md():
    text = (ROOT / "docs" / "product" / "acceptance.md").read_text(encoding="utf-8")
    written = {}
    for eval_id, target in re.findall(r"^\| (EVAL-\d{3}) \|[^|]*\| ([^|]*) \|", text, re.MULTILINE):
        match = re.match(r"≥ (\d\.\d+)", target.strip())
        written[eval_id] = float(match.group(1)) if match else None
    assert written == TARGETS


def test_breakdown_by_form_and_tax_type(results):
    plain, reference = at(results, "breakdown", "form", "plain"), at(results, "breakdown", "form", "reference")
    assert at(plain, "n") == 2 and at(plain, "EVAL-001") == pytest.approx(0.75)
    assert at(plain, "EVAL-007") == pytest.approx(((1 + 2 / 3) / 2 + 1) / 2)
    assert at(reference, "n") == 1 and at(reference, "EVAL-001") == pytest.approx(1.0)
    assert sorted(at(results, "breakdown", "tax_type")) == ["pit", "vat"]
    assert at(results, "breakdown", "tax_type", "vat", "n") == 2


def test_items_and_breakdown_carry_the_set_version_that_added_them(connections):
    """#26: items added in a later set version are scored apart in the breakdown."""
    later = dataclasses.replace(QUESTIONS[2], added_in=2)  # q03: recall 0.5, CP 1
    eval_set = small_set()
    eval_set.questions = [QUESTIONS[0], QUESTIONS[1], later, QUESTIONS[3]]
    results = evaluate(eval_set, FakePipeline(), PARENTS)
    assert [i.get("added_in") for i in at(results, "items")] == [1, 1, 2, 1, 1, 1, 1]
    groups = at(results, "breakdown", "added_in")
    assert sorted(groups) == ["1", "2"]
    assert at(groups, "1", "n") == 2 and at(groups, "1", "EVAL-001") == pytest.approx(1.0)
    assert at(groups, "2", "n") == 1 and at(groups, "2", "EVAL-001") == pytest.approx(0.5)
    assert at(groups, "2", "EVAL-007") == pytest.approx(1.0)


def test_one_item_per_question_and_turn_in_run_order(results):
    items = at(results, "items")
    assert [at(i, "id") for i in items] == ["q01", "q02", "q03", "q04", "c01.1", "c01.2", "c01.3"]
    assert [at(i, "kind") for i in items] == ["question"] * 4 + ["turn"] * 3
    assert [(at(i, "conversation"), at(i, "turn")) for i in items[3:]] == [(None, None), ("c01", 1), ("c01", 2), ("c01", 3)]


def test_an_item_records_what_it_was_scored_on(results):
    q01 = at(results, "items", 0)
    assert (at(q01, "tax_type"), at(q01, "form"), at(q01, "answerable")) == ("vat", "plain", True)
    assert at(q01, "expected") == [A, B]
    assert at(q01, "hits", 0) == {"chunk_id": "379409:D5:K1", "article": A, "found_by": ["keyword"], "score": 0.5}
    assert at(q01, "recall") == 1.0
    assert at(q01, "context_precision") == pytest.approx((1 + 2 / 3) / 2)
    assert at(q01, "tokens") == {"input": 0, "output": 0} and at(q01, "cost_usd") == 0.0


def test_an_unanswerable_item_is_retrieved_but_not_scored(results):
    q04 = at(results, "items", 3)
    assert at(q04, "answerable") is False and at(q04, "expected") == []
    assert (at(q04, "recall"), at(q04, "context_precision")) == (None, None)
    assert [at(h, "chunk_id") for h in at(q04, "hits")] == ["999001:D1"]


def test_unresolved_references_keep_their_reason_not_their_text(results):
    assert at(results, "items", 1, "unresolved") == ["unknown_document"]


def test_no_question_text_is_written(results):
    assert len(at(results, "items")) == 7
    dumped = json.dumps(results, ensure_ascii=False)
    for question in [i.question for i in QUESTIONS + TURNS] + ["Nghị định 117/2025"]:
        assert question not in dumped


def test_latency_excludes_the_warm_up_call(connections):
    pipeline = FakePipeline()
    results = evaluate(small_set(), pipeline, PARENTS)
    assert len(pipeline.calls) == 1 + 7
    totals = [sum(at(i, "latency_s").values()) for i in at(results, "items")]
    assert max(totals) < 100 and len(totals) == 7
    latency = at(results, "latency")
    assert at(latency, "n") == 7
    assert at(latency, "median_s") == pytest.approx(0.5)  # calls 2..8 take 0.2..0.8 s
    assert at(latency, "p95_s") > at(latency, "median_s")
    assert at(latency, "stages") == ["retrieval"]
    assert at(latency, "scope") == "retrieval only, dev laptop"
    assert at(latency, "nfr006") == {"median_s": 10, "p95_s": 20}


def test_cost_is_zero_without_an_llm(results):
    cost = at(results, "cost")
    assert at(cost, "average_usd") == 0.0
    assert at(cost, "note") == "no LLM in the pipeline"
    assert at(cost, "nfr007") == {"average_usd": 0.01}


# --- Configuration, file, summary, comparison ---------------------------------------------------

MANIFEST = {"model": "BAAI/bge-m3", "revision": "5617a9f6", "dimension": 1024, "chunks_sha256": "c" * 64,
            "chunk_count": 5, "bm25_tokenizer": "syllable", "embedded": 0, "seconds": 1.0, "versions": {}}


def write_manifest(index_dir: Path) -> None:
    index_dir.mkdir(parents=True, exist_ok=True)
    (index_dir / "manifest.json").write_text(json.dumps(MANIFEST), encoding="utf-8")


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=True).stdout


def test_configuration_records_commit_set_index_pipeline_and_machine(tmp_path):
    write_manifest(tmp_path / "index")
    config = configuration(small_set(), Path("eval/questions.yaml"), tmp_path / "index", FakePipeline.config, ROOT)
    assert at(config, "commit") == git("rev-parse", "HEAD").strip()
    dirty = git("diff", "HEAD") != ""
    assert at(config, "dirty") is dirty
    assert (at(config, "diff_sha256") is None) is (not dirty)
    assert at(config, "eval_set") == {"path": "eval/questions.yaml", "version": 1, "sha256": "a" * 64}
    assert at(config, "index") == {**{k: MANIFEST[k] for k in ("model", "revision", "chunks_sha256", "chunk_count",
                                                                "bm25_tokenizer")},
                                   "chunking": None, "input_limit": None, "truncated": None}
    assert at(config, "pipeline") == FakePipeline.config
    assert at(config, "bootstrap") == {"resamples": 1000, "seed": 0, "level": 0.95}
    assert sorted(at(config, "versions")) == ["bm25s", "chromadb", "numpy", "python", "pyvi", "sentence-transformers",
                                              "torch", "underthesea"]
    assert sorted(at(config, "machine")) == ["cpu", "cpu_count", "os", "ram_gb"]


def full_results(results: dict, dirty: bool = False, sha: str = "a" * 64) -> dict:
    config = {"commit": "abc1234" + "0" * 33, "dirty": dirty, "diff_sha256": "d" * 64 if dirty else None,
              "eval_set": {"path": "eval/questions.yaml", "version": 1, "sha256": sha}}
    return {"format": 1, "run": {"started": "2026-11-13T15:04:05+07:00", "command": "python -m src.eval.run",
                                 "seconds": 1.0},
            "configuration": config, **results}


def test_results_file_is_named_by_date_and_commit_and_never_overwritten(results, tmp_path):
    first = write_results(full_results(results), tmp_path)
    second = write_results(full_results(results), tmp_path)
    dirty = write_results(full_results(results, dirty=True), tmp_path)
    assert [first.name, second.name, dirty.name] == [
        "2026-11-13-abc1234.json", "2026-11-13-abc1234-2.json", "2026-11-13-abc1234-dirty.json"]
    assert json.loads(first.read_text(encoding="utf-8")) == full_results(results)


def test_summary_lists_every_score_latency_and_cost(results):
    text = summary(full_results(results), Path("eval/results/2026-11-13-abc1234.json"))
    assert "2026-11-13-abc1234.json" in text
    lines = text.splitlines()
    line = next((l for l in lines if "EVAL-001" in l), "")
    assert "0.833" in line and "n=3" in line and "0.80" in line and "PASS" in line
    assert "FAIL" in next((l for l in lines if "EVAL-005" in l), "")
    for eval_id in GENERATION:
        assert "not run (no generation stage)" in next((l for l in lines if eval_id in l), "")
    for part in ("retrieval only, dev laptop", "NFR-006", "NFR-007", "no LLM in the pipeline", "plain", "vat"):
        assert part in text
    assert "DIRTY" not in text


def test_summary_flags_a_dirty_run(results):
    assert "DIRTY: uncommitted changes, not a baseline" in summary(full_results(results, dirty=True), Path("x.json"))


def test_compare_prints_score_changes_and_recall_drops(connections):
    old = full_results(evaluate(small_set(), FakePipeline(), PARENTS))
    hits = dict(HITS)
    hits[QUESTIONS[0].question] = ["379409:D5:K1"]  # q01 loses article B: recall 1.0 -> 0.5
    new = full_results(evaluate(small_set(), FakePipeline(hits), PARENTS))
    text = compare(old, new)
    line = next((l for l in text.splitlines() if "EVAL-001" in l), "")
    assert "0.833" in line and "0.667" in line and "-0.167" in line
    drop = next((l for l in text.splitlines() if "q01" in l), "")
    assert "1.000" in drop and "0.500" in drop
    assert "q02" not in text


def test_compare_prints_the_paired_interval_of_each_retrieval_change(connections):
    old = full_results(evaluate(small_set(), FakePipeline(), PARENTS))
    hits = dict(HITS)
    hits[QUESTIONS[0].question] = ["379409:D5:K1"]
    new = full_results(evaluate(small_set(), FakePipeline(hits), PARENTS))
    low, high = paired_bootstrap_interval([1.0, 1.0, 0.5], [0.5, 1.0, 0.5])
    line = next((l for l in compare(old, new).splitlines() if "EVAL-001" in l), "")
    assert f"paired [{low:+.3f}, {high:+.3f}]" in line
    for eval_id in ("EVAL-005", "EVAL-007"):
        assert "paired [" in next((l for l in compare(old, new).splitlines() if eval_id in l), "")


def test_compare_refuses_runs_on_different_eval_sets(results):
    with pytest.raises(ValueError, match="different eval sets: scores are not comparable"):
        compare(full_results(results), full_results(results, sha="b" * 64))


# --- The command --------------------------------------------------------------------------------

DOCUMENTS = {"379409": "48/2024/QH15", "421739": "149/2025/QH15"}
CHUNK_PARENTS = [("379409:D5:K1", "379409:D5"), ("379409:D5:K25", "379409:D5"), ("379409:D9", "379409:D9"),
                 ("421739:D1", "421739:D1")]


def write_data(data_dir: Path) -> None:
    processed, enriched = data_dir / "processed", data_dir / "enriched"
    processed.mkdir(parents=True)
    enriched.mkdir(parents=True)
    for doc_id, number in DOCUMENTS.items():
        doc = {"source_url": f"https://luatvietnam.vn/thue/van-ban-{doc_id}-d1.html",
               "metadata": {"so_hieu": number}, "blocks": []}
        (processed / f"van-ban-{doc_id}-d1.json").write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    with (enriched / "chunks.jsonl").open("w", encoding="utf-8", newline="\n") as f:
        for chunk_id, parent in CHUNK_PARENTS:
            doc_id, article, *clause = chunk_id.split(":")
            f.write(json.dumps({"id": chunk_id, "doc_id": doc_id, "article": article[1:],
                                "clause": clause[0][1:] if clause else None, "parent_id": parent,
                                "amended_by": []}) + "\n")
    write_manifest(data_dir / "index")


def write_set(path: Path) -> None:
    def question(n, tax_type, form):
        return {"id": f"q{n:02d}", "question": f"Câu hỏi số {n} về thuế?" if form == "plain"
                else f"Điều 9 Luật 48/2024/QH15 câu {n}?", "tax_type": tax_type, "form": form,
                "answer": "Câu trả lời.", "key_facts": ["một sự kiện"], "provisions": ["48/2024/QH15 Điều 9"]}
    questions = [question(n, TAX_TYPES[n % len(TAX_TYPES)], ("plain", "reference")[n % 2]) for n in range(1, 25)]
    questions += [{"id": f"q{n:02d}", "question": f"Câu hỏi ngoài phạm vi số {n}?", "tax_type": "vat",
                   "form": "plain", "answer": "Không có.", "unanswerable": "out_of_scope"} for n in range(25, 31)]
    turn = {"question": "Còn trường hợp khác thì sao?", "tax_type": "vat", "form": "plain", "answer": "Câu trả lời.",
            "key_facts": ["một sự kiện"], "provisions": ["48/2024/QH15 Điều 5 khoản 1"]}
    conversations = [{"id": f"c{n:02d}", "turns": [dict(turn), dict(turn)]} for n in range(1, 6)]
    data = {"version": 1, "as_of": date(2026, 11, 12), "questions": questions, "conversations": conversations}
    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")


@pytest.fixture
def command(tmp_path, connections):
    data, out, set_path = tmp_path / "data", tmp_path / "results", tmp_path / "questions.yaml"
    write_data(data)
    write_set(set_path)
    return ["--set", str(set_path), "--data", str(data), "--out", str(out)], out, set_path


def test_the_command_writes_one_results_file_and_prints_the_summary(command, capsys):
    argv, out, set_path = command
    pipeline = FakePipeline(default=["379409:D9", "379409:D5:K1"])
    assert main(argv, pipeline=pipeline) == 0
    files = sorted(out.glob("*.json")) if out.is_dir() else []
    assert len(files) == 1
    written = json.loads(files[0].read_text(encoding="utf-8"))
    assert list(written) == TOP_KEYS
    assert at(written, "format") == 1
    assert at(written, "configuration", "eval_set", "sha256") == hashlib.sha256(set_path.read_bytes()).hexdigest()
    assert at(written, "scores", "EVAL-001", "value") == 1.0
    assert at(written, "scores", "EVAL-001", "n") == 24
    assert len(at(written, "items")) == 30 + 10
    assert len(pipeline.calls) == 1 + 30 + 10
    assert files[0].name in capsys.readouterr().out


def test_the_command_compares_with_an_earlier_run(command, capsys):
    argv, out, _ = command
    assert main(argv, pipeline=FakePipeline(default=["379409:D9"])) == 0
    files = sorted(out.glob("*.json")) if out.is_dir() else []
    assert len(files) == 1
    capsys.readouterr()
    assert main(argv + ["--compare", str(files[0])], pipeline=FakePipeline(default=["379409:D9"])) == 0
    assert "EVAL-001" in capsys.readouterr().out
    assert len(list(out.glob("*.json"))) == 2


def test_the_command_reads_the_index_folder_it_is_given(command, tmp_path):
    argv, out, _ = command
    variant = tmp_path / "variant"
    variant.mkdir()
    (variant / "manifest.json").write_text(json.dumps({**MANIFEST, "bm25_tokenizer": "pyvi"}), encoding="utf-8")
    assert main(argv + ["--index", str(variant)], pipeline=FakePipeline(default=["379409:D9"])) == 0
    files = sorted(out.glob("*.json")) if out.is_dir() else []
    assert len(files) == 1
    assert at(json.loads(files[0].read_text(encoding="utf-8")), "configuration", "index", "bm25_tokenizer") == "pyvi"


def test_the_command_exits_2_when_comparing_different_eval_sets(command, tmp_path, capsys):
    argv, out, _ = command
    other = json.loads(json.dumps(full_results({"scores": {}, "items": []}, sha="b" * 64)))
    other_path = tmp_path / "other.json"
    other_path.write_text(json.dumps(other), encoding="utf-8")
    assert main(argv + ["--compare", str(other_path)], pipeline=FakePipeline(default=["379409:D9"])) == 2
    assert "different eval sets: scores are not comparable" in capsys.readouterr().out
    assert len(list(out.glob("*.json"))) == 1 if out.is_dir() else False


# --- The real pipeline (AC-011, AC-016) ---------------------------------------------------------

@pytest.mark.corpus
def test_ac011_ac016_one_command_scores_the_eval_set(tmp_path, connections, capsys):
    """Run `python -m src.index` first."""
    assert main(["--out", str(tmp_path)]) == 0
    files = list(tmp_path.glob("*.json"))
    assert len(files) == 1
    written = json.loads(files[0].read_text(encoding="utf-8"))
    assert sorted(at(written, "scores")) == EVAL_IDS
    for eval_id in ("EVAL-001", "EVAL-005", "EVAL-007"):
        assert at(written, "scores", eval_id, "value") is not None
    assert re.fullmatch(r"[0-9a-f]{40}", at(written, "configuration", "commit"))
    assert at(written, "configuration", "pipeline", "rewrite") == "none"
    for entry in at(written, "items"):
        assert at(entry, "latency_s") and set(at(entry, "tokens")) == {"input", "output"}
    assert at(written, "latency", "median_s") > 0 and at(written, "latency", "p95_s") > 0
    assert at(written, "cost", "average_usd") == 0.0
    print(capsys.readouterr().out)
    assert connections == []



# --- Other enriched chunks and the split parameters (#12) -------------------------------------

def test_the_command_reads_the_enriched_folder_it_is_given(command, tmp_path):
    argv, out, _ = command
    data = Path(argv[argv.index("--data") + 1])
    variant = tmp_path / "variant-enriched"
    (data / "enriched").rename(variant)
    try:
        code = main(argv + ["--enriched", str(variant)], pipeline=FakePipeline(default=["379409:D9"]))
    except FileNotFoundError as error:
        pytest.fail(f"read the default enriched folder: {error}")
    assert code == 0
    assert len(list(out.glob("*.json"))) == 1


def test_configuration_records_the_split_from_the_manifest(tmp_path):
    index = tmp_path / "index"
    index.mkdir()
    split = {"max_tokens": 400, "min_intro_tokens": 100}
    (index / "manifest.json").write_text(json.dumps({**MANIFEST, "chunking": split}), encoding="utf-8")
    config = configuration(small_set(), Path("eval/questions.yaml"), index, FakePipeline.config, ROOT)
    assert at(config, "index").get("chunking") == split


def test_configuration_records_no_split_for_an_older_manifest(tmp_path):
    write_manifest(tmp_path / "index")
    config = configuration(small_set(), Path("eval/questions.yaml"), tmp_path / "index", FakePipeline.config, ROOT)
    assert "chunking" in at(config, "index") and at(config, "index")["chunking"] is None


def test_configuration_records_the_input_limit_and_texts_cut_from_the_manifest(tmp_path):
    index = tmp_path / "index"
    index.mkdir()
    (index / "manifest.json").write_text(json.dumps({**MANIFEST, "input_limit": 2048, "truncated": 12}),
                                         encoding="utf-8")
    config = configuration(small_set(), Path("eval/questions.yaml"), index, FakePipeline.config, ROOT)
    assert (at(config, "index").get("input_limit"), at(config, "index").get("truncated")) == (2048, 12)


# --- Fusion settings and the Bonferroni interval (#25) -----------------------------------------

class FusionRetriever:
    """A retriever with a fusion setting that finds one article for every question."""

    def __init__(self, fusion: Fusion):
        self.fusion = fusion

    def retrieve(self, question: str, k: int = TOP_K) -> Retrieval:
        return Retrieval([Hit("379409:D9", ("keyword",), 0.5)], [])


@pytest.fixture
def loads(monkeypatch) -> list:
    """The fusion of every `Retriever.load` call, which returns a `FusionRetriever`."""
    calls = []

    def load(cls, data_dir=Path("data"), embedder=None, index_dir=None, enriched_dir=None, fusion=None):
        calls.append(fusion)
        return FusionRetriever(fusion or Fusion())

    monkeypatch.setattr(Retriever, "load", classmethod(load))
    return calls


FUSION_OPTIONS = ["--rrf-k", "20", "--keyword-weight", "2", "--vector-weight", "1.5", "--per-article",
                  "--candidates", "100"]
FUSION_CONFIG = {"rrf_k": 20, "candidates": 100, "keyword_weight": 2.0, "vector_weight": 1.5, "per_article": True}


def test_the_pipeline_records_the_retrievers_fusion():
    pipeline = RetrievalPipeline(FusionRetriever(Fusion(rrf_k=20, keyword_weight=2.0, per_article=True)))
    assert pipeline.config == {"stages": ["retrieval"], "rewrite": "none", "top_k": 8, "rrf_k": 20,
                               "candidates": 50, "keyword_weight": 2.0, "vector_weight": 1.0, "per_article": True}


def test_the_fusion_options_reach_the_retriever_and_the_file(command, loads):
    argv, out, _ = command
    assert main(argv + FUSION_OPTIONS) == 0
    assert loads == [Fusion(rrf_k=20, keyword_weight=2.0, vector_weight=1.5, per_article=True, candidates=100)]
    files = sorted(out.glob("*.json")) if out.is_dir() else []
    assert len(files) == 1
    pipeline = at(json.loads(files[0].read_text(encoding="utf-8")), "configuration", "pipeline")
    assert {key: at(pipeline, key) for key in FUSION_CONFIG} == FUSION_CONFIG


def test_without_fusion_options_the_retriever_gets_the_default(command, loads):
    argv, _, _ = command
    assert main(argv) == 0
    assert loads in ([None], [Fusion()])


@pytest.mark.parametrize("option", [["--rrf-k", "0"], ["--candidates", "0"], ["--keyword-weight", "0"],
                                    ["--vector-weight", "-1"], ["--comparisons", "0"]])
def test_a_value_the_fusion_refuses_stops_the_command_before_anything_loads(command, loads, option):
    argv, out, _ = command
    with pytest.raises(SystemExit) as stopped:
        main(argv + option)
    assert stopped.value.code == 2
    assert loads == []
    assert not out.exists()


def test_compare_adds_the_bonferroni_interval_for_several_comparisons(connections):
    old = full_results(evaluate(small_set(), FakePipeline(), PARENTS))
    hits = dict(HITS)
    hits[QUESTIONS[0].question] = ["379409:D5:K1"]
    new = full_results(evaluate(small_set(), FakePipeline(hits), PARENTS))
    low, high = paired_bootstrap_interval([1.0, 1.0, 0.5], [0.5, 1.0, 0.5], resamples=10_000, level=1 - 0.05 / 6)
    text = compare(old, new, comparisons=6)
    line = next((l for l in text.splitlines() if "EVAL-001" in l), "")
    assert f"bonferroni [{low:+.3f}, {high:+.3f}]" in line
    assert line.index("paired [") < line.index("bonferroni [")
    for eval_id in ("EVAL-005", "EVAL-007"):
        assert "bonferroni [" in next((l for l in text.splitlines() if eval_id in l), "")
    assert "bonferroni" not in compare(old, new)


def test_the_command_passes_its_comparisons_to_compare(command, capsys):
    argv, out, _ = command
    assert main(argv, pipeline=FakePipeline(default=["379409:D9"])) == 0
    files = sorted(out.glob("*.json")) if out.is_dir() else []
    assert len(files) == 1
    capsys.readouterr()
    assert main(argv + ["--compare", str(files[0]), "--comparisons", "6"],
                pipeline=FakePipeline(default=["379409:D9"])) == 0
    assert "bonferroni [" in capsys.readouterr().out


def test_no_per_article_turns_the_default_off(command, loads):
    argv, out, _ = command
    assert main(argv + ["--no-per-article"]) == 0
    assert loads == [Fusion(per_article=False)]
    files = sorted(out.glob("*.json")) if out.is_dir() else []
    assert at(json.loads(files[0].read_text(encoding="utf-8")), "configuration", "pipeline", "per_article") is False
