"""Central settings. Values come from environment variables or a local .env file."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_env_file() -> None:
    path = ROOT / ".env"
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_env_file()


def _bool(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


# --- Paths -----------------------------------------------------------------
RAW_PAGES = ROOT / "data" / "raw" / "pages.jsonl"
MANUAL_DIR = ROOT / "data" / "manual"
INDEX_DIR = ROOT / "data" / "index"
STATIC_DIR = ROOT / "static"
UNANSWERED_LOG = ROOT / "data" / "unanswered.jsonl"
WATCHER_STATE = ROOT / "data" / "watcher_state.json"

# --- Crawler & Watcher Agent -----------------------------------------------
SITE_HOST = os.getenv("SITE_HOST", "ul.edu.pk")
MAX_PAGES = int(os.getenv("MAX_PAGES", "600"))
CRAWL_DELAY = float(os.getenv("CRAWL_DELAY", "0.6"))
AUTO_SYNC_ENABLED = _bool("AUTO_SYNC_ENABLED", True)
AUTO_SYNC_INTERVAL_MINUTES = int(os.getenv("AUTO_SYNC_INTERVAL_MINUTES", "60"))
WATCHER_MAX_DEPTH = int(os.getenv("WATCHER_MAX_DEPTH", "2"))
INGEST_CACHE_PATH = INDEX_DIR / "embeddings_cache.npz"

# --- Retrieval -------------------------------------------------------------
EMBED_MODEL = os.getenv("EMBED_MODEL", "intfloat/multilingual-e5-small")
TOP_K = int(os.getenv("TOP_K", "8"))
CHUNK_WORDS = int(os.getenv("CHUNK_WORDS", "180"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "30"))

# --- LLM -------------------------------------------------------------------
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "qwen/qwen3.8-27b")

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-3-5-haiku-20241022")

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "").lower()
if not LLM_PROVIDER:
    if GROQ_API_KEY:
        LLM_PROVIDER = "groq"
    elif ANTHROPIC_API_KEY:
        LLM_PROVIDER = "anthropic"
    else:
        LLM_PROVIDER = "groq"

REWRITE_QUERY = _bool("REWRITE_QUERY", True)
MAX_ANSWER_TOKENS = int(os.getenv("MAX_ANSWER_TOKENS", "700"))
HISTORY_TURNS = int(os.getenv("HISTORY_TURNS", "6"))

# --- API -------------------------------------------------------------------
ALLOWED_ORIGINS = [
    o.strip()
    for o in os.getenv(
        "ALLOWED_ORIGINS",
        "https://ul.edu.pk,https://www.ul.edu.pk,http://localhost:8000,http://127.0.0.1:8000",
    ).split(",")
    if o.strip()
]
RATE_LIMIT_PER_MIN = int(os.getenv("RATE_LIMIT_PER_MIN", "20"))
TRUST_PROXY = _bool("TRUST_PROXY", False)
MAX_MESSAGE_CHARS = int(os.getenv("MAX_MESSAGE_CHARS", "600"))
