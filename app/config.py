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
# RAG Configuration (kept from original)
# =============================================================================
OLLAMA_BASE_URL = _env("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = _env("OLLAMA_MODEL", "llama3.1:8b")
EMBED_MODEL = _env("EMBED_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
CHROMA_PATH = _env("CHROMA_PATH", "./data/faiss")
RAW_DOCS_PATH = _env("RAW_DOCS_PATH", "./data/raw")

RAG_TOP_K = int(_env("RAG_TOP_K", "5"))
RAG_MIN_SCORE = float(_env("RAG_MIN_SCORE", "0.35"))


# =============================================================================
# PersonaPlex Configuration
# =============================================================================
# HuggingFace token for accessing PersonaPlex model
# Get yours at: https://huggingface.co/settings/tokens
# Must accept license at: https://huggingface.co/nvidia/personaplex-7b-v1
HF_TOKEN = _env("HF_TOKEN", "")
HF_REPO = _env("HF_REPO", "nvidia/personaplex-7b-v1")

# Device configuration
# Options: "cuda", "cpu", or specific device like "cuda:0"
PERSONAPLEX_DEVICE = _env("PERSONAPLEX_DEVICE", "cuda")

# Enable CPU offloading for systems with limited GPU memory
# Requires 'accelerate' package: pip install accelerate
PERSONAPLEX_CPU_OFFLOAD = _env("PERSONAPLEX_CPU_OFFLOAD", "false").lower() == "true"

# Voice prompt directory (downloaded automatically if not set)
VOICE_PROMPT_DIR = _env("VOICE_PROMPT_DIR", "")
if VOICE_PROMPT_DIR == "":
    VOICE_PROMPT_DIR = None

# Default voice prompt (available: NATF0-3, NATM0-3, VARF0-4, VARM0-4)
# NAT = Natural sounding, VAR = Variety voices
# F = Female, M = Male
DEFAULT_VOICE_PROMPT = _env("DEFAULT_VOICE_PROMPT", "NATF2")

# Default text prompt for persona
# Examples:
#   "You are a wise and friendly teacher."
#   "You enjoy having a good conversation."
#   "You work for ITS Support and help users with technical issues."
DEFAULT_TEXT_PROMPT = _env(
    "DEFAULT_TEXT_PROMPT",
    "You are a helpful ITS support assistant. You help users with technology questions clearly and friendly."
)

# Audio sample rate (PersonaPlex uses 24kHz)
PERSONAPLEX_SAMPLE_RATE = 24000


# =============================================================================
# Server Configuration  
# =============================================================================
HOST = _env("HOST", "0.0.0.0")
PORT = int(_env("PORT", "8998"))

# SSL configuration for secure WebSocket (required for microphone access)
SSL_DIR = _env("SSL_DIR", "")
if SSL_DIR == "":
    SSL_DIR = None


# =============================================================================
# Voice Configuration (Vosk + Pyttsx3)
# =============================================================================
VOSK_MODEL_PATH = _env("VOSK_MODEL_PATH", "./models/vosk-model-small-en-us-0.15")
STT_SAMPLE_RATE = int(_env("STT_SAMPLE_RATE", "16000"))
PIPER_SPEAKER_ID = int(_env("PIPER_SPEAKER_ID", "0"))
