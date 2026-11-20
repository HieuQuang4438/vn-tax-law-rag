"""Hand-check sheets for the judge of an eval run (#15): `docs/reference/eval-results.md`.

    python -m src.eval.handcheck sheet data/eval-answers/<file>.jsonl   # writes the sheet and its key
    python -m src.eval.handcheck score eval/<file>-handcheck.me.md      # prints the agreement

Both files are untracked (`*.me.md`): the sheet holds question, answer and corpus text.
"""

import argparse
import json
import random
import re
from pathlib import Path

import yaml

from src.answer.answerer import markers

SAMPLE = 20
SEED = 0
LABELS = {"Cited supports": "cited", "Context supports": "supported", "Fact": "facts", "Correct": "correct",
          "Says amended": "says_amended"}
HEADING = re.compile(r"^## ([SAM]\d+) · ")
GRADE = re.compile(r"^(Cited supports|Context supports|Correct|Says amended|Fact (\d+) stated):\s*(\S*)\s*$")
RULE = "Yes when the answer says that each of these provisions was amended, replaced or repealed."


def _key_path(sheet_path: Path) -> Path:
    return sheet_path.with_name(sheet_path.name.replace("-handcheck.me.md", "-handcheck-key.me.md"))


def _read_key(key_path: Path) -> dict:
    return json.loads(key_path.read_text(encoding="utf-8").split("```json\n", 1)[1].split("\n```", 1)[0])


def _answer_text(record: dict) -> str:
    return " ".join(s["text"] + (" " + markers(tuple(s["citations"])) if s["citations"] else "")
                    for s in record["sentences"])


def sheet(answers: Path, set_path: Path = Path("eval/questions.yaml"), out_dir: Path = Path("eval")) -> tuple[Path, Path]:
    """Write the sheet and its key; return their paths."""
    records = [json.loads(line) for line in answers.read_text(encoding="utf-8").splitlines() if line.strip()]
    questions = {q["id"]: q for q in yaml.safe_load(set_path.read_text(encoding="utf-8")).get("questions", [])}
    judged = [r for r in records if r.get("verdict")]
    sentences = [(r, n) for r in judged for n, s in enumerate(r["sentences"], 1)
                 if any(i not in set(r["flagged"]) for i in s["citations"])]
    rng = random.Random(SEED)
    chosen_sentences = rng.sample(sentences, min(SAMPLE, len(sentences)))
    chosen_answers = rng.sample(judged, min(SAMPLE, len(judged)))
    amended = [r for r in judged if r["verdict"].get("says_amended") is not None and r.get("amended")]
    chosen_amended = rng.sample(amended, min(SAMPLE, len(amended)))

    stem = answers.stem
    sheet_path, key_path = out_dir / f"{stem}-handcheck.me.md", out_dir / f"{stem}-handcheck-key.me.md"
    lines = [f"# Hand-check, {stem}", "",
             f"Write yes or no after each label. Grade before opening {key_path.name}.", ""]
    key: dict[str, dict] = {}
    for number, (record, index) in enumerate(chosen_sentences, 1):
        name, sentence = f"S{number}", record["sentences"][index - 1]
        passages = {p["id"]: p["text"] for p in record["passages"]}
        cited = [passages[i.split(".")[0]] for i in dict.fromkeys(c.split(".")[0] for c in sentence["citations"])
                 if i in passages]
        lines += [f"## {name} · {record['id']} · sentence {index}", "",
                  f"**Question.** {questions.get(record['id'], {}).get('question', '')}", "",
                  f"**Sentence.** {sentence['text']} {markers(tuple(sentence['citations']))}", "",
                  "**Cited passages.**", "", *("\n\n".join(cited).split("\n")), "",
                  "<details><summary>Context</summary>", "",
                  *("\n\n".join(passages.values()).split("\n")), "", "</details>", "",
                  "Cited supports:", "Context supports:", ""]
        key[name] = {"id": record["id"], "sentence": index, "cited": record["verdict"]["cited"][index - 1],
                     "supported": record["verdict"]["supported"][index - 1]}
    for number, record in enumerate(chosen_answers, 1):
        name = f"A{number}"
        facts = questions.get(record["id"], {}).get("key_facts", [])
        lines += [f"## {name} · {record['id']}", "",
                  f"**Question.** {questions.get(record['id'], {}).get('question', '')}", "",
                  "**Key facts.**", "", *(f"{n}. {fact}" for n, fact in enumerate(facts, 1)), "",
                  "**Answer.**", "", _answer_text(record), "",
                  *(f"Fact {n} stated:" for n in range(1, len(facts) + 1)), "Correct:", ""]
        key[name] = {"id": record["id"], "facts": list(record["verdict"]["facts"]),
                     "correct": record["verdict"]["correct"]}
    for number, record in enumerate(chosen_amended, 1):
        name = f"M{number}"
        passages = [p["text"] for p in record["passages"]]
        lines += [f"## {name} · {record['id']}", "",
                  f"**Question.** {questions.get(record['id'], {}).get('question', '')}", "",
                  "**Amended provisions.** " + ", ".join(f"[{i}]" for i in record["amended"]), "",
                  "<details><summary>Context</summary>", "", *("\n\n".join(passages).split("\n")), "", "</details>", "",
                  "**Answer.**", "", _answer_text(record), "", RULE, "", "Says amended:", ""]
        key[name] = {"id": record["id"], "says_amended": record["verdict"]["says_amended"]}

    out_dir.mkdir(parents=True, exist_ok=True)
    sheet_path.write_bytes("\n".join(lines).encode("utf-8"))
    key_path.write_bytes((f"# Hand-check key, {stem}\n\n```json\n" + json.dumps(key, ensure_ascii=False, indent=2)
                          + "\n```\n").encode("utf-8"))
    return sheet_path, key_path


