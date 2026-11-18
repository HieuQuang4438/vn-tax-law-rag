"""NFR-005: one command rebuilds the index from the cached pages. Approved on #6.

The steps are specified in `docs/reference/index.md` ("Rebuilding from the cached pages").
`subprocess.run` is replaced, so no step really runs.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import rebuild  # noqa: E402

PARSE = [sys.executable, "scripts/crawl_index.py"]
CHUNK = [sys.executable, "-m", "src.chunking"]
ENRICH = [sys.executable, "-m", "src.enrich"]
INDEX = [sys.executable, "-m", "src.index"]


def write_parse_report(root: Path, statuses: dict[str, str]) -> None:
    out = root / "data" / "processed"
    out.mkdir(parents=True, exist_ok=True)
    documents = [{"doc_id": doc_id, "url": f"https://luatvietnam.vn/thue/van-ban-{doc_id}-d1.html", "status": status}
                 for doc_id, status in statuses.items()]
    (out / "_index.json").write_text(json.dumps({"documents": documents}), encoding="utf-8")


@pytest.fixture
def steps(tmp_path, monkeypatch):
    """Records each command run; the parse step writes its report, every step exits 0 unless set."""
    calls, codes, statuses = [], {}, {"379409": "ok", "434729": "ok"}

    def run(command, cwd=None, **kwargs):
        calls.append((list(command), Path(cwd) if cwd else None))
        if list(command) == PARSE:
            write_parse_report(tmp_path, statuses)
        return subprocess.CompletedProcess(command, codes.get(tuple(command), 0))

    monkeypatch.setattr(rebuild.subprocess, "run", run)
    return calls, codes, statuses


def test_runs_parse_chunk_enrich_and_index_in_order_from_the_repository_root(tmp_path, steps):
    calls, _, _ = steps
    assert rebuild.main(tmp_path) == 0
    assert calls == [(PARSE, tmp_path), (CHUNK, tmp_path), (ENRICH, tmp_path), (INDEX, tmp_path)]


def test_a_failing_step_stops_the_run_with_its_exit_code(tmp_path, steps):
    calls, codes, _ = steps
    codes[tuple(CHUNK)] = 3
    assert rebuild.main(tmp_path) == 3
    assert [command for command, _ in calls] == [PARSE, CHUNK]


def test_a_document_that_failed_to_parse_stops_the_run_before_chunking(tmp_path, steps, capsys):
    calls, _, statuses = steps
    statuses["434729"] = "error"
    assert rebuild.main(tmp_path) == 1
    assert [command for command, _ in calls] == [PARSE]
    assert "434729" in capsys.readouterr().out
