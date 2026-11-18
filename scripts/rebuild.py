"""Rebuild everything from the pages cached in data/raw/: parse, chunk, enrich, index (NFR-005).

Usage:
    python scripts/rebuild.py

Specified in docs/reference/index.md, "Rebuilding from the cached pages".
"""

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PARSE = [sys.executable, "scripts/crawl_index.py"]
STEPS = [
    ("parse", PARSE),
    ("chunk", [sys.executable, "-m", "src.chunking"]),
    ("enrich", [sys.executable, "-m", "src.enrich"]),
    ("index", [sys.executable, "-m", "src.index"]),
]


def failed_documents(root: Path) -> list[dict]:
    """Documents the parse step could not process; the crawler records them and goes on."""
    report = json.loads((root / "data" / "processed" / "_index.json").read_text(encoding="utf-8"))
    return [doc for doc in report["documents"] if doc.get("status") != "ok"]


def main(root: Path = ROOT) -> int:
    for name, command in STEPS:
        print(f"== {name}: {' '.join(command[1:])}", flush=True)
        code = subprocess.run(command, cwd=root).returncode
        if code != 0:
            print(f"stopped: {name} exited with {code}")
            return code
        if command == PARSE:
            failed = failed_documents(root)
            if failed:
                print("stopped: a rebuild must not drop a document; failed to parse: "
                      + ", ".join(f"{doc['doc_id']} ({doc.get('error', doc.get('status'))})" for doc in failed))
                return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
