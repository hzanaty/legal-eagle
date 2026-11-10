"""Unit tests for the Source Simulator (v3.1, F9). Run with: python -m pytest tests/test_source_simulator.py -v"""
import os
import sqlite3
from unittest.mock import patch, MagicMock

import pytest

import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from configurations.db import create_schema_if_needed
from agents.source_simulator import (
    fetch_page, detect_containers, map_fields, detect_buttons,
    detect_pagination, pick_nav_link_with_llm, run_simulation,
    run_simulation_from_confirmed_container,
)
from agents.url_sources_runner import scrape_url_source_with_config

LIST_HTML = """
<html><body>
  <div class="news-item"><a href="/1">Minimum Wage Update</a><span class="date">2026-06-01</span><span class="author">BMAS</span></div>
  <div class="news-item"><a href="/2">New Labour Law Passed Today</a><span class="date">2026-06-02</span><span class="author">BMAS</span></div>
  <div class="news-item"><a href="/3">Tax Reform Announcement</a><span class="date">2026-06-03</span><span class="author">BMAS</span></div>
</body></html>
"""


def test_url_sources_new_columns():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    create_schema_if_needed(conn)
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(url_sources)")}
    for c in ("simulation_status", "container_selector", "field_selectors",
              "read_more_selector", "pagination_type", "pagination_selector",
              "depth_level", "requires_js", "simulated_at"):
        assert c in cols, f"missing column {c}"
    conn.close()


def test_fetch_page_static():
    html = "<html><body>" + "<p>Legal news content paragraph number here.</p>" * 30 + "</body></html>"
    with patch("agents.source_simulator.requests.get") as mock_get:
        mock_get.return_value = MagicMock(status_code=200, text=html, raise_for_status=lambda: None)
        result = fetch_page("http://example.com/news")
    assert result["requires_js"] is False


def test_fetch_page_empty_falls_back_to_playwright():
    with patch("agents.source_simulator.requests.get") as mock_get:
        mock_get.return_value = MagicMock(status_code=200, text="<html><body></body></html>", raise_for_status=lambda: None)
        with patch("agents.source_simulator.fetch_page_playwright") as mock_pw:
            mock_pw.return_value = "<html><body>" + "<div class='item'>News</div>" * 40 + "</body></html>"
            result = fetch_page("http://example.com/news")
    assert result["requires_js"] is True


def test_detect_containers_finds_repeating_elements():
    containers = detect_containers(LIST_HTML)
    assert any(c["selector"] == "div.news-item" for c in containers)
    assert any(c["count"] == 3 for c in containers)


def test_map_fields_extracts_title_link_date():
    sel = detect_containers(LIST_HTML)[0]["selector"]
    fields = map_fields(LIST_HTML, sel)
    assert fields["link"] is not None
    assert fields["title"] is not None
    assert fields["date"] is not None


def test_detect_buttons_filters_noise():
    html = """
    <html><body>
      <div class="news-item"><a href="/1">Title 1</a><a class="read-more" href="/1/d">More</a><button class="share-btn">Share</button></div>
      <div class="news-item"><a href="/2">Title 2</a><a class="read-more" href="/2/d">More</a><button class="share-btn">Share</button></div>
      <div class="news-item"><a href="/3">Title 3</a><a class="read-more" href="/3/d">More</a><button class="share-btn">Share</button></div>
    </body></html>
    """
    sel = detect_containers(html)[0]["selector"]
    selectors = [b["selector"] for b in detect_buttons(html, sel)]
    assert any("read-more" in s for s in selectors)
    assert not any("share" in s for s in selectors)


def test_detect_pagination_finds_and_absent():
    with_nav = LIST_HTML.replace("</body>", '<a class="prev-page" href="/news?d=2026-06-29">Previous</a></body>')
    res = detect_pagination(with_nav)
    assert res is not None and res["pagination_type"] in ("date-nav", "page-nav")
    assert detect_pagination(LIST_HTML) is None


def test_pick_nav_link_with_llm_returns_url():
    html = '<html><body><nav><a href="/about">About</a><a href="/news">Current News</a></nav></body></html>'
    client = MagicMock()
    client.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content='{"url": "http://example.com/news", "reason": "news"}'))]
    )
    assert pick_nav_link_with_llm(html, "http://example.com", client) == "http://example.com/news"


