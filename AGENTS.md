# vn-tax-law-rag

Question-answering agent over Vietnamese tax law (laws, decrees, circulars), built with retrieval-augmented generation and answering with article-level citations.

## Rules

Read before writing code here:

- `CONVENTIONS.md` — repo layout, environment, secrets, Python style, LLM rules, testing, git, agent and subagent rules, definition of done.
- `DOCS-CONVENTIONS.md` — everything under `docs/`: front matter, IDs, version annotations, ADRs, releases. Present only if this repo has a `docs/` folder.

Both files are this repo's own. A rule that does not fit this project gets changed in that file, not worked around here. `CONVENTIONS.md` outranks this file: if the two disagree, this file is wrong.

## Project facts

- Visibility: private — to be flipped to public as a portfolio piece, so written as if public from the first commit. `CONVENTIONS.md` §3 and §8 key off this line: a public repo carries no internal identifiers, and a private repo that may ever be flipped to public is written as if it already were.
- Stack: Python 3.12, requests, BeautifulSoup + lxml; bge-m3 via sentence-transformers (CPU), Chroma, bm25s (ADR-0002). LLM not chosen yet.
- Entrypoint: `src/main.py` — run with `python -m src.main`
- Config: `src/config.py` — every env read happens here, nowhere else
- Test: `pytest`
- Session journal: `WORKLOG.md`, append-only, newest on top

## Where things live

| Path | Holds |
|---|---|
| `src/` | importable code |
| `tests/` | `pytest` tests, mirroring `src/` |
| `scripts/` | one-off and ops scripts, never imported by `src/` |
| `data/` | inputs; raw data gitignored, samples committed |
| `eval/` | the hand-written eval set, versioned (`docs/reference/eval-set.md`) |