def score(sheet_path: Path) -> dict[str, tuple[int, int]]:
    """Per line kind (`cited`, `supported`, `facts`, `correct`, `says_amended`): (agreeing with the judge, graded)."""
    key = _read_key(_key_path(sheet_path))
    counts = {kind: [0, 0] for kind in LABELS.values()}
    current = None
    for line in sheet_path.read_text(encoding="utf-8").splitlines():
        heading = HEADING.match(line)
        if heading:
            current = heading.group(1)
            continue
        grade = GRADE.match(line)
        if not grade or current not in key or grade.group(3).lower() not in ("yes", "no"):
            continue
        said = grade.group(3).lower() == "yes"
        if grade.group(2):  # `Fact <n> stated:` against the n-th of the judge's facts (#39)
            facts = key[current].get("facts", [])
            n = int(grade.group(2))
            if not 1 <= n <= len(facts):
                continue
            kind, judged = "facts", facts[n - 1]
        else:
            kind = LABELS[grade.group(1)]
            judged = key[current][kind]
        counts[kind][1] += 1
        counts[kind][0] += said == judged
    return {kind: (agree, graded) for kind, (agree, graded) in counts.items()}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m src.eval.handcheck", description="Hand-check the judge.")
    commands = parser.add_subparsers(dest="command", required=True)
    make = commands.add_parser("sheet", help="write the sheet and its key")
    make.add_argument("answers", help="data/eval-answers/<results file stem>.jsonl")
    make.add_argument("--set", default="eval/questions.yaml", help="the eval set")
    make.add_argument("--out", default="eval", help="where the sheet and the key are written")
    check = commands.add_parser("score", help="print the agreement of a graded sheet with the judge")
    check.add_argument("sheet", help="eval/<stem>-handcheck.me.md")
    args = parser.parse_args(argv)
    if args.command == "sheet":
        sheet_path, key_path = sheet(Path(args.answers), Path(args.set), Path(args.out))
        print(f"Sheet: {sheet_path}\nKey: {key_path}")
        return 0
    for kind, (agree, graded) in score(Path(args.sheet)).items():
        print(f"{kind}: {agree} of {graded}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
