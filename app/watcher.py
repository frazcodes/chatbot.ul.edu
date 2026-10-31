"""Autonomous Website & PDF Watcher Agent for University of Layyah.

Monitors university notice boards, merit lists, admission updates, and downloadable
PDFs in real-time, incrementally indexing newly published documents into the live
RAG pipeline without requiring restarts.
"""
from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests

from . import config
from .chunking import chunk_page
from .crawler import BASE, USER_AGENT, canon, clean_lines, extract_html, extract_pdf

log = logging.getLogger("ul-chatbot.watcher")

# High-priority pages monitored for notices, merit lists, and newly uploaded documents
WATCH_SEEDS = [
    f"{BASE}/",
    f"{BASE}/page/public-notices",
    f"{BASE}/program_merit_list",
    f"{BASE}/page/Admission-Schedule",
    f"{BASE}/page/How-to-Apply",
    f"{BASE}/page/Eligibility-Criteria",
    f"{BASE}/page/Fee-Structure",
    f"{BASE}/page/Scholarships",
    f"{BASE}/page/Tender-Notice",
    f"{BASE}/careers",
    f"{BASE}/academic-calendar",
    f"{BASE}/contact",
]

MAX_NEW_PAGES_PER_SYNC = 25  # Sensible ceiling per sync cycle to avoid rate-limiting


def is_allowed_domain(url: str, allowed_host: str | None = None) -> bool:
    """Validate that URL belongs to university domain or its subdomains."""
    if allowed_host is None:
        allowed_host = config.SITE_HOST
    try:
        netloc = urlparse(url).netloc.lower().split(":")[0]
        allowed = allowed_host.lower().split(":")[0]
        if not netloc:
            return True  # relative URL handled by canon
        return netloc == allowed or netloc.endswith("." + allowed)
    except Exception:
        return False


