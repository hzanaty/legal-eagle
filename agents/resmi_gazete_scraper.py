"""
Resmi Gazete (Turkish Official Gazette) specialized scraper.

Handles date-based URL generation and HTML summary extraction.
Does NOT download PDFs - relies on HTML summaries and glossary filtering.
"""

from datetime import datetime, timedelta
from typing import Dict, List, Tuple
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7"
}


def http_get(url: str, timeout: int = 20, retries: int = 3) -> Tuple[int, str]:
    """Simple HTTP GET with retries."""
    last_err = None
    for attempt in range(retries):
        try:
            r = requests.get(url, headers=DEFAULT_HEADERS, timeout=timeout)
            return r.status_code, r.text
        except Exception as e:
            last_err = e
            if attempt < retries - 1:
                try:
                    import time
                    time.sleep(1.0)
                except Exception:
                    pass
    return -1, f"HTTP error: {last_err or 'unknown'}"


def generate_date_urls(base_url: str, days_back: int = 7) -> List[str]:
    """
    Generate Resmi Gazete URLs for the last N days.
    
    Format: https://www.resmigazete.gov.tr/DD.MM.YYYY
    Example: https://www.resmigazete.gov.tr/19.02.2026
    
    Args:
        base_url: Base gazette URL (e.g., https://www.resmigazete.gov.tr/)
        days_back: How many days to go back (default: 7)
    
    Returns:
        List of date-templated URLs
    """
    urls = []
    
    # Add today's URL (base URL itself)
    urls.append(base_url.rstrip('/'))
    
    # Add past days
    for i in range(1, days_back):
        date = datetime.now() - timedelta(days=i)
        # Format: DD.MM.YYYY
        date_str = date.strftime("%d.%m.%Y")
        url = f"{base_url.rstrip('/')}/{date_str}"
        urls.append(url)
    
    return urls


