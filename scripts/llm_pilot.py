"""LLM pilot for #13: two Gemini models answer the same eval questions from today's top 8.

Run: python scripts/llm_pilot.py
Writes eval/results/llm-pilot/<date>-<commit>.json, and a blind grading sheet
eval/llm-pilot-grading.me.md with its key eval/llm-pilot-key.me.md (both untracked).
Finished items are kept in eval/llm-pilot-progress.me.md, so a run stopped by an error resumes at the
same commit; the file is removed when the run completes.
"""

import hashlib
import json
import random
import statistics
import subprocess
import sys
import time
from datetime import datetime
from importlib.metadata import version
from pathlib import Path

import httpx2
from google import genai
from google.genai import errors, types

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.config import GOOGLE_API_KEYS  # noqa: E402
from src.eval.dataset import load_eval_set  # noqa: E402
from src.retrieval import Retriever  # noqa: E402

# gemini-3.8-flash was dropped after three runs on the free tier stalled (#13); its 3 items are in
# eval/results/llm-pilot/2026-11-16-597534e-partial.json.
MODELS = ("gemini-3.6-flash", "gemini-3.5-flash-lite")
# Paid tier, USD per 1M text tokens, output including thinking: Google AI Studio pricing page, read 2026-11-16.
PRICES = {"gemini-3.6-flash": (0.75, 3.75), "gemini-3.5-flash-lite": (0.30, 2.50)}
PRICES_2027 = {"gemini-3.6-flash": (1.50, 7.50), "gemini-3.5-flash-lite": (0.30, 2.50)}
PRICES_READ = "2026-11-16"
SEED = 0
ANSWERABLE_PER_TYPE = 3
UNANSWERABLE_PER_TYPE = 1
PAUSE_S = 10  # between requests, under the free tier's per-minute limit
WAIT_ALL_LIMITED_S = 60  # when every key is refused with 429
WAIT_UNAVAILABLE_S = 30  # after a 5xx, before the same request again
ROUNDS = 5

DATA = ROOT / "data"
PROMPT = Path(__file__).with_name("llm_pilot_prompt.md")
SET = ROOT / "eval" / "questions.yaml"
OUT = ROOT / "eval" / "results" / "llm-pilot"
SHEET = ROOT / "eval" / "llm-pilot-grading.me.md"
KEY = ROOT / "eval" / "llm-pilot-key.me.md"
PROGRESS = ROOT / "eval" / "llm-pilot-progress.me.md"


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()


def sample(questions: list) -> list:
    """`ANSWERABLE_PER_TYPE` answerable and `UNANSWERABLE_PER_TYPE` unanswerable new questions per tax type."""
    rng = random.Random(SEED)
    chosen = []
    for tax_type in sorted({q.tax_type for q in questions}):
        of_type = sorted((q for q in questions if q.tax_type == tax_type), key=lambda q: int(q.id[1:]))
        chosen += rng.sample([q for q in of_type if not q.unanswerable], ANSWERABLE_PER_TYPE)
        chosen += rng.sample([q for q in of_type if q.unanswerable], UNANSWERABLE_PER_TYPE)
    return chosen


def passages(chunk_ids: list[str]) -> str:
    wanted = set(chunk_ids)
    found = {}
    with (DATA / "enriched" / "chunks.jsonl").open(encoding="utf-8") as lines:
        for line in lines:
            chunk = json.loads(line)
            if chunk["id"] in wanted:
                found[chunk["id"]] = chunk["header"] + "\n" + chunk["text"]
    return "\n\n".join(f"[{n}] {found[chunk_id]}" for n, chunk_id in enumerate(chunk_ids, 1))


class Keys:
    """Tries the keys in order and moves to the next on a 429 (#13); waits and retries on a 5xx or a
    dropped connection."""

    def __init__(self):
        no_retry = types.HttpOptions(retry_options=types.HttpRetryOptions(attempts=1))
        self.clients = [genai.Client(api_key=key, http_options=no_retry) for key in GOOGLE_API_KEYS]
        self.current = 0
        self.refused = 0
        self.unavailable = 0

    def generate(self, model: str, system: str, user: str):
        config = types.GenerateContentConfig(system_instruction=system)
        for _ in range(ROUNDS):
            for _ in self.clients:
                try:
                    start = time.perf_counter()
                    response = self.clients[self.current].models.generate_content(
                        model=model, contents=user, config=config)
                    return response, time.perf_counter() - start
                except errors.ClientError as error:
                    if error.code != 429:
                        raise
                    self.refused += 1
                    self.current = (self.current + 1) % len(self.clients)
                except (errors.ServerError, httpx2.TransportError) as error:
                    print(f"  {model}: {type(error).__name__}, retrying", file=sys.stderr, flush=True)
                    self.unavailable += 1
                    time.sleep(WAIT_UNAVAILABLE_S)
                    break
            else:
                time.sleep(WAIT_ALL_LIMITED_S)
        raise RuntimeError(f"no answer after {ROUNDS} rounds of 429 or 5xx")


def cost(prices: tuple[float, float], prompt: int, output: int) -> float:
    return (prompt * prices[0] + output * prices[1]) / 1_000_000


