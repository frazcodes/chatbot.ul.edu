"""Multilingual sentence embeddings (runs locally, free, no API key)."""
from __future__ import annotations

import numpy as np

from . import config


class Embedder:
    """Wraps a sentence-transformers model. E5 models need query/passage prefixes."""

    def __init__(self, model_name: str | None = None):
        from sentence_transformers import SentenceTransformer  # lazy: heavy import

        local_model_dir = config.ROOT / "models" / "multilingual-e5-small"
        if model_name is None and local_model_dir.exists() and (local_model_dir / "model.safetensors").exists():
            self.model_name = str(local_model_dir)
        else:
            self.model_name = model_name or config.EMBED_MODEL
        self.model = SentenceTransformer(self.model_name)
        self._e5 = "e5" in self.model_name.lower()

    def _encode(self, texts: list[str]) -> np.ndarray:
        vecs = self.model.encode(texts, batch_size=32, normalize_embeddings=True,
                                 show_progress_bar=False)
        return np.asarray(vecs, dtype=np.float32)

    def encode_passages(self, texts: list[str]) -> np.ndarray:
        if self._e5:
            texts = [f"passage: {t}" for t in texts]
        return self._encode(texts)

    def encode_query(self, text: str) -> np.ndarray:
        return self._encode([f"query: {text}" if self._e5 else text])[0]


_instance: Embedder | None = None


def get_embedder() -> Embedder:
    global _instance
    if _instance is None:
        _instance = Embedder()
    return _instance
