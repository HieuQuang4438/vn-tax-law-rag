"""Comparing several runs of each side (approved on #37, step 3B).

The rules are `docs/reference/eval-results.md`, *Comparing several runs*. Results files are built
by hand here, with only the keys the comparison reads, so nothing runs a pipeline.
"""

import importlib
import importlib.util
import json

import numpy as np
import pytest

from src.eval import metrics
from src.eval.metrics import paired_bootstrap_interval
from src.eval.run import compare as compare_two


def module():
    assert importlib.util.find_spec("src.eval.compare") is not None, "src.eval.compare does not exist"
    return importlib.import_module("src.eval.compare")


def helper(name):
    function = getattr(metrics, name, None)
    assert function is not None, f"src.eval.metrics has no {name}"
    return function


PIPELINE = {"stages": ["retrieval", "assembly", "generation"], "rewrite": "none", "top_k": 8,
            "model": "gemini-3.5-flash-lite"}


def question(item_id, recall=1.0, precision=1.0, correct=None, cited=None, supported=None, sentences=None,
             answerable=True, not_found=False, generated=True):
    """One standalone item; `cited` is (cited_supported, cited_sentences), none when not judged."""
    return {"id": item_id, "kind": "question", "conversation": None, "turn": None, "answerable": answerable,
            "recall": recall if answerable else None, "context_precision": precision if answerable else None,
            "generated": generated, "not_found": not_found, "sentences": sentences,
            "cited_supported": cited[0] if cited else None, "cited_sentences": cited[1] if cited else None,
            "supported": supported, "correct": correct if answerable else None}


def turn(item_id, number, recall):
    return {"id": item_id, "kind": "turn", "conversation": item_id.split(".")[0], "turn": number,
            "answerable": True, "recall": recall, "context_precision": recall, "generated": False,
            "not_found": None, "sentences": None, "cited_supported": None, "cited_sentences": None,
            "supported": None, "correct": None}


def run(commit, items, sha="a" * 64, pipeline=PIPELINE):
    return {"format": 1, "run": {"started": "2026-11-20T10:00:00+07:00"},
            "configuration": {"commit": commit + "0" * (40 - len(commit)), "eval_set": {"sha256": sha},
                              "pipeline": dict(pipeline)},
            "scores": {}, "items": items}


def line_of(text, eval_id):
    return next((line for line in text.splitlines() if line.strip().startswith(eval_id)), "")


# --- The two new intervals ----------------------------------------------------------------------

def test_the_paired_ratio_interval_resamples_items_and_takes_the_difference_of_the_ratios():
    paired_ratio = helper("paired_ratio_bootstrap_interval")
    old_top, old_bottom = [1.0, 0.0, 2.0, 3.0], [2.0, 1.0, 2.0, 4.0]
    new_top, new_bottom = [2.0, 1.0, 2.0, 3.0], [2.0, 1.0, 3.0, 4.0]
    rng = np.random.default_rng(0)
    draws = rng.integers(0, 4, size=(1000, 4))
    ratio = lambda top, bottom: np.asarray(top)[draws].sum(axis=1) / np.asarray(bottom)[draws].sum(axis=1)
    differences = ratio(new_top, new_bottom) - ratio(old_top, old_bottom)
    expected = (float(np.percentile(differences, 2.5)), float(np.percentile(differences, 97.5)))
    assert paired_ratio(old_top, old_bottom, new_top, new_bottom) == pytest.approx(expected)


def test_the_paired_nanmean_interval_skips_missing_values_on_each_side():
    paired_nanmean = helper("paired_nanmean_bootstrap_interval")
    old, new = [1.0, None, 0.5, 0.0, 1.0], [1.0, 0.5, None, 0.5, 1.0]
    rng = np.random.default_rng(0)
    draws = rng.integers(0, 5, size=(1000, 5))
    as_array = lambda values: np.asarray([np.nan if v is None else v for v in values], dtype=np.float64)
    differences = np.nanmean(as_array(new)[draws], axis=1) - np.nanmean(as_array(old)[draws], axis=1)
    expected = (float(np.nanpercentile(differences, 2.5)), float(np.nanpercentile(differences, 97.5)))
    assert paired_nanmean(old, new) == pytest.approx(expected)


# --- One file per side matches --compare ----------------------------------------------------------

