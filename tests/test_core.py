"""Offline tests (no network, no model download). Run: python -m unittest discover -s tests -v"""
import hashlib
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import config  # noqa: E402
from app.chunking import chunk_page, split_text  # noqa: E402
from app.crawler import canon, extract_html, strip_boilerplate  # noqa: E402
from app.llm import NO_ANSWER, normalize_history  # noqa: E402
from app.pipeline import RagPipeline  # noqa: E402
from app.ratelimit import SlidingWindowLimiter  # noqa: E402
from app.store import Index, tokenize  # noqa: E402


class FakeEmbedder:
    """Deterministic bag-of-words hashing embedder, good enough to test plumbing."""
    dim = 256

    def _vec(self, text):
        v = np.zeros(self.dim, dtype=np.float32)
        for t in tokenize(text):
            v[int(hashlib.md5(t.encode()).hexdigest(), 16) % self.dim] += 1
        n = np.linalg.norm(v)
        return v / n if n else v

    def encode_passages(self, texts):
        return np.stack([self._vec(t) for t in texts])

    def encode_query(self, text):
        return self._vec(text)


class FakeLLM:
    def __init__(self, answer="OK answer"):
        self._answer, self.last_hits = answer, None

    def rewrite(self, message, history):
        return message

    def answer(self, message, history, hits):
        self.last_hits = hits
        return self._answer

    def answer_stream(self, message, history, hits):
        self.last_hits = hits
        for word in self._answer.split():
            yield word + " "


PAGES = [
    {"url": "https://ul.edu.pk/page/Fee-Structure", "title": "Fee Structure",
     "text": "BS Computer Science tuition fee per semester\nAdmission fee one time\nHostel charges"},
    {"url": "https://ul.edu.pk/page/Transport", "title": "Transport Facility",
     "text": "Pick and drop buses run on routes around Layyah for students"},
    {"url": "https://ul.edu.pk/page/Medical", "title": "Medical Facility",
     "text": "On campus doctors and nurses give first aid and routine care"},
]


def build_index(emb):
    chunks = [c for p in PAGES for c in chunk_page(p)]
    return Index(chunks, emb.encode_passages([c["text"] for c in chunks]))


class ChunkingTests(unittest.TestCase):
    def test_respects_max_words_and_overlaps(self):
        text = "\n".join(f"line{i} " + "word " * 19 for i in range(30))  # 20 words/line
        chunks = split_text(text, max_words=100, overlap_words=25)
        self.assertGreater(len(chunks), 1)
        for c in chunks:
            self.assertLessEqual(len(c.split()), 100)
        # overlap: last line of chunk 0 starts chunk 1
        self.assertEqual(chunks[0].splitlines()[-1], chunks[1].splitlines()[0])

    def test_very_long_single_line_is_split(self):
        chunks = split_text("w " * 500, max_words=100, overlap_words=10)
        self.assertTrue(all(len(c.split()) <= 100 for c in chunks))

    def test_chunk_carries_title_and_unique_ids(self):
        chunks = chunk_page({"url": "https://ul.edu.pk/x", "title": "T", "text": "a\n" * 400}, 50, 5)
        self.assertTrue(all(c["text"].startswith("T\n") for c in chunks))
        self.assertEqual(len({c["id"] for c in chunks}), len(chunks))


class CrawlerTests(unittest.TestCase):
    def test_canon(self):
        self.assertEqual(canon("https://www.ul.edu.pk//page/vision#top"), "https://ul.edu.pk/page/vision")
        self.assertEqual(canon("/admissions", "https://ul.edu.pk/x"), "https://ul.edu.pk/admissions")
        self.assertIsNone(canon("https://facebook.com/x"))
        self.assertIsNone(canon("https://ul.edu.pk/login"))
        self.assertIsNone(canon("https://ul.edu.pk/a.jpg"))
        self.assertIsNone(canon("mailto:info@ul.edu.pk"))
        self.assertIsNone(canon("javascript:void(0)"))

    def test_extract_html_keeps_links_from_nav_and_tables(self):
        html = """<html><head><title>UL</title></head><body>
        <nav><a href="/program-detail/abc/bs-cs">BS CS</a></nav>
        <h1>Eligibility</h1><script>x=1</script>
        <table><tr><th>Program</th><th>Marks</th></tr><tr><td>BS CS</td><td>60%</td></tr></table>
        </body></html>"""
        title, text, links = extract_html(html, "https://ul.edu.pk/page/e")
        self.assertEqual(title, "Eligibility")
        self.assertIn("https://ul.edu.pk/program-detail/abc/bs-cs", links)
        self.assertIn("BS CS | 60%", text)
        self.assertNotIn("x=1", text)
        self.assertNotIn("BS CS\n", text.split("BS CS | 60%")[0])  # nav text removed

    def test_strip_boilerplate(self):
        pages = [{"type": "html", "text": f"Menu\nHome\nUnique content number {i}"} for i in range(10)]
        strip_boilerplate(pages)
        for i, p in enumerate(pages):
            self.assertEqual(p["text"], f"Unique content number {i}")


