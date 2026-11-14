"""#24 cut diagnosis: where the expected articles missing from the top 8 sit. Approach approved
on #24.

The rules are `docs/reference/retrieval.md`, *Cut diagnosis*. Unit tests read fixed rankings
through a fake retriever, so no index or model is needed and nothing goes to the network. The
corpus test at the end reads the local `data/` and the eval set: `pytest -m corpus`.
"""

import json
import socket
from datetime import date
from pathlib import Path

import pytest
from test_eval_run import at, item, write_data, write_set

from src.eval.dataset import Conversation, EvalSet
from src.eval.diagnose import CUTS, DEPTH, diagnose, main, summary, verdict
from src.eval.metrics import bootstrap_interval
from src.retrieval import Rankings, Unresolved

ROOT = Path(__file__).resolve().parent.parent
TOP_KEYS = ["format", "run", "configuration", "recall", "misses", "verdict", "items"]


@pytest.fixture
def connections(monkeypatch) -> list:
    """Every outgoing connection attempt; each one fails."""
    attempts = []

    def refuse(sock, address):
        attempts.append(address)
        raise OSError("network blocked in unit tests")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    return attempts


# --- A small run --------------------------------------------------------------------------------

A, B, C, D = "100:D1", "100:D2", "100:D3", "100:D4"
FILLER = [f"200:D{n}" for n in range(1, 301)]  # one chunk per article, its own id
PARENTS = {"100:D1:K1": A, "100:D1:K2": A, "100:D2": B, "100:D3": C, "100:D4:K1": D, "100:D4:K2": D,
           **{chunk: chunk for chunk in FILLER}}


def placed(positions: dict[str, int], length: int) -> list[str]:
    """`length` chunk ids, each chunk of `positions` at its rank from 1, filler elsewhere."""
    ranking: list[str | None] = [None] * length
    for chunk, rank in positions.items():
        ranking[rank - 1] = chunk
    filler = iter(FILLER)
    return [chunk if chunk is not None else next(filler) for chunk in ranking]


QUESTIONS = [
    item("q01", "Câu hỏi một?", "vat", "plain", [A, B]),
    item("q02", "Điều 1 Nghị định 999/2026 quy định gì?", "vat", "reference", [C]),
    item("q03", "Câu hỏi ba?", "pit", "plain", [D]),
    item("q04", "Câu hỏi bốn?", "pit", "plain", [A]),
    item("q05", "Câu hỏi năm không có đáp án?", "vat", "plain", unanswerable="out_of_scope"),
]
TURNS = [
    item("c01.1", "Lượt một của hội thoại?", "vat", "plain", [A]),
    item("c01.2", "Còn lượt hai thì sao?", "vat", "plain", [B]),
]
RANKINGS = {
    # A at 1, B at 10: B is below the cut
    QUESTIONS[0].question: Rankings(keyword=placed({"100:D2": 1}, 40),
                                    vector=placed({"100:D1:K2": 2, "100:D2": 70}, 250),
                                    final=placed({"100:D1:K2": 1, "100:D2": 10}, 60)),
    # C at 60: beyond 50; no keyword score
    QUESTIONS[1].question: Rankings(keyword=[], vector=placed({"100:D3": 30}, 250),
                                    final=placed({"100:D3": 60}, 80),
                                    unresolved=[Unresolved("Nghị định 999/2026", "unknown_document")]),
    # D, split, in no list's top 50 and not in the pool; its best chunk is K2 in both rankings
    QUESTIONS[2].question: Rankings(keyword=placed({"100:D4:K2": 80, "100:D4:K1": 90}, 100),
                                    vector=placed({"100:D4:K2": 150, "100:D4:K1": 200}, 250),
                                    final=placed({}, 60)),
    # A at 3: no miss
    QUESTIONS[3].question: Rankings(keyword=[], vector=placed({}, 250), final=placed({"100:D1:K1": 3}, 60)),
    QUESTIONS[4].question: Rankings(keyword=[], vector=placed({}, 250), final=placed({}, 60)),
    # a first turn: not scored
    TURNS[0].question: Rankings(keyword=[], vector=placed({}, 250), final=placed({}, 60)),
    # B at 20, keyword 45, vector 55
    TURNS[1].question: Rankings(keyword=placed({"100:D2": 45}, 50), vector=placed({"100:D2": 55}, 250),
                                final=placed({"100:D2": 20}, 60)),
}
RECALL = {  # per scored item, at each cut
    "standalone": [[0.5, 1, 1, 1, 1, 1], [0] * 6, [0] * 6, [1] * 6],
    "follow_up": [[0, 0, 0, 1, 1, 1]],
}