def retrieval_runs():
    old = run("aaaaaaa", [question("q01", 1.0, 1.0), question("q02", 0.5, 0.5), question("q03", 1.0, 0.8),
                          turn("c01.1", 1, 0.0), turn("c01.2", 2, 1.0), turn("c01.3", 2, 0.5)])
    new = run("bbbbbbb", [question("q01", 0.5, 0.5), question("q02", 1.0, 0.7), question("q03", 1.0, 0.8),
                          turn("c01.1", 1, 1.0), turn("c01.2", 2, 0.0), turn("c01.3", 2, 1.0)])
    for results in (old, new):
        standalone = [i for i in results["items"] if i["kind"] == "question"]
        follow_ups = [i for i in results["items"] if i["kind"] == "turn" and i["turn"] > 1]
        results["scores"] = {
            "EVAL-001": {"value": sum(i["recall"] for i in standalone) / len(standalone)},
            "EVAL-005": {"value": sum(i["recall"] for i in follow_ups) / len(follow_ups)},
            "EVAL-007": {"value": sum(i["context_precision"] for i in standalone) / len(standalone)},
        }
    return old, new


@pytest.mark.parametrize("eval_id", ["EVAL-001", "EVAL-005", "EVAL-007"])
def test_with_one_file_per_side_the_retrieval_intervals_are_those_of_compare(eval_id):
    old, new = retrieval_runs()
    expected = line_of(compare_two(old, new), eval_id)
    assert "paired [" in expected
    got = line_of(module().compare_runs([old], [new]), eval_id)
    assert expected.split("paired", 1)[1] in got
    assert expected.split("(", 1)[0].split(eval_id, 1)[1].strip() in got  # old -> new


# --- Several files per side -----------------------------------------------------------------------

def generation_runs():
    """Two runs a side; q01 and q02 answerable, q03 unanswerable."""
    old = [run("aaaaaaa", [question("q01", correct=True, cited=(2, 2), supported=2, sentences=2),
                           question("q02", correct=False, cited=(0, 1), supported=1, sentences=1),
                           question("q03", answerable=False, not_found=True)]),
           run("aaaaab2", [question("q01", correct=False, cited=(1, 2), supported=1, sentences=2),
                           question("q02", correct=False, not_found=True, sentences=1),
                           question("q03", answerable=False, not_found=False)])]
    new = [run("bbbbbbb", [question("q01", correct=True, cited=(2, 2), supported=2, sentences=2),
                           question("q02", correct=True, cited=(1, 1), supported=1, sentences=1),
                           question("q03", answerable=False, not_found=True)]),
           run("bbbbbb2", [question("q01", correct=True, cited=(2, 3), supported=3, sentences=3),
                           question("q02", correct=False, cited=(1, 2), supported=2, sentences=2),
                           question("q03", answerable=False, not_found=True)])]
    return old, new


def test_eval006_averages_each_item_over_its_runs_before_pairing():
    old, new = generation_runs()
    line = line_of(module().compare_runs(old, new), "EVAL-006")
    # q01: 0.5 -> 1.0, q02: 0.0 -> 0.5
    low, high = paired_bootstrap_interval([0.5, 0.0], [1.0, 0.5])
    assert "0.250 -> 0.750" in line and "(+0.500)" in line
    assert f"paired [{low:+.3f}, {high:+.3f}]" in line


def test_eval002_is_the_ratio_of_the_sums_over_every_judged_run():
    old, new = generation_runs()
    line = line_of(module().compare_runs(old, new), "EVAL-002")
    # old: q01 3 of 4, q02 0 of 1 -> 3/5; new: q01 4 of 5, q02 2 of 3 -> 6/8
    low, high = helper("paired_ratio_bootstrap_interval")([3.0, 0.0], [4.0, 1.0], [4.0, 2.0], [5.0, 3.0])
    assert "0.600 -> 0.750" in line
    assert f"paired [{low:+.3f}, {high:+.3f}]" in line


