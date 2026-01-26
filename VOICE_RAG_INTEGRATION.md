# PersonaPlex Voice + RAG Integration Guide

## Overview

This application integrates **NVIDIA PersonaPlex-7b-v1** (a 7 billion parameter speech-to-speech model) with a **Retrieval Augmented Generation (RAG)** pipeline to create a voice-first conversational AI assistant.

### Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         Browser (Web UI)                        │
│                                                                 │
│  ┌────────────────────────────────────────────────────────────┐│
│  │ 1. Audio Capture (MediaRecorder → Opus)                    ││
│  │ 2. WebSocket Communication (binary protocol)               ││
│  │ 3. Audio Playback (Opus → AudioContext)                    ││
│  │ 4. Real-time transcript + response display                 ││
│  └────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────┘
           ↕ Binary WebSocket (0x01 audio, 0x02 text)
┌─────────────────────────────────────────────────────────────────┐
│                      FastAPI/aiohttp Server                     │
│                                                                 │
│  ┌────────────────────────────────────────────────────────────┐│
│  │ PersonaPlexEngine (/api/chat WebSocket)                    ││
│  │  ├─ Receives Opus-encoded audio from client               ││
│  │  ├─ Decodes to PCM (sphn library)                         ││
│  │  ├─ Encodes to Mimi codes (speech codec)                  ││
│  │  ├─ Generates response tokens (Moshi LM)                  ││
│  │  ├─ Decodes to speech (Mimi codec)                        ││
│  │  ├─ Encodes to Opus (sphn library)                        ││
│  │  └─ Sends back to client                                  ││
│  └────────────────────────────────────────────────────────────┘│
│                                                                 │
│  Optional: RAG Integration (Future)                            │
│  ├─ Transcribe user audio to text (Vosk or similar)           │
│  ├─ Query FAISS index with user intent                        │
│  ├─ Format context from retrieved documents                   │
│  └─ Inject into PersonaPlex text prompts                      │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
           ↓ (Optional RAG)
┌─────────────────────────────────────────────────────────────────┐
│ RAG System (Conversation Controller + Retriever)                │
│  ├─ Retriever: FAISS vector search on ITS docs                │
│  ├─ Controller: Orchestrates LLM + RAG logic                  │
│  └─ LLM: Local Ollama instance (provides grounding)           │
└─────────────────────────────────────────────────────────────────┘
```

## Key Components

### 1. **PersonaPlex Engine** (`app/voice/personaplex.py`)
- **Mimi Codec**: Neural audio encoder/decoder at 24kHz
- **Moshi LM**: Speech-to-speech generation with streaming
- **Vosk Integration** (optional): Speech-to-text transcription
- **Opus Streaming**: Low-latency audio transport via WebSocket

### 2. **Web Server** (`app/main.py`)
- **FastAPI** + **aiohttp**: Serves UI and handles WebSocket
- **Binary Protocol**:
  - `0x00`: Handshake complete
  - `0x01 + data`: Audio (Opus encoded)
  - `0x02 + data`: Text tokens
  - `0x03 + data`: Error messages

### 3. **Frontend** (`app/web/static/app.js`)
- **MediaRecorder API**: Captures microphone audio as WebM/Opus
- **AudioContext**: Plays server-generated Opus audio
- **Real-time Visualization**: Displays connection status & transcript

### 4. **RAG Pipeline** (`app/conversation/`, `app/rag/`)
- **Retriever**: FAISS vector search over ITS documentation
- **Conversation Controller**: Manages state and RAG queries
- **Local LLM**: Ollama for grounding responses

## Running the Application

### Prerequisites
```bash
# Ensure you have:
# - Python 3.14+
# - NVIDIA GPU (or use CPU fallback)
# - Ollama running locally (for RAG grounding)
# - HuggingFace token with access to nvidia/personaplex-7b-v1

# Set environment variables:
export HF_TOKEN="your_hf_token_here"
export OLLAMA_BASE_URL="http://localhost:11434"
```

### Startup
```bash
# Activate virtual environment
source .venv/bin/activate

# Run the server (model downloads ~16.7GB on first run)
python scripts/run_dev.py

