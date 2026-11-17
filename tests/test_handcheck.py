"""Hand-check of the judge: at least 20 claims and 20 judgments per run (acceptance.md).
Approach approved on #15. The rules are `docs/reference/eval-results.md`, *Generation stage*.
"""

import json
import re
from pathlib import Path

import pytest
import yaml

from src.eval.handcheck import main, score, sheet

SECTION = re.compile(r"^## ([SAM]\d+) · (q\d+)(?: · sentence (\d+))?$", re.MULTILINE)
RULE = "Yes when the answer says that each of these provisions was amended, replaced or repealed."


def record(n: int, judged: bool = True, amended: bool | None = None) -> dict:
    """An answers-file record; `amended` None writes a record from before #15's choice 1, with no `amended` key."""
    extra = {} if amended is None else {"amended": ["1.25", "2"] if amended else []}
    return {"id": f"q{n:02d}",
            "passages": [{"id": "1", "text": f"[1] Đoạn một của câu {n}."}, {"id": "2", "text": f"[2] Đoạn hai {n}."}],
            "sentences": [{"text": f"Câu {n}-1.", "citations": ["1"]}, {"text": f"Câu {n}-2.", "citations": ["2", "9"]},
                          {"text": f"Câu {n}-3.", "citations": ["9"]}, {"text": f"Câu {n}-4.", "citations": []}],
            "flagged": ["9"], "not_found": False, **extra,
            "verdict": {"cited": [True, n % 2 == 0, False, None], "supported": [True, True, False, n % 3 == 0],
                        "facts": [True], "contradicts": False, "says_amended": n % 4 == 0 if amended else None,
                        "correct": n % 2 == 1}
            if judged else None}


