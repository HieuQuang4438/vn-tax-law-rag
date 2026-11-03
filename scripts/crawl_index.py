"""Crawl every document linked from a luatvietnam.vn summary article.

Usage:
    python scripts/crawl_index.py [<summary-article-url>]

Only links inside the article's tables are taken; sidebar, related-news and footer links are
not part of the list. Pages already cached in data/raw/ are not fetched again, so a failed or
interrupted run can simply be re-run.

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

DEFAULT_INDEX_URL = (
    "https://luatvietnam.vn/thue-phi-le-phi/"
    "tong-hop-danh-sach-luat-thue-va-nghi-dinh-thong-tu-thue-moi-nhat-2026-565-110892-article.html"
)
DELAY_SECONDS = 3  # between live requests only; cached pages are free
# Document pages end in -<numeric id>-d1.html; "-d1-trial.html" ad links do not match.
DOC_URL = re.compile(r"-(\d+)-d1\.html$")


def document_links(index_url: str) -> list[dict]:
    soup = BeautifulSoup(fetch(index_url), "lxml")
    links, seen = [], set()
    for a in soup.select("table a[href]"):
        if a.find_parent(["aside", "footer"]):
            continue
        url = urljoin(index_url, a["href"])
        match = DOC_URL.search(url)
        # The same document is listed under several tax types; its numeric id is the stable key.
        if not match or match.group(1) in seen:
            continue
        seen.add(match.group(1))
        links.append({"doc_id": match.group(1), "url": url, "anchor": clean(a.get_text(" "))})
    return links


def main(index_url: str) -> None:
    links = document_links(index_url)
    print(f"{len(links)} documents listed")
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
        "index_url": index_url,
        "crawled_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "documents": links,
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "_index.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    failed = [d for d in links if d["status"] != "ok"]
    print(f"done: {len(links) - len(failed)} ok, {len(failed)} failed")


if __name__ == "__main__":
    if len(sys.argv) > 2:
        sys.exit(__doc__)
    main(sys.argv[1] if len(sys.argv) == 2 else DEFAULT_INDEX_URL)
