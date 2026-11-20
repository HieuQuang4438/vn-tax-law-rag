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
from src.conversation import rewriter
from src.eval.run import (
    TARGETS,
    AnswerPipeline,
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
EVAL_IDS = [f"EVAL-00{n}" for n in range(1, 10)]
GENERATION = ["EVAL-002", "EVAL-003", "EVAL-004", "EVAL-006", "EVAL-008", "EVAL-009"]
TOP_KEYS = ["format", "run", "configuration", "scores", "breakdown", "latency", "cost", "generation",
            "ac015", "items"]


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
        self.seen: list[tuple] = []  # (question, earlier questions)

    def answer(self, question: str, earlier: tuple[str, ...] = ()) -> Outcome:
        self.calls.append(question)
        self.seen.append((question, tuple(earlier)))
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

    def fuse(self, questions: list[str], k: int = TOP_K) -> Retrieval:
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


# --- Generation stage (#15) ---------------------------------------------------------------------

from src.answer import NOT_FOUND, Answer, Citation, Sentence  # noqa: E402
from src.context import Context, Passage  # noqa: E402
from src.eval.judge import Verdict  # noqa: E402
from src.eval.metrics import ratio_bootstrap_interval  # noqa: E402
from src.eval.run import Progress, ProgressMismatch  # noqa: E402
from src.llm import Call  # noqa: E402
from types import SimpleNamespace  # noqa: E402

GEN_TOP_KEYS = ["format", "run", "configuration", "scores", "breakdown", "latency", "cost", "generation", "ac015",
                "items"]
GEN_ITEM_KEYS = ["generated", "context_tokens", "dropped", "not_found", "sentences", "cited_sentences", "citations",
                 "flagged", "notices", "cited_supported", "supported", "correct", "facts_stated", "key_facts",
                 "contradicts", "ac015", "judge_latency_s", "judge_tokens",
                 "judge_cost_usd"]
CHUNKS = {  # the enriched chunks AC-015 reads: id -> record
    "379409:D5:K1": {"id": "379409:D5:K1", "parent_id": A, "clause": "1", "amended_by": []},
    "379409:D5:K25": {"id": "379409:D5:K25", "parent_id": A, "clause": "25",
                      "amended_by": [{"type": "amends", "source": "427630:D6"}]},
    "379409:D9": {"id": "379409:D9", "parent_id": B, "clause": None, "amended_by": []},
    "421739:D1": {"id": "421739:D1", "parent_id": C, "clause": None,
                  "amended_by": [{"type": "repeals", "source": "999001:D1"}]},
    "427630:D6": {"id": "427630:D6", "parent_id": "427630:D6", "clause": None, "amended_by": []},
    "999001:D1": {"id": "999001:D1", "parent_id": X, "clause": None, "amended_by": []},
}
ARTICLE_A = Passage("1", "article", "379409", "5", ("379409:D5:K1", "379409:D5:K25"), ("1", "25"), "[1] A")
AMENDING_A = Passage("2", "amending", "427630", "6", ("427630:D6",), (), "[2] sửa đổi A")
ARTICLE_B = Passage("3", "article", "379409", "9", ("379409:D9",), ("1", "2"), "[3] B")
ONLY_B = Passage("1", "article", "379409", "9", ("379409:D9",), ("1", "2"), "[1] B")
ONLY_C = Passage("1", "article", "421739", "1", ("421739:D1",), (), "[1] C")


def generated(passages, sentences, flagged=(), not_found=False, notices=0) -> Answer:
    ids = list(dict.fromkeys(i for _, citations in sentences for i in citations))
    context = Context(passages=list(passages), text="\n\n".join(p.text for p in passages), tokens=100 * len(passages),
                      dropped=[])
    return Answer(sentences=[Sentence(text, citations) for text, citations in sentences],
                  citations=[Citation(i, i not in flagged) for i in ids], flagged=list(flagged), not_found=not_found,
                  text="", context=context, call=Call(None, "gemini-3.5-flash-lite", "answer", 9000, 100, 1.0, 0.003, 1),
                  latency_s={"assembly": 0.01, "generation": 1.0}, notices=notices)


ANSWERS = {
    QUESTIONS[0].question: generated([ARTICLE_A, AMENDING_A, ARTICLE_B],
                                     [("Câu một.", ("1.25", "2")), ("Câu hai.", ("7",))], flagged=("7",)),
    QUESTIONS[1].question: generated([ONLY_C], [(NOT_FOUND, ())], not_found=True),
    QUESTIONS[2].question: generated([ONLY_B], [("Câu một.", ("1.2",)), ("Câu hai.", ()), ("Câu ba.", ("1",))],
                                     notices=1),
    QUESTIONS[3].question: generated([ONLY_B], [(NOT_FOUND, ())], not_found=True),
}
DEFAULT_ANSWER = generated([ONLY_B], [("Câu một.", ("1",))])


def judge_call() -> Call:
    return Call(None, "gemini-3.5-flash-lite", "judge", 15000, 300, 2.0, 0.0012, 1)


VERDICTS = {
    QUESTIONS[0].question: Verdict((True, False), (True, True), (True,), False, True, True, judge_call()),
    QUESTIONS[2].question: Verdict((False, None, True), (True, False, True), (False,), False, None, False, judge_call()),
}


class FakeJudge:
    llm = SimpleNamespace(model="gemini-3.5-flash-lite")  # as Judge.llm

    def __init__(self):
        self.calls: list[tuple] = []

    def judge(self, question, key_facts, answer, amended=()):
        self.calls.append((question, tuple(key_facts), tuple(amended)))
        default = Verdict(tuple(True if s.citations else None for s in answer.sentences),
                          tuple(True for _ in answer.sentences), tuple(True for _ in key_facts), False,
                          True if amended else None, True, judge_call())
        return VERDICTS.get(question, default)


class GeneratingPipeline:
    generates = True
    config = {"stages": ["retrieval", "assembly", "generation"], "rewrite": "none", "top_k": 8, "rrf_k": 60,
              "candidates": 50, "model": "gemini-3.5-flash-lite"}

    def __init__(self, answers=ANSWERS, default=None):
        self.answers, self.default = answers, default
        self.answered: list[str] = []
        self.retrieved: list[str] = []

    def _hits(self, question):
        return [Hit(c, ("keyword",), 0.5) for c in HITS.get(question, ["379409:D9"])]

    def answer(self, question: str) -> Outcome:
        self.answered.append(question)
        answer = self.answers.get(question, self.default)
        if answer is None:  # a turn sent to answer() instead of retrieve(): the test asserts on `answered`
            return Outcome(hits=self._hits(question), latency={"retrieval": 0.1})
        return Outcome(hits=self._hits(question), latency={"retrieval": 0.1, **answer.latency_s},
                       tokens={"input": 9000, "output": 100}, cost_usd=0.003, answer=answer)

    def retrieve(self, question: str, earlier: tuple[str, ...] = ()) -> Outcome:
        self.retrieved.append(question)
        return Outcome(hits=self._hits(question), latency={"retrieval": 0.1})


@pytest.fixture
def generation(connections):
    pipeline, judge, answers = GeneratingPipeline(), FakeJudge(), []
    results = evaluate(small_set(), pipeline, PARENTS, judge=judge, chunks=CHUNKS, answers=answers)
    return results, pipeline, judge, answers


def item_of(results, item_id):
    matches = [i for i in at(results, "items") if i.get("id") == item_id]
    assert len(matches) == 1, f"{item_id}: {len(matches)} items"
    return matches[0]


def test_ratio_interval_resamples_items_and_takes_the_ratio_of_sums():
    numerators, denominators = [1.0, 0.0, 2.0, 3.0], [2.0, 1.0, 2.0, 4.0]
    rng = np.random.default_rng(0)
    draws = rng.integers(0, 4, size=(1000, 4))
    ratios = np.asarray(numerators)[draws].sum(axis=1) / np.asarray(denominators)[draws].sum(axis=1)
    expected = (float(np.percentile(ratios, 2.5)), float(np.percentile(ratios, 97.5)))
    assert ratio_bootstrap_interval(numerators, denominators) == pytest.approx(expected)


def test_a_run_without_generation_has_no_generation_or_ac015(results):
    assert at(results, "generation") is None
    assert at(results, "ac015") is None
    assert all(at(i, "generated") is False for i in at(results, "items"))


def test_questions_are_generated_and_turns_only_retrieved(generation):
    results, pipeline, _, _ = generation
    assert pipeline.answered == [q.question for q in QUESTIONS]
    assert pipeline.retrieved == [QUESTIONS[0].question] + [t.question for t in TURNS]  # warm-up first
    assert [at(i, "generated") for i in at(results, "items")] == [True] * 4 + [False] * 3


def test_items_get_the_generation_keys_after_cost(generation):
    results, *_ = generation
    for entry in at(results, "items"):
        keys = list(entry)
        assert keys[keys.index("cost_usd") + 1:] == GEN_ITEM_KEYS
    assert list(results) == GEN_TOP_KEYS[3:]  # evaluate's part of the file


def test_answerable_answers_are_judged_and_not_found_ones_are_not(generation):
    _, _, judge, _ = generation
    assert judge.calls == [(QUESTIONS[0].question, ("một sự kiện",), ("1.25",)),
                           (QUESTIONS[2].question, ("một sự kiện",), ())]


def test_an_item_records_its_answer_as_ids_and_counts(generation):
    results, *_ = generation
    q01 = item_of(results, "q01")
    assert (at(q01, "not_found"), at(q01, "sentences"), at(q01, "cited_sentences")) == (False, 2, 2)
    assert (at(q01, "citations"), at(q01, "flagged")) == (["1.25", "2", "7"], ["7"])
    assert (at(q01, "notices"), at(item_of(results, "q03"), "notices")) == (0, 1)
    assert (at(q01, "cited_supported"), at(q01, "supported"), at(q01, "correct")) == (1, 2, True)
    assert (at(q01, "context_tokens"), at(q01, "dropped")) == (300, [])
    assert at(q01, "judge_tokens") == {"input": 15000, "output": 300}
    assert at(q01, "judge_cost_usd") == pytest.approx(0.0012)
    assert at(q01, "judge_latency_s") == pytest.approx(2.0)
    q02 = item_of(results, "q02")
    assert (at(q02, "not_found"), at(q02, "correct"), at(q02, "cited_supported"), at(q02, "judge_tokens")) == \
        (True, False, None, None)
    assert at(item_of(results, "q04"), "correct") is None
    turn = item_of(results, "c01.2")
    assert all(at(turn, key) is None for key in GEN_ITEM_KEYS if key != "generated")


def test_eval002_is_the_share_of_cited_sentences_supported_by_their_citations(generation):
    results, *_ = generation
    entry = score(results, "EVAL-002")
    assert at(entry, "value") == pytest.approx(2 / 4)
    assert at(entry, "n") == 4
    assert at(entry, "interval") == pytest.approx(list(ratio_bootstrap_interval([1, 1], [2, 2])))
    assert at(entry, "judge") == "gemini-3.5-flash-lite"


def test_eval003_is_the_mean_share_of_supported_sentences_over_answered_questions(generation):
    results, *_ = generation
    entry = score(results, "EVAL-003")
    assert at(entry, "value") == pytest.approx((1 + 2 / 3) / 2)
    assert at(entry, "n") == 2


def test_eval006_counts_a_not_found_answer_as_incorrect(generation):
    results, *_ = generation
    entry = score(results, "EVAL-006")
    assert at(entry, "value") == pytest.approx(1 / 3)
    assert at(entry, "n") == 3


def test_eval008_says_why_it_is_not_run(generation):
    results, *_ = generation
    assert (at(score(results, "EVAL-008"), "value"), at(score(results, "EVAL-008"), "reason")) == (None, "not scored")


# --- EVAL-004, FR-CORE-012 (approved on #16) ---

UNANSWERED = item("q05", "Câu hỏi năm không có đáp án?", "vat", "plain", unanswerable="out_of_scope")


def unanswerable_run(judge) -> dict:
    """q04 answered not found, q05 answered from the passages: both unanswerable."""
    eval_set = EvalSet(version=1, as_of=date(2026, 11, 12), sha256="a" * 64,
                       questions=[QUESTIONS[3], UNANSWERED], conversations=[])
    answers = {QUESTIONS[3].question: ANSWERS[QUESTIONS[3].question], UNANSWERED.question: DEFAULT_ANSWER}
    return evaluate(eval_set, GeneratingPipeline(answers), PARENTS, judge=judge, chunks=CHUNKS)


def test_eval004_is_the_share_of_unanswerable_questions_answered_not_found(connections):
    entry = score(unanswerable_run(FakeJudge()), "EVAL-004")
    assert (at(entry, "value"), at(entry, "n"), at(entry, "target"), at(entry, "passes")) == (0.5, 2, 0.80, False)
    assert at(entry, "interval") == pytest.approx(list(bootstrap_interval([1.0, 0.0])))
    assert entry.get("reason") is None


def test_eval004_needs_no_judge(connections):
    entry = score(unanswerable_run(None), "EVAL-004")
    assert (at(entry, "value"), at(entry, "n")) == (0.5, 2)
    assert "judge" not in entry


def test_eval004_is_over_unanswerable_questions_only(generation):
    results, *_ = generation
    entry = score(results, "EVAL-004")
    assert (at(entry, "value"), at(entry, "n"), at(entry, "passes")) == (1.0, 1, True)


def test_answerable_not_found_answers_are_split_by_recall(connections):
    """q02 has recall 1, q03 0.5 and q06 0 (its hits default to article B; it expects C)."""
    q06 = item("q06", "Câu hỏi sáu về thuế thu nhập cá nhân?", "pit", "plain", [C])
    eval_set = EvalSet(version=1, as_of=date(2026, 11, 12), sha256="a" * 64,
                       questions=[QUESTIONS[1], QUESTIONS[2], q06], conversations=[])
    not_found = ANSWERS[QUESTIONS[1].question]
    answers = {q.question: not_found for q in (QUESTIONS[1], QUESTIONS[2], q06)}
    results = evaluate(eval_set, GeneratingPipeline(answers), PARENTS, judge=FakeJudge(), chunks=CHUNKS)
    assert at(results, "generation", "not_found", "answerable") == 3
    assert at(results, "generation", "not_found", "answerable_by_recall") == {"all": 1, "some": 1, "none": 1}


def test_the_generation_summary_counts_not_found_flagged_and_judge_calls(generation):
    results, *_ = generation
    assert at(results, "generation", "answered") == 4
    assert at(results, "generation", "not_found") == {"answerable": 1, "answerable_of": 3,
                                                      "answerable_by_recall": {"all": 1, "some": 0, "none": 0},
                                                      "unanswerable": 1, "unanswerable_of": 1}
    assert at(results, "generation", "flagged") == {"ids": 1, "items": 1}
    judge = at(results, "generation", "judge")
    assert (at(judge, "model"), at(judge, "calls")) == ("gemini-3.5-flash-lite", 2)
    assert at(judge, "cost_usd") == pytest.approx(0.0024)


def test_ac015_passes_retrieval_misses_and_uncited(generation):
    """q02 lists article C whole; its not-found answer cites nothing of it, so it is uncited (choice B2)."""
    results, *_ = generation
    assert at(results, "ac015") == {"applies": ["q01", "q03"], "retrieval_misses": ["q03"], "uncited": ["q02"],
                                    "passes": ["q01"], "fails": [], "green": True}
    assert at(item_of(results, "q01"), "ac015") == {"in_context": True, "asked": ["1.25"], "noticed": [],
                                                    "cites_amending": True, "says_amended": True, "passes": True}
    assert at(item_of(results, "q02"), "ac015") == {"in_context": True, "asked": [], "noticed": None,
                                                    "cites_amending": None, "says_amended": None, "passes": None}
    assert at(item_of(results, "q03"), "ac015") == {"in_context": False, "asked": None, "noticed": None,
                                                    "cites_amending": None, "says_amended": None, "passes": None}
    assert at(item_of(results, "q04"), "ac015") is None


def one_question(provisions, answer, judge=None, answers=None) -> tuple[dict, "FakeJudge"]:
    question = Item(id="q01", line=1, question=QUESTIONS[0].question, tax_type="vat", form="plain",
                    answer="Câu trả lời.", key_facts=["một sự kiện"], provisions=provisions)
    eval_set = EvalSet(version=1, as_of=date(2026, 11, 12), sha256="a" * 64, questions=[question], conversations=[])
    judge = judge or FakeJudge()
    results = evaluate(eval_set, GeneratingPipeline({question.question: answer}), PARENTS, judge=judge, chunks=CHUNKS,
                       answers=answers)
    return results, judge


class SaysNotAmended(FakeJudge):
    """A judge that finds no statement of an amendment."""

    def judge(self, question, key_facts, answer, amended=()):
        verdict = super().judge(question, key_facts, answer, amended)
        return dataclasses.replace(verdict, says_amended=False if amended else None)


LISTED_K25 = Provision(text="khoản 25 Điều 5", article=A, chunk="379409:D5:K25")
ARTICLE_C_3 = Passage("3", "article", "421739", "1", ("421739:D1",), (), "[3] C")
NOTICE_K25 = ("Khoản 25 Điều 5 Luật 48/2024/QH15 được sửa đổi, bổ sung bởi Điều 6 Nghị định 1.", ("1.25", "2"))


def test_a_noticed_provision_says_amended_without_asking_the_judge(connections):
    """Choice 1 on #15: the notice is built from the link line, so it says the provision was amended."""
    answer = generated([ARTICLE_A, AMENDING_A], [("Câu một.", ("1.25",)), NOTICE_K25], notices=1)
    results, judge = one_question([LISTED_K25], answer, judge=SaysNotAmended())
    assert at(item_of(results, "q01"), "ac015") == {"in_context": True, "asked": ["1.25"], "noticed": ["1.25"],
                                                    "cites_amending": True, "says_amended": True, "passes": True}
    assert judge.calls[0][2] == ()
    assert at(results, "ac015", "passes") == ["q01"]


def test_a_model_sentence_citing_the_amended_provision_is_not_a_notice(connections):
    answer = generated([ARTICLE_A, AMENDING_A], [("Câu một.", ("1.25", "2")), ("Câu hai.", ("1.1",))])
    results, judge = one_question([LISTED_K25], answer, judge=SaysNotAmended())
    assert at(item_of(results, "q01"), "ac015", "noticed") == []
    assert at(item_of(results, "q01"), "ac015", "says_amended") is False
    assert judge.calls[0][2] == ("1.25",)


def test_the_judge_is_asked_only_about_the_provisions_no_notice_covers(connections):
    answer = generated([ARTICLE_A, AMENDING_A, ARTICLE_C_3],
                       [("Câu một.", ("1.25",)), ("Câu hai.", ("3",)), NOTICE_K25], notices=1)
    results, judge = one_question([LISTED_K25, provision(C)], answer, judge=SaysNotAmended())
    entry = at(item_of(results, "q01"), "ac015")
    assert (at(entry, "asked"), at(entry, "noticed")) == (["1.25", "3"], ["1.25"])
    assert judge.calls[0][2] == ("3",)
    assert at(entry, "says_amended") is False and at(entry, "passes") is False
    _, agreeing = one_question([LISTED_K25, provision(C)], answer)
    assert agreeing.calls[0][2] == ("3",)


def test_the_answers_record_holds_the_ids_the_judge_was_asked_about(connections):
    answer = generated([ARTICLE_A, AMENDING_A, ARTICLE_C_3],
                       [("Câu một.", ("1.25",)), ("Câu hai.", ("3",)), NOTICE_K25], notices=1)
    answers = []
    one_question([LISTED_K25, provision(C)], answer, answers=answers)
    assert answers[0].get("amended") == ["3"]


def test_a_listed_article_whose_answer_cites_another_clause_is_uncited(connections):
    answer = generated([ARTICLE_A, AMENDING_A], [("Câu một.", ("1.1",))])
    results, judge = one_question([provision(A)], answer)
    assert at(results, "ac015", "uncited") == ["q01"]
    assert at(results, "ac015", "applies") == []
    assert at(results, "ac015", "green") is None
    assert at(item_of(results, "q01"), "ac015", "asked") == []
    assert judge.calls[0][2] == ()  # the judge is not asked about an amendment


def test_a_listed_article_cited_whole_is_asked_about_its_amended_clause(connections):
    answer = generated([ARTICLE_A, AMENDING_A], [("Câu một.", ("1",))])
    results, judge = one_question([provision(A)], answer)
    assert at(item_of(results, "q01"), "ac015", "asked") == ["1.25"]
    assert at(results, "ac015", "fails") == ["q01"]  # it does not cite [2]
    assert judge.calls[0][2] == ("1.25",)


def test_a_listed_clause_is_asked_about_whether_or_not_the_answer_cites_it(connections):
    listed = Provision(text="khoản 25 Điều 5", article=A, chunk="379409:D5:K25")
    answer = generated([ARTICLE_A, AMENDING_A], [("Câu một.", ("1.1",))])
    results, judge = one_question([listed], answer)
    assert at(item_of(results, "q01"), "ac015", "asked") == ["1.25"]
    assert at(results, "ac015", "fails") == ["q01"]
    assert at(results, "ac015", "uncited") == []
    assert judge.calls[0][2] == ("1.25",)


def test_ac015_is_green_when_every_question_in_the_context_passes(connections):
    answers = dict(ANSWERS)
    answers[QUESTIONS[1].question] = generated([ONLY_C], [("Bị bãi bỏ.", ("1",))])
    results = evaluate(small_set(), GeneratingPipeline(answers), PARENTS, judge=FakeJudge(), chunks=CHUNKS)
    assert at(results, "ac015", "fails") == ["q02"]  # q02 cites [1], which holds no amending source
    assert at(results, "ac015", "green") is False
    answers[QUESTIONS[1].question] = generated([ONLY_C, Passage("2", "amending", "999001", "1", ("999001:D1",), (),
                                                                "[2] bãi bỏ")],
                                               [("Bị bãi bỏ.", ("1", "2"))])
    results = evaluate(small_set(), GeneratingPipeline(answers), PARENTS, judge=FakeJudge(), chunks=CHUNKS)
    assert at(results, "ac015", "passes") == ["q01", "q02"]
    assert at(results, "ac015", "green") is True


def test_latency_and_cost_are_over_the_generated_items(generation):
    results, *_ = generation
    assert at(results, "latency", "n") == 4
    assert at(results, "latency", "median_s") == pytest.approx(0.1 + 0.01 + 1.0)
    assert at(results, "latency", "scope") == "full pipeline, dev laptop"
    assert at(results, "cost", "average_usd") == pytest.approx(0.003)
    assert at(results, "cost", "note") == ""


def test_the_answers_list_gets_one_record_per_generated_item(generation):
    _, _, _, answers = generation
    assert [record.get("id") for record in answers] == ["q01", "q02", "q03", "q04"]
    q01 = answers[0]
    assert list(q01) == ["id", "passages", "sentences", "flagged", "not_found", "amended", "verdict"]
    assert (q01["amended"], answers[1]["amended"], answers[2]["amended"]) == (["1.25"], [], [])
    assert q01["passages"] == [{"id": "1", "text": "[1] A"}, {"id": "2", "text": "[2] sửa đổi A"},
                               {"id": "3", "text": "[3] B"}]
    assert q01["sentences"] == [{"text": "Câu một.", "citations": ["1.25", "2"]},
                                {"text": "Câu hai.", "citations": ["7"]}]
    assert q01["verdict"] == {"cited": [True, False], "supported": [True, True], "facts": [True],
                              "contradicts": False, "says_amended": True, "correct": True}
    assert answers[1]["verdict"] is None


def test_the_summary_marks_judged_scores_as_not_hand_checked(generation, tmp_path):
    results, *_ = generation
    text = summary(results, tmp_path / "x.json")
    assert text.count("judge gemini-3.5-flash-lite, not hand-checked") == 4  # EVAL-002, 003, 006 and 009 (#39)
    assert "not found on 1 of 3 answerable (by recall@k: 1 all, 0 some, 0 none) and 1 of 1 unanswerable" in text
    line = next((l for l in text.splitlines() if "EVAL-004" in l), "")
    assert "1.000" in line and "n=1" in line and "PASS" in line and "judge" not in line
    assert "AC-015: 1 pass, 0 fail, 1 retrieval misses, of 2; 1 uncited: GREEN" in text


# --- Conversation turns through a rewriter (FR-CORE-016, AC-014, approved on #19) ---------------

class RecordingRetriever:
    """Finds HITS for every question it is given, and records each call."""

    fusion = Fusion()

    def __init__(self):
        self.calls: list[tuple] = []

    def retrieve(self, question, k=TOP_K):
        self.calls.append(("retrieve", question))
        return Retrieval([Hit(c, ("keyword",), 0.5) for c in HITS.get(question, ["999001:D1"])], [])

    def fuse(self, questions, k=TOP_K):
        self.calls.append(("fuse", tuple(questions)))
        return Retrieval([Hit("379409:D9", ("keyword", "vector"), 0.03)], [])


class RewriteLLM:
    model = "gemini-3.5-flash-lite"

    def generate(self, prompt, system, user, schema, validate=None):
        return Call(schema.model_validate({"question": "Câu hỏi đã viết lại?"}), self.model, prompt, 300, 40, 0.8,
                    0.0001, 1)


FIRST, SECOND = TURNS[0].question, TURNS[1].question


def test_turns_get_the_questions_of_the_turns_before_them(connections):
    pipeline = FakePipeline()
    evaluate(small_set(), pipeline, PARENTS)
    assert pipeline.seen[1:] == [(q.question, ()) for q in QUESTIONS] + [
        (FIRST, ()), (SECOND, (FIRST,)), (TURNS[2].question, (FIRST, SECOND))]


def test_the_pipeline_retrieves_a_follow_up_with_its_rewrite():
    retriever = RecordingRetriever()
    pipeline = RetrievalPipeline(retriever, rewriter=rewriter("concat"))
    first, follow_up = pipeline.answer(FIRST, ()), pipeline.answer(SECOND, (FIRST,))
    assert retriever.calls == [("retrieve", FIRST), ("retrieve", f"{FIRST} {SECOND}")]
    assert (getattr(first, "rewritten", None), getattr(follow_up, "rewritten", None)) == (False, True)
    assert list(first.latency) == ["retrieval"] and list(follow_up.latency) == ["rewrite", "retrieval"]


def test_the_pipeline_fuses_the_two_queries_of_fuse():
    retriever = RecordingRetriever()
    RetrievalPipeline(retriever, rewriter=rewriter("fuse")).answer(SECOND, (FIRST,))
    assert retriever.calls == [("fuse", (SECOND, f"{FIRST} {SECOND}"))]


def test_none_keeps_today_s_pipeline():
    retriever = RecordingRetriever()
    pipeline = RetrievalPipeline(retriever)
    outcome = pipeline.answer(SECOND, (FIRST,))
    assert retriever.calls == [("retrieve", SECOND)]
    assert getattr(outcome, "rewritten", None) is False and list(outcome.latency) == ["retrieval"]
    assert (pipeline.config["stages"], pipeline.config["rewrite"]) == (["retrieval"], "none")


def test_the_pipeline_records_its_rewriter():
    config = RetrievalPipeline(RecordingRetriever(), rewriter=rewriter("concat")).config
    assert (config["stages"], config["rewrite"]) == (["rewrite", "retrieval"], "concat")
    assert "rewrite_model" not in config


def test_an_llm_rewrite_records_its_model_prompt_tokens_and_cost():
    from src.conversation import PROMPT as REWRITE_PROMPT

    pipeline = RetrievalPipeline(RecordingRetriever(), rewriter=rewriter("llm", RewriteLLM()))
    assert pipeline.config["rewrite"] == "llm"
    assert pipeline.config.get("rewrite_model") == "gemini-3.5-flash-lite"
    assert pipeline.config.get("rewrite_prompt") == hashlib.sha256(REWRITE_PROMPT.read_bytes()).hexdigest()
    outcome = pipeline.answer(SECOND, (FIRST,))
    assert outcome.tokens == {"input": 300, "output": 40}
    assert outcome.cost_usd == pytest.approx(0.0001)
    assert outcome.latency.get("rewrite") == pytest.approx(0.8)


def test_the_answer_pipeline_rewrites_the_turns_it_retrieves():
    answerer = SimpleNamespace(llm=SimpleNamespace(model="gemini-3.5-flash-lite"), assembler=SimpleNamespace(budget=24000))
    retriever = RecordingRetriever()
    pipeline = AnswerPipeline(retriever, answerer, rewriter=rewriter("fuse"))
    assert (pipeline.config["stages"], pipeline.config["rewrite"]) == (
        ["rewrite", "retrieval", "assembly", "generation"], "fuse")
    pipeline.retrieve(SECOND, (FIRST,))
    assert retriever.calls == [("fuse", (SECOND, f"{FIRST} {SECOND}"))]


def test_an_item_records_whether_its_query_was_rewritten(connections):
    results = evaluate(small_set(), RetrievalPipeline(RecordingRetriever(), rewriter=rewriter("concat")), PARENTS)
    assert [at(item_of(results, i), "rewritten") for i in ("q01", "q04", "c01.1", "c01.2", "c01.3")] == \
        [None, None, False, True, True]
    keys = list(item_of(results, "c01.2"))
    assert keys[keys.index("turn") + 1] == "rewritten"


def test_a_rewrite_stage_is_still_retrieval_only(connections):
    results = evaluate(small_set(), RetrievalPipeline(RecordingRetriever(), rewriter=rewriter("concat")), PARENTS)
    assert at(results, "latency", "stages") == ["rewrite", "retrieval"]
    assert at(results, "latency", "scope") == "retrieval only, dev laptop"


def test_standalone_questions_never_go_through_the_rewriter(connections):
    retriever = RecordingRetriever()
    evaluate(small_set(), RetrievalPipeline(retriever, rewriter=rewriter("concat")), PARENTS)
    assert ("retrieve", QUESTIONS[0].question) in retriever.calls  # the warm-up and q01, as written
    assert [c for c in retriever.calls if c[0] == "retrieve" and c[1].startswith(QUESTIONS[0].question + " ")] == []


@pytest.mark.parametrize("name", ["concat", "fuse"])
def test_the_rewrite_option_reaches_the_pipeline_and_the_file(command, loads, name):
    argv, out, _ = command
    assert main(argv + ["--rewrite", name]) == 0
    files = sorted(out.glob("*.json")) if out.is_dir() else []
    assert len(files) == 1
    pipeline = at(json.loads(files[0].read_text(encoding="utf-8")), "configuration", "pipeline")
    assert (at(pipeline, "rewrite"), at(pipeline, "stages")) == (name, ["rewrite", "retrieval"])


def test_the_command_rewrites_with_concat_by_default(command, loads):
    argv, out, _ = command
    assert main(argv) == 0
    files = sorted(out.glob("*.json")) if out.is_dir() else []
    assert len(files) == 1
    pipeline = at(json.loads(files[0].read_text(encoding="utf-8")), "configuration", "pipeline")
    assert (at(pipeline, "rewrite"), at(pipeline, "stages")) == ("concat", ["rewrite", "retrieval"])


def test_an_unknown_rewriter_stops_the_command(command, loads):
    argv, _, _ = command
    with pytest.raises(SystemExit) as stopped:
        main(argv + ["--rewrite", "rerank"])
    assert stopped.value.code == 2 and loads == []


# --- Resume ---

def header() -> dict:
    return {"commit": "a" * 40, "eval_set_sha256": "a" * 64, "pipeline": GeneratingPipeline.config}


def test_progress_keeps_each_generated_item_and_a_rerun_reuses_them(tmp_path, connections):
    path = tmp_path / "progress.jsonl"
    first = evaluate(small_set(), GeneratingPipeline(), PARENTS, judge=FakeJudge(), chunks=CHUNKS,
                     progress=Progress.open(path, header()))
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    assert len(lines) == 1 + 4
    assert json.loads(lines[0]) == header()
    pipeline, judge = GeneratingPipeline(), FakeJudge()
    second = evaluate(small_set(), pipeline, PARENTS, judge=judge, chunks=CHUNKS, progress=Progress.open(path, header()))
    assert pipeline.answered == [] and judge.calls == []
    assert at(second, "scores") == at(first, "scores")


def test_progress_from_another_run_is_refused(tmp_path):
    path = tmp_path / "progress.jsonl"
    path.write_bytes((json.dumps({**header(), "commit": "b" * 40}) + "\n").encode("utf-8"))
    with pytest.raises(ProgressMismatch):
        Progress.open(path, header())


def test_the_command_generates_writes_the_answers_file_and_removes_the_progress(command, capsys):
    argv, out, _ = command
    data = Path(argv[argv.index("--data") + 1])
    assert main(argv + ["--generate"], pipeline=GeneratingPipeline(answers={}, default=DEFAULT_ANSWER),
                judge=FakeJudge()) == 0
    files = sorted(out.glob("*.json")) if out.is_dir() else []
    assert len(files) == 1
    written = json.loads(files[0].read_text(encoding="utf-8"))
    assert at(written, "generation", "answered") == 30
    answers_file = data / "eval-answers" / (files[0].stem + ".jsonl")
    assert answers_file.exists()
    assert len(answers_file.read_text(encoding="utf-8").splitlines()) == 30
    assert not (data / "eval-answers" / "progress.jsonl").exists()
    assert "not hand-checked" in capsys.readouterr().out


def test_the_command_stops_on_progress_from_another_run(command, capsys):
    argv, out, _ = command
    data = Path(argv[argv.index("--data") + 1])
    (data / "eval-answers").mkdir()
    (data / "eval-answers" / "progress.jsonl").write_bytes(
        (json.dumps({"commit": "0" * 40, "eval_set_sha256": "0" * 64, "pipeline": {}}) + "\n").encode("utf-8"))
    code = main(argv + ["--generate"], pipeline=GeneratingPipeline(answers={}, default=DEFAULT_ANSWER),
                judge=FakeJudge())
    assert code == 2
    assert not out.exists() or not list(out.glob("*.json"))
    assert "progress.jsonl" in capsys.readouterr().out


# --- Re-judging a run (approved on #37, step 1A) ------------------------------------------------

REJUDGE_KEYS = ("cited_supported", "supported", "correct", "facts_stated", "key_facts", "contradicts", "judge_latency_s",
                "judge_tokens", "judge_cost_usd", "ac015")


def rejudge_function():
    from src.eval import run as runner

    function = getattr(runner, "rejudge", None)
    assert function is not None, "src.eval.run has no rejudge"
    return function


class RecordingJudge(FakeJudge):
    """Finds every answer wrong, says no provision was amended, and records what it was shown."""

    def __init__(self):
        super().__init__()
        self.shown: list[tuple] = []

    def judge(self, question, key_facts, answer, amended=()):
        self.calls.append((question, tuple(key_facts), tuple(amended)))
        self.shown.append(([(s.text, tuple(s.citations)) for s in answer.sentences], answer.context.text,
                           tuple(answer.flagged)))
        return Verdict(tuple(False if s.citations else None for s in answer.sentences),
                       tuple(False for _ in answer.sentences), tuple(False for _ in key_facts), True,
                       False if amended else None, False, judge_call())


def judged_run() -> tuple[dict, list[dict]]:
    answers = []
    results = full_results(evaluate(small_set(), GeneratingPipeline(), PARENTS, judge=FakeJudge(), chunks=CHUNKS,
                                    answers=answers))
    results["configuration"]["pipeline"] = {**GeneratingPipeline.config, "prompts": {"answer": "a", "judge": "j"},
                                            "judge_model": "gemini-3.5-flash-lite"}
    return json.loads(json.dumps(results)), json.loads(json.dumps(answers))


def test_rejudge_shows_the_judge_what_the_first_judge_saw(connections):
    old, records = judged_run()
    judge = RecordingJudge()
    rejudge_function()(old, records, small_set(), judge)
    assert judge.calls == [(QUESTIONS[0].question, ("một sự kiện",), ("1.25",)),
                           (QUESTIONS[2].question, ("một sự kiện",), ())]
    sentences, context_text, flagged = judge.shown[0]
    assert sentences == [("Câu một.", ("1.25", "2")), ("Câu hai.", ("7",))]
    assert context_text == "[1] A\n\n[2] sửa đổi A\n\n[3] B"
    assert flagged == ("7",)


def test_rejudge_replaces_only_the_judge_keys_of_the_judged_items(connections):
    old, records = judged_run()
    new, _ = rejudge_function()(old, records, small_set(), RecordingJudge())
    before = {i["id"]: i for i in old["items"]}
    for entry in at(new, "items"):
        unchanged = {k: v for k, v in entry.items() if k not in REJUDGE_KEYS}
        assert unchanged == {k: v for k, v in before[entry["id"]].items() if k not in REJUDGE_KEYS}
    q01 = item_of(new, "q01")
    assert (at(q01, "cited_supported"), at(q01, "supported"), at(q01, "correct")) == (0, 0, False)
    assert item_of(new, "q02") == before["q02"]  # not found: not judged
    assert item_of(new, "q04") == before["q04"]  # unanswerable


def test_rejudge_scores_the_judged_metrics_again_and_keeps_the_rest(connections):
    old, records = judged_run()
    new, _ = rejudge_function()(old, records, small_set(), RecordingJudge())
    assert at(new, "scores", "EVAL-006", "value") == 0.0
    assert at(new, "scores", "EVAL-003", "value") == 0.0
    for eval_id in ("EVAL-001", "EVAL-004", "EVAL-005", "EVAL-007", "EVAL-008"):
        assert at(new, "scores", eval_id) == old["scores"][eval_id]
    for key in ("breakdown", "latency", "cost"):
        assert at(new, key) == old[key]
    assert at(new, "generation", "judge", "calls") == 2


def test_rejudge_takes_ac015_from_the_new_verdict(connections):
    old, records = judged_run()
    assert "q01" in old["ac015"]["passes"]
    new, _ = rejudge_function()(old, records, small_set(), RecordingJudge())
    assert at(item_of(new, "q01"), "ac015", "says_amended") is False
    assert at(item_of(new, "q01"), "ac015", "passes") is False
    assert "q01" in at(new, "ac015", "fails")


def test_rejudge_records_carry_the_new_verdict_and_the_rest_unchanged(connections):
    old, records = judged_run()
    _, new_records = rejudge_function()(old, records, small_set(), RecordingJudge())
    assert [r["id"] for r in new_records] == [r["id"] for r in records]
    for before, after in zip(records, new_records):
        assert {k: v for k, v in after.items() if k != "verdict"} == {k: v for k, v in before.items() if k != "verdict"}
        if before["verdict"] is None:
            assert after["verdict"] is None
    q01 = next(r for r in new_records if r["id"] == "q01")
    assert q01["verdict"]["correct"] is False and q01["verdict"]["facts"] == [False]


def run_main(argv, **kwargs) -> int:
    """main's exit code, an argparse exit included, so an unknown option fails on an assertion."""
    try:
        return main(argv, **kwargs)
    except SystemExit as error:
        return error.code


def generated_file(command) -> Path:
    argv, out, _ = command
    assert main(argv + ["--generate"], pipeline=GeneratingPipeline(answers={}, default=DEFAULT_ANSWER),
                judge=FakeJudge()) == 0
    files = sorted(out.glob("*.json"))
    assert len(files) == 1
    return files[0]


def test_the_command_rejudges_a_run_without_retrieval_or_generation(command, monkeypatch, capsys):
    argv, out, _ = command
    data = Path(argv[argv.index("--data") + 1])
    first = generated_file(command)

    def no_retriever(*args, **kwargs):
        raise AssertionError("a re-judge loads no retriever")

    monkeypatch.setattr(Retriever, "load", no_retriever)
    judge = RecordingJudge()
    capsys.readouterr()
    assert run_main(argv + ["--rejudge", str(first)], judge=judge) == 0
    second = [p for p in sorted(out.glob("*.json")) if p != first]
    assert len(second) == 1
    written = json.loads(second[0].read_text(encoding="utf-8"))
    assert at(written, "run", "rejudge_of") == first.stem
    assert len(judge.calls) == 24
    assert at(written, "scores", "EVAL-006", "value") == 0.0
    answers_file = data / "eval-answers" / (second[0].stem + ".jsonl")
    assert answers_file.exists()
    assert len(answers_file.read_text(encoding="utf-8").splitlines()) == 30
    assert second[0].name in capsys.readouterr().out


def test_the_command_refuses_rejudge_with_generate(command, capsys):
    argv, out, _ = command
    first = generated_file(command)
    capsys.readouterr()
    assert run_main(argv + ["--rejudge", str(first), "--generate"], judge=RecordingJudge()) == 2
    assert "--rejudge does not run with --generate" in capsys.readouterr().out
    assert len(list(out.glob("*.json"))) == 1


def test_the_command_refuses_rejudge_without_the_answers_file(command, capsys):
    argv, out, _ = command
    data = Path(argv[argv.index("--data") + 1])
    first = generated_file(command)
    (data / "eval-answers" / (first.stem + ".jsonl")).unlink()
    capsys.readouterr()
    assert run_main(argv + ["--rejudge", str(first)], judge=RecordingJudge()) == 2
    assert first.stem + ".jsonl" in capsys.readouterr().out
    assert len(list(out.glob("*.json"))) == 1


def test_the_command_refuses_rejudge_on_another_eval_set(command, capsys):
    argv, out, set_path = command
    first = generated_file(command)
    set_path.write_text(set_path.read_text(encoding="utf-8") + "# changed\n", encoding="utf-8")
    capsys.readouterr()
    assert run_main(argv + ["--rejudge", str(first)], judge=RecordingJudge()) == 2
    assert "different eval sets" in capsys.readouterr().out
    assert len(list(out.glob("*.json"))) == 1


# --- A seed per run (approved on #37, a seed per run) --------------------------------------------

def written_pipeline(out: Path) -> dict:
    files = sorted(out.glob("*.json")) if out.is_dir() else []
    assert len(files) == 1
    return at(json.loads(files[0].read_text(encoding="utf-8")), "configuration", "pipeline")


def test_the_seed_option_is_recorded_in_the_pipeline(command):
    argv, out, _ = command
    assert run_main(argv + ["--generate", "--seed", "2"], pipeline=GeneratingPipeline(answers={}, default=DEFAULT_ANSWER),
                    judge=FakeJudge()) == 0
    assert at(written_pipeline(out), "seed") == 2
    assert "seed" not in GeneratingPipeline.config  # the pipeline's own config is not changed


def test_without_a_seed_the_pipeline_has_no_seed_key(command):
    argv, out, _ = command
    assert run_main(argv + ["--generate"], pipeline=GeneratingPipeline(answers={}, default=DEFAULT_ANSWER),
                    judge=FakeJudge()) == 0
    assert "seed" not in written_pipeline(out)


class Built(Exception):
    """Raised by the fake LLM once it is built: the test only needs its arguments."""


def test_the_command_builds_its_model_with_the_seed(command, loads, monkeypatch):
    import src.llm

    built = []

    def fake_llm(*args, **kwargs):
        built.append(kwargs.get("seed"))
        raise Built

    monkeypatch.setattr(src.llm, "LLM", fake_llm)
    argv, _, _ = command
    try:
        outcome = main(argv + ["--rewrite", "llm", "--seed", "3"])
    except Built:
        outcome = "built"
    except SystemExit as error:
        outcome = f"exit {error.code}"
    assert outcome == "built"
    assert built == [3]


def test_the_command_refuses_a_seed_with_rejudge(command, capsys):
    argv, out, _ = command
    first = generated_file(command)
    capsys.readouterr()
    assert run_main(argv + ["--rejudge", str(first), "--seed", "1"], judge=RecordingJudge()) == 2
    assert "--seed does not run with --rejudge" in capsys.readouterr().out
    assert len(list(out.glob("*.json"))) == 1


# --- Key-fact coverage, EVAL-009 (approved on #39) ----------------------------------------------

class Contradicts(FakeJudge):
    """States every key fact and contradicts one of them."""

    def judge(self, question, key_facts, answer, amended=()):
        verdict = super().judge(question, key_facts, answer, amended)
        return dataclasses.replace(verdict, facts=tuple(True for _ in key_facts), contradicts=True, correct=False)


def test_eval009_is_the_mean_coverage_over_answerable_questions(generation):
    results, *_ = generation
    entry = score(results, "EVAL-009")
    # q01 states its one key fact, q02 is not found, q03 states none
    assert at(entry, "value") == pytest.approx(1 / 3)
    assert (at(entry, "n"), at(entry, "target"), at(entry, "passes")) == (3, None, None)
    assert at(entry, "interval") == pytest.approx(list(bootstrap_interval([1.0, 0.0, 0.0])))
    assert at(entry, "judge") == "gemini-3.5-flash-lite"


def test_items_record_the_key_facts_stated(generation):
    results, *_ = generation
    keys = ("facts_stated", "key_facts", "contradicts")
    assert [tuple(at(item_of(results, q), k) for k in keys) for q in ("q01", "q02", "q03", "q04")] == [
        (1, 1, False), (0, 1, None), (0, 1, False), (None, None, None)]


def test_an_answer_that_contradicts_a_key_fact_covers_nothing(connections):
    results, _ = one_question([provision(B)], DEFAULT_ANSWER, judge=Contradicts())
    q01 = item_of(results, "q01")
    assert (at(q01, "facts_stated"), at(q01, "contradicts")) == (1, True)
    assert at(score(results, "EVAL-009"), "value") == 0.0


def rescore_function():
    from src.eval import run as runner

    function = getattr(runner, "rescore", None)
    assert function is not None, "src.eval.run has no rescore"
    return function


def before_eval009(results: dict) -> dict:
    """A results file as written before #39: no coverage keys and no EVAL-009."""
    old = json.loads(json.dumps(results))
    old["scores"].pop("EVAL-009", None)
    for entry in old["items"]:
        for key in ("facts_stated", "key_facts", "contradicts"):
            entry.pop(key, None)
    return old


def test_rescore_gives_an_earlier_run_eval009_from_its_stored_verdicts(connections):
    scored, records = judged_run()
    new = rescore_function()(before_eval009(scored), records, small_set())
    assert at(new, "scores", "EVAL-009") == at(scored, "scores", "EVAL-009")
    assert list(at(new, "scores")) == EVAL_IDS
    for before, after in zip(scored["items"], at(new, "items")):
        assert list(after) == list(before)  # the keys back in their order
        assert after == before


def test_the_command_rescores_a_run_without_retrieval_or_judge(command, monkeypatch, capsys):
    argv, out, _ = command
    data = Path(argv[argv.index("--data") + 1])
    first = generated_file(command)
    path_of_answers = data / "eval-answers" / (first.stem + ".jsonl")
    first.write_text(json.dumps(before_eval009(json.loads(first.read_text(encoding="utf-8")))), encoding="utf-8")

    def no_retriever(*args, **kwargs):
        raise AssertionError("a re-score loads no retriever")

    monkeypatch.setattr(Retriever, "load", no_retriever)
    judge = RecordingJudge()
    capsys.readouterr()
    assert run_main(argv + ["--rescore", str(first)], judge=judge) == 0
    assert judge.calls == []
    second = [p for p in sorted(out.glob("*.json")) if p != first]
    assert len(second) == 1
    written = json.loads(second[0].read_text(encoding="utf-8"))
    assert at(written, "run", "rescore_of") == first.stem
    assert at(written, "scores", "EVAL-009", "value") == 1.0
    copied = data / "eval-answers" / (second[0].stem + ".jsonl")
    assert copied.exists() and copied.read_bytes() == path_of_answers.read_bytes()


def test_the_command_refuses_rescore_with_generate(command, capsys):
    argv, out, _ = command
    first = generated_file(command)
    capsys.readouterr()
    assert run_main(argv + ["--rescore", str(first), "--generate"], judge=RecordingJudge()) == 2
    assert "--rescore does not run with --generate" in capsys.readouterr().out
    assert len(list(out.glob("*.json"))) == 1


# --- The context's k (approved on #36, choice 1A) ------------------------------------------------

class KRetriever:
    """Finds `k` hits for every question, the expected article of q01 only at rank 9, and records each k."""

    fusion = Fusion()

    def __init__(self):
        self.ks: list[tuple[str, int]] = []

    def _hits(self, k):
        chunks = ["999001:D1"] * 8 + ["379409:D9"] * 8
        return Retrieval([Hit(c, ("keyword",), 0.5) for c in chunks[:k]], [])

    def retrieve(self, question, k=TOP_K):
        self.ks.append(("retrieve", k))
        return self._hits(k)

    def fuse(self, questions, k=TOP_K):
        self.ks.append(("fuse", k))
        return self._hits(k)


class HitsAnswerer:
    """Records how many hits each answer was given."""

    llm = SimpleNamespace(model="gemini-3.5-flash-lite")
    assembler = SimpleNamespace(budget=24000)

    def __init__(self):
        self.given: list[int] = []

    def answer(self, question, result):
        self.given.append(len(result.hits))
        return SimpleNamespace(call=None, latency_s={"assembly": 0.0, "generation": 0.0})


def with_context_k(retriever, answerer, k):
    """The pipeline with a context k, or None while `AnswerPipeline` takes none, so the test fails on an assertion."""
    try:
        return AnswerPipeline(retriever, answerer, context_k=k)
    except TypeError:
        return None


def test_the_context_k_sets_the_hits_an_answer_is_given():
    retriever, answerer = KRetriever(), HitsAnswerer()
    pipeline = with_context_k(retriever, answerer, 12)
    assert pipeline is not None
    outcome = pipeline.answer(QUESTIONS[0].question)
    assert retriever.ks == [("retrieve", 12)]
    assert answerer.given == [12]
    assert len(outcome.hits) == 12


def test_the_context_k_leaves_the_turns_at_top_k():
    retriever = KRetriever()
    pipeline = with_context_k(retriever, HitsAnswerer(), 12)
    assert pipeline is not None
    pipeline.retrieve(SECOND, (FIRST,))
    assert retriever.ks == [("retrieve", TOP_K)]


def test_without_a_context_k_an_answer_is_given_top_k_hits():
    retriever, answerer = KRetriever(), HitsAnswerer()
    pipeline = AnswerPipeline(retriever, answerer)
    pipeline.answer(QUESTIONS[0].question)
    assert answerer.given == [TOP_K]
    assert "context_k" not in pipeline.config


def test_the_context_k_is_recorded_in_the_pipeline_config():
    pipeline = with_context_k(KRetriever(), HitsAnswerer(), 12)
    assert pipeline is not None
    assert pipeline.config.get("context_k") == 12
    assert pipeline.config.get("top_k") == TOP_K


def test_more_hits_than_top_k_are_stored_and_scored_at_top_k(connections):
    results = evaluate(small_set(), RetrievalPipeline(KRetriever(), k=12), PARENTS)
    item = item_of(results, "q01")
    assert len(at(item, "hits")) == 12
    assert at(item, "recall") == 0.0  # its expected article is only at rank 9
    assert at(item, "context_precision") == 0.0


def test_the_command_builds_the_answer_pipeline_with_the_context_k(command, loads, monkeypatch):
    import src.answer
    import src.eval.run as run_module
    import src.llm

    built = []

    def fake_pipeline(*args, **kwargs):
        built.append(kwargs.get("context_k"))
        raise Built

    monkeypatch.setattr(src.llm, "LLM", lambda *args, **kwargs: SimpleNamespace(model="gemini-3.5-flash-lite"))
    monkeypatch.setattr(src.answer.Answerer, "load", classmethod(lambda cls, *args, **kwargs: HitsAnswerer()))
    monkeypatch.setattr(run_module, "AnswerPipeline", fake_pipeline)
    argv, _, _ = command
    try:
        outcome = main(argv + ["--generate", "--context-k", "12"])
    except Built:
        outcome = "built"
    except SystemExit as error:
        outcome = f"exit {error.code}"
    assert outcome == "built"
    assert built == [12]


def test_the_command_refuses_a_context_k_without_generate(command, loads, capsys):
    argv, out, _ = command
    assert run_main(argv + ["--context-k", "12"]) == 2
    assert "--context-k needs --generate" in capsys.readouterr().out
    assert not list(out.glob("*.json")) if out.is_dir() else True


def test_the_command_refuses_a_context_k_below_top_k(command, capsys):
    argv, out, _ = command
    assert run_main(argv + ["--generate", "--context-k", "4"],
                    pipeline=GeneratingPipeline(answers={}, default=DEFAULT_ANSWER), judge=FakeJudge()) == 2
    assert f"--context-k must be at least {TOP_K}" in capsys.readouterr().out
