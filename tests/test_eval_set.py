"""The eval set's format and checks (#7). Approach approved on #7.

The format, the rules and the messages are `docs/reference/eval-set.md`. Unit tests check sets
written to a temporary folder against a small corpus in the shape of `data/processed/` and
`data/enriched/chunks.jsonl`. The corpus test at the end checks the real `eval/questions.yaml`
against the local corpus (gitignored): `pytest -m corpus`.
"""

import hashlib
import json
from datetime import date
from pathlib import Path

import pytest
import yaml

from src.eval.check import check, main
from src.eval.dataset import TAX_TYPES, EvalSetError, load_eval_set

ROOT = Path(__file__).resolve().parent.parent

DOCUMENTS = {"379409": "48/2024/QH15", "421739": "149/2025/QH15"}
CHUNKS = [
    # Article 5 of the VAT Law is split; clause 25 is amended by Article 1 of Law 149/2025.
    ("379409:D5:K1", "379409:D5", []),
    ("379409:D5:K25", "379409:D5", [{"type": "amends", "source": "421739:D1"}]),
    ("379409:D9", "379409:D9", []),
    ("421739:D1", "421739:D1", []),
    ("421739:D2", "421739:D2", []),
]
CORPUS_MD = """# Corpus

## Amendments from outside the corpus

| Amended | Provisions | Amended by |
|---|---|---|
| 379409 (Law 48/2024) | point a, clause 1, Article 9 | Law 90/2025/QH15, Article 4 |
| 404357 (Decree 181/2025) | Annex III | Decree 273/2026/NĐ-CP |
| 421739 (Law 149/2025) | points g and n of clause 1, Articles 2 and 7 | Law 15/2026/QH16, Article 2 clause 2 |

Adding these documents to the corpus would let the links be read.
"""


@pytest.fixture
def corpus(tmp_path) -> tuple[Path, Path, Path]:
    processed, enriched = tmp_path / "processed", tmp_path / "enriched"
    processed.mkdir()
    enriched.mkdir()
    for doc_id, number in DOCUMENTS.items():
        doc = {"source_url": f"https://luatvietnam.vn/thue/van-ban-{doc_id}-d1.html",
               "metadata": {"so_hieu": number}, "blocks": []}
        (processed / f"van-ban-{doc_id}-d1.json").write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    (processed / "_index.json").write_text(json.dumps({"documents": []}), encoding="utf-8")
    with (enriched / "chunks.jsonl").open("w", encoding="utf-8", newline="\n") as f:
        for chunk_id, parent, amended_by in CHUNKS:
            doc_id, article, *clause = chunk_id.split(":")
            f.write(json.dumps({"id": chunk_id, "doc_id": doc_id, "article": article[1:],
                                "clause": clause[0][1:] if clause else None, "parent_id": parent,
                                "amended_by": amended_by}) + "\n")
    corpus_md = tmp_path / "corpus.md"
    corpus_md.write_text(CORPUS_MD, encoding="utf-8")
    return processed, enriched, corpus_md


def answerable(n: int, tax_type: str = "vat", form: str = "plain",
               provisions: tuple[str, ...] = ("48/2024/QH15 Điều 5 khoản 1",)) -> dict:
    question = "Điều 5 Luật 48/2024/QH15 quy định gì?" if form == "reference" else "Đối tượng nào phải nộp thuế?"
    return {"id": f"q{n:02d}", "question": question, "tax_type": tax_type, "form": form,
            "answer": "Câu trả lời mong đợi.", "key_facts": ["một sự kiện"], "provisions": list(provisions)}


def unanswerable(n: int, tax_type: str = "vat") -> dict:
    return {"id": f"q{n:02d}", "question": "Thuế sử dụng đất phi nông nghiệp là bao nhiêu?", "tax_type": tax_type,
            "form": "plain", "answer": "Các văn bản không quy định nội dung này.", "unanswerable": "out_of_scope"}


def turn(form: str = "plain") -> dict:
    item = answerable(0, form=form)
    del item["id"]
    return item


def valid_set() -> dict:
    """30 questions, 6 unanswerable (20%), every tax type and both forms, 5 two-turn conversations."""
    questions = [answerable(n, tax_type=TAX_TYPES[n % len(TAX_TYPES)], form=("plain", "reference")[n % 2])
                 for n in range(1, 25)]
    questions += [unanswerable(n) for n in range(25, 31)]
    conversations = [{"id": f"c{n:02d}", "turns": [turn(), turn()]} for n in range(1, 6)]
    return {"version": 1, "as_of": date(2026, 11, 12), "questions": questions, "conversations": conversations}


def write(tmp_path: Path, data: dict) -> Path:
    path = tmp_path / "questions.yaml"
    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return path


def run(tmp_path, corpus, data: dict):
    return check(write(tmp_path, data), *corpus)


def item(data: dict, item_id: str) -> dict:
    return next(q for q in data["questions"] if q["id"] == item_id)