class SearchTests(unittest.TestCase):
    def setUp(self):
        self.emb = FakeEmbedder()
        self.index = build_index(self.emb)

    def _top(self, q):
        return self.index.search(self.emb.encode_query(q), q, top_k=3)[0]["chunk"]["url"]

    def test_finds_right_page(self):
        self.assertTrue(self._top("hostel fee").endswith("Fee-Structure"))
        self.assertTrue(self._top("bus pick and drop").endswith("Transport"))
        self.assertTrue(self._top("doctor first aid").endswith("Medical"))

    def test_save_and_load_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            self.index.save(Path(d))
            loaded = Index.load(Path(d))
        self.assertEqual(loaded.chunks, self.index.chunks)
        self.assertTrue(np.allclose(loaded.emb, self.index.emb))

    def test_per_url_cap(self):
        page = {"url": "https://ul.edu.pk/big", "title": "Big", "text": "\n".join(["fee info"] * 400)}
        chunks = chunk_page(page, 20, 0)
        idx = Index(chunks, self.emb.encode_passages([c["text"] for c in chunks]))
        hits = idx.search(self.emb.encode_query("fee"), "fee", top_k=10, per_url=3)
        self.assertEqual(len(hits), 3)


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.emb = FakeEmbedder()
        self.index = build_index(self.emb)

    def test_returns_answer_with_deduped_sources(self):
        llm = FakeLLM("The fee is X")
        out = RagPipeline(self.index, self.emb, llm).chat("hostel fee", [])
        self.assertEqual(out["answer"], "The fee is X")
        self.assertTrue(out["sources"][0]["url"].endswith("Fee-Structure"))
        urls = [s["url"] for s in out["sources"]]
        self.assertEqual(len(urls), len(set(urls)))
        self.assertTrue(llm.last_hits)

    def test_no_answer_marker_hides_sources(self):
        llm = FakeLLM(f"{NO_ANSWER} Mujhe nahi mila.")
        out = RagPipeline(self.index, self.emb, llm).chat("who won the cricket world cup", [])
        self.assertEqual(out["answer"], "Mujhe nahi mila.")
        self.assertEqual(out["sources"], [])

    def test_stream_returns_tokens_and_sources(self):
        llm = FakeLLM("The fee is X")
        chunks = list(RagPipeline(self.index, self.emb, llm).chat_stream("hostel fee", []))
        tokens = [c["token"] for c in chunks if c["type"] == "token"]
        full = "".join(tokens).strip()
        self.assertEqual(full, "The fee is X")
        done = [c for c in chunks if c["type"] == "done"][0]
        self.assertTrue(done["sources"][0]["url"].endswith("Fee-Structure"))

    def test_stream_no_answer_marker_hides_sources(self):
        llm = FakeLLM(f"{NO_ANSWER} Mujhe nahi mila.")
        chunks = list(RagPipeline(self.index, self.emb, llm).chat_stream("who won cricket cup", []))
        tokens = [c["token"] for c in chunks if c["type"] == "token"]
        full = "".join(tokens).strip()
        self.assertEqual(full, "Mujhe nahi mila.")
        done = [c for c in chunks if c["type"] == "done"][0]
        self.assertEqual(done["sources"], [])

    def test_logs_unanswered_query(self):
        with tempfile.TemporaryDirectory() as td:
            orig = config.UNANSWERED_LOG
            config.UNANSWERED_LOG = Path(td) / "unanswered.jsonl"
            try:
                llm = FakeLLM(f"{NO_ANSWER} Nahi mila")
                RagPipeline(self.index, self.emb, llm).chat("unknown query", [])
                self.assertTrue(config.UNANSWERED_LOG.exists())
                content = config.UNANSWERED_LOG.read_text(encoding="utf-8")
                self.assertIn("unknown query", content)
            finally:
                config.UNANSWERED_LOG = orig

    def test_detects_contextual_actions(self):
        llm = FakeLLM("Here is fee info")
        out = RagPipeline(self.index, self.emb, llm).chat("fee challan kaise nikalein", [])
        self.assertIn("actions", out)
        action_labels = [a["label"] for a in out["actions"]]
        self.assertTrue(any("Challan" in l or "Fee" in l for l in action_labels))


