"""Polite crawler for the University of Layyah website.

Usage:  python -m app.crawler
Output: data/raw/pages.jsonl  (one JSON object per page / PDF)
"""
from __future__ import annotations

import hashlib
import json
import re
import time
from collections import Counter, deque
from io import BytesIO
from urllib import robotparser
from urllib.parse import urldefrag, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from . import config

USER_AGENT = "UL-Chatbot-Crawler/1.0 (university student project)"
BASE = f"https://{config.SITE_HOST}"

# Pages taken from the site's menu. The crawler also discovers links on its own.
SEED_PATHS = [
    "/", "/admissions", "/page/Admission-Schedule", "/page/How-to-Apply",
    "/page/Eligibility-Criteria", "/page/Fee-Structure", "/program_merit_list",
    "/page/Ecat-Result", "/page/vision", "/page/page-2", "/academic-calendar",
    "/page/Facilities", "/page/Scholarships", "/page/Medical", "/page/Transport",
    "/page/qec", "/page/faculty-hostel", "/page/Tender-Notice", "/page/public-notices",
    "/careers", "/page/forms", "/contact",
]
SKIP_PATH_PARTS = ("/login", "/logout", "/register", "/challan")
SKIP_EXT = (
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".ico", ".mp4", ".mp3",
    ".zip", ".rar", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".css", ".js",
)
MAX_BYTES = 15 * 1024 * 1024


def canon(url: str, base: str | None = None) -> str | None:
    """Normalise a URL; return None if it is outside the university site."""
    if base:
        url = urljoin(base, url)
    url, _ = urldefrag(url.strip())
    p = urlparse(url)
    if p.scheme not in ("http", "https"):
        return None
    host = p.netloc.lower().removeprefix("www.")
    if host != config.SITE_HOST:
        return None
    path = re.sub(r"/{2,}", "/", p.path) or "/"
    low = path.lower()
    if any(part in low for part in SKIP_PATH_PARTS) or low.endswith(SKIP_EXT):
        return None
    query = f"?{p.query}" if p.query else ""
    scheme = p.scheme or "https"
    return f"{scheme}://{host}{path}{query}"


def clean_lines(text: str) -> list[str]:
    lines = []
    for raw in text.splitlines():
        line = re.sub(r"\s+", " ", raw).strip()
        if len(line) < 2 or not re.search(r"\w", line):
            continue
        lines.append(line)
    return lines


def extract_html(html: str, url: str) -> tuple[str, str, list[str]]:
    """Return (title, text, discovered_links)."""
    soup = BeautifulSoup(html, "lxml")

    # Collect links first: the menu holds links to every program page.
    links = []
    for a in soup.find_all("a", href=True):
        c = canon(a["href"], url)
        if c:
            links.append(c)

    for tag in soup(["script", "style", "noscript", "svg", "iframe", "form",
                     "button", "select", "nav", "header", "footer"]):
        tag.decompose()

    for tr in soup.find_all("tr"):  # keep table rows readable: "a | b | c"
        cells = [c.get_text(" ", strip=True) for c in tr.find_all(["th", "td"])]
        tr.replace_with(soup.new_string(" | ".join(x for x in cells if x) + "\n"))

    heading = soup.find(["h1", "h2"])
    title = heading.get_text(" ", strip=True) if heading else ""
    if not title and soup.title:
        title = soup.title.get_text(" ", strip=True)
    text = "\n".join(clean_lines(soup.get_text("\n")))
    return title or url, text, links


def extract_pdf(content: bytes, url: str) -> tuple[str, str]:
    from pypdf import PdfReader

    reader = PdfReader(BytesIO(content))
    parts = []
    for page in reader.pages[:60]:
        try:
            parts.append(page.extract_text() or "")
        except Exception:
            continue
    name = urlparse(url).path.rsplit("/", 1)[-1].rsplit(".", 1)[0]
    title = re.sub(r"[-_]+", " ", name).strip() or "PDF document"
    return title, "\n".join(clean_lines("\n".join(parts)))


def strip_boilerplate(pages: list[dict], ratio: float = 0.35, min_pages: int = 8) -> None:
    """Remove lines that repeat on many HTML pages (menus, footers, widgets)."""
    html_pages = [p for p in pages if p["type"] == "html"]
    if len(html_pages) < min_pages:
        return
    counter: Counter[str] = Counter()
    for p in html_pages:
        counter.update(set(p["text"].split("\n")))
    threshold = max(3, int(len(html_pages) * ratio))
    common = {line for line, n in counter.items() if n >= threshold}
    for p in html_pages:
        p["text"] = "\n".join(l for l in p["text"].split("\n") if l not in common)


def crawl() -> list[dict]:
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT

    robots = robotparser.RobotFileParser()
    try:
        r = session.get(f"{BASE}/robots.txt", timeout=15)
        robots.parse(r.text.splitlines() if r.ok else [])
    except requests.RequestException:
        robots.parse([])

    queue = deque(filter(None, (canon(BASE + p) for p in SEED_PATHS)))
    seen = set(queue)
    pages: list[dict] = []

    while queue and len(pages) < config.MAX_PAGES:
        url = queue.popleft()
        if not robots.can_fetch(USER_AGENT, url):
            print(f"[robots] skip {url}")
            continue
        try:
            resp = session.get(url, timeout=25)
        except requests.RequestException as exc:
            print(f"[error] {url}: {exc}")
            continue
        if resp.status_code != 200 or len(resp.content) > MAX_BYTES:
            print(f"[skip {resp.status_code}] {url}")
            continue

        ctype = resp.headers.get("content-type", "").lower()
        try:
            if "pdf" in ctype or url.lower().endswith(".pdf"):
                title, text = extract_pdf(resp.content, url)
                kind, links = "pdf", []
            elif "html" in ctype:
                title, text, links = extract_html(resp.text, url)
                kind = "html"
            else:
                continue
        except Exception as exc:  # a broken page must not stop the crawl
            print(f"[parse error] {url}: {exc}")
            continue

        pages.append({"url": url, "title": title, "text": text, "type": kind})
        print(f"[{len(pages):>3}] {kind:4} {url}")

        for link in links:
            if link not in seen:
                seen.add(link)
                queue.append(link)
        time.sleep(config.CRAWL_DELAY)

    strip_boilerplate(pages)

    unique, hashes = [], set()
    for p in pages:
        if len(p["text"]) < 40:
            continue
        h = hashlib.md5(p["text"].encode("utf-8")).hexdigest()
        if h in hashes:
            continue
        hashes.add(h)
        unique.append(p)
    return unique


def main() -> None:
    pages = crawl()
    config.RAW_PAGES.parent.mkdir(parents=True, exist_ok=True)
    with config.RAW_PAGES.open("w", encoding="utf-8") as f:
        for p in pages:
            f.write(json.dumps(p, ensure_ascii=False) + "\n")
    print(f"\nSaved {len(pages)} pages -> {config.RAW_PAGES}")


if __name__ == "__main__":
    main()