def line_of(path: Path, item_id: str) -> int:
    for n, text in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if text.strip() == f"- id: {item_id}":
            return n
    raise AssertionError(f"{item_id} not in the file")


def has(messages: list[str], *parts: str) -> bool:
    return any(all(part in message for part in parts) for message in messages)


# --- A valid set ----------------------------------------------------------------------------


def test_a_valid_set_has_no_errors_and_no_warnings(tmp_path, corpus):
    report = run(tmp_path, corpus, valid_set())
    assert (report.errors, report.warnings) == ([], [])


def test_the_command_exits_0_on_a_valid_set_and_1_on_errors(tmp_path, corpus):
    processed, enriched, corpus_md = corpus
    options = {"processed_dir": processed, "enriched_dir": enriched, "corpus_md": corpus_md}
    assert main([str(write(tmp_path, valid_set()))], **options) == 0
    broken = valid_set()
    broken["questions"].pop()
    assert main([str(write(tmp_path, broken))], **options) == 1


# --- Provisions -----------------------------------------------------------------------------


def test_provisions_resolve_to_their_article_and_chunk(tmp_path, corpus):
    data = valid_set()
    item(data, "q01")["provisions"] = ["48/2024/QH15 Điều 5 khoản 25", "149/2025/QH15 Điều 1",
                                       "48/2024/qh15 Điều 9 khoản 2"]
    path = write(tmp_path, data)
    loaded = load_eval_set(path, *corpus[:2])
    q01 = next((q for q in loaded.questions if q.id == "q01"), None)
    assert q01 is not None, "q01 not loaded"
    assert [(p.article, p.chunk) for p in q01.provisions] == [
        ("379409:D5", "379409:D5:K25"),  # clause of a split article: its clause chunk
        ("421739:D1", "421739:D1"),
        ("379409:D9", "379409:D9"),  # clause of an unsplit article: the article chunk; number in any case
    ]
    assert loaded.version == 1
    assert loaded.as_of == date(2026, 11, 12)
    assert loaded.sha256 == hashlib.sha256(path.read_bytes()).hexdigest()


def test_turns_are_numbered_after_their_conversation(tmp_path, corpus):
    loaded = load_eval_set(write(tmp_path, valid_set()), *corpus[:2])
    assert len(loaded.conversations) == 5
    assert [t.id for t in loaded.conversations[0].turns] == ["c01.1", "c01.2"]
    assert len(loaded.questions) == 30


def test_loading_a_set_with_errors_raises_with_the_checkers_messages(tmp_path, corpus):
    data = valid_set()
    item(data, "q01")["tax_type"] = "gtgt"
    with pytest.raises(EvalSetError) as error:
        load_eval_set(write(tmp_path, data), *corpus[:2])
    assert has(error.value.errors, "q01", 'tax_type "gtgt"')


def edit(field: str, value):
    def apply(q: dict) -> None:
        if value is None:
            del q[field]
        else:
            q[field] = value
    return apply


@pytest.mark.parametrize("target, change, message", [
    ("q03", edit("question", None), 'missing field "question"'),
    ("q03", edit("provision", ["48/2024/QH15 Điều 5"]), 'unknown field "provision"'),
    ("q03", edit("tax_type", "gtgt"), 'tax_type "gtgt"'),
    ("q03", edit("form", "ref"), 'form "ref"'),
    ("q25", edit("unanswerable", "unknown"), 'unanswerable "unknown"'),
    ("q03", edit("provisions", []), "no provisions"),
    ("q03", edit("key_facts", []), "key_facts: 1 to 4"),
    ("q03", edit("key_facts", ["a", "b", "c", "d", "e"]), "key_facts: 1 to 4"),
    ("q25", edit("provisions", ["48/2024/QH15 Điều 9"]), "unanswerable but has provisions"),
    ("q25", edit("key_facts", ["a"]), "unanswerable but has key_facts"),
    ("q03", edit("provisions", ["Điều 5 Luật 48/2024"]), 'cannot read provision "Điều 5 Luật 48/2024"'),
    ("q03", edit("provisions", ["99/2099/QH15 Điều 1"]), 'unknown document "99/2099/QH15"'),
    ("q03", edit("provisions", ["48/2024/QH15 Điều 99"]), "no Điều 99 in 48/2024/QH15"),
    ("q03", edit("provisions", ["48/2024/QH15 Điều 5 khoản 7"]), "no khoản 7 in Điều 5 of 48/2024/QH15"),
])
def test_question_errors(tmp_path, corpus, target, change, message):
    data = valid_set()
    change(item(data, target))
    path = write(tmp_path, data)
    report = check(path, *corpus)
    assert has(report.errors, f"line {line_of(path, target)}: {target}: ", message), report.errors


def test_a_duplicate_id_is_an_error(tmp_path, corpus):
    data = valid_set()
    item(data, "q04")["id"] = "q03"
    assert has(run(tmp_path, corpus, data).errors, 'duplicate id "q03"')


