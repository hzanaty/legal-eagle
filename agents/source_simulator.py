"""Source Simulator — auto-discovers scraping config for a URL source (v3.1, F9).

Replaces the 11-field manual URL-source form with a single URL field plus a
one-time discovery pass. Pipeline: fetch (static → Playwright fallback) → detect
repeating article containers → map field selectors → pick a "read more" button →
detect pagination → capture a sample article. An optional LLM step picks the nav
link toward a listing page when the entry URL isn't itself the listing.

All DOM heuristics are pure Python (BeautifulSoup); only depth navigation and
(future) pagination classification use the LLM. Functions are individually
testable without a browser or AI.
"""
from __future__ import annotations

import json
from collections import Counter
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; LegalEagle/3.0)",
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "en-US,en;q=0.9",
}
_SKELETON_THRESHOLD = 500  # chars — below this, page is considered a JS skeleton


def fetch_page_playwright(url: str) -> str:
    """Render page with Playwright and return HTML. Raises on failure."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(url, wait_until="networkidle", timeout=30000)
        html = page.content()
        browser.close()
    return html


def fetch_page(url: str) -> Dict[str, Any]:
    """Fetch URL: static first, Playwright fallback if the response is skeletal.
    Returns {"html": str, "requires_js": bool}. Raises RuntimeError if both fail."""
    try:
        resp = requests.get(url, headers=DEFAULT_HEADERS, timeout=20)
        resp.raise_for_status()
        html = resp.text
        soup = BeautifulSoup(html, "html.parser")
        if len(soup.get_text(separator=" ", strip=True)) >= _SKELETON_THRESHOLD:
            return {"html": html, "requires_js": False}
    except Exception:
        pass
    try:
        html = fetch_page_playwright(url)
        return {"html": html, "requires_js": True}
    except Exception as exc:
        raise RuntimeError(f"Failed to fetch {url}: {exc}") from exc


def _css_from(tag) -> str:
    classes = tag.get("class")
    return (f"{tag.name}." + ".".join(classes)) if classes else tag.name


_SKIP_TAGS = frozenset([
    "html", "body", "head", "script", "style", "nav", "header", "footer",
    # inline/sub-field elements are never article containers
    "span", "a", "time", "em", "strong", "b", "i", "small", "abbr",
    "cite", "label", "code", "sup", "sub", "br", "img", "input",
])


def detect_containers(html: str, min_count: int = 3) -> List[Dict[str, Any]]:
    """Find repeating elements (tag + class) appearing >= min_count times.
    Returns candidates sorted by count desc with sample texts.

    Inline/sub-field tags (span, a, time, etc.) are excluded — they are field
    elements inside a card, not the card itself. Candidates must also contain
    at least one link, since article cards almost always link to their detail page.
    """
    soup = BeautifulSoup(html, "html.parser")
    counter: Counter = Counter()
    for tag in soup.find_all(True):
        classes = tag.get("class")
        if not classes:
            continue
        counter[f"{tag.name}.{'.'.join(sorted(classes))}"] += 1

    candidates: List[Dict[str, Any]] = []
    for selector, count in counter.most_common(20):
        if count < min_count:
            break
        tag_name = selector.split(".")[0]
        if tag_name in _SKIP_TAGS:
            continue
        # `selector` is already a valid CSS selector: "div.news-item" or "div.a.b"
        # (element carrying all listed classes) — use it directly.
        try:
            matches = soup.select(selector)
        except Exception:
            continue
        if len(matches) < min_count:
            continue
        # Require at least one internal link — article cards link to their detail page.
        # This filters out pure-text containers like paragraphs or heading groups.
        if not any(m.find("a", href=True) for m in matches[:3]):
            continue
        candidates.append({
            "selector": selector,
            "count": len(matches),
            "sample_texts": [m.get_text(separator=" ", strip=True)[:100] for m in matches[:3]],
        })
    return candidates


def map_fields(html: str, container_selector: str) -> Dict[str, Optional[str]]:
    """Within a container, find CSS selectors for title, link, date, author."""
    soup = BeautifulSoup(html, "html.parser")
    containers = soup.select(container_selector)
    result: Dict[str, Optional[str]] = {"title": None, "link": None, "date": None, "author": None}
    if not containers:
        return result
    first = containers[0]

    for a in first.find_all("a", href=True):
        if len(a.get_text(strip=True)) > 10:
            result["link"] = _css_from(a)
            result["title"] = result["link"]
            break

    # Tier 1: explicit <time> tag
    time_tag = first.find("time")
    if time_tag:
        result["date"] = _css_from(time_tag)
    # Tier 2: element whose CSS class signals a date (works regardless of format)
    if not result["date"]:
        _date_class_hints = ("date", "published", "timestamp", "pubdate", "post-date", "entry-date")
        for el in first.find_all(True):
            classes = " ".join(el.get("class", [])).lower()
            if any(h in classes for h in _date_class_hints):
                result["date"] = _css_from(el)
                break
    # Tier 3: content-based — any short element whose text parses as a valid date.
    # Uses the same dateutil-backed parser as the rest of the pipeline, so it handles
    # numeric (DD/MM/YYYY, YYYY-MM-DD), ISO, and named-month formats (e.g. "05 September 2026").
    if not result["date"]:
        try:
            from agents.news_filter import parse_date_string as _pds
            for el in first.find_all(True):
                txt = el.get_text(strip=True)
                if 5 <= len(txt) <= 80 and _pds(txt) is not None:
                    result["date"] = _css_from(el)
                    break
        except Exception:
            pass

    byline_hints = ("author", "byline", "kurum", "source", "publisher", "creator")
    for el in first.find_all(True):
        if any(h in " ".join(el.get("class", [])).lower() for h in byline_hints):
            result["author"] = _css_from(el)
            break
    return result


_NOISE_CLASSES = frozenset([
    "share", "print", "social", "facebook", "twitter", "linkedin",
    "whatsapp", "email", "bookmark", "save", "subscribe", "comment",
])
_DATE_NAV_HINTS = frozenset([
    "prev", "previous", "vorig", "önceki", "anterior", "ältere", "older", "back", "zurück",
])
_PAGE_NAV_HINTS = frozenset(["pagination", "pager", "next"])


def detect_buttons(html: str, container_selector: str) -> List[Dict[str, Any]]:
    """Find clickable elements consistent across containers, filtering share/print noise."""
    soup = BeautifulSoup(html, "html.parser")
    containers = soup.select(container_selector)
    if not containers:
        return []
    counter: Counter = Counter()
    labels: Dict[str, str] = {}
    for container in containers:
        seen = set()
        for el in container.find_all(["a", "button"]):
            classes_str = " ".join(el.get("class", []))
            if any(n in classes_str.lower() for n in _NOISE_CLASSES):
                continue
            label = el.get_text(strip=True)
            if not label or len(label) > 30:
                continue
            key = _css_from(el)
            if key not in seen:
                counter[key] += 1
                labels[key] = label
                seen.add(key)
    n = len(containers)
    results: List[Dict[str, Any]] = []
    for selector, count in counter.most_common(8):
        if count < max(2, n // 2):
            continue
        results.append({"selector": selector, "label": labels.get(selector, ""),
                        "description": f"Appears in {count}/{n} articles"})
        if len(results) == 4:
            break
    return results


def _is_read_more(el) -> bool:
    """Article 'read more' links are NOT pagination — exclude them."""
    cls = " ".join(el.get("class", [])).lower()
    txt = el.get_text(strip=True).lower()
    return "read" in cls or "weiterlesen" in txt or "read more" in txt


def detect_pagination(html: str) -> Optional[Dict[str, str]]:
    """Scan for pagination controls. Date-nav (prev/older) is preferred over page-nav.
    Read-more article links are excluded. Returns None if absent."""
    soup = BeautifulSoup(html, "html.parser")
    els = soup.find_all(["a", "button", "li"])
    # Pass 1: date-navigation (previous day / older) anywhere on the page
    for el in els:
        if _is_read_more(el):
            continue
        cls = " ".join(el.get("class", [])).lower()
        txt = el.get_text(strip=True).lower()
        if any(h in cls or h in txt for h in _DATE_NAV_HINTS):
            return {"pagination_type": "date-nav", "pagination_selector": _css_from(el)}
    # Pass 2: classic page navigation
    for el in els:
        if _is_read_more(el):
            continue
        cls = " ".join(el.get("class", [])).lower()
        if any(h in cls for h in _PAGE_NAV_HINTS):
            return {"pagination_type": "page-nav", "pagination_selector": _css_from(el)}
    return None


def pick_nav_link_with_llm(html: str, base_url: str, ai_client: Any) -> Optional[str]:
    """Ask the LLM which nav link leads to a news/announcements listing. Returns abs URL or None."""
    soup = BeautifulSoup(html, "html.parser")
    nav_links = []
    for el in soup.find_all(["nav", "ul", "div"], limit=5):
        for a in el.find_all("a", href=True):
            text = a.get_text(strip=True)
            if text and len(text) < 60:
                nav_links.append(f"- {text}: {urljoin(base_url, a['href'])}")
    if not nav_links:
        return None
    prompt = (
        "You are helping a web scraper find the news/announcements listing page of a website.\n"
        f"The entry URL is: {base_url}\n\n"
        f"Navigation links found on the page:\n" + "\n".join(nav_links[:20]) + "\n\n"
        "Which single link is most likely to lead to a news, announcements, or press releases listing page?\n"
        'Respond with JSON only: {"url": "<absolute url>", "reason": "<one sentence>"}\n'
        "If none of the links seem relevant, respond: null"
    )
    try:
        response = ai_client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=200,
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content.strip()
        if content.lower() == "null":
            return None
        return json.loads(content).get("url")
    except Exception:
        return None


def run_simulation(url: str, ai_client: Any = None, max_depth: int = 5) -> Any:
    """Generator yielding progress events. Pauses at containers_found for user confirmation."""
    try:
        fetch_result = fetch_page(url)
    except RuntimeError as exc:
        yield {"type": "fetch_failed", "data": {"error": str(exc)}}
        return

    current_html = fetch_result["html"]
    current_url = url
    yield {"type": "fetch_done", "data": {"requires_js": fetch_result["requires_js"]}}

    for depth in range(max_depth + 1):
        containers = detect_containers(current_html)
        if containers:
            best = containers[0]
            yield {"type": "containers_found", "data": {
                "depth": depth, "selector": best["selector"], "count": best["count"],
                "sample_texts": best["sample_texts"], "all_candidates": containers,
                "requires_js": fetch_result["requires_js"], "resolved_url": current_url,
            }}
            return
        if depth < max_depth and ai_client is not None:
            yield {"type": "no_containers", "data": {"depth": depth, "url": current_url}}
            next_url = pick_nav_link_with_llm(current_html, current_url, ai_client)
            if next_url:
                yield {"type": "navigating_deeper", "data": {"url": next_url, "depth": depth + 1}}
                try:
                    fetch_result = fetch_page(next_url)
                    current_html = fetch_result["html"]
                    current_url = next_url
                    continue
                except RuntimeError:
                    pass
        yield {"type": "failed", "data": {"error": "No article containers found", "depth": depth}}
        return


def run_simulation_from_confirmed_container(
    html: str, url: str, container_selector: str, depth_level: int,
    requires_js: bool, ai_client: Any = None,
) -> Any:
    """Second half — after the user confirms the container. Yields fields/buttons/pagination/sample/complete."""
    if not html:
        try:
            html = fetch_page(url)["html"]
        except RuntimeError as exc:
            yield {"type": "failed", "data": {"error": str(exc)}}
            return

    result: Dict[str, Any] = {
        "url": url, "requires_js": requires_js, "container_selector": container_selector,
        "field_selectors": None, "read_more_selector": None,
        "pagination_type": None, "pagination_selector": None,
        "depth_level": depth_level, "sample_link": None,
    }

    fields = map_fields(html, container_selector)
    result["field_selectors"] = json.dumps(fields)
    yield {"type": "fields_mapped", "data": {"fields": fields}}

    buttons = detect_buttons(html, container_selector)
    if buttons:
        result["read_more_selector"] = buttons[0]["selector"]
        yield {"type": "buttons_found", "data": {"buttons": buttons}}

    pagination = detect_pagination(html)
    if pagination:
        result["pagination_type"] = pagination["pagination_type"]
        result["pagination_selector"] = pagination["pagination_selector"]
        yield {"type": "pagination_found", "data": pagination}

    soup = BeautifulSoup(html, "html.parser")
    containers = soup.select(container_selector)
    if containers:
        link_el = containers[0].find("a", href=True)
        if link_el:
            result["sample_link"] = urljoin(url, link_el["href"])
            yield {"type": "sample_captured", "data": {"sample_link": result["sample_link"]}}

    yield {"type": "complete", "data": result}
