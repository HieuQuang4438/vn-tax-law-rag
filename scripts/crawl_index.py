"""Crawl every document linked from luatvietnam.vn summary articles.

Usage:
    python scripts/crawl_index.py [<summary-article-url> ...]

With no argument, crawls the summary articles in INDEX_URLS. Only links inside each article's
tables are taken; sidebar, related-news and footer links are not part of the list. A document
listed in several articles, or under several tax types, is crawled once. Pages already cached
in data/raw/ are not fetched again, so a failed or interrupted run can simply be re-run.

Writes:
    data/processed/<slug>.json, .md   one pair per document (see crawl_one.py)
    data/processed/_index.json        the document list and the outcome for each
"""

import json
import re
import sys
import time
from datetime import datetime, timezone
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from crawl_one import OUT_DIR, RAW_DIR, clean, crawl, fetch, slug_from_url

# The corpus is defined by these lists — docs/product/requirements.md FR-CORE-001.
INDEX_URLS = [
    # Tax laws, decrees and circulars in force in 2026.
    "https://luatvietnam.vn/thue-phi-le-phi/"
    "tong-hop-danh-sach-luat-thue-va-nghi-dinh-thong-tu-thue-moi-nhat-2026-565-110892-article.html",
    # Personal income tax: adds the PIT law and its decree and circular, missing from the first list.
    "https://luatvietnam.vn/thue-phi-le-phi/tong-hop-van-ban-huong-dan-ve-thue-tncn-moi-nhat-565-96172-article.html",
]
DELAY_SECONDS = 3  # between live requests only; cached pages are free
# Document pages end in -<numeric id>-d1.html; "-d1-trial.html" ad links do not match.
DOC_URL = re.compile(r"-(\d+)-d1\.html$")


def document_links(index_urls: list[str]) -> list[dict]:
    links, by_id = [], {}
    for index_url in index_urls:
        soup = BeautifulSoup(fetch(index_url), "lxml")
        for a in soup.select("table a[href]"):
            if a.find_parent(["aside", "footer"]):
                continue
            url = urljoin(index_url, a["href"])
            match = DOC_URL.search(url)
            if not match:
                continue
            # The same document is listed under several tax types and in several articles;
            # its numeric id is the stable key.
            doc_id = match.group(1)
            if doc_id in by_id:
                if index_url not in by_id[doc_id]["listed_in"]:
                    by_id[doc_id]["listed_in"].append(index_url)
                continue
            by_id[doc_id] = {"doc_id": doc_id, "url": url, "anchor": clean(a.get_text(" ")), "listed_in": [index_url]}
            links.append(by_id[doc_id])
    return links


def main(index_urls: list[str]) -> None:
    links = document_links(index_urls)
    print(f"{len(links)} documents listed in {len(index_urls)} summary articles")
    for i, link in enumerate(links, 1):
        cached = (RAW_DIR / f"{slug_from_url(link['url'])}.html").exists()
        try:
            doc = crawl(link["url"])
            link.update(status="ok", so_hieu=doc["metadata"].get("so_hieu"), blocks=len(doc["blocks"]))
        except Exception as exc:  # one bad page must not stop the batch
            link.update(status="error", error=f"{type(exc).__name__}: {exc}")
        print(f"[{i}/{len(links)}] {link['status']:5} {link.get('so_hieu') or link['url']}")
        if not cached and i < len(links):
            time.sleep(DELAY_SECONDS)

    manifest = {
        "index_urls": index_urls,
        "crawled_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "documents": links,
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "_index.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    failed = [d for d in links if d["status"] != "ok"]
    print(f"done: {len(links) - len(failed)} ok, {len(failed)} failed")


if __name__ == "__main__":
    main(sys.argv[1:] or INDEX_URLS)
