"""FR-CORE-013/014 web chat page, the static page the app serves (#30). Approach approved on #30.
AC-010: the web interface answers a question end to end, shows citations as links to the
source, and shows the not-advice notice.

The rules are `docs/reference/web.md`, *The page*. These tests read what the app serves; the
page's script is checked by hand in the end-to-end run (#30, *Risks*).
"""

import json
import re
import threading
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.web import create_app, texts

ROOT = Path(__file__).resolve().parents[2]
NAMES = texts.NAMES


@pytest.fixture
def client():
    never = threading.Event()  # the page is served while the index loads

    def load():
        never.wait(5)
        raise RuntimeError("not loaded in these tests")

    with TestClient(create_app(load)) as client:
        yield client
        never.set()


def page_texts(html: str) -> dict:
    match = re.search(r'<script id="texts" type="application/json">(.*?)</script>', html, re.S)
    assert match, "the page carries its texts"
    return json.loads(match.group(1))


def test_the_page_is_served_while_the_index_loads(client):
    response = client.get("/")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert client.get("/api/status").json() == {"status": "loading"}


def test_the_page_carries_the_texts_of_src_web_texts(client):
    found = page_texts(client.get("/").text)
    assert found == {name: getattr(texts, name) for name in NAMES}


def test_the_texts_keep_the_wording_of_the_streamlit_page():
    assert texts.TITLE == "Hỏi đáp pháp luật thuế Việt Nam"
    assert texts.PLACEHOLDER == "Đặt câu hỏi về thuế…"
    assert texts.NOTICE == "Đây là thông tin kèm nguồn, không phải tư vấn pháp lý hay tư vấn thuế."
    assert texts.NEW_CONVERSATION == "Cuộc hội thoại mới"
    assert texts.SPINNER == "Đang tìm và trả lời…"
    assert texts.ERROR == "Chưa trả lời được lúc này, vui lòng thử lại sau."
    assert texts.LOAD_ERROR == "Chưa tải được chỉ mục văn bản nên chưa thể trả lời."
    assert texts.QUOTA == "Đang có nhiều câu hỏi, vui lòng thử lại sau một phút."


def test_the_browser_tab_shows_the_title(client):
    assert f"<title>{texts.TITLE}</title>" in client.get("/").text


def test_the_stylesheet_and_the_script_are_served(client):
    html = client.get("/").text
    for path in ("static/app.css", "static/app.js"):
        assert f'"{path}"' in html
        assert client.get("/" + path).status_code == 200


def test_the_page_loads_no_script_from_another_origin(client):
    html = client.get("/").text
    assert re.findall(r'<script[^>]*\ssrc="([^"]+)"', html) == ["static/app.js"]
    for href in re.findall(r'<link[^>]*rel="stylesheet"[^>]*href="([^"]+)"', html):
        assert href == "static/app.css" or href.startswith("https://fonts.googleapis.com/")


def test_the_script_calls_the_api_by_relative_paths(client):
    script = client.get("/static/app.js").text
    for path in ("api/status", "api/load", "api/documents", "api/ask"):
        assert f'"{path}"' in script
    assert '"/api/' not in script


def test_the_script_holds_no_copy_of_the_texts(client):
    response = client.get("/static/app.js")
    assert response.status_code == 200
    script = response.text
    for name in NAMES:
        assert getattr(texts, name) not in script


def test_the_top_bar_has_a_button_for_the_source_panel(client):
    html = client.get("/").text
    topbar = re.search(r'<header class="topbar">(.*?)</header>', html, re.S).group(1)
    button = re.search(r'<button[^>]*id="panel-toggle"[^>]*>', topbar)
    assert button, "the top bar carries #panel-toggle"
    assert 'aria-controls="panel"' in button.group(0)
    assert 'aria-expanded="false"' in button.group(0)


def test_the_panel_head_has_its_title_alone(client):
    html = client.get("/").text
    head = re.search(r'<div class="panel-head">(.*?)</div>', html, re.S).group(1)
    assert re.sub(r"\s+", " ", head).strip() == '<h2 id="panel-h">Nguồn của câu trả lời</h2>'


