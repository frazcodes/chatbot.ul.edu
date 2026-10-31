"""Audit verification and regression test suite.
Tests the exact implementation and edge-case behavior of the RAG pipeline,
frontend contracts, watcher agent, document replacement, and data freshness architecture.
"""
import hashlib
import http.server
import json
import socket
import sys
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import config
from app.ingest import compute_chunk_hash, embed_chunks_cached
from app.llm import LLM
from app.pipeline import RagPipeline, detect_actions
from app.store import Index
from app.watcher import WebsiteWatcherAgent, is_allowed_domain
from tests.test_core import FakeEmbedder, FakeLLM


def make_simple_pdf(text: str) -> bytes:
    """Generate a valid 1-page PDF containing text with exact byte offsets for test fixtures."""
    stream_data = f"BT /F1 12 Tf 50 700 Td ({text}) Tj ET\n".encode("latin1")
    stream_len = len(stream_data)
    objects = [
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n",
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n",
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>\nendobj\n",
        f"4 0 obj\n<< /Length {stream_len} >>\nstream\n".encode("latin1") + stream_data + b"endstream\nendobj\n",
        b"5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n",
    ]
    header = b"%PDF-1.4\n"
    offsets = [0]
    pos = len(header)
    for o in objects:
        offsets.append(pos)
        pos += len(o)
    xref_pos = pos
    xref = f"xref\n0 {len(offsets)}\n0000000000 65535 f \n".encode("latin1")
    for off in offsets[1:]:
        xref += f"{off:010d} 00000 n \n".encode("latin1")
    trailer = f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref_pos}\n%%EOF\n".encode("latin1")
    return header + b"".join(objects) + xref + trailer


class AuditImplementationTests(unittest.TestCase):
    def test_frontend_watchdog_and_retry_contract(self):
        js = (config.STATIC_DIR / "chatbot.js").read_text(encoding="utf-8")
        # 1. 22-second watchdog and AbortController
        self.assertIn("22000", js, "Watchdog must have 22-second timer")
        self.assertIn("AbortController", js, "Must use AbortController")
        self.assertIn("streamAborted", js, "Must flag aborted stream")

        # 2. One-click retry button
        self.assertIn("Dobara Koshish Karein 🔄", js, "Must render interactive retry button")
        self.assertIn("retryBtn.addEventListener", js, "Must attach click listener for retry")

        # 3. Partial stream recovery and stream type detection
        self.assertIn("text/event-stream", js, "Must detect SSE content type")
        self.assertIn('data.type === "error"', js, "Must handle error stream message")
        self.assertIn('data.type === "done"', js, "Must handle done stream message")

    def test_llm_timeout_and_retry(self):
        llm = LLM()
        if llm.provider == "groq":
            self.assertEqual(llm.client.timeout, 20.0, "Groq client must have 20.0s timeout")
        import inspect
        src_call = inspect.getsource(llm._call)
        src_stream = inspect.getsource(llm._call_stream)
        self.assertIn("attempt in range(2)", src_call, "_call must have retry loop")
        self.assertIn("attempt in range(2)", src_stream, "_call_stream must have retry loop")

    def test_fallback_actions_always_populated(self):
        actions = detect_actions("Random unrelated question", "")
        self.assertTrue(len(actions) >= 1, "Must always return non-empty fallback action buttons")
        labels = [a["label"] for a in actions]
        self.assertTrue(any("Portal" in l or "WhatsApp" in l or "Call" in l for l in labels))

    def test_live_retrieval_without_restart(self):
        emb = FakeEmbedder()
        chunks = [{"id": "0", "url": "https://ul.edu.pk/initial", "title": "Initial", "text": "initial degree info"}]
        index = Index(chunks, emb.encode_passages([c["text"] for c in chunks]))
        pipe = RagPipeline(index, emb, FakeLLM())

        qvec = emb.encode_query("artificial intelligence")
        hits_before = pipe.index.search(qvec, "artificial intelligence", top_k=5)
        self.assertFalse(any("artificial intelligence" in h["chunk"]["text"] for h in hits_before))

        # Add new chunk live
        new_chunks = [{"id": "1", "url": "https://ul.edu.pk/new-notice.pdf", "title": "AI Notice", "text": "artificial intelligence BS admission notice"}]
        pipe.index.add_chunks(new_chunks, emb.encode_passages([c["text"] for c in new_chunks]))

        # Search immediately without reloading or restart
        hits_after = pipe.index.search(qvec, "artificial intelligence", top_k=5)
        self.assertTrue(any("artificial intelligence" in h["chunk"]["text"] for h in hits_after))
        self.assertEqual(hits_after[0]["chunk"]["id"], "1")