def test_run_simulation_yields_progress_events():
    with patch("agents.source_simulator.fetch_page") as mock_fetch:
        mock_fetch.return_value = {"html": LIST_HTML, "requires_js": False}
        events = list(run_simulation("http://example.com/news", ai_client=None))
    types = [e["type"] for e in events]
    assert "fetch_done" in types
    assert "containers_found" in types


def test_confirmed_container_completes():
    sel = detect_containers(LIST_HTML)[0]["selector"]
    events = list(run_simulation_from_confirmed_container(
        html=LIST_HTML, url="http://example.com/news", container_selector=sel,
        depth_level=0, requires_js=False))
    types = [e["type"] for e in events]
    assert "fields_mapped" in types and "complete" in types
    complete = [e for e in events if e["type"] == "complete"][0]["data"]
    assert complete["container_selector"] == sel


def test_scrape_uses_stored_selectors():
    source = {
        "url": "http://example.com/news",
        "container_selector": "div.news-item",
        "field_selectors": '{"title": "a", "link": "a", "date": "span.date", "author": "span.author"}',
        "requires_js": 0,
    }
    with patch("agents.url_sources_runner.requests.get") as mock_get:
        mock_get.return_value = MagicMock(status_code=200, text=LIST_HTML, raise_for_status=lambda: None)
        items = scrape_url_source_with_config(source)
    assert len(items) == 3
    assert items[0]["title"] == "Minimum Wage Update"
    assert items[0]["link"] == "http://example.com/1"


def test_scrape_returns_empty_when_unsimulated():
    assert scrape_url_source_with_config({"url": "http://x", "container_selector": None}) == []


# ── Regression: url_date_template NULL renders as empty string (not "None") ──

def _jinja_render_url_date_template(value):
    """Render the fixed Jinja expression for url_date_template given a DB value."""
    from jinja2 import Environment
    env = Environment()
    tmpl = env.from_string("{{ (s.url_date_template or '')|e }}")

    class _S:
        url_date_template = value

    return tmpl.render(s=_S())


def test_url_date_template_null_renders_empty():
    """NULL from DB must render as '' so JS receives falsy value and skips the template branch."""
    assert _jinja_render_url_date_template(None) == ""


def test_url_date_template_empty_string_renders_empty():
    assert _jinja_render_url_date_template("") == ""


def test_url_date_template_valid_renders_passthrough():
    tpl = "https://example.com/{DD}.{MM}.{YYYY}"
    assert _jinja_render_url_date_template(tpl) == tpl


def _derive_sim_url(source_url, url_date_template_str):
    """Replicate the simulate route's sim_url derivation for unit testing."""
    from agents.url_sources_runner import _normalize_date_template
    from datetime import datetime, timedelta
    sim_url = source_url
    template = (url_date_template_str or "").strip()
    if template:
        yesterday = datetime.now() - timedelta(days=1)
        tpl = _normalize_date_template(template)
        sim_url = (tpl
                   .replace("{DD}", yesterday.strftime("%d"))
                   .replace("{MM}", yesterday.strftime("%m"))
                   .replace("{YYYY}", yesterday.strftime("%Y")))
    return sim_url


def test_sim_url_null_template_uses_source_url():
    """When url_date_template is NULL/empty, sim_url must equal the source URL unchanged."""
    url = "https://hzanaty.github.io/xanadu-gov/xanadu.html"
    assert _derive_sim_url(url, None) == url
    assert _derive_sim_url(url, "") == url


def test_sim_url_valid_template_produces_dated_url():
    """A valid dated template must produce a URL with today's date substituted."""
    from datetime import datetime, timedelta
    yesterday = datetime.now() - timedelta(days=1)
    result = _derive_sim_url(
        "https://example.com/",
        "https://example.com/{DD}.{MM}.{YYYY}"
    )
    assert yesterday.strftime("%d") in result
    assert yesterday.strftime("%m") in result
    assert yesterday.strftime("%Y") in result
    assert result.startswith("https://example.com/")
