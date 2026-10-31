"""Build the search index from crawled pages + hand-written notes.

Usage:  python -m app.ingest
"""
from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
import re
import numpy as np

from . import config
from .chunking import chunk_page
from .embeddings import get_embedder
from .store import Index

log = logging.getLogger("ul-chatbot.ingest")


def compute_chunk_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_cache(cache_path: Path = config.INGEST_CACHE_PATH) -> dict[str, np.ndarray]:
    """Load cached chunk text hash -> embedding vector mapping."""
    cache: dict[str, np.ndarray] = {}
    if cache_path.exists():
        try:
            data = np.load(cache_path, allow_pickle=True)
            hashes = data["hashes"]
            embeddings = data["embeddings"]
            for h, vec in zip(hashes, embeddings):
                cache[str(h)] = np.asarray(vec, dtype=np.float32)
            return cache
        except Exception as exc:
            log.warning("Could not load embedding cache from %s: %s", cache_path, exc)

    # Fallback / Seed from existing index if available
    chunks_file = config.INDEX_DIR / "chunks.json"
    emb_file = config.INDEX_DIR / "embeddings.npy"
    if chunks_file.exists() and emb_file.exists():
        try:
            c_data = json.loads(chunks_file.read_text(encoding="utf-8"))
            e_data = np.load(emb_file)
            if len(c_data) == len(e_data):
                for c, vec in zip(c_data, e_data):
                    h = compute_chunk_hash(c["text"])
                    cache[h] = np.asarray(vec, dtype=np.float32)
        except Exception:
            pass
    return cache


def save_cache(cache: dict[str, np.ndarray], cache_path: Path = config.INGEST_CACHE_PATH) -> None:
    """Persist chunk embedding cache to disk."""
    if not cache:
        return
    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        hashes = np.array(list(cache.keys()))
        embeddings = np.array(list(cache.values()), dtype=np.float32)
        np.savez_compressed(cache_path, hashes=hashes, embeddings=embeddings)
    except Exception as exc:
        log.warning("Could not save embedding cache to %s: %s", cache_path, exc)


def embed_chunks_cached(
    chunks: list[dict],
    embedder=None,
    cache_path: Path = config.INGEST_CACHE_PATH,
) -> np.ndarray:
    """Embed chunks using incremental hash caching.
    
    Unchanged chunks reuse cached embeddings without re-invoking the model.
    """
    if not chunks:
        return np.zeros((0, 384), dtype=np.float32)

    cache = load_cache(cache_path)
    cached_count = 0
    missing_indices = []
    missing_texts = []
    result_vectors = [None] * len(chunks)

    for i, chunk in enumerate(chunks):
        h = compute_chunk_hash(chunk["text"])
        if h in cache:
            result_vectors[i] = cache[h]
            cached_count += 1
        else:
            missing_indices.append(i)
            missing_texts.append(chunk["text"])

    if missing_texts:
        if embedder is None:
            embedder = get_embedder()
        print(f"Generating embeddings for {len(missing_texts)} new/modified chunks ({cached_count} loaded from cache)...")
        new_vecs = embedder.encode_passages(missing_texts)
        for idx, vec in zip(missing_indices, new_vecs):
            h = compute_chunk_hash(chunks[idx]["text"])
            cache[h] = vec
            result_vectors[idx] = vec
        save_cache(cache, cache_path)
    else:
        print(f"All {cached_count} chunk embeddings loaded from incremental cache without regeneration.")

    return np.asarray(result_vectors, dtype=np.float32)


def load_crawled() -> list[dict]:
    if not config.RAW_PAGES.exists():
        print(f"(no crawled data at {config.RAW_PAGES} - run: python -m app.crawler)")
        return []
    with config.RAW_PAGES.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def load_manual() -> list[dict]:
    """Markdown files in data/manual. Optional first line:  url: https://...
    Use them for facts that are not on the website (or are only inside images)."""
    pages = []
    for path in sorted(config.MANUAL_DIR.glob("*.md")):
        text = path.read_text(encoding="utf-8").strip()
        url = f"https://{config.SITE_HOST}/"
        m = re.match(r"url:\s*(\S+)\s*\n", text)
        if m:
            url, text = m.group(1), text[m.end():].strip()
        h = re.search(r"^#\s+(.+)$", text, re.M)
        pages.append({"url": url, "title": h.group(1).strip() if h else path.stem,
                      "text": text, "type": "manual"})
    return pages


def main() -> None:
    pages = load_crawled() + load_manual()
    chunks = [c for p in pages for c in chunk_page(p, config.CHUNK_WORDS, config.CHUNK_OVERLAP)]
    if not chunks:
        raise SystemExit("Nothing to index. Run the crawler first.")
    print(f"{len(pages)} pages -> {len(chunks)} chunks.")
    vectors = embed_chunks_cached(chunks)
    Index(chunks, vectors).save(config.INDEX_DIR)
    print(f"Index saved to {config.INDEX_DIR}")


if __name__ == "__main__":
    main()