class AuditDataFreshnessTests(unittest.TestCase):
    def test_changed_pdf_discovery_and_reprocessing(self):
        """Verify watcher discovers an updated PDF at the same URL and does not skip it."""
        agent = WebsiteWatcherAgent(state_path=Path("dummy.json"), raw_pages_path=None)
        agent.seen = {
            "https://ul.edu.pk/storage/career/files/merit.pdf": {
                "hash": "old_hash_123",
                "title": "Merit List",
                "type": "pdf",
                "version": 1,
            }
        }

        mock_session = MagicMock()
        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.headers = {"content-type": "text/html"}
        mock_resp.text = '<a href="https://ul.edu.pk/storage/career/files/merit.pdf">Merit List</a>'
        mock_session.get.return_value = mock_resp

        candidates = agent.discover_candidates(mock_session)
        self.assertIn(
            "https://ul.edu.pk/storage/career/files/merit.pdf",
            candidates,
            "Known PDF URL must be included in candidate checks for modification verification",
        )

    def test_etag_and_last_modified_conditional_requests(self):
        """Verify conditional headers are sent and HTTP 304 is handled as unchanged."""
        agent = WebsiteWatcherAgent(state_path=Path("dummy.json"), raw_pages_path=None)
        test_url = "https://ul.edu.pk/notice.pdf"
        agent.seen = {
            test_url: {
                "hash": "hash123",
                "etag": '"etag-v1"',
                "last_modified": "Mon, 01 Jan 2026 00:00:00 GMT",
                "version": 1,
            }
        }

        mock_session = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 304
        mock_session.get.return_value = mock_resp

        res = agent.fetch_and_extract(mock_session, test_url)
        self.assertIsNotNone(res)
        self.assertTrue(res.get("unchanged"))

        # Verify headers were passed in GET request
        call_kwargs = mock_session.get.call_args[1]
        self.assertEqual(call_kwargs["headers"].get("If-None-Match"), '"etag-v1"')
        self.assertEqual(call_kwargs["headers"].get("If-Modified-Since"), "Mon, 01 Jan 2026 00:00:00 GMT")

    def test_versioning_and_superseded_behavior(self):
        """Verify updating an existing URL's chunk supersedes old versions and prevents duplicate active chunks."""
        emb = FakeEmbedder()
        chunks = [{"id": "0", "url": "https://ul.edu.pk/notice.pdf", "title": "Old Notice", "text": "Merit list 1: closing merit 60 percent"}]
        index = Index(chunks, emb.encode_passages([c["text"] for c in chunks]))

        # Simulating updated notice at the exact same URL
        new_chunks = [{"id": "1", "url": "https://ul.edu.pk/notice.pdf", "title": "Updated Notice", "text": "Merit list 2: closing merit 68 percent"}]
        index.add_chunks(new_chunks, emb.encode_passages([c["text"] for c in new_chunks]), replace_existing_urls=True)

        urls = [c["url"] for c in index.chunks]
        # Chunks must be replaced, NOT duplicated
        self.assertEqual(urls.count("https://ul.edu.pk/notice.pdf"), 1, "Only the latest chunk must remain active in index")
        self.assertEqual(index.chunks[0]["id"], "1")
        self.assertEqual(index.chunks[0]["text"], "Merit list 2: closing merit 68 percent")

    def test_domain_validation_and_crawl_depth(self):
        """Verify allowed-domain checking rejects third-party URLs and supports multi-hop depth."""
        self.assertTrue(is_allowed_domain("https://ul.edu.pk/admissions"))
        self.assertTrue(is_allowed_domain("https://sub.ul.edu.pk/page"))
        self.assertFalse(is_allowed_domain("https://facebook.com/university"))
        self.assertFalse(is_allowed_domain("https://google.com/search"))
        self.assertFalse(is_allowed_domain("https://external-malicious.com/phishing"))

    def test_incremental_hash_caching_in_ingest(self):
        """Verify app.ingest skips re-embedding when chunk hashes are cached."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_file = Path(tmpdir) / "cache.npz"
            mock_embedder = MagicMock()
            mock_embedder.encode_passages.return_value = [
                [0.1] * 384,
                [0.2] * 384,
            ]

            chunks = [
                {"text": "Chunk text one regarding computer science."},
                {"text": "Chunk text two regarding electrical engineering."},
            ]

            # 1. First run: uncached -> invokes encode_passages
            vecs1 = embed_chunks_cached(chunks, embedder=mock_embedder, cache_path=cache_file)
            self.assertEqual(len(vecs1), 2)
            self.assertEqual(mock_embedder.encode_passages.call_count, 1)

            # 2. Second run: identical chunks -> loaded from cache, 0 embedder calls!
            mock_embedder.reset_mock()
            vecs2 = embed_chunks_cached(chunks, embedder=mock_embedder, cache_path=cache_file)
            self.assertEqual(len(vecs2), 2)
            self.assertEqual(mock_embedder.encode_passages.call_count, 0)

            # 3. Third run: 1 modified chunk -> only 1 text passed to embedder
            mock_embedder.encode_passages.return_value = [[0.9] * 384]
            modified_chunks = [
                {"text": "Chunk text one regarding computer science."},
                {"text": "Chunk text two MODIFIED regarding electrical engineering."},
            ]
            vecs3 = embed_chunks_cached(modified_chunks, embedder=mock_embedder, cache_path=cache_file)
            self.assertEqual(len(vecs3), 2)
            self.assertEqual(mock_embedder.encode_passages.call_count, 1)
            # Verify only the 1 modified text was passed
            call_args = mock_embedder.encode_passages.call_args[0][0]
            self.assertEqual(len(call_args), 1)
            self.assertEqual(call_args[0], modified_chunks[1]["text"])

    def test_traceable_enrollment_evidence(self):
        """Verify data/manual/admissions.md does not contain untraceable enrollment estimates."""
        content = (config.MANUAL_DIR / "admissions.md").read_text(encoding="utf-8")
        self.assertNotIn("several thousand students", content)
        self.assertIn("Registrar Office", content)


class AuditEndToEndFixtureTests(unittest.TestCase):
    """Full workflow demonstration test using a real local HTTP server fixture.
    
    Publishes a new PDF -> verifies chatbot answers -> modifies the same PDF at unchanged URL
    -> runs watcher sync -> verifies chatbot retrieves updated content with correct source without restart.
    """
    def setUp(self):
        self.server_port = self._find_free_port()
        self.server_url = f"http://127.0.0.1:{self.server_port}"
        self.pdf_content = make_simple_pdf(
            "University of Layyah Fall 2026 Admissions Notice: Last date is 15 October 2026 with 50 percent eligibility."
        )
        self.etag = '"v1"'
        self.pdf_url = f"{self.server_url}/storage/admission_notice.pdf"

        # HTTP Server Handler with dynamic payload
        test_case = self

        class FixtureHandler(http.server.BaseHTTPRequestHandler):
            def log_message(self, format, *args):
                pass  # suppress console log noise

            def do_GET(self):
                if self.path == "/" or self.path == "/page/public-notices":
                    html = f'<html><body><a href="{test_case.pdf_url}">Admission Notice</a></body></html>'
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html")
                    self.send_header("Content-Length", str(len(html)))
                    self.end_headers()
                    self.wfile.write(html.encode("utf-8"))
                elif self.path == "/storage/admission_notice.pdf":
                    if self.headers.get("If-None-Match") == test_case.etag:
                        self.send_response(304)
                        self.end_headers()
                        return

                    self.send_response(200)
                    self.send_header("Content-Type", "application/pdf")
                    self.send_header("ETag", test_case.etag)
                    self.send_header("Content-Length", str(len(test_case.pdf_content)))
                    self.end_headers()
                    self.wfile.write(test_case.pdf_content)
                else:
                    self.send_response(404)
                    self.end_headers()

        self.httpd = http.server.HTTPServer(("127.0.0.1", self.server_port), FixtureHandler)
        self.server_thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.server_thread.start()

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.server_thread.join(timeout=2)

    def _find_free_port(self) -> int:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            return s.getsockname()[1]

    def test_e2e_changed_pdf_reprocessing_without_restart(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            temp_path = Path(tmpdir)
            state_path = temp_path / "watcher_state.json"
            raw_path = temp_path / "pages.jsonl"
            index_path = temp_path / "index"

            emb = FakeEmbedder()
            fake_llm = FakeLLM()

            # 1. Initialize running pipeline with baseline chunk
            baseline = [{"id": "base-1", "url": f"{self.server_url}/contact", "title": "Contact", "text": "Contact university at info@ul.edu.pk 0606-920247"}]
            index = Index(baseline, emb.encode_passages([c["text"] for c in baseline]))
            pipeline = RagPipeline(index, emb, fake_llm)

            agent = WebsiteWatcherAgent(state_path=state_path, raw_pages_path=raw_path, index_dir=index_path)

            # Override seeds to point to our test fixture
            from app import watcher
            orig_seeds = watcher.WATCH_SEEDS
            orig_site_host = config.SITE_HOST
            try:
                watcher.WATCH_SEEDS = [f"{self.server_url}/"]
                config.SITE_HOST = f"127.0.0.1:{self.server_port}"

                # 2. Run initial watcher sync -> discovers & indexes PDF v1
                stats1 = agent.sync(pipeline)
                self.assertEqual(stats1["new_pages_indexed"], 1)

                # Query pipeline: verify v1 content retrieved
                qvec = emb.encode_query("admission last date October")
                hits1 = pipeline.index.search(qvec, "admission last date October", top_k=3)
                pdf_hits1 = [h for h in hits1 if h["chunk"]["url"] == self.pdf_url]
                self.assertEqual(len(pdf_hits1), 1)
                self.assertIn("15 October 2026", pdf_hits1[0]["chunk"]["text"])
                self.assertEqual(pdf_hits1[0]["chunk"].get("version"), 1)

                # 3. Modify PDF at the EXACT SAME URL on the test server
                self.pdf_content = make_simple_pdf(
                    "University of Layyah Fall 2026 Admissions Notice: Last date EXTENDED to 30 November 2026 with 50 percent eligibility."
                )
                self.etag = '"v2"'

                # 4. Run watcher sync again on the RUNNING pipeline (no restart!)
                stats2 = agent.sync(pipeline)
                self.assertEqual(stats2["modified_pages_indexed"], 1)

                # 5. Query the running pipeline again immediately without restart
                hits2 = pipeline.index.search(qvec, "admission last date November", top_k=3)
                pdf_hits2 = [h for h in hits2 if h["chunk"]["url"] == self.pdf_url]
                
                # Check that ONLY the latest version is active in the search results
                self.assertEqual(len(pdf_hits2), 1, "Only single latest version chunk must be active")
                self.assertIn("30 November 2026", pdf_hits2[0]["chunk"]["text"])
                self.assertNotIn("15 October 2026", pdf_hits2[0]["chunk"]["text"])
                self.assertEqual(pdf_hits2[0]["chunk"].get("version"), 2)

                # 6. Verify old version chunk was preserved and recorded in superseded log
                superseded_file = index_path / "superseded_chunks.jsonl"
                self.assertTrue(superseded_file.exists(), "Superseded log must exist")
                superseded_lines = [json.loads(l) for l in superseded_file.read_text(encoding="utf-8").splitlines() if l.strip()]
                self.assertTrue(any(s.get("is_superseded") and "15 October 2026" in s.get("text", "") for s in superseded_lines))

            finally:
                watcher.WATCH_SEEDS = orig_seeds
                config.SITE_HOST = orig_site_host


if __name__ == "__main__":
    unittest.main()
