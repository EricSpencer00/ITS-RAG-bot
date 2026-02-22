from __future__ import annotations

import os
from pathlib import Path

# Load .env file
from dotenv import load_dotenv
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path)


def _env(key: str, default: str) -> str:
    return os.getenv(key, default)


# =============================================================================
# RAG Configuration
# =============================================================================
OLLAMA_BASE_URL = _env("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = _env("OLLAMA_MODEL", "gemma:2b")  # fast default; change to llama3.1:8b for higher quality
OLLAMA_LLM_NUM_PREDICT = int(_env("OLLAMA_LLM_NUM_PREDICT", "120"))   # token cap — keeps voice responses short
OLLAMA_TEMPERATURE = float(_env("OLLAMA_TEMPERATURE", "0.15"))         # lower = more deterministic/focused
EMBED_MODEL = _env("EMBED_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
CHROMA_PATH = _env("CHROMA_PATH", "./data/faiss")
RAW_DOCS_PATH = _env("RAW_DOCS_PATH", "./data/raw")

RAG_TOP_K = int(_env("RAG_TOP_K", "5"))
RAG_MIN_SCORE = float(_env("RAG_MIN_SCORE", "0.35"))


# =============================================================================
# Server Configuration
# =============================================================================
HOST = _env("HOST", "0.0.0.0")
PORT = int(_env("PORT", "8000"))


# =============================================================================
# STT Configuration — faster-whisper (CTranslate2)
# =============================================================================
# Model sizes: tiny, base, small, medium, large-v3
# "base" is a good balance of speed & accuracy for M1
WHISPER_MODEL_SIZE = _env("WHISPER_MODEL_SIZE", "tiny.en")
WHISPER_DEVICE = _env("WHISPER_DEVICE", "cpu")       # cpu works great on M1
WHISPER_COMPUTE_TYPE = _env("WHISPER_COMPUTE_TYPE", "int8")  # int8 is fastest on CPU
STT_SAMPLE_RATE = int(_env("STT_SAMPLE_RATE", "16000"))
# Number of silent 100ms chunks before STT commits (4 = ~400ms, was 8 = ~800ms)
STT_SILENCE_CHUNKS = int(_env("STT_SILENCE_CHUNKS", "4"))


# =============================================================================
# TTS Configuration — Edge TTS (Microsoft neural voices)
# =============================================================================
# Popular voices:
#   en-US-GuyNeural      — male, professional
#   en-US-JennyNeural     — female, friendly
#   en-US-AriaNeural      — female, conversational
#   en-US-DavisNeural     — male, calm
TTS_VOICE = _env("TTS_VOICE", "en-US-GuyNeural")
TTS_RATE = _env("TTS_RATE", "+15%")     # speaking speed adjustment
TTS_VOLUME = _env("TTS_VOLUME", "+0%")  # volume adjustment
# Minimum chars in TTS buffer before a comma-break is allowed
TTS_CHUNK_MIN_CHARS = int(_env("TTS_CHUNK_MIN_CHARS", "60"))