def answer(keys: Keys, model: str, system: str, user: str) -> dict:
    refused, unavailable = keys.refused, keys.unavailable
    response, seconds = keys.generate(model, system, user)
    usage = response.usage_metadata
    prompt = usage.prompt_token_count or 0
    output = (usage.candidates_token_count or 0) + (usage.thoughts_token_count or 0)
    candidate = response.candidates[0] if response.candidates else None
    return {
        "answer": response.text,
        "finish_reason": str(candidate.finish_reason) if candidate else None,
        "prompt_tokens": prompt,
        "answer_tokens": usage.candidates_token_count or 0,
        "thinking_tokens": usage.thoughts_token_count or 0,
        "latency_s": round(seconds, 3),
        "cost_usd": cost(PRICES[model], prompt, output),
        "cost_usd_2027": cost(PRICES_2027[model], prompt, output),
        "refused_429": keys.refused - refused,
        "unavailable_5xx": keys.unavailable - unavailable,
    }


def summary(items: list[dict], model: str) -> dict:
    runs = [item["models"][model] for item in items]
    latency = sorted(run["latency_s"] for run in runs)
    return {
        "n": len(runs),
        "latency_median_s": statistics.median(latency),
        "latency_p95_s": latency[min(len(latency) - 1, int(0.95 * len(latency)))],
        "prompt_tokens_mean": statistics.mean(run["prompt_tokens"] for run in runs),
        "output_tokens_mean": statistics.mean(run["answer_tokens"] + run["thinking_tokens"] for run in runs),
        "cost_usd_mean": statistics.mean(run["cost_usd"] for run in runs),
        "cost_usd_max": max(run["cost_usd"] for run in runs),
        "cost_usd_2027_mean": statistics.mean(run["cost_usd_2027"] for run in runs),
        "refused_429": sum(run["refused_429"] for run in runs),
        "unavailable_5xx": sum(run["unavailable_5xx"] for run in runs),
    }


def write_sheet(items: list[dict], questions: dict) -> None:
    rng = random.Random(SEED)
    key, lines = {}, ["# LLM pilot, blind grading (#13)", "",
                      "Per answer: correct / partial / wrong against the expected answer and key facts;",
                      "cites a passage (yes/no); for an unanswerable question, says not found (yes/no).", ""]
    for item in items:
        labels = dict(zip("XY", rng.sample(MODELS, 2)))
        key[item["id"]] = labels
        question = questions[item["id"]]
        lines += [f"## {item['id']} ({item['tax_type']}{', unanswerable' if question.unanswerable else ''})", "",
                  f"**Question.** {question.question}", "", f"**Expected.** {question.answer}", ""]
        lines += [f"- {fact}" for fact in question.key_facts] + [""]
        for label, model in labels.items():
            lines += [f"### {label}", "", item["models"][model]["answer"] or "(no text)", "",
                      f"Grade {label}: ", ""]
    SHEET.write_bytes("\n".join(lines).encode("utf-8"))
    KEY.write_bytes(("```json\n" + json.dumps(key, indent=2) + "\n```\n").encode("utf-8"))


def main() -> None:
    commit = git("rev-parse", "--short=7", "HEAD")
    eval_set = load_eval_set(SET, DATA / "processed", DATA / "enriched")
    chosen = sample([q for q in eval_set.questions if q.added_in == 2])
    retriever = Retriever.load(DATA)
    system = PROMPT.read_text(encoding="utf-8")
    keys = Keys()
    done = json.loads(PROGRESS.read_text(encoding="utf-8")) if PROGRESS.exists() else {"commit": commit, "items": []}
    if done["commit"] != commit:
        raise SystemExit(f"{PROGRESS.name} is from commit {done['commit']}; remove it to start again")
    items = done["items"]
    resumed = len(items)
    for question in chosen[resumed:]:
        hits = [hit.chunk_id for hit in retriever.retrieve(question.question).hits]
        user = f"Passages:\n\n{passages(hits)}\n\nQuestion: {question.question}"
        item = {"id": question.id, "tax_type": question.tax_type, "unanswerable": question.unanswerable,
                "hits": hits, "models": {}}
        for model in MODELS:
            item["models"][model] = answer(keys, model, system, user)
            time.sleep(PAUSE_S)
        items.append(item)
        PROGRESS.write_bytes(json.dumps(done, ensure_ascii=False).encode("utf-8"))
        print(f"{question.id} done", flush=True)
    started = datetime.now().astimezone()
    results = {
        "configuration": {
            "commit": git("rev-parse", "HEAD"),
            "dirty": bool(git("diff", "HEAD")),
            "eval_set": {"version": eval_set.version, "sha256": eval_set.sha256},
            "sample": {"seed": SEED, "answerable_per_tax_type": ANSWERABLE_PER_TYPE,
                       "unanswerable_per_tax_type": UNANSWERABLE_PER_TYPE, "ids": [q.id for q in chosen]},
            "retrieval": "Retriever.load(data), default Fusion(), top 8",
            "prompt_sha256": hashlib.sha256(PROMPT.read_bytes()).hexdigest(),
            "models": list(MODELS),
            "generation": "default GenerateContentConfig, system instruction only",
            "prices_usd_per_mtok": {"read": PRICES_READ, "2026": PRICES, "from_2027": PRICES_2027},
            "keys": len(GOOGLE_API_KEYS),
            "pause_s": PAUSE_S,
            "resumed_after_items": resumed,
            "google_genai": version("google-genai"),
            "finished": started.isoformat(timespec="seconds"),
        },
        "summary": {model: summary(items, model) for model in MODELS},
        "items": items,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"{started:%Y-%m-%d}-{commit}.json"
    path.write_bytes((json.dumps(results, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    write_sheet(items, {q.id: q for q in chosen})
    PROGRESS.unlink(missing_ok=True)
    print(f"Results: {path.relative_to(ROOT)}")
    for model, numbers in results["summary"].items():
        print(f"  {model}: {json.dumps(numbers)}")


if __name__ == "__main__":
    main()