def write(tmp_path: Path, records: list[dict]) -> tuple[Path, Path]:
    answers = tmp_path / "data" / "eval-answers" / "2026-11-20-abcdef0.jsonl"
    answers.parent.mkdir(parents=True)
    answers.write_bytes("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records).encode("utf-8"))
    questions = [{"id": r["id"], "question": f"Câu hỏi {r['id']}?", "key_facts": [f"Sự kiện của {r['id']}."]}
                 for r in records]
    set_path = tmp_path / "questions.yaml"
    set_path.write_text(yaml.safe_dump({"version": 2, "questions": questions}, allow_unicode=True), encoding="utf-8")
    return answers, set_path


def text_of(path: Path) -> str:
    assert path.exists(), f"{path.name} not written"
    return path.read_text(encoding="utf-8")


def sections(text: str) -> list[tuple[str, str, str | None]]:
    return SECTION.findall(text)


def test_the_sheet_and_its_key_are_named_after_the_answers_file(tmp_path):
    answers, set_path = write(tmp_path, [record(n) for n in range(1, 26)])
    sheet_path, key_path = sheet(answers, set_path, tmp_path / "eval")
    assert sheet_path == tmp_path / "eval" / "2026-11-20-abcdef0-handcheck.me.md"
    assert key_path == tmp_path / "eval" / "2026-11-20-abcdef0-handcheck-key.me.md"
    assert sheet_path.exists() and key_path.exists()


def test_the_sheet_samples_20_sentences_and_20_answers(tmp_path):
    answers, set_path = write(tmp_path, [record(n) for n in range(1, 26)] + [record(26, judged=False)])
    sheet_path, _ = sheet(answers, set_path, tmp_path / "eval")
    found = sections(text_of(sheet_path))
    assert [s[0] for s in found if s[0].startswith("S")] == [f"S{n}" for n in range(1, 21)]
    assert [s[0] for s in found if s[0].startswith("A")] == [f"A{n}" for n in range(1, 21)]
    assert all(question != "q26" for _, question, _ in found)  # not judged


def test_only_sentences_with_an_id_in_the_context_are_sampled(tmp_path):
    answers, set_path = write(tmp_path, [record(n) for n in range(1, 4)])
    sheet_path, _ = sheet(answers, set_path, tmp_path / "eval")
    found = sections(text_of(sheet_path))
    sentences = sorted((question, int(number)) for kind, question, number in found if kind.startswith("S"))
    assert sentences == [(f"q0{n}", i) for n in range(1, 4) for i in (1, 2)]  # all of them, fewer than 20
    assert len([s for s in found if s[0].startswith("A")]) == 3


def test_the_sheet_shows_what_to_grade_and_no_verdict(tmp_path):
    answers, set_path = write(tmp_path, [record(n) for n in range(1, 4)])
    sheet_path, key_path = sheet(answers, set_path, tmp_path / "eval")
    text = text_of(sheet_path)
    assert "Câu hỏi q01?" in text and "Sự kiện của q01." in text and "[1] Đoạn một của câu 1." in text
    lines = text.splitlines()
    assert lines.count("Cited supports:") == 6 and lines.count("Context supports:") == 6
    assert lines.count("Correct:") == 3
    assert "true" not in text.lower() and "false" not in text.lower()
    key = json.loads(text_of(key_path).split("```json\n", 1)[1].split("\n```", 1)[0])
    assert sorted(key) == sorted([f"S{n}" for n in range(1, 7)] + ["A1", "A2", "A3"])
    s = next(entry for entry in key.values() if entry.get("id") == "q02" and entry.get("sentence") == 2)
    assert (s["cited"], s["supported"]) == (True, True)
    a = next(entry for name, entry in key.items() if name.startswith("A") and entry["id"] == "q02")
    assert a["correct"] is False


def test_the_sheet_is_the_same_every_time(tmp_path):
    answers, set_path = write(tmp_path, [record(n) for n in range(1, 26)])
    first = text_of(sheet(answers, set_path, tmp_path / "one")[0])
    assert first == text_of(sheet(answers, set_path, tmp_path / "two")[0])


def grade(sheet_path: Path, key_path: Path, wrong: set[str], blank: set[str]) -> None:
    """Fill the sheet from the key, inverting the sections in `wrong` and leaving `blank` empty."""
    key = json.loads(text_of(key_path).split("```json\n", 1)[1].split("\n```", 1)[0])
    lines, current = [], None
    for line in text_of(sheet_path).splitlines():
        heading = SECTION.match(line)
        if heading:
            current = heading.group(1)
        for label, field in (("Cited supports:", "cited"), ("Context supports:", "supported"), ("Correct:", "correct"),
                             ("Says amended:", "says_amended")):
            if line == label and current not in blank:
                value = key[current][field] != (current in wrong)
                line = f"{label} {'yes' if value else 'NO'}"
        lines.append(line)
    sheet_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_score_counts_agreement_per_kind_and_skips_blanks(tmp_path):
    answers, set_path = write(tmp_path, [record(n) for n in range(1, 26)])
    sheet_path, key_path = sheet(answers, set_path, tmp_path / "eval")
    grade(sheet_path, key_path, wrong={"S1", "A2"}, blank={"S3", "A4", "A5"})
    assert score(sheet_path) == {"cited": (18, 19), "supported": (18, 19), "correct": (17, 18),
                                 "says_amended": (0, 0)}


def test_the_command_writes_the_sheet_and_prints_the_agreement(tmp_path, capsys):
    answers, set_path = write(tmp_path, [record(n) for n in range(1, 26)])
    out = tmp_path / "eval"
    assert main(["sheet", str(answers), "--set", str(set_path), "--out", str(out)]) == 0
    sheet_path = out / "2026-11-20-abcdef0-handcheck.me.md"
    assert sheet_path.exists()
    grade(sheet_path, out / "2026-11-20-abcdef0-handcheck-key.me.md", wrong=set(), blank=set())
    capsys.readouterr()
    assert main(["score", str(sheet_path)]) == 0
    printed = capsys.readouterr().out
    for line in ("cited: 20 of 20", "supported: 20 of 20", "correct: 20 of 20", "says_amended: 0 of 0"):
        assert line in printed


# --- says_amended (AC-015, choice 4 on #15) ------------------------------------------------------

def test_the_sheet_samples_20_answers_graded_on_says_amended(tmp_path):
    records = ([record(n, amended=True) for n in range(1, 26)] + [record(26, amended=False)]
               + [record(27, judged=False, amended=True)])
    answers, set_path = write(tmp_path, records)
    sheet_path, _ = sheet(answers, set_path, tmp_path / "eval")
    found = sections(text_of(sheet_path))
    graded = [(kind, question) for kind, question, _ in found if kind.startswith("M")]
    assert [kind for kind, _ in graded] == [f"M{n}" for n in range(1, 21)]
    assert not {"q26", "q27"} & {question for _, question in graded}  # nothing asked, or not judged


def test_the_says_amended_sample_leaves_the_other_samples_unchanged(tmp_path):
    before = sections(text_of(sheet(*write(tmp_path / "old", [record(n) for n in range(1, 26)]), tmp_path / "a")[0]))
    after = sections(text_of(sheet(*write(tmp_path / "new", [record(n, amended=True) for n in range(1, 26)]),
                                   tmp_path / "b")[0]))
    assert [s for s in after if not s[0].startswith("M")] == before


def test_a_says_amended_section_shows_the_ids_the_context_and_the_answer(tmp_path):
    answers, set_path = write(tmp_path, [record(n, amended=n == 2) for n in range(1, 4)])
    sheet_path, key_path = sheet(answers, set_path, tmp_path / "eval")
    text = text_of(sheet_path)
    assert "## M1 · q02" in text
    section = text.split("## M1 · q02", 1)[1]
    assert "Câu hỏi q02?" in section
    assert "**Amended provisions.** [1.25], [2]" in section
    assert "[2] Đoạn hai 2." in section and "Câu 2-1. [1]" in section
    lines = section.splitlines()
    assert lines.count(RULE) == 1 and lines.count("Says amended:") == 1
    assert sum(1 for kind, _, _ in sections(text) if kind.startswith("M")) == 1
    assert "true" not in text.lower() and "false" not in text.lower()
    key = json.loads(text_of(key_path).split("```json\n", 1)[1].split("\n```", 1)[0])
    assert key["M1"] == {"id": "q02", "says_amended": False}


def test_score_counts_agreement_on_says_amended(tmp_path):
    answers, set_path = write(tmp_path, [record(n, amended=True) for n in range(1, 26)])
    sheet_path, key_path = sheet(answers, set_path, tmp_path / "eval")
    grade(sheet_path, key_path, wrong={"M1"}, blank={"M2"})
    assert score(sheet_path).get("says_amended") == (18, 19)
