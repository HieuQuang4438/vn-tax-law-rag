# vn-tax-law-rag

Question-answering agent over Vietnamese tax law (laws, decrees, circulars), built with retrieval-augmented generation and answering with article-level citations.

<!-- Demo link and screenshot go here once there is something to show. -->

## The problem

Vietnamese tax rules are spread across three layers of documents — a law, the decrees that
detail it, and the circulars that guide those — and 2025–2026 brought a wave of new and amending
texts. Answering one practical question ("what do household businesses have to declare?") means
reading several documents and knowing which provision currently applies. This project is also
how I am learning RAG end to end, from crawling and chunking to evaluation.

## What it does

Planned — see Status for what exists today.

- Answers questions about current Vietnamese tax law in Vietnamese.
- Cites the document, article and clause behind every answer, with a link to the source text.
- Says it found nothing rather than guessing when the documents do not cover the question.

## How it works

1. **Crawl** — `scripts/crawl_index.py` reads the summary article listing current tax documents and
   runs `scripts/crawl_one.py` on each: fetch the page, cache the raw HTML, extract metadata plus
   the full text as ordered blocks.
2. **Chunk** — split along the legal structure (chapter / article / clause), not by token count,
   so each retrieved unit is something a citation can point to. *Not built yet.*
3. **Retrieve** — hybrid keyword + embedding search, because users ask both in prose and by
   document number. *Not built yet.*
4. **Answer** — an LLM answers only from the retrieved articles and cites them. *Not built yet.*
5. **Evaluate** — a hand-written question set with expected articles, scored on retrieval recall
   and citation correctness. *Not built yet.*

## Data

The corpus is about 27 tax laws, decrees and circulars in force in 2026. Vietnamese legal
normative documents are not protected by copyright (Law on Intellectual Property, Article 15),
but the website they are taken from adds its own summaries and annotations. Only the crawler is
published; crawled pages and parsed text stay local (`data/` is gitignored).

## Run it

```bash
git clone <clone url>
cd vn-tax-law-rag
python -m venv .venv
.venv\Scripts\Activate.ps1        # Windows PowerShell; bash: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env              # then fill in the real values
python scripts/crawl_index.py        # all listed documents; or crawl_one.py <document-url>
```

## Tests

```bash
pytest
```

## Built with

Python 3.12, requests, BeautifulSoup + lxml. LLM, embedding model and vector store not chosen yet.

## Status

Early. The crawler fetches all 27 listed documents; every one has an unbroken run of articles
from Điều 1 to its last article. Chunking, retrieval, the agent and evaluation do not exist yet.