class HistoryTests(unittest.TestCase):
    def test_normalize(self):
        h = [{"role": "assistant", "content": "hi"}, {"role": "user", "content": "a"},
             {"role": "user", "content": "b"}, {"role": "assistant", "content": "c"},
             {"role": "system", "content": "evil"}, {"role": "user", "content": "  "}]
        out = normalize_history(h, 10)
        self.assertEqual([t["role"] for t in out], ["user", "assistant"])
        self.assertEqual(out[0]["content"], "a\nb")


class RateLimitTests(unittest.TestCase):
    def test_limit_and_window(self):
        rl = SlidingWindowLimiter(3, 60)
        self.assertTrue(all(rl.allow("ip", now=t) for t in (0, 1, 2)))
        self.assertFalse(rl.allow("ip", now=3))
        self.assertTrue(rl.allow("other", now=3))
        self.assertTrue(rl.allow("ip", now=61))


class WatcherAndIncrementalTests(unittest.TestCase):
    def setUp(self):
        self.emb = FakeEmbedder()
        chunks = [
            {"id": "0", "url": "https://ul.edu.pk/p1", "title": "P1", "text": "admissions merit list criteria"},
            {"id": "1", "url": "https://ul.edu.pk/p2", "title": "P2", "text": "bus routes and transport timings"},
        ]
        vectors = self.emb.encode_passages([c["text"] for c in chunks])
        self.index = Index(chunks, vectors)

    def test_add_chunks_incrementally(self):
        new_chunks = [
            {"id": "2", "url": "https://ul.edu.pk/storage/career/files/new_tender.pdf", "title": "New Tender PDF", "text": "scientific laboratory equipment tender procurement"},
        ]
        new_vectors = self.emb.encode_passages([c["text"] for c in new_chunks])
        added = self.index.add_chunks(new_chunks, new_vectors)
        self.assertEqual(added, 1)
        self.assertEqual(len(self.index.chunks), 3)
        self.assertEqual(len(self.index.emb), 3)

        # Verify search retrieves newly added chunk
        qvec = self.emb.encode_query("laboratory equipment tender")
        hits = self.index.search(qvec, "laboratory equipment tender", top_k=2)
        self.assertTrue(len(hits) > 0)
        self.assertEqual(hits[0]["chunk"]["id"], "2")
        self.assertIn("tender", hits[0]["chunk"]["text"])

    def test_watcher_sync_cycle(self):
        from unittest.mock import MagicMock
        from app.watcher import WebsiteWatcherAgent

        with tempfile.TemporaryDirectory() as td:
            state_file = Path(td) / "watcher_state.json"
            agent = WebsiteWatcherAgent(state_path=state_file, raw_pages_path=None, index_dir=Path(td) / "index")
            self.assertEqual(len(agent.seen), 0)

            # Mock candidate discovery & fetch
            agent.discover_candidates = MagicMock(return_value=["https://ul.edu.pk/storage/files/notice.pdf"])
            agent.fetch_and_extract = MagicMock(return_value={
                "url": "https://ul.edu.pk/storage/files/notice.pdf",
                "title": "Admissions Notice 2026",
                "text": "Admissions open for BS and MS programs in university of layyah",
                "type": "pdf",
            })

            pipeline = RagPipeline(self.index, self.emb, FakeLLM())
            initial_chunks = len(pipeline.index.chunks)

            stats = agent.sync(pipeline)
            self.assertEqual(stats["status"], "success")
            self.assertEqual(stats["new_pages_indexed"], 1)
            self.assertTrue(len(pipeline.index.chunks) > initial_chunks)
            self.assertIn("https://ul.edu.pk/storage/files/notice.pdf", agent.seen)

            # Second sync with unchanged content should index 0 new pages
            stats2 = agent.sync(pipeline)
            self.assertEqual(stats2["new_pages_indexed"], 0)


if __name__ == "__main__":
    unittest.main()
