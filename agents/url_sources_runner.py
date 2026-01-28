from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from urllib.parse import urljoin, urlparse

import feedparser
import requests
from bs4 import BeautifulSoup


# -------------------------------
# Models
# -------------------------------

@dataclass
class Source:
    url: str
    mode: str  # auto | force_static | force_dynamic
    sample_link: Optional[str] = None


# -------------------------------
# HTTP helpers
# -------------------------------

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ar-SA,ar;q=0.9,en-US;q=0.8,en;q=0.7"
}


def http_get(url: str, timeout: int = 20, retries: int = 3, backoff_sec: float = 1.0) -> Tuple[int, str]:
    last_err = None
    for attempt in range(retries):
        try:
            r = requests.get(url, headers=DEFAULT_HEADERS, timeout=timeout)
            return r.status_code, r.text
        except Exception as e:
            last_err = e
            if attempt < retries - 1:
                try:
                    import time as _t
                    _t.sleep(backoff_sec)
                except Exception:
                    pass
            else:
                return -1, f"HTTP error: {e}"
    return -1, f"HTTP error: {last_err or 'unknown'}"


# -------------------------------
# Dynamic rendering (Playwright)
# -------------------------------

async def _render_html_async(url: str, wait_selector: Optional[str] = None, timeout_ms: int = 30000) -> str:
    try:
        from playwright.async_api import async_playwright  # lazy import
    except Exception as e:
        return f"__ERROR__: Playwright import failed: {e}"

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True, args=["--disable-blink-features=AutomationControlled"])
            context = await browser.new_context(
                locale="ar-SA",
                timezone_id="Asia/Riyadh",
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
                extra_http_headers={
                    "Accept-Language": "ar-SA,ar;q=0.9,en-US;q=0.8,en;q=0.7",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                },
            )
            # Block heavy resources to speed up rendering
            async def _route_handler(route):
                try:
                    if route.request.resource_type in ("image", "font"):
                        await route.abort()
                    else:
                        await route.continue_()
                except Exception:
                    try:
                        await route.continue_()
                    except Exception:
                        pass
            try:
                await context.route("**/*", _route_handler)
            except Exception:
                pass
            # Stealth: remove webdriver flag
            try:
                await context.add_init_script("""
                    Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                """)
            except Exception:
                pass
            page = await context.new_page()
            # Apply default timeouts (navigation + actions)
            try:
                page.set_default_navigation_timeout(timeout_ms)
                page.set_default_timeout(timeout_ms)
            except Exception:
                pass
            # Use 'load' for GOSI (heavier SPA), 'domcontentloaded' otherwise; retry once on page/context closure
            try:
                if "gosi.gov.sa" in url:
                    await page.goto(url, timeout=timeout_ms, wait_until="load")
                else:
                    await page.goto(url, timeout=timeout_ms, wait_until="domcontentloaded")
            except Exception:
                # Re-create page once and retry navigation
                try:
                    await page.close()
                except Exception:
                    pass
                page = await context.new_page()
                try:
                    page.set_default_navigation_timeout(timeout_ms)
                    page.set_default_timeout(timeout_ms)
                except Exception:
                    pass
                await page.goto(url, timeout=timeout_ms, wait_until="load" if "gosi.gov.sa" in url else "domcontentloaded")
            try:
                await page.wait_for_load_state("networkidle", timeout=timeout_ms // 2)
            except Exception:
                pass
            # Trigger lazy loading
            try:
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await page.wait_for_timeout(500)
            except Exception:
                pass
            # Additional wait: ensure a minimum number of anchors appear
            try:
                await page.wait_for_function("document.querySelectorAll('a[href]').length >= 10", timeout=timeout_ms//2)
            except Exception:
                pass
            if wait_selector:
                try:
                    await page.wait_for_selector(wait_selector, timeout=timeout_ms)
                except Exception:
                    # If selector not found, proceed with whatever is rendered
                    pass
            html = await page.content()
            await browser.close()
            return html
    except Exception as e:
        return f"__ERROR__: Playwright render failed: {e}"


def render_html(url: str, wait_selector: Optional[str] = None, timeout_ms: int = 30000) -> Tuple[bool, str]:
    try:
        html = asyncio.run(_render_html_async(url, wait_selector=wait_selector, timeout_ms=timeout_ms))
        if html.startswith("__ERROR__"):
            return False, html
        return True, html
    except Exception as e:
        return False, f"__ERROR__: Playwright runtime failed: {e}"


# -------------------------------
# Dynamic rendering + generic link collection (Playwright)
# -------------------------------

async def _render_and_collect_links_async(
    url: str,
    read_label: Optional[str] = None,
    detail_pattern: Optional[str] = None,
    timeout_ms: int = 60000
) -> Tuple[str, List[str]]:
    try:
        from playwright.async_api import async_playwright  # lazy import
    except Exception as e:
        return f"__ERROR__: Playwright import failed: {e}", []

    # Simple Arabic-aware normalization for label matching (server-side JS has its own as well)
    def _normalize_label_py(s: Optional[str]) -> str:
        if not s:
            return ""
        try:
            import re
            t = s.strip()
            t = re.sub(r"[\u064B-\u065F\u0670\u0640]", "", t)  # diacritics + tatweel
            t = re.sub(r"[إأآٱ]", "ا", t)
            t = t.replace("ى", "ي").replace("\u200e", "").replace("\u200f", "")
            return t.lower()
        except Exception:
            return (s or "").strip().lower()

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True, args=["--disable-blink-features=AutomationControlled"])
            context = await browser.new_context(
                locale="ar-SA",
                timezone_id="Asia/Riyadh",
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
                extra_http_headers={
                    "Accept-Language": "ar-SA,ar;q=0.9,en-US;q=0.8,en;q=0.7",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                },
            )
            # Initialize history navigation capture for SPA sites
            try:
                await context.add_init_script("""
                    (function(){
                      try{
                        window.__leNavs = [];
                        const _ps = history.pushState;
                        history.pushState = function(s,t,u){ try{ if(u){ window.__leNavs.push(new URL(u, location.href).href);} }catch(e){}; return _ps.apply(this, arguments); };
                        const _rs = history.replaceState;
                        history.replaceState = function(s,t,u){ try{ if(u){ window.__leNavs.push(new URL(u, location.href).href);} }catch(e){}; return _rs.apply(this, arguments); };
                      }catch(e){}
                    })();
                """)
            except Exception:
                pass
            # Block only heavy resources; keep stylesheets enabled for proper JS layout
            async def _route_handler(route):
                try:
                    if route.request.resource_type in ("image", "font"):
                        await route.abort()
                    else:
                        await route.continue_()
                except Exception:
                    try:
                        await route.continue_()
                    except Exception:
                        pass
            try:
                await context.route("**/*", _route_handler)
            except Exception:
                pass

            page = await context.new_page()
            # Navigation capture for SPA routes (frame navigations)
            nav_urls_py = set()
            try:
                def _on_framenav(frame):
                    try:
                        u = frame.url
                        from urllib.parse import urlparse as _uparse
                        bu = _uparse(url)
                        ru = _uparse(u)
                        if bu.netloc and ru.netloc and ru.scheme and (ru.netloc == bu.netloc):
                            if ((detail_pattern is None) or (detail_pattern in u)) and _is_probable_html_url(u):
                                nav_urls_py.add(u)
                    except Exception:
                        pass
                page.on("framenavigated", _on_framenav)
            except Exception:
                pass

            # Network response capture for candidate URLs (same-origin, optional detail pattern)
            collected_links_py = set()
            async def _on_response(resp):
                try:
                    u = resp.url
                    status = 0
                    try:
                        status = resp.status
                    except Exception:
                        status = 0
                    # Only consider successful responses
                    if status != 200:
                        return
                    # Content-Type must look like HTML
                    ctype = ""
                    try:
                        hdrs = resp.headers or {}
                        ctype = (hdrs.get("content-type") or "").lower()
                    except Exception:
                        ctype = ""
                    if "text/html" not in ctype:
                        return
                    from urllib.parse import urlparse as _uparse
                    bu = _uparse(url)
                    ru = _uparse(u)
                    # same-origin
                    if bu.netloc and ru.netloc and ru.scheme and ru.netloc and (ru.netloc == bu.netloc):
                        # If detail_pattern provided, prefer those; otherwise collect all same-origin
                        if ((detail_pattern is None) or (detail_pattern in u)) and _is_probable_html_url(u):
                            collected_links_py.add(u)
                except Exception:
                    pass
            try:
                page.on("response", _on_response)
            except Exception:
                pass
            await page.goto(url, timeout=timeout_ms, wait_until="domcontentloaded")
            try:
                await page.wait_for_load_state("networkidle", timeout=timeout_ms // 2)
            except Exception:
                pass
            # Site-specific readiness for GOSI News listing
            try:
                if "gosi.gov.sa" in url:
                    await page.wait_for_selector("#newsList", timeout=timeout_ms)
            except Exception:
                pass
            # If a read-more label is provided, wait briefly for it to appear (generic, site-agnostic)
            try:
                if read_label:
                    loc_label = page.get_by_text(read_label, exact=False)
                    await loc_label.first.wait_for(state="visible", timeout=3000)
            except Exception:
                pass
            # Attempt to trigger lazy load
            try:
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await page.wait_for_timeout(500)
            except Exception:
                pass
            # Heuristic wait: ensure detail identifier appears in HTML (e.g., 'NewsDetails')
            try:
                await page.wait_for_function("document.documentElement.outerHTML.includes('NewsDetails')", timeout=timeout_ms // 3)
            except Exception:
                pass

            # Additional progressive scrolls to trigger lazy-load listings (Angular/SPA)
            try:
                for _ in range(4):
                    await page.mouse.wheel(0, 1200)
                    await page.wait_for_timeout(800)
            except Exception:
                pass
            # Wait for likely listing markers if present
            try:
                await page.wait_for_selector("a.readMore, div.newsItemDetails, article", timeout=3000)
            except Exception:
                pass

            # Stability loop for detail links: progressively scroll until anchor count stabilizes or threshold reached
            try:
                if detail_pattern:
                    prev_count = -1
                    stable_rounds = 0
                    for _ in range(6):
                        try:
                            count = await page.evaluate(
                                "(pat) => { const a=[...document.querySelectorAll('a[href]')]; return a.filter(el => (el.getAttribute('href')||'').includes(pat)).length; }",
                                detail_pattern
                            )
                        except Exception:
                            count = 0
                        if count == prev_count:
                            stable_rounds += 1
                        else:
                            stable_rounds = 0
                        if count >= 6 or stable_rounds >= 2:
                            break
                        try:
                            await page.mouse.wheel(0, 1200)
                        except Exception:
                            pass
                        await page.wait_for_timeout(800)
                        prev_count = count
            except Exception:
                pass

            # Evaluate in-page to collect candidate links (anchors, data-* hrefs, onclick URLs, label-based)
            norm_label = _normalize_label_py(read_label)
            try:
                links = await page.evaluate(
                    r"""(label) => {
                        const urls = new Set();
                        const push = (u) => {
                            if (!u) return;
                            try { urls.add(new URL(u, location.href).href); } catch (e) {}
                        };
                        // 1) All anchors
                        document.querySelectorAll('a[href]').forEach(a => push(a.getAttribute('href')));
                        // 2) Scan shadow roots for anchors
                        const scanShadow = (root) => {
                            try {
                                if (!root || typeof root.querySelectorAll !== 'function') return;
                                root.querySelectorAll('a[href]').forEach(a => push(a.getAttribute('href')));
                            } catch (e) {}
                        };
                        document.querySelectorAll('*').forEach(el => {
                            const sr = el.shadowRoot;
                            if (sr) scanShadow(sr);
                        });
                        // 3) Non-anchor href/data-* candidates + common SPA attributes
                        document.querySelectorAll('[data-href],[data-url],[data-link],[data-target],[href],[routerlink],[ng-reflect-router-link]').forEach(el => {
                            if (el.tagName && el.tagName.toLowerCase() === 'a') return;
                            const h = el.getAttribute('href')
                                || el.getAttribute('data-href')
                                || el.getAttribute('data-url')
                                || el.getAttribute('data-link')
                                || el.getAttribute('data-target')
                                || el.getAttribute('routerlink')
                                || el.getAttribute('ng-reflect-router-link');
                            if (h) push(h);
                        });
                        // 4) onclick URL extraction (absolute + relative + assignment/window.open)
                        const reUrlAbs = /(https?:\/\/[^\s'"()<>]+)/g;
                        const reUrlRelQuoted = /['"]\/[^'"()<>]+['"]/g;
                        const reAssign = /(location\\.href\\s*=\\s*['"]([^'"]+)['"])|location\\.assign\\(\\s*['"]([^'"]+)['"]\\s*\\)|window\\.open\\(\\s*['"]([^'"]+)['"]/g;
                        document.querySelectorAll('[onclick]').forEach(el => {
                            const oc = el.getAttribute('onclick') || '';
                            let m;
                            while ((m = reUrlAbs.exec(oc)) !== null) { push(m[0]); }
                            const rq = oc.match(reUrlRelQuoted) || [];
                            rq.forEach(q => push(q.slice(1, -1)));
                            while ((m = reAssign.exec(oc)) !== null) {
                                const u = m[2] || m[3] || m[4];
                                if (u) push(u);
                            }
                        });
                        // 5) Label-based discovery
                        const normalize = (t) => {
                            if (!t) return '';
                            return t.replace(/[\u064B-\u065F\u0670\u0640]/g,'')
                                    .replace(/[إأآٱ]/g,'ا')
                                    .replace(/ى/g,'ي')
                                    .replace(/[\u200e\u200f]/g,'')
                                    .toLowerCase()
                                    .trim();
                        };
                        const normLabel = normalize(label || '');
                        if (normLabel) {
                            const candidates = Array.from(document.querySelectorAll('a,button,span,div,[role="button"],[role="link"]'));
                            for (const el of candidates) {
                                const txt = normalize(el.innerText || el.textContent || '');
                                if (txt && txt.includes(normLabel)) {
                                    const a = el.closest && el.closest('a[href]');
                                    if (a && a.getAttribute('href')) push(a.getAttribute('href'));
                                    const h = el.getAttribute('href') || el.getAttribute('data-href') || el.getAttribute('data-url') || el.getAttribute('data-link') || el.getAttribute('data-target');
                                    if (h) push(h);
                                    const oc = el.getAttribute('onclick') || '';
                                    let m;
                                    while ((m = reUrlAbs.exec(oc)) !== null) { push(m[0]); }
                                    const rq2 = oc.match(reUrlRelQuoted) || [];
                                    rq2.forEach(q => push(q.slice(1, -1)));
                                    while ((m = reAssign.exec(oc)) !== null) {
                                        const u = m[2] || m[3] || m[4];
                                        if (u) push(u);
                                    }
                                }
                            }
                        }
                        // same-origin filter
                        const origin = location.origin;
                        let out = Array.from(urls).filter(u => {
                            try { return new URL(u, location.href).origin === origin; } catch (e) { return false; }
                        });
                        return out.slice(0, 50);
                    }""",
                    norm_label,
                )
            except Exception:
                links = []

            # Attribute-deep scan: search all attributes for values containing the detail pattern (generic)
            try:
                if detail_pattern and isinstance(detail_pattern, str):
                    attr_links = await page.evaluate(
                        r"""(detailPattern) => {
                            const urls = new Set();
                            const push = (u) => {
                                if (!u) return;
                                try { urls.add(new URL(u, location.href).href); } catch (e) {}
                            };
                            const els = Array.from(document.querySelectorAll("*"));
                            for (const el of els) {
                                for (const attr of (el.attributes || [])) {
                                    const v = attr.value || "";
                                    if (typeof v === "string" && v.includes(detailPattern)) {
                                        push(v);
                                    }
                                }
                            }
                            return Array.from(urls).slice(0, 50);
                        }""",
                        detail_pattern
                    )
                    if (not links) and attr_links:
                        links = attr_links
                    else:
                        # union
                        try:
                            links = list(dict.fromkeys((links or []) + (attr_links or [])))[:50]
                        except Exception:
                            pass
            except Exception:
                pass

            # Secondary fallback: scan scripts for URLs containing detail pattern
            try:
                if (not links) and detail_pattern:
                    script_links = await page.evaluate(
                        r"""(detailPattern) => {
                            const urls = new Set();
                            const push = (u) => {
                                if (!u) return;
                                try { urls.add(new URL(u, location.href).href); } catch (e) {}
                            };
                            const scripts = Array.from(document.scripts || []);
                            for (const s of scripts) {
                                const t = s.textContent || '';
                                const abs = t.match(/https?:\/\/[^\s"'()<>]+/g) || [];
                                abs.forEach(u => { if (u.includes(detailPattern)) push(u); });
                                const rel = t.match(/['"]\/[^"'()<>]+['"]/g) || [];
                                rel.forEach(q => {
                                    const u = q.slice(1, -1);
                                    if (u.includes(detailPattern)) push(u);
                                });
                            }
                            return Array.from(urls).slice(0, 20);
                        }""",
                        detail_pattern
                    )
                    if script_links and not links:
                        links = script_links
            except Exception:
                pass

            # If still empty and we have a label, try limited click-based discovery
            try:
                if (not links) and norm_label:
                    # Use direct text matching (best-effort)
                    loc = page.get_by_text(read_label or "", exact=False)
                    try:
                        count = await loc.count()
                    except Exception:
                        count = 0
                    discovered = set()
                    for i in range(min(count, 3)):
                        # Try opening in popup via middle click first
                        try:
                            async with page.expect_popup(timeout=3000) as pp:
                                await loc.nth(i).click(button="middle")
                            popup = await pp.value
                            try:
                                if popup and popup.url:
                                    discovered.add(popup.url)
                            finally:
                                await popup.close()
                            continue
                        except Exception:
                            pass
                        # Fallback: same-page URL change (SPA/history) or URL match via pattern, then go back
                        try:
                            old_url = page.url
                            await loc.nth(i).click()
                            try:
                                if detail_pattern:
                                    await page.wait_for_url(f"**{detail_pattern}**", timeout=3000)
                                else:
                                    await page.wait_for_timeout(150)
                                    for _ in range(10):
                                        if page.url != old_url:
                                            break
                                        await page.wait_for_timeout(300)
                                # Try to capture canonical/og:url even if URL didn't change
                                try:
                                    meta_url = await page.evaluate("""() => {
                                        const og = document.querySelector("meta[property='og:url']");
                                        if (og && og.content) return og.content;
                                        const ln = document.querySelector("link[rel='canonical']");
                                        return (ln && ln.href) ? ln.href : null;
                                    }""")
                                except Exception:
                                    meta_url = None
                                if meta_url and (meta_url != old_url):
                                    discovered.add(meta_url)
                                elif page.url != old_url:
                                    discovered.add(page.url)
                            except Exception:
                                pass
                            # Try to go back if URL changed
                            try:
                                await page.go_back()
                            except Exception:
                                pass
                        except Exception:
                            pass
                    # Filter discovered
                    if discovered:
                        base = page.url
                        from urllib.parse import urlparse, urljoin
                        same_origin = []
                        try:
                            base_origin = f"{urlparse(base).scheme}://{urlparse(base).netloc}"
                        except Exception:
                            base_origin = ""
                        for u in discovered:
                            try:
                                if base_origin and u.startswith(base_origin):
                                    same_origin.append(u)
                            except Exception:
                                pass
                        # Apply detail pattern preference
                        if detail_pattern:
                            same_origin = [u for u in same_origin if detail_pattern in u] or same_origin
                        links = list(dict.fromkeys(links + same_origin))[:20]
            except Exception:
                pass

            # If still empty, try generic click-based discovery on common clickable elements
            try:
                if not links:
                    loc2 = page.locator("[role='link'], [onclick], [data-href], [routerlink], [ng-reflect-router-link], button")
                    try:
                        count2 = await loc2.count()
                    except Exception:
                        count2 = 0
                    discovered2 = set()
                    for i in range(min(count2, 5)):
                        # Try opening in popup via middle click first
                        try:
                            async with page.expect_popup(timeout=3000) as pp:
                                await loc2.nth(i).click(button="middle")
                            popup = await pp.value
                            try:
                                if popup and popup.url:
                                    discovered2.add(popup.url)
                            finally:
                                await popup.close()
                            continue
                        except Exception:
                            pass
                        # Fallback: same-page URL change (SPA/history) or URL match via pattern, then go back
                        try:
                            old_url2 = page.url
                            await loc2.nth(i).click()
                            try:
                                if detail_pattern:
                                    await page.wait_for_url(f"**{detail_pattern}**", timeout=3000)
                                else:
                                    await page.wait_for_timeout(150)
                                    for _ in range(10):
                                        if page.url != old_url2:
                                            break
                                        await page.wait_for_timeout(300)
                                # Try to capture canonical/og:url even if URL didn't change
                                try:
                                    meta_url2 = await page.evaluate("""() => {
                                        const og = document.querySelector("meta[property='og:url']");
                                        if (og && og.content) return og.content;
                                        const ln = document.querySelector("link[rel='canonical']");
                                        return (ln && ln.href) ? ln.href : null;
                                    }""")
                                except Exception:
                                    meta_url2 = None
                                if meta_url2 and (meta_url2 != old_url2):
                                    discovered2.add(meta_url2)
                                elif page.url != old_url2:
                                    discovered2.add(page.url)
                            except Exception:
                                pass
                            # Try to go back if URL changed
                            try:
                                await page.go_back()
                            except Exception:
                                pass
                        except Exception:
                            pass
                    # Filter discovered URLs
                    if discovered2:
                        base = page.url
                        from urllib.parse import urlparse as _uparse
                        same_origin2 = []
                        try:
                            base_origin2 = f"{_uparse(base).scheme}://{_uparse(base).netloc}"
                        except Exception:
                            base_origin2 = ""
                        for u2 in discovered2:
                            try:
                                if base_origin2 and u2.startswith(base_origin2):
                                    same_origin2.append(u2)
                            except Exception:
                                pass
                        # Apply detail pattern preference if provided
                        if detail_pattern:
                            same_origin2 = [u for u in same_origin2 if detail_pattern in u] or same_origin2
                        links = list(dict.fromkeys((links or []) + same_origin2))[:20]
            except Exception:
                pass

            # Merge any network-captured links (same-origin), preferring detail_pattern
            try:
                from urllib.parse import urlparse as _uparse
                base_origin = ""
                try:
                    bu = _uparse(url)
                    base_origin = f"{bu.scheme}://{bu.netloc}" if (bu.scheme and bu.netloc) else ""
                except Exception:
                    base_origin = ""

                # Merge response-captured HTML pages
                if collected_links_py:
                    same_origin3 = []
                    for u2 in list(collected_links_py)[:50]:
                        try:
                            if base_origin and u2.startswith(base_origin):
                                same_origin3.append(u2)
                        except Exception:
                            pass
                    if detail_pattern:
                        same_origin3 = [u for u in same_origin3 if detail_pattern in u] or same_origin3
                    links = list(dict.fromkeys((links or []) + same_origin3))[:50]

                # Merge frame navigation URLs
                if nav_urls_py:
                    same_origin_nav = []
                    for u3 in list(nav_urls_py)[:50]:
                        try:
                            if base_origin and u3.startswith(base_origin):
                                same_origin_nav.append(u3)
                        except Exception:
                            pass
                    if detail_pattern:
                        same_origin_nav = [u for u in same_origin_nav if detail_pattern in u] or same_origin_nav
                    links = list(dict.fromkeys((links or []) + same_origin_nav))[:50]
            except Exception:
                pass

            # Safely retrieve HTML content, guarding against page/context closure
            try:
                html = await page.content()
            except Exception:
                # Recreate page once and retry content retrieval
                try:
                    await page.close()
                except Exception:
                    pass
                page = await context.new_page()
                try:
                    page.set_default_navigation_timeout(timeout_ms)
                    page.set_default_timeout(timeout_ms)
                except Exception:
                    pass
                try:
                    if "gosi.gov.sa" in url:
                        await page.goto(url, timeout=timeout_ms, wait_until="load")
                    else:
                        await page.goto(url, timeout=timeout_ms, wait_until="domcontentloaded")
                    html = await page.content()
                except Exception as e2:
                    await browser.close()
                    return f"__ERROR__: Playwright render+collect failed: {e2}", []
            await browser.close()
            return html, (links or [])
    except Exception as e:
        return f"__ERROR__: Playwright render+collect failed: {e}", []


def render_and_collect_links(
    url: str,
    read_label: Optional[str] = None,
    detail_pattern: Optional[str] = None,
    timeout_ms: int = 60000
) -> Tuple[bool, str, List[str]]:
    """
    Render a page dynamically and collect candidate detail links in a site-agnostic way:
    - anchors
    - data-href/data-url/href on non-anchor elements
    - onclick URL patterns
    - label-based nearest links
    Fallback to empty link list on failure.
    """
    try:
        html, links = asyncio.run(_render_and_collect_links_async(url, read_label=read_label, detail_pattern=detail_pattern, timeout_ms=timeout_ms))
        if isinstance(html, str) and html.startswith("__ERROR__"):
            return False, html, []
        return True, html, links
    except Exception as e:
        return False, f"__ERROR__: Playwright runtime failed: {e}", []


# New helper: GOSI per-card click discovery using Playwright (strict detail prefix)
def gosi_click_discover(url: str, detail_pattern: Optional[str] = None, timeout_ms: int = 60000) -> List[str]:
    try:
        from playwright.async_api import async_playwright  # lazy import
    except Exception:
        return []

    async def _run():
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True, args=["--disable-blink-features=AutomationControlled"])
                context = await browser.new_context(
                    locale="ar-SA",
                    timezone_id="Asia/Riyadh",
                    user_agent=DEFAULT_HEADERS["User-Agent"],
                    extra_http_headers={
                        "Accept-Language": DEFAULT_HEADERS.get("Accept-Language", "ar-SA,ar;q=0.9,en-US;q=0.8,en;q=0.7"),
                        "Accept": DEFAULT_HEADERS.get("Accept", "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"),
                    },
                )
                page = await context.new_page()
                try:
                    await page.goto(url, timeout=timeout_ms, wait_until="load")
                except Exception:
                    await browser.close()
                    return []
                try:
                    await page.wait_for_selector("#newsList", timeout=timeout_ms // 2)
                except Exception:
                    pass

                urls: List[str] = []
                # Progressive scroll to load more cards and optional "load more" clicks
                try:
                    for _ in range(8):
                        try:
                            await page.mouse.wheel(0, 1400)
                        except Exception:
                            pass
                        await page.wait_for_timeout(700)
                        # Try clicking Arabic "load more" buttons if present
                        try:
                            btn = await page.query_selector("text=عرض المزيد, text=المزيد")
                            if btn:
                                try:
                                    await btn.click()
                                    await page.wait_for_timeout(1200)
                                except Exception:
                                    pass
                        except Exception:
                            pass
                except Exception:
                    pass
                # Query card-like containers under #newsList
                try:
                    card_handles = await page.query_selector_all("#newsList div.newsItemDetails, #newsList article, #newsList div[class*='news'] div[class*='item']")
                except Exception:
                    card_handles = []
                for i, card in enumerate(card_handles[:30]):
                    # Ensure card is in viewport to trigger lazy-load of internal elements
                    try:
                        await card.scroll_into_view_if_needed()
                        await page.wait_for_timeout(200)
                    except Exception:
                        pass
                    href = None
                    # Descendant anchor first
                    try:
                        a = await card.query_selector("a[href]")
                        if a:
                            v = await a.get_attribute("href")
                            if v:
                                href = v
                    except Exception:
                        pass
                    # SPA attributes on card
                    if not href:
                        for attr in ["routerlink", "ng-reflect-router-link", "data-href", "data-url", "data-link", "data-target", "href"]:
                            try:
                                v = await card.get_attribute(attr)
                            except Exception:
                                v = None
                            if v:
                                href = v
                                break
                    # SPA attributes on descendants
                    if not href:
                        try:
                            descs = await card.query_selector_all("[routerlink], [ng-reflect-router-link], [data-href], [data-url], [data-link], [data-target], [href]")
                            for el in descs:
                                # skip normal anchors (handled above)
                                try:
                                    tag = await el.evaluate("el => el.tagName")
                                except Exception:
                                    tag = ""
                                if tag and tag.lower() == "a":
                                    continue
                                got = None
                                for attr in ["routerlink", "ng-reflect-router-link", "data-href", "data-url", "data-link", "data-target", "href"]:
                                    try:
                                        vv = await el.get_attribute(attr)
                                    except Exception:
                                        vv = None
                                    if vv:
                                        got = vv
                                        break
                                if got:
                                    href = got
                                    break
                        except Exception:
                            pass
                    # onclick URL patterns (card or descendants)
                    if not href:
                        try:
                            oc = await card.get_attribute("onclick") or ""
                        except Exception:
                            oc = ""
                        if oc:
                            import re as _re
                            m = (_re.search(r"'(https?://[^']+)'", oc)
                                 or _re.search(r'"(https?://[^"]+)"', oc)
                                 or _re.search(r"'(/[^']+)'", oc)
                                 or _re.search(r'"(/[^"]+)"', oc))
                            if m and m.group(1):
                                href = m.group(1)
                        if not href:
                            try:
                                oc_desc = await card.query_selector("[onclick]")
                                if oc_desc:
                                    oc2 = await oc_desc.get_attribute("onclick") or ""
                                    import re as _re
                                    m2 = (_re.search(r"'(https?://[^']+)'", oc2)
                                          or _re.search(r'"(https?://[^"]+)"', oc2)
                                          or _re.search(r"'(/[^']+)'", oc2)
                                          or _re.search(r'"(/[^"]+)"', oc2))
                                    if m2 and m2.group(1):
                                        href = m2.group(1)
                            except Exception:
                                pass
                    # Click capture if still not found
                    if not href:
                        clickable = None
                        try:
                            clickable = await card.query_selector("a, [routerlink], [ng-reflect-router-link], [data-href], [onclick]")
                        except Exception:
                            clickable = None
                        discovered = None
                        if clickable:
                            # Try popup via middle click
                            try:
                                async with page.expect_popup(timeout=3000) as pp:
                                    await clickable.click(button="middle")
                                popup = await pp.value
                                try:
                                    if popup and popup.url:
                                        discovered = popup.url
                                finally:
                                    try:
                                        await popup.close()
                                    except Exception:
                                        pass
                            except Exception:
                                # Same-tab SPA navigation
                                old = page.url
                                try:
                                    await clickable.click()
                                    try:
                                        if detail_pattern:
                                            await page.wait_for_url(f"**{detail_pattern}**", timeout=3000)
                                        else:
                                            await page.wait_for_timeout(250)
                                    except Exception:
                                        pass
                                    if page.url != old:
                                        discovered = page.url
                                    else:
                                        # Try canonical/og:url
                                        try:
                                            meta = await page.evaluate("""() => {
                                                const og = document.querySelector("meta[property='og:url']");
                                                if (og && og.content) return og.content;
                                                const ln = document.querySelector("link[rel='canonical']");
                                                return (ln && ln.href) ? ln.href : null;
                                            }""")
                                            if meta:
                                                discovered = meta
                                        except Exception:
                                            pass
                                except Exception:
                                    pass
                                # Go back
                                try:
                                    await page.go_back()
                                except Exception:
                                    pass
                        if discovered:
                            href = discovered
                    # Normalize and filter
                    if href:
                        try:
                            absu = urljoin(url, href)
                            from urllib.parse import urlparse as _uparse
                            bu = _uparse(url); ru = _uparse(absu)
                            if bu.netloc and ru.netloc and ru.scheme and (ru.netloc == bu.netloc):
                                if ((detail_pattern is None) or (detail_pattern in absu)) and _is_probable_html_url(absu):
                                    urls.append(absu)
                        except Exception:
                            pass

                await browser.close()
                # dedupe preserve order
                out: List[str] = []
                seen = set()
                for u2 in urls:
                    if u2 not in seen:
                        seen.add(u2)
                        out.append(u2)
                return out
        except Exception:
            return []

    try:
        return asyncio.run(_run())
    except Exception:
        return []

# -------------------------------
# RSS autodiscovery
# -------------------------------

def autodiscover_feed_links(base_url: str, html: str) -> List[str]:
    links: List[str] = []
    try:
        soup = BeautifulSoup(html, "html.parser")
        for link in soup.find_all("link"):
            rel = (link.get("rel") or [""])
            type_attr = (link.get("type") or "").lower()
            href = link.get("href")
            if not href:
                continue
            if "alternate" in [x.lower() for x in rel] and ("rss" in type_attr or "atom" in type_attr or "xml" in type_attr):
                links.append(urljoin(base_url, href))
    except Exception:
        pass
    return list(dict.fromkeys(links))  # dedupe preserve order


def parse_feed(feed_url: str, source_name: str) -> List[Dict]:
    d = feedparser.parse(feed_url)
    items: List[Dict] = []
    for e in d.entries[:20]:
        title = getattr(e, "title", "") or ""
        link = getattr(e, "link", "") or ""
        published = getattr(e, "published", "") or getattr(e, "updated", "") or ""
        items.append({
            "source": source_name,
            "source_type": "RSS",
            "title": title,
            "link": link,
            "date": published,
            "content": getattr(e, "summary", "") or getattr(e, "description", "") or "",
        })
    return items


# -------------------------------
# Static HTML extraction (heuristic)
# -------------------------------

def _largest_text_block(soup: BeautifulSoup) -> str:
    # Prefer <article>, then <main>, then div with most <p> text
    art = soup.find("article")
    if art:
        return art.get_text("\n", strip=True)

    main = soup.find("main")
    if main:
        return main.get_text("\n", strip=True)

    best_text = ""
    best_len = 0
    for div in soup.find_all("div"):
        ps = div.find_all("p")
        if len(ps) >= 2:
            text = "\n".join(p.get_text(" ", strip=True) for p in ps)
            l = len(text)
            if l > best_len:
                best_len = l
                best_text = text
    if best_text:
        return best_text

    # Fallback: whole page text
    return soup.get_text("\n", strip=True)[:8000]


def extract_listing_links(base_url: str, html: str) -> List[str]:
    soup = BeautifulSoup(html, "html.parser")
    # Try to find a container with many anchors
    candidates: List[Tuple[int, str]] = []  # (count, css_id)
    blocks = soup.find_all(["section", "div", "ul", "ol", "main", "article"])

    for i, b in enumerate(blocks):
        anchors = b.find_all("a", href=True)
        # Consider a block as newsy if many anchors with text present
        anchors = [a for a in anchors if (a.get_text(strip=True) and len(a.get_text(strip=True)) >= 5)]
        if len(anchors) >= 3:
            candidates.append((len(anchors), f"idx:{i}"))

    anchors: List[str] = []
    if candidates:
        # Choose largest block
        candidates.sort(reverse=True)
        idx = int(candidates[0][1].split(":")[1])
        container = blocks[idx]
        for a in container.find_all("a", href=True):
            txt = a.get_text(strip=True)
            if len(txt) >= 5:  # avoid nav items (reduced threshold for Arabic pages)
                anchors.append(urljoin(base_url, a["href"]))
    else:
        # Fallback: take all anchors on page
        for a in soup.find_all("a", href=True):
            txt = a.get_text(strip=True)
            if len(txt) >= 5:
                anchors.append(urljoin(base_url, a["href"]))

    # Deduplicate, prefer same-domain links
    anchors = list(dict.fromkeys(anchors))
    domain = urlparse(base_url).netloc
    same_domain = [u for u in anchors if urlparse(u).netloc == domain]
    if same_domain:
        anchors = same_domain

    # Secondary fallback: if still empty, accept any meaningful anchor (short Arabic text, title, aria-label)
    if not anchors:
        alt_anchors: List[str] = []
        for a in soup.find_all("a", href=True):
            txt = a.get_text(strip=True)
            title = a.get("title") or a.get("aria-label") or ""
            if txt or title:
                alt_anchors.append(urljoin(base_url, a["href"]))
        alt_anchors = list(dict.fromkeys(alt_anchors))
        same_domain_alt = [u for u in alt_anchors if urlparse(u).netloc == domain]
        anchors = same_domain_alt or alt_anchors

    return anchors[:10]


def extract_article(base_url: str, url: str, html: str) -> Dict:
    soup = BeautifulSoup(html, "html.parser")
    # Title heuristics - prefer specific meta tags over generic page title
    title = ""
    
    # 1. Try Open Graph title first (most reliable for articles)
    ogt = soup.find("meta", property="og:title")
    if ogt and ogt.get("content"):
        title = ogt["content"].strip()
    
    # 2. Try Twitter title
    if not title:
        twt = soup.find("meta", {"name": "twitter:title"})
        if twt and twt.get("content"):
            title = twt["content"].strip()
    
    # 3. Try h1 tag (most articles have a main heading)
    if not title:
        h1 = soup.find("h1")
        if h1:
            title = h1.get_text(strip=True)
    
    # 4. Try article header
    if not title:
        article = soup.find("article")
        if article:
            header = article.find(["h1", "h2", "header"])
            if header:
                title = header.get_text(strip=True)
    
    # 5. Fallback to page title (but clean it from site name suffix)
    if not title:
        if soup.title and soup.title.string:
            raw_title = soup.title.string.strip()
            # Remove common site name patterns (e.g., "Article Title | Site Name" or "Article Title - Site Name")
            import re as _re
            cleaned = _re.split(r'\s*[\|\-–—]\s*', raw_title)[0].strip()
            title = cleaned if cleaned else raw_title

    content_text = _largest_text_block(soup)
    date_text = ""
    og_date = soup.find("meta", property="article:published_time")
    if og_date and og_date.get("content"):
        date_text = og_date["content"].strip()
    # Fallback: parse Gregorian date from visible text when meta is missing
    if not date_text:
        try:
            txt_all = soup.get_text(" ", strip=True)
            import re as _re
            m = _re.search(r"\b(\d{4})[/-](\d{2})[/-](\d{2})\b", txt_all)
            if m:
                y, mn, d = m.group(1), m.group(2), m.group(3)
                date_text = f"{y}-{mn}-{d}"
        except Exception:
            pass

    return {
        "source": urlparse(base_url).netloc,
        "source_type": "URL_Static",
        "title": title[:300],
        "link": url,
        "date": date_text,
        "content": content_text[:10000],
    }


def derive_detail_pattern(sample_link: str) -> Optional[str]:
    try:
        p = urlparse(sample_link)
        path = p.path or ""
        parts = [seg for seg in path.split("/") if seg]
        if not parts:
            return None
        # If known segment exists, derive prefix up to it
        if "NewsDetails" in parts:
            idx = parts.index("NewsDetails")
            prefix = "/" + "/".join(parts[: idx + 1]) + "/"
            return prefix
        # Fallback: take up to first 3 segments but do NOT force trailing slash
        # This ensures query-style detail routes like '/details?p=123' are matched via '/details'
        prefix = "/" + "/".join(parts[: min(3, len(parts))])
        return prefix
    except Exception:
        return None


def _is_probable_html_url(u: str) -> bool:
    """
    Generic heuristic to exclude obvious non-HTML assets and prefer HTML pages.
    - Excludes common static asset extensions
    - Allows URLs without extension, with trailing '/', or with .html/.htm
    """
    try:
        from urllib.parse import urlparse as _uparse
        parsed = _uparse(u)
        path = parsed.path or ""
        # No path or endswith slash → likely HTML route
        if not path or path.endswith("/"):
            return True
        # Extract extension
        import os
        _, ext = os.path.splitext(path.lower())
        if not ext:
            return True
        if ext in (".html", ".htm"):
            return True
        # Common non-HTML assets
        non_html_exts = {
            ".css", ".js", ".mjs", ".map",
            ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".ico",
            ".woff", ".woff2", ".ttf", ".eot", ".otf",
            ".pdf", ".zip", ".rar", ".7z",
            ".mp3", ".mp4", ".webm", ".ogg",
            ".xml"
        }
        return ext not in non_html_exts
    except Exception:
        # Be permissive on errors
        return True


def _find_links_by_label(soup: BeautifulSoup, base_url: str, label: str) -> List[str]:
    links: List[str] = []
    try:
        label_norm = label.strip()
        if not label_norm:
            return links
        for tag_name in ["a", "button", "span", "div"]:
            for el in soup.find_all(tag_name):
                txt = el.get_text(strip=True) or ""
                if label_norm in txt:
                    # Common attributes used by SPAs
                    href = (
                        el.get("href")
                        or el.get("data-href")
                        or el.get("data-url")
                        or el.get("data-link")
                        or el.get("data-target")
                        or el.get("routerlink")
                        or el.get("ng-reflect-router-link")
                    )
                    if href:
                        links.append(urljoin(base_url, href))
                        continue
                    # Try nearest ancestor <a>
                    parent_a = el.find_parent("a", href=True)
                    if parent_a and parent_a.get("href"):
                        links.append(urljoin(base_url, parent_a.get("href")))
                        continue
                    # Parse onclick attribute for URL patterns (absolute + relative)
                    onclick = el.get("onclick") or ""
                    if onclick:
                        try:
                            import re
                            m = (re.search(r"'(https?://[^']+)'", onclick)
                                 or re.search(r'"(https?://[^"]+)"', onclick)
                                 or re.search(r"'(/[^']+)'", onclick)
                                 or re.search(r'"(/[^"]+)"', onclick))
                            if m and m.group(1):
                                links.append(urljoin(base_url, m.group(1)))
                        except Exception:
                            pass
    except Exception:
        pass
    return list(dict.fromkeys(links))


def _find_links_by_attrs(soup: BeautifulSoup, base_url: str, detail_pattern: Optional[str] = None) -> List[str]:
    """
    Site-agnostic attribute-based link harvesting from static HTML:
    - href on non-anchor elements
    - data-href, data-url, data-link, data-target
    - routerlink, ng-reflect-router-link (Angular)
    Applies optional detail_pattern filter and same-origin dedupe afterwards (handled by caller).
    """
    links: List[str] = []
    try:
        attrs = ["href", "data-href", "data-url", "data-link", "data-target", "routerlink", "ng-reflect-router-link"]
        for el in soup.find_all(True):  # any tag
            # Skip normal anchors; they will be handled separately
            if el.name and el.name.lower() == "a":
                continue
            href = None
            for a in attrs:
                v = el.get(a)
                if v:
                    href = v
                    break
            if href:
                if (detail_pattern is None) or (detail_pattern in href):
                    links.append(urljoin(base_url, href))
        # Also inspect onclick attributes for URL patterns
        for el in soup.find_all(attrs={"onclick": True}):
            oc = el.get("onclick") or ""
            try:
                import re
                mabs = re.findall(r"(https?://[^\s'\"()<>]+)", oc) or []
                for u in mabs:
                    if (detail_pattern is None) or (detail_pattern in u):
                        links.append(urljoin(base_url, u))
                mrel = re.findall(r"['\"](/[^'\"()<>]+)['\"]", oc) or []
                for u in mrel:
                    if (detail_pattern is None) or (detail_pattern in u):
                        links.append(urljoin(base_url, u))
            except Exception:
                pass
    except Exception:
        pass
    return list(dict.fromkeys(links))


def extract_listing_cards(base_url: str, listing_html: str, max_items: int = 20, candidate_links: Optional[List[str]] = None, title_href_pairs: Optional[List[Dict]] = None) -> List[Dict]:
    """
    Site-agnostic fallback: extract visible listing cards (titles/dates/summaries) from the rendered HTML
    without following detail links. Inspired by the old url_snap logic.
    """
    items: List[Dict] = []
    try:
        soup = BeautifulSoup(listing_html, "html.parser")

        # Primary containers as per old code
        containers = soup.select("div.newsItemDetails")

        # Generic fallbacks if no primary containers
        if not containers:
            containers = soup.select("article")
        if not containers:
            containers = soup.select("div[class*='news'] div[class*='item'], div[class*='card'], div[class*='post']")

        def _text(el) -> str:
            try:
                return (el.get_text(" ", strip=True) or "")
            except Exception:
                return ""

        def _find_title(c) -> str:
            for sel in ["h1", "h2", "h3", "header h1", "header h2", "header h3", ".title", "[class*=title]"]:
                el = c.select_one(sel)
                if el:
                    t = _text(el)
                    if t:
                        return t
            return ""

        def _find_date(c) -> str:
            # class-based first
            for sel in ["span.newsItemDate", ".date", "[class*=date]", "time[datetime]", "time"]:
                el = c.select_one(sel)
                if el:
                    txt = el.get("datetime") or _text(el)
                    if txt:
                        return txt
            # regex fallback: YYYY-MM-DD or DD/MM/YYYY (simple)
            import re as _re
            txt_all = _text(c)
            m = _re.search(r"\d{4}-\d{2}-\d{2}", txt_all) or _re.search(r"\b\d{1,2}/\d{1,2}/\d{2,4}\b", txt_all)
            return m.group(0) if m else ""

        def _find_summary(c) -> str:
            for sel in ["p", ".summary", "[class*=summary] p"]:
                el = c.select_one(sel)
                if el:
                    s = _text(el)
                    if s:
                        return s
            # fallback: aggregate first 2-3 p tags
            ps = c.find_all("p")
            if ps:
                return " ".join((_text(p) for p in ps[:3] if _text(p)))
            return ""

        def _find_link(c, idx: int) -> str:
            # Prefer descendant anchors
            a = c.select_one("a[href]")
            if a and a.get("href"):
                try:
                    return urljoin(base_url, a.get("href"))
                except Exception:
                    pass
            # Attributes commonly used by SPAs
            for attr in ["data-href", "data-url", "data-link", "routerlink", "ng-reflect-router-link", "href"]:
                v = c.get(attr)
                if v:
                    try:
                        return urljoin(base_url, v)
                    except Exception:
                        pass
            # onclick URL patterns
            oc = c.get("onclick") or ""
            if oc:
                import re as _re
                m = (_re.search(r"'(https?://[^']+)'", oc)
                     or _re.search(r'"(https?://[^"]+)"', oc)
                     or _re.search(r"'(/[^']+)'", oc)
                     or _re.search(r'"(/[^"]+)"', oc))
                if m and m.group(1):
                    try:
                        return urljoin(base_url, m.group(1))
                    except Exception:
                        pass
            # Candidate mapping by title or index (for listing-card fallback)
            try:
                # Title-based mapping using discovered pairs
                if title_href_pairs:
                    def _norm(s: str) -> str:
                        try:
                            import re
                            t = (s or "").strip()
                            t = re.sub(r"[\u064B-\u065F\u0670\u0640]", "", t)  # diacritics + tatweel
                            t = re.sub(r"[إأآٱ]", "ا", t)
                            t = t.replace("ى", "ي").replace("\u200e", "").replace("\u200f", "").lower()
                            return t
                        except Exception:
                            return (s or "").strip().lower()
                    card_title = _norm(_find_title(c))
                    best = None
                    best_len = 0
                    for pair in title_href_pairs:
                        pt = _norm(pair.get("title", ""))
                        if pt and card_title and (pt in card_title or card_title in pt):
                            l = len(pt)
                            if l > best_len:
                                best = pair
                                best_len = l
                    if best and best.get("href"):
                        return best["href"]
                # Index-based mapping using candidate_links
                if candidate_links and idx < len(candidate_links):
                    return candidate_links[idx]
            except Exception:
                pass
            # Final fallback: for GOSI, never return listing URL; else keep compatibility
            try:
                if "gosi.gov.sa" in base_url:
                    return ""
            except Exception:
                pass
            return base_url

        for idx, c in enumerate(containers[:max_items]):
            title = _find_title(c)
            summary = _find_summary(c)
            if not (title or summary):
                continue
            date_text = _find_date(c)
            link = _find_link(c, idx)

            # GOSI-specific safe reconstruction using sample prefix and date when no link found
            try:
                if ("gosi.gov.sa" in base_url) and (not link or link == base_url) and date_text:
                    import re as _re
                    m = _re.search(r"(\d{4})-(\d{2})-(\d{2})", date_text)
                    if m:
                        yyyy, mm, dd = m.group(1), m.group(2), m.group(3)
                        ddmmyyyy = f"{dd}{mm}{yyyy}"
                        # Try multiple section ids to find a valid NewsDetails URL
                        for sec in [1, 2, 3, 4, 5]:
                            candidate_path = f"/ar/MediaCenter/News/NewsDetails/{sec}/{ddmmyyyy}"
                            candidate = urljoin(base_url, candidate_path)
                            st, _ = http_get(candidate, timeout=10)
                            if st == 200:
                                link = candidate
                                break
            except Exception:
                pass

            items.append({
                "source": urlparse(base_url).netloc,
                "source_type": "URL_Static",
                "title": (title or "")[:300],
                "link": link,
                "date": date_text or "",
                "content": (summary or "")[:10000],
            })
    except Exception:
        return []
    return items


def static_collect_with_hints(base_url: str, listing_html: str, detail_pattern: Optional[str] = None, read_more_label: Optional[str] = None) -> Tuple[List[Dict], List[Dict]]:
    items: List[Dict] = []
    errors: List[Dict] = []

    # 1) Try RSS autodiscovery
    feeds = autodiscover_feed_links(base_url, listing_html)
    for f in feeds[:2]:
        try:
            items.extend(parse_feed(f, source_name=urlparse(base_url).netloc))
        except Exception as e:
            errors.append({"url": base_url, "error": f"feed parse failed: {e}"})
    if items:
        return items, errors

    # 2) Collect anchors using hints
    soup = BeautifulSoup(listing_html, "html.parser")
    anchors: List[str] = []

    try:
        if detail_pattern:
            for a in soup.find_all("a", href=True):
                href = a.get("href") or ""
                if detail_pattern in href:
                    anchors.append(urljoin(base_url, href))
    except Exception:
        pass

    label = (read_more_label or "").strip()
    if label:
        anchors.extend(_find_links_by_label(soup, base_url, label))

    # Attribute-based discovery (routerlink/data-href/etc.)
    try:
        anchors.extend(_find_links_by_attrs(soup, base_url, detail_pattern=detail_pattern))
    except Exception:
        pass

    # Deduplicate, prefer same-domain
    anchors = list(dict.fromkeys(anchors))
    domain = urlparse(base_url).netloc
    same_domain = [u for u in anchors if urlparse(u).netloc == domain]
    if same_domain:
        anchors = same_domain

    # Prefer detail pattern when available
    try:
        if detail_pattern:
            preferred = [u for u in anchors if detail_pattern in u]
            if preferred:
                anchors = preferred
    except Exception:
        pass

    # Filter to probable HTML pages only
    try:
        anchors = [u for u in anchors if _is_probable_html_url(u)]
    except Exception:
        pass

    # 3) Fallback to heuristic extraction if no anchors found
    if not anchors:
        anchors = extract_listing_links(base_url, listing_html)

    if not anchors:
        errors.append({"url": base_url, "error": "no anchors found on listing"})
        return items, errors

    # 4) Fetch details and extract articles
    for href in anchors[:10]:
        status, html = http_get(href, timeout=25)
        if status != 200:
            errors.append({"url": href, "error": f"detail fetch status {status}"})
            continue
        try:
            items.append(extract_article(base_url, href, html))
        except Exception as e:
            errors.append({"url": href, "error": f"detail parse failed: {e}"})

    return items, errors


def static_collect(base_url: str, listing_html: str) -> Tuple[List[Dict], List[Dict]]:
    items: List[Dict] = []
    errors: List[Dict] = []

    # 1) Try RSS autodiscovery
    feeds = autodiscover_feed_links(base_url, listing_html)
    for f in feeds[:2]:
        try:
            items.extend(parse_feed(f, source_name=urlparse(base_url).netloc))
        except Exception as e:
            errors.append({"url": base_url, "error": f"feed parse failed: {e}"})
    if items:
        return items, errors

    # 2) Heuristic listing extraction
    anchors = extract_listing_links(base_url, listing_html)

    # Filter to probable HTML pages only
    try:
        anchors = [u for u in anchors if _is_probable_html_url(u)]
    except Exception:
        pass

    if not anchors:
        errors.append({"url": base_url, "error": "no anchors found on listing"})
        return items, errors

    for href in anchors:
        if not _is_probable_html_url(href):
            continue
        status, html = http_get(href, timeout=25)
        if status != 200:
            errors.append({"url": href, "error": f"detail fetch status {status}"})
            continue
        try:
            items.append(extract_article(base_url, href, html))
        except Exception as e:
            errors.append({"url": href, "error": f"detail parse failed: {e}"})
    return items, errors


# -------------------------------
# Unified Runner
# -------------------------------

def run_unified_sources(url_sources: List[Dict[str, str]], profile_slug: Optional[str] = None) -> Dict[str, List[Dict]]:
    """
    url_sources: [{"url": str, "mode": "auto|force_static|force_dynamic", "sample_link": Optional[str]}]
    Returns: {"items": [...], "errors": [...]}
    """
    print(f"[Sources] {len(url_sources)} sources to process")
    items: List[Dict] = []
    errors: List[Dict] = []

    def _static_path(u: str, detail_pattern: Optional[str], read_label: Optional[str]) -> Tuple[List[Dict], List[Dict]]:
        print(f"  [static] Fetch listing: {u}")
        st, html = http_get(u, timeout=30)
        print(f"  [static] listing status={st}")
        if st != 200:
            return [], [{"url": u, "error": f"listing fetch status {st}"}]
        items_s, errors_s = static_collect_with_hints(u, html, detail_pattern=detail_pattern, read_more_label=read_label)
        print(f"  [static] items={len(items_s)} errors={len(errors_s)}")
        return items_s, errors_s

    def _dynamic_path(u: str, detail_pattern: Optional[str], read_label: Optional[str]) -> Tuple[List[Dict], List[Dict]]:
        """
        Generic dynamic collector:
        - Render with Playwright (keep stylesheets).
        - Collect candidate links via anchors, data-* attrs, onclick URLs, and label-based nearest links.
        - If links found, fetch details directly; else, fall back to static_collect_with_hints on rendered HTML.
        """
        items_collected: List[Dict] = []
        errors: List[Dict] = []

        print(f"  [dynamic] Render listing: {u}")
        ok, html, links = render_and_collect_links(u, read_label=read_label, detail_pattern=detail_pattern, timeout_ms=20000)
        if not ok:
            print(f"  [dynamic] render failed: {html}")
            return [], [{"url": u, "error": html}]
        try:
            print(f"  [dynamic] candidates links={len(links)}")
        except Exception:
            pass

        # Build title/href pairs from listing container (GOSI-specific structure)
        title_href_pairs: List[Dict] = []
        try:
            soup_pairs = BeautifulSoup(html, "html.parser")
            cont = soup_pairs.select_one("#newsList")
            if cont:
                # Helper to normalize Arabic text for title matching
                def _norm_ar(s: str) -> str:
                    try:
                        import re
                        t = (s or "").strip()
                        t = re.sub(r"[\u064B-\u065F\u0670\u0640]", "", t)  # diacritics + tatweel
                        t = re.sub(r"[إأآٱ]", "ا", t)
                        t = t.replace("ى", "ي").replace("\u200e", "").replace("\u200f", "").lower()
                        return t
                    except Exception:
                        return (s or "").strip().lower()
                # Scan card-like containers and descendants for a real detail href
                cards = cont.select("div.newsItemDetails, article, div[class*='news'] div[class*='item']")
                for card in cards:
                    title_txt = ""
                    for sel in ["h1", "h2", "h3", ".title", "[class*=title]"]:
                        el = card.select_one(sel)
                        if el:
                            title_txt = el.get_text(strip=True) or ""
                            if title_txt:
                                break
                    # Try descendant anchors first
                    href = ""
                    a = card.select_one("a[href]")
                    if a and a.get("href"):
                        href = a.get("href") or ""
                    # SPA attributes on the card node
                    if not href:
                        for attr in ["routerlink", "ng-reflect-router-link", "data-href", "data-url", "data-link", "data-target", "href"]:
                            v = card.get(attr)
                            if v:
                                href = v
                                break
                    # SPA attributes on descendants within the card
                    if not href:
                        try:
                            for el in card.select("[routerlink], [ng-reflect-router-link], [data-href], [data-url], [data-link], [data-target], [href]"):
                                # skip normal anchors as already handled
                                if el.name and el.name.lower() == "a" and el.get("href"):
                                    continue
                                for attr in ["routerlink", "ng-reflect-router-link", "data-href", "data-url", "data-link", "data-target", "href"]:
                                    v = el.get(attr)
                                    if v:
                                        href = v
                                        break
                                if href:
                                    break
                        except Exception:
                            pass
                    # onclick URL patterns (card node)
                    if not href:
                        oc = card.get("onclick") or ""
                        if oc:
                            import re as _re
                            m = (_re.search(r"'(https?://[^']+)'", oc)
                                 or _re.search(r'"(https?://[^"]+)"', oc)
                                 or _re.search(r"'(/[^']+)'", oc)
                                 or _re.search(r'"(/[^"]+)"', oc))
                            if m and m.group(1):
                                href = m.group(1)
                    # onclick URL patterns (descendants)
                    if not href:
                        try:
                            import re as _re
                            for el in card.select("[onclick]"):
                                oc2 = el.get("onclick") or ""
                                m2 = (_re.search(r"'(https?://[^']+)'", oc2)
                                      or _re.search(r'"(https?://[^"]+)"', oc2)
                                      or _re.search(r"'(/[^']+)'", oc2)
                                      or _re.search(r'"(/[^"]+)"', oc2))
                                if m2 and m2.group(1):
                                    href = m2.group(1)
                                    break
                        except Exception:
                            pass
                    # Normalize and filter to same-origin + detail_pattern (sample-derived prefix)
                    if href:
                        absu = urljoin(u, href)
                        from urllib.parse import urlparse as _uparse
                        bu = _uparse(u)
                        ru = _uparse(absu)
                        if bu.netloc and ru.netloc and ru.scheme and (ru.netloc == bu.netloc):
                            if ((detail_pattern is None) or (detail_pattern in absu)) and _is_probable_html_url(absu):
                                title_href_pairs.append({"title": title_txt or card.get_text(strip=True) or "", "href": absu})
                # Fallback: include plain anchors under #newsList if any were missed
                for a in cont.select("a[href]"):
                    href = a.get("href") or ""
                    txt = a.get_text(strip=True) or ""
                    if href and txt:
                        absu = urljoin(u, href)
                        from urllib.parse import urlparse as _uparse
                        bu = _uparse(u)
                        ru = _uparse(absu)
                        if bu.netloc and ru.netloc and ru.scheme and (ru.netloc == bu.netloc):
                            if ((detail_pattern is None) or (detail_pattern in absu)) and _is_probable_html_url(absu):
                                title_href_pairs.append({"title": txt, "href": absu})
                # De-duplicate preserving order
                seen = set()
                dedup_pairs: List[Dict] = []
                for pr in title_href_pairs:
                    h = pr.get("href")
                    if h and h not in seen:
                        seen.add(h)
                        dedup_pairs.append(pr)
                title_href_pairs = dedup_pairs
        except Exception:
            pass
        print(f"  [dynamic] title/href pairs={len(title_href_pairs)}")
        # Fallback: extract links via regex from rendered HTML when dynamic harvesting yields none
        try:
            if (not links) and html and isinstance(html, str):
                import re
                raw_links = []
                # Capture hrefs pointing to detail paths, absolute or relative
                for m in re.findall(r'href=["\\\']([^"\\\']*NewsDetails[^"\\\']*)["\\\']', html):
                    raw_links.append(m)
                for m in re.findall(r'(https?://[^\\s"\\\']*NewsDetails[^\\s"\\\']*)', html):
                    raw_links.append(m)
                # De-dup and normalize to absolute
                normd = []
                for h in list(dict.fromkeys(raw_links))[:50]:
                    try:
                        normd.append(urljoin(u, h))
                    except Exception:
                        pass
                if normd:
                    links = normd
        except Exception:
            pass

        # If dynamic link harvesting succeeded, fetch details; else fallback to static heuristics
        pair_links = [pr.get("href") for pr in (title_href_pairs or []) if pr.get("href")]
        try:
            link_list = list(dict.fromkeys((links or []) + pair_links))
        except Exception:
            link_list = list(dict.fromkeys(links or []))
        # Prefer detail pattern if provided
        if detail_pattern:
            preferred = [u for u in link_list if detail_pattern in u]
            link_list = preferred or link_list
        # Filter to probable HTML pages only
        link_list = [u for u in link_list if _is_probable_html_url(u)]
        # GOSI-specific: strengthen candidates via per-card click discovery (strict prefix)
        try:
            if "gosi.gov.sa" in u and detail_pattern:
                more = gosi_click_discover(u, detail_pattern, timeout_ms=60000)
                if more:
                    link_list = list(dict.fromkeys(link_list + more))
        except Exception:
            pass
        print(f"  [dynamic] detail targets={len(link_list)}")
        if link_list:
            for href in link_list[:10]:
                status, dhtml = http_get(href, timeout=25)
                try:
                    print(f"    [detail] status={status} url={href}")
                except Exception:
                    pass
                if status != 200:
                    errors.append({"url": href, "error": f"detail fetch status {status}"})
                    continue
                # If the detail page is JS-gated or too thin, render dynamically as a fallback
                use_dynamic_detail = False
                try:
                    if isinstance(dhtml, str):
                        if "This website requires JavaScript" in dhtml:
                            use_dynamic_detail = True
                        elif len(dhtml) < 800:
                            use_dynamic_detail = True
                except Exception:
                    pass
                if use_dynamic_detail:
                    ok2, dhtml2 = render_html(href, wait_selector=None, timeout_ms=40000)
                    if ok2 and isinstance(dhtml2, str) and not dhtml2.startswith("__ERROR__"):
                        dhtml = dhtml2
                try:
                    items_collected.append(extract_article(u, href, dhtml))
                except Exception as e:
                    errors.append({"url": href, "error": f"detail parse failed: {e}"})
            try:
                print(f"  [dynamic] collected items={len(items_collected)} errors={len(errors)}")
            except Exception:
                pass
            # If detail fetches are poor (JS placeholder or very short content), fallback to listing snapshot cards
            try:
                poor = (not items_collected) or all((("This website requires JavaScript" in (it.get("content") or "")) or (len((it.get("content") or "")) < 200)) for it in items_collected)
            except Exception:
                poor = False
            if poor:
                cards = extract_listing_cards(u, html, candidate_links=link_list, title_href_pairs=title_href_pairs)
                if cards:
                    # Dynamic pipeline fallback: mark as URL_Dynamic
                    try:
                        for it in cards:
                            if isinstance(it, dict):
                                it["source_type"] = "URL_Dynamic"
                    except Exception:
                        pass
                    return cards, []
            # Augment with static hints if underfilled (<10 items)
            try:
                if len(items_collected) < 10:
                    prev_count = len(items_collected)
                    more_items, more_errors = static_collect_with_hints(u, html, detail_pattern=detail_pattern, read_more_label=read_label)
                    # Filter to detail_pattern links when provided
                    try:
                        if detail_pattern:
                            more_items = [it for it in (more_items or []) if detail_pattern in (it.get("link") or "")]
                    except Exception:
                        pass
                    # Merge unique by link and cap to 10
                    existing_links = set()
                    try:
                        existing_links = set([it.get("link") for it in items_collected if it.get("link")])
                    except Exception:
                        existing_links = set()
                    for it in more_items or []:
                        lnk = it.get("link")
                        if lnk and (lnk not in existing_links):
                            items_collected.append(it)
                            existing_links.add(lnk)
                            if len(items_collected) >= 10:
                                break
                    errors.extend(more_errors or [])
                    try:
                        print(f"  [augment] static hints added count={len(items_collected) - prev_count}")
                    except Exception:
                        pass
            except Exception:
                pass
            # Augment with listing snapshot cards to reach top 10 using date-based reconstruction and title pairing
            try:
                if len(items_collected) < 10:
                    cards2 = extract_listing_cards(u, html, candidate_links=link_list, title_href_pairs=title_href_pairs)
                    existing_links = set()
                    try:
                        existing_links = set([it.get("link") for it in items_collected if it.get("link")])
                    except Exception:
                        existing_links = set()
                    for it in (cards2 or []):
                        lnk = it.get("link")
                        if not lnk:
                            continue
                        # Respect detail_pattern when provided
                        if detail_pattern and (detail_pattern not in lnk):
                            continue
                        if lnk in existing_links:
                            continue
                        items_collected.append(it)
                        existing_links.add(lnk)
                        if len(items_collected) >= 10:
                            break
            except Exception:
                pass
            try:
                print(f"  [dynamic] collected items={len(items_collected)} errors={len(errors)}")
            except Exception:
                pass
            # Mark dynamic provenance for all items collected via dynamic pipeline
            try:
                for it in items_collected:
                    if isinstance(it, dict):
                        it["source_type"] = "URL_Dynamic"
            except Exception:
                pass
            return items_collected, errors

        # Fallback: snapshot listing cards (titles/dates/summaries) if detail links aren’t discoverable
        cards = extract_listing_cards(u, html, candidate_links=link_list, title_href_pairs=title_href_pairs)
        try:
            print(f"  [fallback] listing-cards used count={len(cards)}")
        except Exception:
            pass
        if cards:
            # Dynamic pipeline fallback: mark as URL_Dynamic
            try:
                for it in cards:
                    if isinstance(it, dict):
                        it["source_type"] = "URL_Dynamic"
            except Exception:
                pass
            return cards, []

        # Else fallback to existing static logic on the rendered HTML (anchor-based)
        its, errs = static_collect_with_hints(u, html, detail_pattern=detail_pattern, read_more_label=read_label)
        # Items gathered as part of dynamic fallback should be marked URL_Dynamic
        try:
            for it in its:
                if isinstance(it, dict):
                    it["source_type"] = "URL_Dynamic"
        except Exception:
            pass
        return its, errs

    for idx, src in enumerate(url_sources):
        u = src.get("url") or ""
        mode = (src.get("mode") or "auto").lower()
        sample = src.get("sample_link")
        detail_pattern = derive_detail_pattern(sample) if sample else None
        read_label = src.get("read_more_label")
        try:
            print(f"[Source {idx+1}/{len(url_sources)}] url={u} mode={mode} detail_prefix={detail_pattern or '-'} read_more_label={read_label or '-'}")
        except Exception:
            pass

        if not u:
            errors.append({"url": u, "error": "missing url"})
            continue

        try:
            if mode == "force_static":
                its, errs = _static_path(u, detail_pattern, read_label)
                try:
                    print(f"[source] static path items={len(its)} errors={len(errs)}")
                except Exception:
                    pass
                items.extend(its); errors.extend(errs)
            elif mode == "force_dynamic":
                # Optional validation using sample_link
                if sample:
                    ok, sample_html = render_html(sample, wait_selector=None, timeout_ms=40000)
                    if not ok or not sample_html or sample_html.startswith("__ERROR__"):
                        errors.append({"url": sample, "error": "sample_link dynamic validation failed"})
                its, errs = _dynamic_path(u, detail_pattern, read_label)
                try:
                    print(f"[source] dynamic path items={len(its)} errors={len(errs)}")
                except Exception:
                    pass
                items.extend(its); errors.extend(errs)
            else:
                # auto: try static then fallback to dynamic if too few
                its, errs = _static_path(u, detail_pattern, read_label)
                try:
                    print(f"[source] static path items={len(its)} errors={len(errs)}")
                except Exception:
                    pass
                if len(its) >= 1:
                    items.extend(its); errors.extend(errs)
                else:
                    print("[source] static path yielded none, trying dynamic ...")
                    its2, errs2 = _dynamic_path(u, detail_pattern, read_label)
                    try:
                        print(f"[source] dynamic path items={len(its2)} errors={len(errs2)}")
                    except Exception:
                        pass
                    items.extend(its2)
                    if its2:
                        # Dynamic succeeded; suppress static-path errors to avoid misleading “no anchors found”
                        errors.extend(errs2)
                    else:
                        errors.extend(errs + errs2)
        except Exception as e:
            errors.append({"url": u, "error": f"runner exception: {e}"})
            continue

    try:
        print(f"[Sources] cumulative items={len(items)} errors={len(errors)}")
    except Exception:
        pass
    return {"items": items, "errors": errors}