class WebsiteWatcherAgent:
    def __init__(
        self,
        state_path: Path = config.WATCHER_STATE,
        raw_pages_path: Path | None = config.RAW_PAGES,
        index_dir: Path = config.INDEX_DIR,
    ):
        self.state_path = state_path
        self.raw_pages_path = raw_pages_path
        self.index_dir = index_dir
        self._sync_lock = threading.Lock()
        self.is_syncing = False
        self.last_sync_time: str | None = None
        self.last_sync_stats: dict = {}
        self.seen: dict[str, dict] = {}
        self._load_state()

    def _load_state(self) -> None:
        """Load known URLs and their hashes from disk or initialise from raw pages."""
        if self.state_path.exists():
            try:
                data = json.loads(self.state_path.read_text(encoding="utf-8"))
                self.seen = data.get("seen", {})
                self.last_sync_time = data.get("last_sync_time")
                self.last_sync_stats = data.get("last_sync_stats", {})
                log.info("Watcher loaded %d tracked pages from %s", len(self.seen), self.state_path)
                return
            except Exception:
                log.exception("Could not read watcher state file, initialising fresh")

        # Initial seed: read existing raw_pages so we don't re-index old pages
        self.seen = {}
        if self.raw_pages_path and self.raw_pages_path.exists():
            try:
                with self.raw_pages_path.open("r", encoding="utf-8") as f:
                    for line in f:
                        if not line.strip():
                            continue
                        try:
                            record = json.loads(line)
                            url = record.get("url")
                            if url:
                                text = record.get("text", "")
                                thash = hashlib.md5(text.encode("utf-8")).hexdigest()
                                self.seen[url] = {
                                    "hash": thash,
                                    "title": record.get("title", ""),
                                    "type": record.get("type", "html"),
                                    "version": 1,
                                    "indexed_at": "initial_crawl",
                                }
                        except Exception:
                            continue
                log.info("Initialised watcher state with %d existing pages", len(self.seen))
                self._save_state()
            except Exception:
                log.exception("Failed to initialize watcher state from RAW_PAGES")

    def _save_state(self) -> None:
        """Persist tracked URLs and metadata to disk."""
        try:
            self.state_path.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "last_sync_time": self.last_sync_time,
                "last_sync_stats": self.last_sync_stats,
                "total_tracked": len(self.seen),
                "seen": self.seen,
            }
            self.state_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            log.exception("Failed to save watcher state")

    def discover_candidates(
        self,
        session: requests.Session,
        max_depth: int | None = None,
    ) -> list[str]:
        """Poll watch seeds and crawl up to max_depth for new and modified documents.
        
        Performs domain validation, link deduplication, polite delays, and preserves
        previously discovered URLs so changed PDFs or notices can be inspected.
        """
        depth_limit = max_depth if max_depth is not None else config.WATCHER_MAX_DEPTH
        discovered: list[str] = []
        discovered_set: set[str] = set()
        visited_html: set[str] = set()

        # Queue contains (url, depth)
        queue: list[tuple[str, int]] = [(s, 0) for s in WATCH_SEEDS if is_allowed_domain(s)]

        while queue:
            current_url, current_depth = queue.pop(0)
            if current_url in visited_html:
                continue
            visited_html.add(current_url)

            # Ensure seed itself is in discovered list for inspection
            if current_url not in discovered_set:
                discovered_set.add(current_url)
                discovered.append(current_url)

            try:
                resp = session.get(current_url, timeout=15)
                if not resp.ok:
                    continue
                content_type = resp.headers.get("content-type", "").lower()
                if "html" not in content_type and not current_url.endswith(".html"):
                    continue

                _, _, links = extract_html(resp.text, current_url)
                for link in links:
                    if not is_allowed_domain(link):
                        continue
                    if link not in discovered_set:
                        discovered_set.add(link)
                        discovered.append(link)

                    low = link.lower()
                    is_document = low.endswith(".pdf") or "/storage/" in low or "/files/" in low
                    if not is_document and current_depth + 1 < depth_limit and link not in visited_html:
                        queue.append((link, current_depth + 1))

                time.sleep(config.CRAWL_DELAY)
            except requests.RequestException as exc:
                log.warning("Watcher failed to scan %s: %s", current_url, exc)

        # Ensure all previously tracked PDFs and notices are also re-evaluated for modifications
        for tracked_url in list(self.seen.keys()):
            low = tracked_url.lower()
            if (low.endswith(".pdf") or "/storage/" in low or "/files/" in low
                    or any(k in low for k in ("merit", "notice", "admission", "career", "tender"))):
                if tracked_url not in discovered_set and is_allowed_domain(tracked_url):
                    discovered_set.add(tracked_url)
                    discovered.append(tracked_url)

        # Prioritise downloadable PDFs and urgent notices first
        def priority_key(u: str) -> int:
            low = u.lower()
            if low.endswith(".pdf") or "/storage/" in low or "/files/" in low:
                return 0
            if any(k in low for k in ("merit", "notice", "admission", "career", "tender")):
                return 1
            return 2

        discovered.sort(key=priority_key)
        return discovered

    def fetch_and_extract(self, session: requests.Session, url: str) -> dict | None:
        """Fetch URL with ETag and Last-Modified conditional headers; extract content.
        
        Returns:
            - {"url": url, "unchanged": True} if unchanged (HTTP 304 or identical hash)
            - dict with page details, new hash, and incremented version if modified or new
            - None if download or extraction fails
        """
        try:
            headers = {}
            existing = self.seen.get(url, {})
            if existing.get("etag"):
                headers["If-None-Match"] = existing["etag"]
            if existing.get("last_modified"):
                headers["If-Modified-Since"] = existing["last_modified"]

            resp = session.get(url, headers=headers, timeout=20, stream=True)
            if resp.status_code == 304:
                log.debug("HTTP 304 Not Modified for %s", url)
                return {"url": url, "unchanged": True}

            if not resp.ok:
                log.warning("Watcher failed to fetch %s (HTTP %d)", url, resp.status_code)
                return None

            content = resp.content
            if len(content) > 15 * 1024 * 1024:  # 15MB limit
                log.warning("Skipping oversized document %s (%d bytes)", url, len(content))
                return None

            etag = resp.headers.get("etag")
            last_modified = resp.headers.get("last-modified")
            binary_hash = hashlib.sha256(content).hexdigest()

            content_type = resp.headers.get("content-type", "").lower()
            is_pdf = "pdf" in content_type or url.lower().endswith(".pdf") or "/files/" in url.lower()

            if is_pdf:
                title, text = extract_pdf(content, url)
                doc_type = "pdf"
            else:
                html = content.decode("utf-8", errors="replace")
                title, text, _ = extract_html(html, url)
                doc_type = "html"

            text = text.strip()
            if len(text) < 40:  # Skip blank pages or failed scans
                return None

            thash = hashlib.md5(text.encode("utf-8")).hexdigest()

            # Content hash fallback check
            if existing:
                same_text = existing.get("hash") == thash
                same_bin = existing.get("content_hash") and existing.get("content_hash") == binary_hash
                if same_text or same_bin:
                    # Update metadata and mark unchanged
                    existing["etag"] = etag
                    existing["last_modified"] = last_modified
                    existing["last_checked"] = datetime.now(timezone.utc).isoformat()
                    return {"url": url, "unchanged": True}

            # Document is new or has modified content
            current_ver = (existing.get("version", 1) + 1) if existing else 1
            return {
                "url": url,
                "title": title or url,
                "text": text,
                "type": doc_type,
                "etag": etag,
                "last_modified": last_modified,
                "hash": thash,
                "content_hash": binary_hash,
                "version": current_ver,
                "unchanged": False,
                "is_modified": bool(existing),
            }
        except Exception as exc:
            log.warning("Watcher error extracting %s: %s", url, exc)
            return None

    def sync(self, pipeline) -> dict:
        """Run a full check cycle: discover, fetch, chunk, embed, and incrementally index."""
        if not self._sync_lock.acquire(blocking=False):
            return {"status": "in_progress", "message": "Sync already running"}

        self.is_syncing = True
        start_time = time.time()
        new_pages = 0
        modified_pages = 0
        new_chunks_count = 0

        try:
            session = requests.Session()
            session.headers["User-Agent"] = USER_AGENT

            log.info("Watcher sync started: discovering candidates from seeds...")
            candidates = self.discover_candidates(session)
            log.info("Watcher found %d candidates for inspection", len(candidates))

            to_index_chunks = []
            pages_to_record = []

            for url in candidates[:MAX_NEW_PAGES_PER_SYNC]:
                page = self.fetch_and_extract(session, url)
                if not page or page.get("unchanged"):
                    continue

                thash = page.get("hash") or hashlib.md5(page.get("text", "").encode("utf-8")).hexdigest()
                existing = self.seen.get(url)
                if existing and existing.get("hash") == thash:
                    continue

                chunks = chunk_page(page, config.CHUNK_WORDS, config.CHUNK_OVERLAP)
                if not chunks:
                    continue

                version = page.get("version", (existing.get("version", 1) + 1 if existing else 1))
                for c in chunks:
                    c["version"] = version
                    c["is_superseded"] = False

                to_index_chunks.extend(chunks)
                pages_to_record.append(page)
                self.seen[url] = {
                    "hash": thash,
                    "content_hash": page.get("content_hash"),
                    "etag": page.get("etag"),
                    "last_modified": page.get("last_modified"),
                    "title": page.get("title", url),
                    "type": page.get("type", "html"),
                    "version": version,
                    "chunks": len(chunks),
                    "indexed_at": datetime.now(timezone.utc).isoformat(),
                    "last_checked": datetime.now(timezone.utc).isoformat(),
                }

                if page.get("is_modified") or (existing is not None):
                    modified_pages += 1
                else:
                    new_pages += 1
                time.sleep(config.CRAWL_DELAY)

            if to_index_chunks and pipeline is not None:
                log.info("Generating embeddings for %d new/updated chunks...", len(to_index_chunks))
                texts = [c["text"] for c in to_index_chunks]
                new_vectors = pipeline.embedder.encode_passages(texts)

                # Incrementally update the live index and supersede existing chunks for same URLs
                pipeline.index.add_chunks(
                    to_index_chunks,
                    new_vectors,
                    replace_existing_urls=True,
                    directory=self.index_dir,
                )
                new_chunks_count = len(to_index_chunks)

                # Append newly indexed or modified pages to raw pages log
                if pages_to_record and self.raw_pages_path:
                    self.raw_pages_path.parent.mkdir(parents=True, exist_ok=True)
                    with self.raw_pages_path.open("a", encoding="utf-8") as f:
                        for p in pages_to_record:
                            f.write(json.dumps(p, ensure_ascii=False) + "\n")

                log.info(
                    "Watcher successfully indexed %d new pages, %d modified pages, and %d chunks to live index!",
                    new_pages, modified_pages, new_chunks_count
                )

            duration = round(time.time() - start_time, 2)
            self.last_sync_time = datetime.now(timezone.utc).isoformat()
            self.last_sync_stats = {
                "candidates_checked": len(candidates),
                "new_pages_indexed": new_pages,
                "modified_pages_indexed": modified_pages,
                "new_chunks_added": new_chunks_count,
                "total_tracked_pages": len(self.seen),
                "duration_seconds": duration,
                "status": "success",
            }
            self._save_state()
            return self.last_sync_stats

        except Exception as exc:
            log.exception("Watcher sync cycle encountered error")
            return {"status": "error", "message": str(exc)}
        finally:
            self.is_syncing = False
            self._sync_lock.release()

    def get_status(self, pipeline) -> dict:
        """Return real-time agent status and telemetry."""
        return {
            "is_syncing": self.is_syncing,
            "auto_sync_enabled": config.AUTO_SYNC_ENABLED,
            "sync_interval_minutes": config.AUTO_SYNC_INTERVAL_MINUTES,
            "last_sync_time": self.last_sync_time,
            "last_sync_stats": self.last_sync_stats,
            "tracked_pages_count": len(self.seen),
            "current_index_chunks": len(pipeline.index.chunks) if (pipeline and hasattr(pipeline, "index")) else 0,
            "seeds_monitored": len(WATCH_SEEDS),
        }


# Singleton watcher agent instance
watcher_agent = WebsiteWatcherAgent()