# Access the UI at: https://localhost:8998
# (or https://<your-ip>:8998 for remote access)
```

### First Run
1. Server will initialize the PersonaPlex engine (~5-10 minutes on first run)
2. Model files (~16.7GB) will be downloaded and cached
3. Voice prompts (18 variants) will be extracted
4. Warmup runs will prepare GPU/CPU
5. Server will be ready for connections

## Technical Details

### Audio Codec Details
- **Incoming**: Browser captures 16-bit PCM → encodes as Opus (WebM container) → sends as binary
- **Server**: Receives WebM → decodes to Opus stream → decodes to PCM with `sphn.OpusStreamReader`
- **Processing**: PCM → Mimi codes → Moshi tokens → Mimi PCM → Opus stream
- **Outgoing**: Opus stream → encodes to Opus packets → sends as binary → browser decodes

### Sampling Rates
- **PersonaPlex**: 24kHz (Mimi codec native)
- **Browser**: 24kHz (AudioContext sample rate)
- **Opus**: Supports 8/12/16/24kHz

### Streaming Architecture
- **Receive Loop**: Non-blocking deque-based buffering
- **Generation Loop**: Continuous frame processing with 1ms yield
- **Send Loop**: Buffered Opus transmission with 10ms pacing
- **CPU**: ~8 cores, minimal overhead per frame

## Integration Points for RAG

### Current Status
PersonaPlex currently generates pure conversational responses based on voice/text prompts, without RAG context.

### Planned Integration Approaches

#### Option 1: Prompt Engineering (Simplest)
```python
# Inject RAG context into the text prompt
text_prompt = f"""
You are a helpful ITS support assistant. Use ONLY the following context to answer questions:

{rag_context}

If the user asks about something not in the context, politely decline and suggest they contact the ITS Service Desk.
"""
```

#### Option 2: Streaming Token Injection (Advanced)
```python
# Intercept Moshi token generation
# Inject RAG tokens alongside user tokens
# Allows real-time RAG grounding during generation
```

#### Option 3: Hybrid Voice + RAG (Recommended)
```python
# Run PersonaPlex for natural voice generation
# Parallel: Run Vosk/Whisper for transcription
# Parallel: Run RAG retriever on transcribed text
# Combine: Use RAG context to guide PersonaPlex generation
```

## Configuration

### Environment Variables
```bash
# HuggingFace
export HF_TOKEN="hf_xxxxx"
export HF_REPO="nvidia/personaplex-7b-v1"

# Server
export HOST="0.0.0.0"
export PORT="8998"
export SSL_DIR=".ssl"

# PersonaPlex
export PERSONAPLEX_DEVICE="cuda"  # or "cpu"
export PERSONAPLEX_CPU_OFFLOAD="false"
export DEFAULT_VOICE_PROMPT="NATF2"
export DEFAULT_TEXT_PROMPT="You are a helpful assistant."

# RAG (if using)
export OLLAMA_BASE_URL="http://localhost:11434"
export OLLAMA_MODEL="mistral"
export CHROMA_PATH="./data/faiss"
export RAG_TOP_K="3"
export RAG_MIN_SCORE="0.5"
```

### Model Files
```
~/.cache/huggingface/hub/models--nvidia--personaplex-7b-v1/
├── model.safetensors                          (16.7GB - Moshi LM)
├── tokenizer-e351c8d8-checkpoint125.safetensors  (Mimi codec)
├── tokenizer_spm_32k_3.model                  (Text tokenizer)
└── voices/                                     (18 voice prompts)
    ├── NATF1.pt, NATF2.pt, ... NATM4.pt
    ├── VARF1.pt, VARF2.pt, ... VARM4.pt
    └── ...
```

## Troubleshooting

### "Nothing is coming out of the agent to my speakers"
1. Check browser console (F12) for audio decode errors
2. Verify Opus codec support in browser
3. Check server logs for generation errors
4. Try a different voice prompt
5. Verify GPU memory (requires ~10GB VRAM)

### "Model download is slow"
- First download is ~16.7GB and will take 5-15 minutes depending on connection
- Models are cached in `~/.cache/huggingface/` for subsequent runs
- Use a wired connection for faster downloads

### "Server freezes on first connection"
- Fixed in v2.0: Model now preloads at server startup
- Watch for "Engine initialized" message before connecting

### "404 Model not found"
- Verify `HF_TOKEN` is set and has access to gated model
- Visit https://huggingface.co/nvidia/personaplex-7b-v1 to request access

## Performance Notes

### Latency
- **Audio capture**: ~20ms
- **Opus encode**: ~5ms
- **Network**: ~50-200ms (depends on connection)
- **PersonaPlex token generation**: ~20-50ms per frame
- **Opus decode**: ~5ms
- **Audio playback**: ~20ms
- **End-to-end**: ~150-400ms (typical)

### Resource Usage
- **GPU**: ~10GB VRAM (8.4GB model + overhead)
- **CPU**: ~2-4 cores during inference
- **Memory**: ~16GB system RAM
- **Bandwidth**: ~64kbps Opus (16ms voice frames every 20ms)

### Throughput
- **Speech frames**: 960 samples @ 24kHz = 40ms per frame
- **Token generation**: 8-12 tokens per frame (variable)
- **Effective bitrate**: 24kHz × 24-bit = 576kbps PCM → 64kbps Opus (11:1 compression)

## References

- [NVIDIA PersonaPlex GitHub](https://github.com/NVIDIA/personaplex)
- [Moshi Paper](https://arxiv.org/abs/2410.00037)
- [sphn (Opus Python bindings)](https://github.com/anibali/sphn)
- [WebSocket Binary Protocol](https://developer.mozilla.org/en-US/docs/Web/API/WebSocket)
- [24kHz Audio](https://www.sweetwater.com/insync/sample-rate/)
