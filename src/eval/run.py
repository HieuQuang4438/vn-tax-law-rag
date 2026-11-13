"""Run the eval set through the pipeline and write a results file (#9, FR-CORE-015).

Format and rules: `docs/reference/eval-results.md`. Interface stub: not implemented yet.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from src.eval.dataset import EvalSet
from src.retrieval import TOP_K, Hit, Unresolved

TARGETS = {"EVAL-001": 0.80, "EVAL-002": 0.90, "EVAL-003": 0.90, "EVAL-004": 0.80,
           "EVAL-005": 0.70, "EVAL-006": 0.80, "EVAL-007": 0.60, "EVAL-008": None}
NOT_RUN = "no generation stage"


@dataclass
class Outcome:
    hits: list[Hit]
    unresolved: list[Unresolved] = field(default_factory=list)
    latency: dict[str, float] = field(default_factory=dict)  # seconds per stage
    tokens: dict[str, int] = field(default_factory=lambda: {"input": 0, "output": 0})
    cost_usd: float = 0.0


class Pipeline(Protocol):
    config: dict  # recorded under configuration.pipeline

    def answer(self, question: str) -> Outcome:
        ...


class RetrievalPipeline:
    def __init__(self, retriever, k: int = TOP_K):
        self.config = {}

    def answer(self, question: str) -> Outcome:
        return Outcome(hits=[])


def evaluate(eval_set: EvalSet, pipeline: Pipeline, parents: dict[str, str], k: int = TOP_K) -> dict:
    """scores, breakdown, latency, cost and items for one run."""
    return {}


def configuration(eval_set: EvalSet, set_path: Path, index_dir: Path, pipeline_config: dict,
                  root: Path = Path(".")) -> dict:
    return {}


def write_results(results: dict, out_dir: Path) -> Path:
    return out_dir / "results.json"


def summary(results: dict, path: Path) -> str:
    return ""


def compare(old: dict, new: dict) -> str:
    return ""


def main(argv: list[str] | None = None, pipeline: Pipeline | None = None) -> int:
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
