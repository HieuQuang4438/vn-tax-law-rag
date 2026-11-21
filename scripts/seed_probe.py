"""Does a seed make the answer model repeat itself? (#37, step 2A.)

Sends one stored request, the answer prompt with one item's passages and question, 5 times with a
fixed seed and 5 times without, and prints how many distinct replies each set gave. The request is
rebuilt from the answers file as `src.answer` builds it, so no retrieval runs. Prints ids and
counts only, never the question or the reply.

    python scripts/seed_probe.py eval/results/2026-11-19-69f6ab4.json [--seed 37] [--calls 5]
"""

import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.answer.answerer import PROMPT, AnswerOutput  # noqa: E402
from src.eval.dataset import load_eval_set  # noqa: E402
from src.llm import LLM  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python scripts/seed_probe.py")
    parser.add_argument("results", help="a --generate results file; its answers file must exist")
    parser.add_argument("--set", default="eval/questions.yaml")
    parser.add_argument("--data", default="data")
    parser.add_argument("--seed", type=int, default=37)
    parser.add_argument("--calls", type=int, default=5)
    args = parser.parse_args(argv)
    results_path, data = Path(args.results), Path(args.data)
    items = json.loads(results_path.read_text(encoding="utf-8"))["items"]
    records = {r["id"]: r for r in map(json.loads, (data / "eval-answers" / f"{results_path.stem}.jsonl")
                                       .read_text(encoding="utf-8").splitlines())}
    # the first answerable standalone question with every expected article retrieved and an answer
    chosen = next(i for i in items if i["kind"] == "question" and i["answerable"] and i["recall"] == 1
                  and not i["not_found"] and i["id"] in records)
    question = {q.id: q for q in load_eval_set(Path(args.set), data / "processed", data / "enriched").questions}[
        chosen["id"]].question
    context = "\n\n".join(p["text"] for p in records[chosen["id"]]["passages"])
    system, user = PROMPT.read_text(encoding="utf-8"), f"Passages:\n\n{context}\n\nQuestion: {question}"
    print(f"Item {chosen['id']}, {args.calls} calls each")
    for label, seed in (("seeded", args.seed), ("unseeded", None)):
        llm = LLM(seed=seed)
        replies = []
        for _ in range(args.calls):
            call = llm.generate("answer", system, user, AnswerOutput)
            replies.append(hashlib.sha256(call.parsed.model_dump_json().encode("utf-8")).hexdigest())
        print(f"  {label} (seed {seed}): {len(set(replies))} distinct replies of {len(replies)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
