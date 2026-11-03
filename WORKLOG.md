# Worklog — vn-tax-law-rag

> Append-only journal. One block per working session: **what was done / what was decided and why / what is actually true**.
>
> Rules — full version in `CONVENTIONS.md` §8:
>
> - Newest on top. Never edit an earlier block; correct it in a new one.
> - Three parts per block: `Done` · `Decided + why` · `Real state / warnings`.
> - Label **verified** separately from **assumed**. Only what was run this session counts as verified.
> - Remaining work does not go here — that is issues and milestones (§7).
> - No secrets. No raw error dumps; quote the one decisive line.

---

## Session 1 — 2026-11-03 · Repo created

**Done**

- Scaffolded from `git-repos/templates/repo/` — minimal + product + public overlays.
- `scripts/crawl_one.py`: fetches one luatvietnam.vn document page, caches raw HTML in
  `data/raw/`, writes metadata + ordered text blocks to `data/processed/<slug>.json` and `.md`.
- `scripts/crawl_index.py`: takes the document links from the summary article's tables
  (sidebar/footer excluded, deduplicated by document id), crawls each with a 3 s delay, writes
  `data/processed/_index.json`.
- Parser rewritten to walk the DOM: headings sitting as bare text next to a table were dropped
  (Law 09/2026/QH16 lost its Article 4).

**Decided + why**

- Source is the HTML page, not the site's "Print" PDF: HTML keeps the chapter/article/clause
  structure that chunking will need; a PDF would have to be re-parsed to get it back.
- The whole page is cached, not just the document body, so parsing can change without re-crawling.
- `data/processed/` is gitignored as well as `data/raw/`: it is third-party page content.
- Visibility: private now, to be flipped public — written as if public.
- LLM provider not chosen; `src/config.py` keeps the scaffold's Gemini default until it is.

**Real state / warnings**

- Verified: all 27 documents crawled, each with articles 1..N and no gaps (checked by `^Điều N\s*\.`).
- Article headings are not uniform: `Điều 1 .` (space before the dot) occurs. Circulars 89 and 86
  contain more `Điều N.` lines than articles — quoted articles inside forms or amended text.
- Verified: crawler run on Circular 90/2026/TT-BTC — 579 blocks, articles 1–38 and appendix forms
  present; metadata (number, type, issuer, issue date, signer, summary) parsed.
- Effective date and validity status are paid-only on the site and are not captured; the
  document's own "Hiệu lực thi hành" article is the fallback.
- Block `kind` (site CSS class) does not map cleanly to articles: 40 `docitem-5` blocks vs 38
  articles. Chunking should detect articles by the `Điều N.` heading.
- Appendix forms make up most of the ~365k characters; chunking must handle or drop them.