def test_eval003_keeps_an_item_judged_in_no_run_of_a_side_as_missing():
    old, new = generation_runs()
    old[0]["items"][1].update(cited_supported=None, cited_sentences=None, supported=None)  # q02 never judged in old
    line = line_of(module().compare_runs(old, new), "EVAL-003")
    # old: q01 (1 + 0.5) / 2 = 0.75, q02 none; new: q01 (1 + 1) / 2 = 1.0, q02 (1 + 1) / 2 = 1.0
    low, high = helper("paired_nanmean_bootstrap_interval")([0.75, None], [1.0, 1.0])
    assert "0.750 -> 1.000" in line
    assert f"paired [{low:+.3f}, {high:+.3f}]" in line


def test_eval004_is_paired_over_the_unanswerable_questions():
    old, new = generation_runs()
    line = line_of(module().compare_runs(old, new), "EVAL-004")
    assert "0.500 -> 1.000" in line and "(+0.500)" in line


def test_the_first_line_names_the_commits_of_each_side():
    old, new = generation_runs()
    first = module().compare_runs(old, new).splitlines()[0]
    for commit in ("aaaaaaa", "aaaaab2", "bbbbbbb", "bbbbbb2"):
        assert commit in first


def test_several_comparisons_add_the_bonferroni_interval():
    old, new = generation_runs()
    assert "bonferroni [" not in line_of(module().compare_runs(old, new), "EVAL-006")
    assert "bonferroni [" in line_of(module().compare_runs(old, new, comparisons=2), "EVAL-006")


def test_the_items_are_taken_in_the_order_of_the_first_new_file():
    old, new = generation_runs()
    reordered = [dict(results, items=list(reversed(results["items"]))) for results in new]
    values_old, values_new = [0.0, 0.5], [0.5, 1.0]  # q02 then q01
    low, high = paired_bootstrap_interval(values_old, values_new)
    assert f"paired [{low:+.3f}, {high:+.3f}]" in line_of(module().compare_runs(old, reordered), "EVAL-006")


def test_runs_on_different_eval_sets_are_refused():
    old, new = generation_runs()
    new[1]["configuration"]["eval_set"]["sha256"] = "b" * 64
    with pytest.raises(ValueError, match="different eval sets: scores are not comparable"):
        module().compare_runs(old, new)


def test_runs_of_one_side_with_different_configurations_are_refused():
    old, new = generation_runs()
    old[1]["configuration"]["pipeline"]["top_k"] = 12
    with pytest.raises(ValueError, match="the runs of one side differ in configuration"):
        module().compare_runs(old, new)


def test_runs_of_one_side_may_differ_in_their_seed():
    """Approved on #37, a seed per run: the runs of one side differ by their seeds and nothing else."""
    old, new = generation_runs()
    old[0]["configuration"]["pipeline"]["seed"] = 1
    old[1]["configuration"]["pipeline"]["seed"] = 2
    try:
        text = module().compare_runs(old, new)
    except ValueError as error:
        text = str(error)
    assert line_of(text, "EVAL-006") != "", text


# --- The command ----------------------------------------------------------------------------------

def write(tmp_path, runs, prefix):
    paths = []
    for n, results in enumerate(runs, 1):
        path = tmp_path / f"{prefix}{n}.json"
        path.write_text(json.dumps(results), encoding="utf-8")
        paths.append(str(path))
    return ",".join(paths)


def test_the_command_prints_the_comparison_and_writes_nothing(tmp_path, capsys):
    old, new = generation_runs()
    argv = ["--old", write(tmp_path, old, "old"), "--new", write(tmp_path, new, "new")]
    before = sorted(p.name for p in tmp_path.iterdir())
    assert module().main(argv) == 0
    assert "EVAL-006" in capsys.readouterr().out
    assert sorted(p.name for p in tmp_path.iterdir()) == before


def test_the_command_exits_2_on_different_eval_sets(tmp_path, capsys):
    old, new = generation_runs()
    new[0]["configuration"]["eval_set"]["sha256"] = "b" * 64
    argv = ["--old", write(tmp_path, old, "old"), "--new", write(tmp_path, new, "new")]
    assert module().main(argv) == 2
    assert "different eval sets: scores are not comparable" in capsys.readouterr().out


def test_a_metric_with_no_paired_item_is_left_out_and_nan_is_never_printed():
    old, new = retrieval_runs()
    text = module().compare_runs([old], [new])
    assert all(line_of(text, eval_id) == "" for eval_id in ("EVAL-002", "EVAL-003", "EVAL-004", "EVAL-006"))
    assert "nan" not in text.lower()
