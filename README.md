# ITS Voice RAG Bot PoC

Voice-first, open-source proof-of-concept for ITS support using local STT/TTS, RAG over public KB articles, and local LLM inference via Ollama. All components are open-source, privacy-respecting, and run entirely on-device.

**Status**: ✅ Ready for production (v0.1)

## Key Features

- 🎤 **Real-time speech recognition** (Vosk STT)
- 🔊 **Text-to-speech responses** (pyttsx3 macOS voices)
- 📚 **RAG over 225 ITS KB articles** (492 chunks indexed in FAISS)
- 🤖 **Local LLM inference** (Ollama llama3.1:8b)
- 🎯 **Intent detection** (VPN, MFA, password reset, ticket creation)
- 📱 **Web UI with WebSocket** (real-time audio streaming)
- 🔒 **Privacy-first** (no cloud APIs, local processing only)

## System Requirements

- **OS**: macOS (M1/M2+ tested)
- **Python**: 3.14 (3.11+ supported, 3.14 optimized)
- **RAM**: 8GB minimum (16GB+ recommended for LLM)
- **Disk**: ~5GB (FAISS index + models)
- **Ollama**: Running locally with `llama3.1:8b` model

## Quick Start

### 1. Install Dependencies

```bash
cd /Users/eric/GitHub/live-bot-its
source .venv/bin/activate  # Virtual environment already set up
pip install -r requirements.txt
```

### 2. Verify Vosk Model

```bash
# Vosk model already downloaded to models/
ls -la models/vosk-model-small-en-us-0.15/
```

### 3. Ensure Ollama is Running

```bash
ollama list  # Should show llama3.1:8b installed
```

### 4. Start the Server

```bash
source .venv/bin/activate
python -m uvicorn app.web.server:app --host 127.0.0.1 --port 8000
```

Server runs at: **http://127.0.0.1:8000**

## Usage

### Web Interface

1. Open http://127.0.0.1:8000 in your browser
2. **Text queries**: Type questions in the input box
3. **Voice queries**: Click the record button (requires microphone + browser WebSocket support)
4. **View sources**: Each response shows the KB articles used

### Example Queries

```
"How do I connect to VPN?"
"How do I set up MFA?"
"How do I reset my password?"
"What is the WiFi network?"
"How do I access Outlook?"
"I need to create a ticket"
```

## Architecture

```
Browser (WebSocket) 
    ↓
FastAPI Server (app/web/server.py)
    ├─→ Vosk STT (speech-to-text)
    ├─→ Conversation Controller
    │   ├─→ Intent Detection
    │   ├─→ RAG Retriever (FAISS)
    │   └─→ Ollama LLM (llama3.1:8b)
    └─→ pyttsx3 TTS (text-to-speech)
```

## Project Structure

```
live-bot-its/
├── app/
│   ├── main.py                 # FastAPI app definition
│   ├── config.py               # Configuration (env vars)
│   ├── conversation/           # Conversation logic + RAG
│   ├── rag/                    # FAISS retriever + ingestion
│   ├── voice/                  # STT + TTS modules
│   └── web/
│       ├── server.py           # ASGI entry point
│       └── static/             # HTML/JS/CSS UI
├── data/
│   ├── faiss/                  # Vector index (492 chunks)
│   └── raw/                    # Raw KB articles
├── models/
│   └── vosk-model-small-en-us-0.15/  # STT model (41MB)
├── scripts/
│   ├── ingest_docs.py          # Re-ingest KB articles
│   └── test_setup.py           # Verify all components
├── .env                        # Runtime configuration
├── requirements.txt            # Python dependencies
└── SETUP_COMPLETE.md          # Detailed setup documentation
```

## Configuration

Edit `.env` to customize:

```bash
# LLM
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.1:8b

# RAG
RAG_TOP_K=5                     # Documents to retrieve
RAG_MIN_SCORE=0.35              # Relevance threshold

# Speech
STT_SAMPLE_RATE=16000           # Audio sample rate
VOSK_MODEL_PATH=./models/vosk-model-small-en-us-0.15

# Server
HOST=127.0.0.1
PORT=8000
```

## Knowledge Base

- **Source**: Loyola University Chicago ITS KB (https://services.luc.edu/TDClient/)
- **Coverage**: 225 articles on VPN, MFA, passwords, email, WiFi, and more
- **Format**: FAISS vector index (492 chunks, 384-dim embeddings)
- **Update**: Run `python scripts/ingest_docs.py` to re-scrape latest articles

## Verification

Run the setup verification:

```bash
bash verify_setup.sh
```

This checks:
- ✓ Python dependencies installed
- ✓ Vosk model available
- ✓ FAISS index loaded
- ✓ Ollama running
- ✓ FastAPI server ready

## Python Dependencies

All Python 3.14 compatible (tested):

- **fastapi** (0.109.0) - Web framework
- **uvicorn** (0.27.0) - ASGI server
- **faiss-cpu** (1.7.4) - Vector database
- **sentence-transformers** (2.2.2) - Embeddings
- **vosk** (0.3.45) - Speech recognition
- **pyttsx3** (2.92) - Text-to-speech
- **requests** (2.31.0) - HTTP client
- **beautifulsoup4** (4.12.2) - Web scraping

## Troubleshooting

### Ollama not running
```bash
# Start Ollama
ollama serve

# In another terminal, pull the model
ollama pull llama3.1:8b
```

### WebSocket connection fails
- Ensure firewall allows localhost:8000
- Check browser console for WebSocket errors
- Try a different browser (Firefox, Chrome tested)

### STT not transcribing
- Vosk model loads on first use (2-3 seconds)
- Check microphone permissions in System Preferences
- WebSocket audio must be PCM 16-bit, 16kHz

### LLM responses slow
- llama3.1:8b takes 5-20 seconds depending on response length
- Use `llama3.1:7b` for faster (but less capable) responses
- Increase system RAM allocation to Ollama

## Performance Notes

- **First STT request**: 2-3 seconds (model load)
- **Subsequent STT**: <100ms per utterance
- **RAG retrieval**: ~50-100ms (FAISS search)
- **LLM inference**: 5-20 seconds (llama3.1:8b)
- **TTS generation**: 1-2 seconds (macOS system TTS)

## Limitations

- ⚠️ Vosk model (English US only) - no multilingual support
- ⚠️ pyttsx3 limited voice options - no neural voices
- ⚠️ llama3.1:8b less capable than larger models
- ⚠️ KB limited to public Loyola ITS articles

## Next Steps

1. **Improve retrieval**: Tune `RAG_TOP_K` and `RAG_MIN_SCORE`
2. **Add custom docs**: Place files in `./data/raw/` and re-run ingestion
3. **Switch models**: Change `OLLAMA_MODEL` for different LLMs
4. **Deploy**: Docker container or systemd service for production
5. **Mobile**: WebSocket server supports mobile clients

## Security & Privacy

- ✅ All processing on-device (no cloud APIs)
- ✅ Public KB articles only (no private data)
- ✅ No audio storage (streamed to processing)
- ✅ No user data collection
- ✅ Open-source (auditable code)

## Support

See [SETUP_COMPLETE.md](SETUP_COMPLETE.md) for detailed component documentation.

---

**Built with**: FastAPI · Vosk · pyttsx3 · FAISS · sentence-transformers · Ollama
**License**: MIT
- TTS uses macOS system voices via pyttsx3 (no models needed).
- Vector storage uses FAISS for Python 3.14 compatibility.

## Public ITS seed
- https://services.luc.edu/TDClient/33/Portal/Shared/Search/?c=all&s=A