class FakeRetriever:
    def __init__(self, rankings=None, default=None):
        self._rankings, self._default = rankings or {}, default or Rankings()
        self.calls: list[str] = []

    def rankings(self, question: str) -> Rankings:
        self.calls.append(question)
        return self._rankings.get(question, self._default)


def small_set() -> EvalSet:
    return EvalSet(version=1, as_of=date(2026, 11, 12), sha256="a" * 64, questions=list(QUESTIONS),
                   conversations=[Conversation("c01", 1, list(TURNS))])


@pytest.fixture
def retriever() -> FakeRetriever:
    return FakeRetriever(RANKINGS)


@pytest.fixture
def results(connections, retriever) -> dict:
    return diagnose(small_set(), retriever, PARENTS)


def entry(results: dict, item_id: str) -> dict:
    found = [e for e in at(results, "items") if at(e, "id") == item_id]
    assert len(found) == 1, item_id
    return found[0]


def test_the_cuts_and_the_depth():
    assert CUTS == (8, 12, 16, 20, 30, 50)
    assert DEPTH == 50


@pytest.mark.parametrize("group", ["standalone", "follow_up"])
def test_recall_at_each_cut_reads_the_first_k_of_the_final_ranking(results, group):
    for n, k in enumerate(CUTS):
        values = [float(per_item[n]) for per_item in RECALL[group]]
        score = at(results, "recall", group, str(k))
        assert at(score, "value") == pytest.approx(sum(values) / len(values)), k
        assert at(score, "n") == len(values), k
        assert at(score, "interval") == pytest.approx(list(bootstrap_interval(values))), k


def test_every_item_is_ranked_once_in_file_order(results, retriever):
    assert retriever.calls == [i.question for i in QUESTIONS + TURNS]


def test_items_are_the_scored_items_in_run_order(results):
    assert [at(e, "id") for e in at(results, "items")] == ["q01", "q02", "q03", "q04", "c01.2"]
    first = entry(results, "q01")
    assert (at(first, "kind"), at(first, "conversation"), at(first, "turn")) == ("question", None, None)
    assert at(first, "expected") == [A, B]
    assert at(first, "recall") == {str(k): v for k, v in zip(CUTS, RECALL["standalone"][0])}
    turn = entry(results, "c01.2")
    assert (at(turn, "kind"), at(turn, "conversation"), at(turn, "turn")) == ("turn", "c01", 2)
    assert at(entry(results, "q02"), "unresolved") == ["unknown_document"]


def test_a_miss_below_the_cut(results):
    assert at(entry(results, "q01"), "misses") == [
        {"article": B, "final_rank": 10, "keyword_rank": 1, "vector_rank": 70, "place": "below_cut",
         "lists": ["keyword"], "split": False}]


def test_a_miss_beyond_50_with_no_keyword_score(results):
    assert at(entry(results, "q02"), "misses") == [
        {"article": C, "final_rank": 60, "keyword_rank": None, "vector_rank": 30, "place": "beyond_50",
         "lists": ["vector"], "split": False}]


def test_a_split_miss_not_in_the_pool_counts_at_its_best_chunk(results):
    assert at(entry(results, "q03"), "misses") == [
        {"article": D, "final_rank": None, "keyword_rank": 80, "vector_rank": 150, "place": "not_in_pool",
         "lists": [], "split": True}]


def test_an_article_in_the_top_8_is_no_miss(results):
    assert at(entry(results, "q04"), "misses") == []


def test_misses_are_counted_per_group(results):
    assert at(results, "misses", "standalone") == {
        "articles": 3, "below_cut": 1, "beyond_50": 1, "not_in_pool": 1, "share_below_cut": pytest.approx(1 / 3),
        "lists": {"both": 0, "keyword": 1, "vector": 1, "neither": 1}, "split": 1, "unresolved": 1}
    assert at(results, "misses", "follow_up") == {
        "articles": 1, "below_cut": 1, "beyond_50": 0, "not_in_pool": 0, "share_below_cut": pytest.approx(1.0),
        "lists": {"both": 0, "keyword": 1, "vector": 0, "neither": 0}, "split": 0, "unresolved": 0}


