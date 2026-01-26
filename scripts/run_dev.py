#!/usr/bin/env python3
"""
ITS Voice RAG Bot Development Server

Starts the FastAPI server with Vosk STT and pyttsx3 TTS.
"""
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)