def test_an_error_in_a_turn_names_the_turn(tmp_path, corpus):
    data = valid_set()
    data["conversations"][0]["turns"][1]["form"] = "ref"
    assert has(run(tmp_path, corpus, data).errors, "c01.2: ", 'form "ref"')


# --- The set as a whole ---------------------------------------------------------------------


def without(data: dict, *ids: str) -> dict:
    data["questions"] = [q for q in data["questions"] if q["id"] not in ids]
    return data


def test_too_few_questions(tmp_path, corpus):
    data = valid_set()
    data["questions"].append(unanswerable(31))
    data = without(data, "q01", "q02")
    assert has(run(tmp_path, corpus, data).errors, "30 to 50 questions, found 29")


def test_too_many_questions(tmp_path, corpus):
    data = valid_set()
    data["questions"] += [answerable(n) for n in range(31, 41)] + [unanswerable(n) for n in range(41, 52)]
    assert has(run(tmp_path, corpus, data).errors, "30 to 50 questions, found 51")


def test_too_few_unanswerable_questions(tmp_path, corpus):
    data = valid_set()
    item(data, "q30").update(answerable(30))
    assert has(run(tmp_path, corpus, data).errors, "unanswerable share 0.17 is below 0.20")


def test_a_tax_type_with_no_question(tmp_path, corpus):
    data = valid_set()
    for q in data["questions"]:
        if q["tax_type"] == "sct":
            q["tax_type"] = "vat"
    assert has(run(tmp_path, corpus, data).errors, 'no question with tax_type "sct"')


def test_a_form_with_no_question(tmp_path, corpus):
    data = valid_set()
    for q in data["questions"]:
        q["form"] = "plain"
        q["question"] = "Đối tượng nào phải nộp thuế?"
    assert has(run(tmp_path, corpus, data).errors, 'no question with form "reference"')


def test_too_few_conversations(tmp_path, corpus):
    data = valid_set()
    data["conversations"].pop()
    assert has(run(tmp_path, corpus, data).errors, "at least 5 conversations, found 4")


@pytest.mark.parametrize("turns", [1, 4])
def test_a_conversation_needs_2_to_3_turns(tmp_path, corpus, turns):
    data = valid_set()
    data["conversations"][1]["turns"] = [turn() for _ in range(turns)]
    assert has(run(tmp_path, corpus, data).errors, "c02", "2 to 3 turns")


@pytest.mark.parametrize("field, value", [("version", 0), ("version", "one"), ("as_of", "soon")])
def test_version_and_date(tmp_path, corpus, field, value):
    data = valid_set()
    data[field] = value
    assert has(run(tmp_path, corpus, data).errors, field)


# --- Warnings -------------------------------------------------------------------------------


def test_an_amended_provision_without_its_amending_provision_is_warned(tmp_path, corpus):
    data = valid_set()
    item(data, "q01")["provisions"] = ["48/2024/QH15 Điều 5 khoản 25"]
    item(data, "q03")["provisions"] = ["48/2024/QH15 Điều 5"]  # the whole article holds clause 25
    report = run(tmp_path, corpus, data)
    assert report.errors == []
    assert has(report.warnings, "q01: ", "amended by 421739:D1, which is not listed")
    assert has(report.warnings, "q03: ", "amended by 421739:D1, which is not listed")


def test_an_amended_provision_listed_with_its_amending_provision_is_not_warned(tmp_path, corpus):
    data = valid_set()
    item(data, "q01")["provisions"] = ["48/2024/QH15 Điều 5 khoản 25", "149/2025/QH15 Điều 1"]
    assert run(tmp_path, corpus, data).warnings == []


@pytest.mark.parametrize("provision", ["48/2024/QH15 Điều 9", "149/2025/QH15 Điều 2"])
def test_a_provision_amended_from_outside_the_corpus_is_warned(tmp_path, corpus, provision):
    data = valid_set()
    item(data, "q01")["provisions"] = [provision]
    report = run(tmp_path, corpus, data)
    assert report.errors == []
    assert has(report.warnings, "q01: ", "amended from outside the corpus")


def test_a_reference_question_that_names_no_provision_is_warned(tmp_path, corpus):
    data = valid_set()
    item(data, "q02")["question"] = "Đối tượng nào phải nộp thuế?"  # q02 is a reference question
    item(data, "q04")["question"] = "Luật 48/2024/QH15 áp dụng cho ai?"  # a document number is enough
    warnings = run(tmp_path, corpus, data).warnings
    assert has(warnings, "q02: ", "form reference but names no provision")
    assert not has(warnings, "q04: ")


# --- The real set (Done when on #7) -----------------------------------------------------------


@pytest.mark.corpus
def test_the_eval_set_checks_clean_against_the_corpus():
    report = check(ROOT / "eval" / "questions.yaml", ROOT / "data" / "processed", ROOT / "data" / "enriched",
                   ROOT / "docs" / "reference" / "corpus.md")
    assert report.errors == []

