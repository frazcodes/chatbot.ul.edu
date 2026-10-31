"""Hybrid search index: dense vectors + BM25 keywords, fused with Reciprocal Rank Fusion."""
from __future__ import annotations

import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

import threading

RRF_K = 60
_STOP = set(
    "the a an of and or to in on at for is are was were be been by with from as that this it its "
    "what which who whom how when where do does did can could i you we they he she me my your our "
    "their about into than then so if not no".split()
)
_TOKEN = re.compile(r"\w+", re.UNICODE)


def tokenize(text: str) -> list[str]:
    return [t for t in _TOKEN.findall(text.lower())
            if t not in _STOP and (len(t) > 1 or t.isdigit())]


class BM25:
    def __init__(self, docs: list[list[str]], k1: float = 1.5, b: float = 0.75):
        self.n, self.k1, self.b = len(docs), k1, b
        self.dl = np.array([len(d) for d in docs], dtype=np.float32)
        self.avgdl = float(self.dl.mean()) if self.n else 1.0
        self.postings: dict[str, list[tuple[int, int]]] = defaultdict(list)
        for i, d in enumerate(docs):
            for term, tf in Counter(d).items():
                self.postings[term].append((i, tf))
        self.idf = {
            t: math.log(1 + (self.n - len(p) + 0.5) / (len(p) + 0.5))
            for t, p in self.postings.items()
        }

    def scores(self, query_tokens: list[str]) -> np.ndarray:
        s = np.zeros(self.n, dtype=np.float32)
        for term in set(query_tokens):
            for i, tf in self.postings.get(term, ()):
                norm = tf + self.k1 * (1 - self.b + self.b * self.dl[i] / (self.avgdl or 1))
                s[i] += self.idf[term] * tf * (self.k1 + 1) / norm
        return s


class Index:
    def __init__(self, chunks: list[dict], embeddings: np.ndarray):
        assert len(chunks) == len(embeddings)
        self._lock = threading.Lock()
        self.chunks = list(chunks)
        self.emb = np.asarray(embeddings, dtype=np.float32)
        self.bm25 = BM25([tokenize(c["text"]) for c in chunks])

    # -- persistence ---------------------------------------------------------
    def save(self, directory: Path) -> None:
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "chunks.json").write_text(
            json.dumps(self.chunks, ensure_ascii=False), encoding="utf-8")
        np.save(directory / "embeddings.npy", self.emb)

    @classmethod
    def load(cls, directory: Path) -> "Index":
        chunks = json.loads((directory / "chunks.json").read_text(encoding="utf-8"))
        return cls(chunks, np.load(directory / "embeddings.npy"))

    def add_chunks(
        self,
        new_chunks: list[dict],
        new_embeddings: np.ndarray,
        replace_existing_urls: bool = True,
        directory: Path | None = None,
    ) -> int:
        """Incrementally update the live index.
        
        When replace_existing_urls is True, existing active chunks matching the same URLs
        are cleanly superseded and removed from the active search index, preserving version
        integrity and preventing old and new document chunks from being active simultaneously.
        """
        if not new_chunks:
            return 0
        assert len(new_chunks) == len(new_embeddings), "Chunks and embeddings count must match"
        new_vecs = np.asarray(new_embeddings, dtype=np.float32)

        if len(self.emb) > 0 and self.emb.shape[1] != new_vecs.shape[1]:
            raise ValueError(
                f"Embedding dimension mismatch: existing index has dimension {self.emb.shape[1]} "
                f"but new vectors have dimension {new_vecs.shape[1]}. "
                "Re-run: python -m app.ingest to rebuild the index."
            )

        with self._lock:
            superseded: list[dict] = []
            if replace_existing_urls and self.chunks:
                new_urls = {c["url"] for c in new_chunks if "url" in c}
                keep_indices = []
                for idx, c in enumerate(self.chunks):
                    if c.get("url") in new_urls:
                        c_copy = dict(c)
                        c_copy["is_superseded"] = True
                        superseded.append(c_copy)
                    else:
                        keep_indices.append(idx)

                retained_chunks = [self.chunks[i] for i in keep_indices]
                retained_emb = self.emb[keep_indices] if len(keep_indices) > 0 else np.zeros((0, new_vecs.shape[1]), dtype=np.float32)
                
                # Tag new chunks
                active_new_chunks = []
                for c in new_chunks:
                    c_clean = dict(c)
                    c_clean["is_superseded"] = False
                    active_new_chunks.append(c_clean)

                combined_chunks = retained_chunks + active_new_chunks
                if len(retained_emb) == 0:
                    combined_emb = new_vecs
                else:
                    combined_emb = np.vstack([retained_emb, new_vecs])
            else:
                active_new_chunks = []
                for c in new_chunks:
                    c_clean = dict(c)
                    c_clean["is_superseded"] = False
                    active_new_chunks.append(c_clean)
                combined_chunks = list(self.chunks) + active_new_chunks
                if len(self.emb) == 0:
                    combined_emb = new_vecs
                else:
                    combined_emb = np.vstack([self.emb, new_vecs])

            # Prepare new BM25 index completely before swapping references
            new_bm25 = BM25([tokenize(c["text"]) for c in combined_chunks])

            # Atomic reference swap: readers never observe a partially updated state
            self.chunks = combined_chunks
            self.emb = combined_emb
            self.bm25 = new_bm25

            if directory is not None:
                self.save(directory)
                if superseded:
                    try:
                        superseded_log = directory / "superseded_chunks.jsonl"
                        with superseded_log.open("a", encoding="utf-8") as f:
                            for sc in superseded:
                                f.write(json.dumps(sc, ensure_ascii=False) + "\n")
                    except Exception:
                        pass

            return len(new_chunks)

    # -- search --------------------------------------------------------------
    def search(self, query_vec: np.ndarray, query_text: str,
               top_k: int = 6, pool: int = 24, per_url: int = 3) -> list[dict]:
        with self._lock:
            chunks = self.chunks
            emb = self.emb
            bm25 = self.bm25

        if not chunks:
            return []
        dense = emb @ query_vec
        bm = bm25.scores(tokenize(query_text))

        fused: dict[int, float] = defaultdict(float)
        for rank, i in enumerate(np.argsort(-dense)[:pool]):
            fused[int(i)] += 1.0 / (RRF_K + rank + 1)
        keyword_ids = [int(i) for i in np.argsort(-bm)[:pool] if bm[i] > 0]
        for rank, i in enumerate(keyword_ids):
            fused[i] += 1.0 / (RRF_K + rank + 1)

        hits, per_page = [], Counter()
        for i, score in sorted(fused.items(), key=lambda kv: -kv[1]):
            url = chunks[i]["url"]
            if per_page[url] >= per_url:  # keep results diverse
                continue
            per_page[url] += 1
            hits.append({"chunk": chunks[i], "score": score,
                         "dense": float(dense[i]), "bm25": float(bm[i])})
            if len(hits) >= top_k:
                break
        return hits
