"""Split page text into overlapping, self-describing chunks."""
from __future__ import annotations

import hashlib


def _split_long_line(line: str, max_words: int) -> list[str]:
    words = line.split()
    return [" ".join(words[i:i + max_words]) for i in range(0, len(words), max_words)]


def split_text(text: str, max_words: int = 180, overlap_words: int = 30) -> list[str]:
    """Pack whole lines into chunks of ~max_words, carrying a small overlap."""
    lines: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        lines.extend(_split_long_line(line, max_words) if len(line.split()) > max_words else [line])

    chunks: list[str] = []
    current: list[str] = []
    count = 0
    for line in lines:
        n = len(line.split())
        if current and count + n > max_words:
            chunks.append("\n".join(current))
            tail: list[str] = []
            tail_words = 0
            for prev in reversed(current):  # overlap: reuse the last few lines
                w = len(prev.split())
                if tail_words + w > overlap_words:
                    break
                tail.insert(0, prev)
                tail_words += w
            current, count = tail, tail_words
        current.append(line)
        count += n
    if current:
        last = "\n".join(current)
        if not chunks or last != chunks[-1]:
            chunks.append(last)
    return chunks


def chunk_page(page: dict, max_words: int = 180, overlap_words: int = 30) -> list[dict]:
    title = (page.get("title") or "").strip()
    url = page["url"]
    uid = hashlib.md5(url.encode("utf-8")).hexdigest()[:8]
    out = []
    for i, body in enumerate(split_text(page["text"], max_words, overlap_words)):
        out.append({
            "id": f"{uid}-{i}",
            "url": url,
            "title": title,
            # Title is repeated in every chunk so the chunk is meaningful on its own.
            "text": f"{title}\n{body}" if title else body,
        })
    return out
