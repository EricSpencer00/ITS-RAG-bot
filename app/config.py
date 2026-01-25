from __future__ import annotations

import os


def _env(key: str, default: str) -> str:
    return os.getenv(key, default)


OLLAMA_BASE_URL = _env("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = _env("OLLAMA_MODEL", "llama3.1:8b")
EMBED_MODEL = _env("EMBED_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
CHROMA_PATH = _env("CHROMA_PATH", "./data/faiss")
RAW_DOCS_PATH = _env("RAW_DOCS_PATH", "./data/raw")

VOSK_MODEL_PATH = _env("VOSK_MODEL_PATH", "./models/vosk-model-small-en-us-0.15")
STT_SAMPLE_RATE = int(_env("STT_SAMPLE_RATE", "16000"))

PIPER_SPEAKER_ID = int(_env("PIPER_SPEAKER_ID", "0"))

RAG_TOP_K = int(_env("RAG_TOP_K", "5"))
RAG_MIN_SCORE = float(_env("RAG_MIN_SCORE", "0.35"))

HOST = _env("HOST", "127.0.0.1")
PORT = int(_env("PORT", "8000"))
