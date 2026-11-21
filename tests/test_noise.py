"""Run-to-run noise in EVAL-006 (approved on #37, step 0A): `scripts/noise.py`.

The rules are `docs/reference/eval-results.md`, *Run-to-run noise*. Results and answers files are
built by hand, with only the keys the script reads.
"""

import importlib.util
import json
import math
import sys
from pathlib import Path

import numpy as np
import pytest

from src.eval.metrics import paired_bootstrap_interval

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "noise.py"


def noise():
    assert SCRIPT.exists(), "scripts/noise.py does not exist"
    spec = importlib.util.spec_from_file_location("noise", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules["noise"] = module
    spec.loader.exec_module(module)
    return module


def item(item_id, correct, not_found=False, answerable=True, kind="question"):
    return {"id": item_id, "kind": kind, "answerable": answerable, "not_found": not_found,
            "correct": correct if answerable else None}


def record(item_id, texts, facts=None, not_found=False):
    verdict = None if facts is None else {"facts": list(facts), "correct": all(facts)}
    return {"id": item_id, "sentences": [{"text": t, "citations": []} for t in texts], "not_found": not_found,
            "verdict": verdict}


# --- Same text ------------------------------------------------------------------------------------

def test_normalised_text_drops_punctuation_and_collapses_whitespace():
    normalised = noise().normalised
    assert normalised(["Thuế  suất là 10%.", " Có, theo khoản 2. "]) == ("Thuế suất là 10", "Có theo khoản 2")
    assert normalised(["Một."]) != normalised(["Hai."])


def test_a_pair_is_split_by_verdict_change_and_by_same_text():
    a = [item("q01", True), item("q02", True), item("q03", False), item("q04", True), item("q05", None, answerable=False)]
    b = [item("q01", False), item("q02", False), item("q03", False), item("q04", True), item("q05", None, answerable=False)]
    a_records = [record("q01", ["Câu một."]), record("q02", ["Câu hai."]), record("q03", ["Ba."]),
                 record("q04", ["Bốn."])]
    b_records = [record("q01", ["Câu một."]), record("q02", ["Câu hai"]), record("q03", ["Khác."]),
                 record("q04", ["Bốn."])]
    split = noise().pair_split(a, b, a_records, b_records)
    assert {k: split[k] for k in ("n", "same_text", "same_normalised", "changed", "changed_same_text",
                                  "changed_same_normalised")} == {
        "n": 4, "same_text": 2, "same_normalised": 3, "changed": 2, "changed_same_text": 1,
        "changed_same_normalised": 2}
    low, high = paired_bootstrap_interval([1.0, 1.0, 0.0, 1.0], [0.0, 0.0, 0.0, 1.0])
    assert split["half_width"] == pytest.approx((high - low) / 2)


def test_an_item_without_a_correct_in_both_runs_is_left_out_of_the_pair():
    a = [item("q01", True), item("q02", None)]
    b = [item("q01", True), item("q02", True)]
    split = noise().pair_split(a, b, [record("q01", ["A."])], [record("q01", ["A."]), record("q02", ["B."])])
    assert split["n"] == 1


# --- Projection -----------------------------------------------------------------------------------

def test_the_projection_uses_the_mean_item_variance_across_runs():
    runs = [[item("q01", True), item("q02", True), item("q03", False)],
            [item("q01", False), item("q02", True), item("q03", False)],
            [item("q01", True), item("q02", True), item("q03", True)]]
    projection = noise().projection(runs)
    per_item = [np.var([1, 0, 1], ddof=1), np.var([1, 1, 1], ddof=1), np.var([0, 0, 1], ddof=1)]
    variance = float(np.mean(per_item))
    assert projection["n"] == 3
    assert projection["variance"] == pytest.approx(variance)
    assert sorted(projection["half_width"]) == [1, 2, 3, 4, 5]
    for k in range(1, 6):
        assert projection["half_width"][k] == pytest.approx(1.96 * math.sqrt(2 * variance / (k * 3)))


def test_the_projection_needs_three_runs():
    with pytest.raises(ValueError):
        noise().projection([[item("q01", True)], [item("q01", False)]])


# --- Share of key facts ---------------------------------------------------------------------------

def test_the_share_of_key_facts_is_the_mean_of_the_verdict_facts():
    facts_share = noise().facts_share
    assert facts_share(item("q01", False), record("q01", ["A."], facts=[True, False, True, True])) == 0.75
    assert facts_share(item("q01", False, not_found=True), record("q01", [], not_found=True)) == 0.0
    assert facts_share(item("q01", None), record("q01", ["A."])) is None
    assert facts_share(item("q05", None, answerable=False), record("q05", ["A."])) is None


def test_a_pair_scores_binary_eval006_and_the_share_of_key_facts():
    a = [item("q01", True), item("q02", False)]
    b = [item("q01", True), item("q02", True)]
    scores = noise().pair_scores(a, b, [record("q01", ["A."], [True]), record("q02", ["B."], [True, False])],
                                 [record("q01", ["A."], [True]), record("q02", ["B."], [True, True])])
    assert scores["EVAL-006"][:2] == pytest.approx((0.5, 1.0))
    assert scores["EVAL-006"][2:] == pytest.approx(paired_bootstrap_interval([1.0, 0.0], [1.0, 1.0]))
    assert scores["facts"][:2] == pytest.approx((0.75, 1.0))
    assert scores["facts"][2:] == pytest.approx(paired_bootstrap_interval([1.0, 0.5], [1.0, 1.0]))


# --- The command ----------------------------------------------------------------------------------

def write_run(tmp_path, stem, items, records):
    results = tmp_path / "results" / f"{stem}.json"
    results.parent.mkdir(exist_ok=True)
    results.write_text(json.dumps({"items": items}), encoding="utf-8")
    answers = tmp_path / "answers" / f"{stem}.jsonl"
    answers.parent.mkdir(exist_ok=True)
    answers.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records), encoding="utf-8")
    return str(results)


def test_the_command_prints_numbers_and_never_the_answer_text(tmp_path, capsys):
    secret = "Văn bản bí mật của câu trả lời."
    paths = []
    for n, verdicts in enumerate([(True, False), (False, False), (True, True)], 1):
        items = [item("q01", verdicts[0]), item("q02", verdicts[1])]
        records = [record("q01", [secret], [verdicts[0]]), record("q02", [secret + str(n)], [verdicts[1]])]
        paths.append(write_run(tmp_path, f"run{n}", items, records))
    argv = ["--runs", ",".join(paths), "--pairs", f"{paths[0]}:{paths[1]}", "--answers", str(tmp_path / "answers")]
    assert noise().main(argv) == 0
    out = capsys.readouterr().out
    assert secret not in out and "bí mật" not in out
    assert "run1" in out and "run2" in out
    assert "k = 3" in out or "k=3" in out
