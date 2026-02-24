from __future__ import annotations

import pickle
from pathlib import Path
from typing import List, Dict

# these imports are heavy and not required for a stripped-down demo; if the
# ML/RAG dependencies are missing the module will still import but the
# Retriever class raises a helpful error when used.
try:
    import faiss
    import numpy as np
    from sentence_transformers import SentenceTransformer
except ImportError:  # pragma: no cover - demo environment may omit these
    faiss = None  # type: ignore[var-annotated]
    np = None  # type: ignore[var-annotated]
    SentenceTransformer = None  # type: ignore[var-annotated]

from app.config import CHROMA_PATH, EMBED_MODEL, RAG_TOP_K, RAG_MIN_SCORE


class Retriever:
    def __init__(self) -> None:
        if SentenceTransformer is None or faiss is None or np is None:
            raise RuntimeError(
                "RAG/embedding libraries not installed. "
                "Install the full requirements (`requirements-full.txt`) or run in an environment "
                "that includes `faiss-cpu` and `sentence-transformers`."
            )

        self.embedder = SentenceTransformer(EMBED_MODEL)
        index_path = Path(CHROMA_PATH) / "faiss.index"
        meta_path = Path(CHROMA_PATH) / "metadata.pkl"
        
        if index_path.exists() and meta_path.exists():
            self.index = faiss.read_index(str(index_path))
            with open(meta_path, "rb") as f:
                self.metadata = pickle.load(f)
        else:
            self.index = faiss.IndexFlatIP(384)  # all-MiniLM-L6-v2 dimension
            self.metadata = []

    def query(self, text: str) -> List[Dict[str, str]]:
        if self.index.ntotal == 0:
            return []
        
        query_emb = self.embedder.encode([text], normalize_embeddings=True)
        scores, indices = self.index.search(query_emb, min(RAG_TOP_K, self.index.ntotal))
        
        docs = []
        for score, idx in zip(scores[0], indices[0]):
            if idx == -1 or score < RAG_MIN_SCORE:
                continue
            meta = self.metadata[idx]
            docs.append({
                "content": meta["content"],
                "source": meta.get("source", "unknown"),
                "title": meta.get("title", ""),
                "score": f"{score:.3f}",
            })
        return docs
