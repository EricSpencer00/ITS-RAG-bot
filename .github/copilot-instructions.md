# ITS Voice RAG Bot - Copilot Instructions

This workspace contains a voice-first PoC for ITS support using:
- FastAPI web server with WebSocket audio streaming
- Vosk for STT (speech-to-text)
- pyttsx3 for TTS (text-to-speech) via macOS system voices
- FAISS for vector storage
- sentence-transformers for embeddings
- Ollama for local LLM inference
- Public ITS documentation only (no private/internal data)

## Project Structure
- app/ - Main application code
  - voice/ - STT and TTS modules
  - rag/ - Retrieval and ingestion
  - conversation/ - State and controller
  - web/ - FastAPI server and static files
  - config.py - Environment configuration
- data/ - Raw documents and FAISS index
- scripts/ - Ingestion and server runner
- requirements.txt - Python dependencies

## Key Commands
- Ingest docs: python scripts/ingest_docs.py
- Run server: python scripts/run_dev.py
- Access UI: http://127.0.0.1:8000

## Notes
- Python 3.14 compatible (uses FAISS instead of chromadb)
- Requires Ollama running locally
- Vosk model must be downloaded separately
- All data sources must be public