def test_the_welcome_has_two_points(client):
    script = client.get("/static/app.js").text
    assert "Điều khoản đã bị sửa đổi được nêu rõ, kèm văn bản sửa đổi." in script
    assert "Hỏi tiếp trong cùng hội thoại" not in script


def test_a_text_box_inside_a_framed_box_draws_no_focus_ring_of_its_own(client):
    css = client.get("/static/app.css").text
    rule = re.search(r"([^{}]*)\{\s*box-shadow:\s*none;?\s*\}", css.replace("\n", " "))
    selectors = rule.group(1) if rule else ""
    assert ".composer textarea:focus-visible" in selectors
    assert ".search input:focus-visible" in selectors


def test_a_history_row_offers_to_rename_its_conversation(client):
    script = client.get("/static/app.js").text
    assert 'data-act="rename"' in script
    assert 'aria-label="Đổi tên hội thoại' in script
    assert 'maxlength="100"' in script


# --- Type -----------------------------------------------------------------------------------------

def rules(css: str) -> dict[str, dict[str, str]]:
    """Each selector's declarations, later rules over earlier ones, at-rules' bodies included."""
    found: dict[str, dict[str, str]] = {}
    for selectors, body in re.findall(r"([^{}]+)\{([^{}]*)\}", re.sub(r"/\*.*?\*/", "", css, flags=re.S)):
        declarations = dict((k.strip(), v.strip()) for k, v in
                            (d.split(":", 1) for d in body.split(";") if ":" in d))
        for selector in selectors.split(","):
            found.setdefault(" ".join(selector.split()), {}).update(declarations)
    return found


@pytest.fixture
def css(client) -> str:
    return client.get("/static/app.css").text


def test_every_text_box_is_16_px(css):
    found = rules(css)
    for box in (".composer textarea", ".search input", ".hist-input"):
        assert found[box].get("font-size") == "var(--fs-16)", box


def test_no_text_is_under_12_px(css):
    sizes = [int(px) for px in re.findall(r"(?:font-size|--fs-\d+):\s*(\d+)px", css)]
    assert sizes and min(sizes) >= 12


def test_no_capitals_are_made_by_css(css):
    assert "uppercase" not in css


def test_the_article_heading_above_an_excerpt_is_the_document_s_type(css):
    loc = rules(css)[".excerpt .loc"]
    found = (loc.get("font-family"), loc.get("font-size"), loc.get("font-weight"), loc.get("color"))
    assert found == ("var(--font-doc)", "var(--fs-16)", "600", "var(--ink)")


@pytest.mark.parametrize("selector", [".dlg-head h2", ".status h2"])
def test_the_page_s_own_titles_are_sans(css, selector):
    title = rules(css)[selector]
    assert "font-family" not in title  # the body's, --font-ui
    assert (title.get("font-size"), title.get("font-weight")) == ("var(--fs-20)", "600")


@pytest.mark.parametrize("selector", [".welcome h2", ".brand-name", ".doc-title"])
def test_a_serif_heading_leaves_room_for_the_marks(css, selector):
    assert float(rules(css)[selector]["line-height"]) >= 1.3


def test_the_answer_and_the_excerpt_share_the_body_line_height(css):
    found = rules(css)
    assert found[":root"]["--lh-body"] == "1.7"
    assert found[".a-body"]["line-height"] == found[".excerpt"]["line-height"] == "var(--lh-body)"


def test_a_text_with_a_closing_script_tag_cannot_end_the_texts_block(monkeypatch):
    def load():
        raise RuntimeError("not loaded in these tests")

    monkeypatch.setattr(texts, "NOTICE", "a </script><b>b</b>")
    with TestClient(create_app(load)) as client:
        html = client.get("/").text
    assert "a </script>" not in html
    assert page_texts(html)["NOTICE"] == "a </script><b>b</b>"


def test_the_streamlit_page_is_gone():
    assert not (ROOT / "src" / "app.py").exists()
    assert "streamlit" not in (ROOT / "requirements.txt").read_text(encoding="utf-8").lower()
