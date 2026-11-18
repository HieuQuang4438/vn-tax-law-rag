"""Crawl one legal document page from luatvietnam.vn.

Usage:
    python scripts/crawl_one.py <document-url>

Writes:
    data/raw/<slug>.html        raw page, cached so re-runs do not hit the site
    data/processed/<slug>.json  metadata + ordered text blocks
    data/processed/<slug>.md    plain full text, for eyeballing
"""

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup, Tag

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
OUT_DIR = ROOT / "data" / "processed"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130 Safari/537.36"

# Labels in the "Tổng quan" table -> output keys. Paid-only fields show "Đã biết".
META_FIELDS = {
    "Số hiệu": "so_hieu",
    "Loại văn bản": "loai_van_ban",
    "Cơ quan ban hành": "co_quan_ban_hanh",
    "Ngày ban hành": "ngay_ban_hanh",
    "Người ký": "nguoi_ky",
    "Trích yếu": "trich_yeu",
    "Ngày hiệu lực": "ngay_hieu_luc",
    "Tình trạng hiệu lực": "tinh_trang_hieu_luc",
}


def slug_from_url(url: str) -> str:
    return url.rstrip("/").rsplit("/", 1)[-1].removesuffix(".html")


def fetch(url: str) -> str:
    raw_path = RAW_DIR / f"{slug_from_url(url)}.html"
    if raw_path.exists():
        return raw_path.read_text(encoding="utf-8")
    resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=30)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    raw_path.write_text(resp.text, encoding="utf-8")
    return resp.text


def clean(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("\xa0", " ")).strip()


def parse_metadata(soup: BeautifulSoup) -> dict:
    meta = {"tieu_de": clean(soup.select_one("h1.the-document-title").get_text())}
    for cell in soup.select("div.div-table td.bg-f7f7f7"):
        label = clean(cell.find("strong").get_text()).rstrip(":") if cell.find("strong") else ""
        key = META_FIELDS.get(label)
        value_cell = cell.find_next_sibling("td")
        if key and value_cell and "Đã biết" not in value_cell.get_text():
            meta[key] = clean(value_cell.get_text(" "))
    return meta


INLINE_TAGS = {"a", "span", "strong", "b", "em", "i", "u", "sup", "sub", "font", "small"}


def block_lines(node: Tag) -> list[str]:
    """Text lines of a node: one line per block element or <br>, one line per table row.

    Walks children instead of collecting <p> tags, because some headings sit as bare text
    or inline tags directly inside a div, next to paragraphs and tables.
    """
    lines, inline = [], []

    def flush() -> None:
        text = clean("".join(inline))
        if text:
            lines.append(text)
        inline.clear()

    for child in node.children:
        if not isinstance(child, Tag):
            inline.append(str(child))
        elif child.name in ("script", "style"):
            continue
        elif child.name == "br":
            flush()
        elif child.name in INLINE_TAGS and not child.find(["p", "div", "table", "br"]):
            inline.append(child.get_text())
        elif child.name == "table":
            flush()
            # Rows of nested tables belong to the cell that holds them.
            for tr in child.find_all("tr"):
                if tr.find_parent("table") is not child:
                    continue
                cells = [" ".join(block_lines(td)) for td in tr.find_all(["td", "th"], recursive=False)]
                row = " | ".join(c for c in cells if c)
                if row:
                    lines.append(row)
        else:
            flush()
            lines.extend(block_lines(child))
    flush()
    return lines


def parse_body(soup: BeautifulSoup) -> list[dict]:
    # The page has several div.the-document-body (one per tab); only one holds the text.
    body = next(b for b in soup.select("div.the-document-body") if b.find("div", id=re.compile(r"^demuc\d+$")))
    blocks = []
    for div in body.find_all("div", id=re.compile(r"^demuc\d+$"), recursive=False):
        # Drop site widgets (follow/note buttons, form download links, amendment labels) and
        # the site's own comments between provisions: none of it is the document's text.
        for junk in div.select("div.document-tip, span.tooltip-button, div.docitemadd, div.docitem-binhluan"):
            junk.decompose()
        lines = block_lines(div)
        if lines:
            blocks.append({
                "id": div["id"],
                "kind": next((c for c in div.get("class", []) if c.startswith("docitem-")), None),
                "text": "\n".join(lines),
            })
    return blocks


def crawl(url: str) -> dict:
    """Fetch (or read cached), parse and write one document. Returns the parsed document."""
    soup = BeautifulSoup(fetch(url), "lxml")
    doc = {
        "source_url": url,
        "crawled_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "metadata": parse_metadata(soup),
        "blocks": parse_body(soup),
    }
    slug = slug_from_url(url)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / f"{slug}.json").write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT_DIR / f"{slug}.md").write_text("\n\n".join(b["text"] for b in doc["blocks"]), encoding="utf-8")
    return doc


def main(url: str) -> None:
    doc = crawl(url)
    slug = slug_from_url(url)
    print(f"{slug}: {len(doc['blocks'])} blocks, {sum(len(b['text']) for b in doc['blocks'])} chars")
    print(json.dumps(doc["metadata"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