def test_the_verdict_reads_the_standalone_misses_only(results):
    # follow-ups alone would say ranking (1 of 1); standalone says retrieval, 1 of 3, within two of the line
    assert at(results, "verdict") == {"result": "retrieval", "below_cut": 1, "misses": 3, "borderline": True}


@pytest.mark.parametrize("below_cut, misses, result, borderline", [
    (15, 20, "ranking", False),
    (10, 20, "ranking", True),
    (9, 20, "retrieval", True),
    (4, 20, "retrieval", False),
    (0, 0, None, False),
])
def test_the_decision_rule(below_cut, misses, result, borderline):
    assert verdict(below_cut, misses) == {"result": result, "below_cut": below_cut, "misses": misses,
                                          "borderline": borderline}


def test_no_question_text_is_written(results):
    written = json.dumps(results, ensure_ascii=False)
    assert at(results, "items")
    for i in QUESTIONS + TURNS:
        assert i.question not in written, i.id


def test_summary_prints_recall_misses_and_the_verdict(results):
    full = {**results, "configuration": {"commit": "a" * 40, "dirty": True}}
    text = summary(full, Path("eval/results/diagnostics/2026-11-15-aaaaaaa-dirty.json"))
    assert "2026-11-15-aaaaaaa-dirty.json" in text
    assert "DIRTY" in text
    for word in ("below_cut", "beyond_50", "not_in_pool", "retrieval", "borderline"):
        assert word in text, word


# --- The command --------------------------------------------------------------------------------

@pytest.fixture
def command(tmp_path, connections):
    data, out, set_path = tmp_path / "data", tmp_path / "diagnostics", tmp_path / "questions.yaml"
    write_data(data)
    write_set(set_path)
    return ["--set", str(set_path), "--data", str(data), "--out", str(out)], out


def test_the_command_writes_one_file_and_prints_the_summary(command, capsys):
    argv, out = command
    retriever = FakeRetriever(default=Rankings(final=["379409:D9"]))
    assert main(argv, retriever=retriever) == 0
    files = sorted(out.glob("*.json")) if out.is_dir() else []
    assert len(files) == 1
    written = json.loads(files[0].read_text(encoding="utf-8"))
    assert list(written) == TOP_KEYS
    assert at(written, "format") == 1
    assert at(written, "run", "command").startswith("python -m src.eval.diagnose")
    pipeline = at(written, "configuration", "pipeline")
    assert (at(pipeline, "top_k"), at(pipeline, "depth"), at(pipeline, "cuts")) == (8, 50, list(CUTS))
    assert at(pipeline, "rewrite") == "none"
    assert at(written, "recall", "standalone", "8", "value") == 1.0
    assert at(written, "misses", "follow_up", "articles") == 5
    assert at(written, "verdict", "result") is None
    assert len(retriever.calls) == 30 + 10
    assert files[0].name in capsys.readouterr().out


# --- The real retriever -------------------------------------------------------------------------

@pytest.mark.corpus
def test_recall_at_8_equals_the_runner_scores(connections):
    """Run `python -m src.index` first."""
    from src.eval.dataset import load_eval_set
    from src.eval.run import RetrievalPipeline, _parents, evaluate
    from src.retrieval import Retriever

    data = ROOT / "data"
    retriever = Retriever.load(data)
    eval_set = load_eval_set(ROOT / "eval" / "questions.yaml", data / "processed", data / "enriched")
    parents = _parents(data / "enriched")
    run = evaluate(eval_set, RetrievalPipeline(retriever), parents)
    diagnosed = diagnose(eval_set, retriever, parents)
    assert at(diagnosed, "recall", "standalone", "8", "value") == pytest.approx(at(run, "scores", "EVAL-001", "value"))
    assert at(diagnosed, "recall", "follow_up", "8", "value") == pytest.approx(at(run, "scores", "EVAL-005", "value"))
    assert connections == []