def extract_gazette_summary(url: str, html: str, date_str: str) -> List[Dict]:
    """
    Extract gazette items from the daily summary page HTML.
    
    Args:
        url: The gazette URL for this date
        html: HTML content of the page
        date_str: Date string for this gazette (DD.MM.YYYY)
    
    Returns:
        List of news items with title, content (summary), link, date
    """
    items: List[Dict] = []
    
    try:
        soup = BeautifulSoup(html, "html.parser")
        
        # Strategy 1: Look for common gazette listing patterns
        # The page typically has a table or list of gazette entries
        
        # Try finding gazette entries in various container patterns
        containers = []
        
        # Pattern 1: Look for divs/sections with gazette-related classes
        containers.extend(soup.select("div[class*='gazette'], div[class*='resmi'], section[class*='gazette']"))
        
        # Pattern 2: Look for table rows (common for gazette listings)
        containers.extend(soup.select("table tr"))
        
        # Pattern 3: Look for article tags
        containers.extend(soup.select("article"))
        
        # Pattern 4: Look for list items
        containers.extend(soup.select("ul li, ol li"))
        
        # Pattern 5: Generic divs with links (fallback)
        if not containers:
            containers = soup.select("div")
        
        seen_titles = set()
        
        for container in containers:
            # Try to extract title and summary
            title = ""
            content = ""
            link = url  # Default to the main gazette URL
            
            # Look for headings
            heading = container.find(['h1', 'h2', 'h3', 'h4', 'h5', 'h6'])
            if heading:
                title = heading.get_text(strip=True)
            
            # If no heading, try strong/b tags
            if not title:
                strong = container.find(['strong', 'b'])
                if strong:
                    title = strong.get_text(strip=True)
            
            # If still no title, use first text in container
            if not title:
                text = container.get_text(strip=True)
                if text and len(text) > 10:
                    # Take first line or first 200 chars as title
                    lines = text.split('\n')
                    title = lines[0][:200] if lines else text[:200]
            
            # Extract content/summary (all text in container)
            content = container.get_text("\n", strip=True)
            
            # Look for PDF link
            pdf_link = container.find('a', href=lambda h: h and '.pdf' in h.lower())
            if pdf_link and pdf_link.get('href'):
                link = urljoin(url, pdf_link.get('href'))
            else:
                # Look for any link
                any_link = container.find('a', href=True)
                if any_link and any_link.get('href'):
                    href = any_link.get('href')
                    # Skip navigation/menu links
                    if not any(skip in href.lower() for skip in ['#', 'javascript:', 'mailto:']):
                        link = urljoin(url, href)
            
            # Quality filters
            if not title or len(title) < 10:
                continue
            
            if title in seen_titles:
                continue
            
            # Avoid navigation/header items
            if any(skip in title.lower() for skip in ['menü', 'menu', 'arama', 'search', 'giriş', 'login']):
                continue
            
            seen_titles.add(title)
            
            items.append({
                "source": "resmigazete.gov.tr",
                "source_type": "URL_Static",
                "title": title[:300],
                "link": link,
                "date": date_str,
                "content": content[:2000],
            })
            
            # Limit to top 20 items per day
            if len(items) >= 20:
                break
        
        # If we found very few items, try a simpler approach: extract all text with gazette keywords
        if len(items) < 3:
            # Look for gazette-related keywords in the page
            gazette_keywords = ['resmi gazete', 'sayı', 'tarih', 'kanun', 'yönetmelik', 'tebliğ', 'genelge']
            
            # Find all paragraphs and divs
            all_blocks = soup.find_all(['p', 'div', 'td'])
            
            for block in all_blocks:
                text = block.get_text(strip=True)
                
                # Check if this block contains gazette-related content
                if any(keyword in text.lower() for keyword in gazette_keywords) and len(text) > 30:
                    # Extract title (first 200 chars or first line)
                    lines = text.split('\n')
                    title = lines[0][:200] if lines else text[:200]
                    
                    if title in seen_titles or len(title) < 10:
                        continue
                    
                    seen_titles.add(title)
                    
                    items.append({
                        "source": "resmigazete.gov.tr",
                        "source_type": "URL_Static",
                        "title": title,
                        "link": url,
                        "date": date_str,
                        "content": text[:2000],
                    })
                    
                    if len(items) >= 20:
                        break
    
    except Exception as e:
        print(f"[Resmi Gazete] Error parsing gazette summary: {e}")
        return []
    
    return items


def scrape_resmi_gazete(base_url: str, days_back: int = 7) -> Tuple[List[Dict], List[Dict]]:
    """
    Scrape Resmi Gazete for the last N days.
    
    Args:
        base_url: Base gazette URL (e.g., https://www.resmigazete.gov.tr/)
        days_back: How many days to go back (default: 7)
    
    Returns:
        (items, errors) tuple
    """
    items: List[Dict] = []
    errors: List[Dict] = []
    
    print(f"[Resmi Gazete] Scraping gazette for last {days_back} days")
    
    # Generate date URLs
    urls = generate_date_urls(base_url, days_back)
    print(f"[Resmi Gazete] Generated {len(urls)} date URLs")
    
    for url in urls:
        print(f"[Resmi Gazete] Fetching: {url}")
        
        status, html = http_get(url, timeout=20)
        
        if status != 200:
            errors.append({
                "url": url,
                "error": f"HTTP status {status}"
            })
            print(f"[Resmi Gazete] Failed to fetch {url}: status {status}")
            continue
        
        # Extract date from URL
        date_str = ""
        try:
            if url != base_url.rstrip('/'):
                # Extract DD.MM.YYYY from URL
                parts = url.split('/')
                if parts:
                    date_str = parts[-1]
            else:
                # Today
                date_str = datetime.now().strftime("%d.%m.%Y")
        except Exception:
            date_str = ""
        
        # Extract items from this day's gazette
        day_items = extract_gazette_summary(url, html, date_str)
        
        print(f"[Resmi Gazete] Extracted {len(day_items)} items from {url}")
        
        items.extend(day_items)
    
    print(f"[Resmi Gazete] Total items: {len(items)}, Errors: {len(errors)}")
    
    return items, errors
