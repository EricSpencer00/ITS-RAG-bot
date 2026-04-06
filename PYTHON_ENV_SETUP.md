# Python Environment Setup Guide

This guide covers setting up a Python virtual environment for the ITS Voice RAG Bot.

## Quick Start (macOS/Linux)

### 1. Create Virtual Environment
```bash
# Navigate to project
cd /Users/eric/GitHub/live-bot-its

# Create venv
python3 -m venv venv

# Activate it
source venv/bin/activate

# Verify (should show venv in prompt)
which python
```

### 2. Install Dependencies

**Core (minimal, voice + chat only):**
```bash
pip install --upgrade pip
pip install -r requirements.txt
```

**Full (includes RAG, embeddings, local inference):**
```bash
pip install --upgrade pip
pip install -r requirements-full.txt
```

The difference:
- `requirements.txt` — FastAPI, edge-tts, requests (lightweight)
- `requirements-full.txt` — adds faiss-cpu, sentence-transformers, faster-whisper, torch (for local models)

### 3. Verify Installation
```bash
python -c "from app.main import app; print('✓ App imports successfully')"
```

---

## Full Setup Instructions

### Step 1: Python Version
Requires **Python 3.8+** (tested on 3.9, 3.10, 3.11)

Check your version:
```bash
python3 --version
```

### Step 2: Create Virtual Environment

**macOS/Linux:**
```bash
python3 -m venv venv
source venv/bin/activate
```

**Windows (PowerShell):**
```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

**Windows (CMD):**
```cmd
python -m venv venv
venv\Scripts\activate.bat
```

### Step 3: Upgrade pip, setuptools, wheel
```bash
pip install --upgrade pip setuptools wheel
```

### Step 4: Install Requirements

**Option A: Lightweight (voice + chat only)**
```bash
pip install -r requirements.txt
```

Contents of `requirements.txt`:
```
fastapi==0.104.1
uvicorn[standard]==0.24.0
python-multipart==0.0.6
aiohttp==3.9.1
edge-tts==6.1.9
requests==2.31.0
python-dotenv==1.0.0
huggingface-hub==0.19.0
```

**Option B: Full (RAG + embeddings + local Whisper STT)**
```bash
pip install -r requirements-full.txt
```

Adds:
```
faiss-cpu==1.7.4
sentence-transformers==2.2.2
faster-whisper==0.10.0
torch==2.1.0
```

**Install time:**
- Lightweight: ~30 seconds
- Full: ~2-5 minutes (torch is large)

### Step 5: Set Environment Variables

Copy `.env.example` to `.env` and fill in your tokens:

```bash
cp .env.example .env

# Edit .env with your values:
# - HF_TOKEN=hf_your_token_here
# - OLLAMA_MODEL=llama3.1:8b
# - WHISPER_MODEL_SIZE=base.en
```

### Step 6: Verify Dependencies

Test each major component:

```bash
# FastAPI server
python -c "from fastapi import FastAPI; print('✓ FastAPI OK')"

# HuggingFace API
python -c "from huggingface_hub import InferenceClient; print('✓ HF API OK')"

# Edge TTS
python -c "import edge_tts; print('✓ Edge TTS OK')"

# RAG (if installed)
python -c "import faiss; print('✓ FAISS OK')" 2>/dev/null || echo "⚠ FAISS not installed (optional)"

# Whisper STT (if installed)
python -c "from faster_whisper import WhisperModel; print('✓ Faster-Whisper OK')" 2>/dev/null || echo "⚠ Faster-Whisper not installed (optional)"

# Sentence Transformers (if installed)
python -c "from sentence_transformers import SentenceTransformer; print('✓ Sentence-Transformers OK')" 2>/dev/null || echo "⚠ Sentence-Transformers not installed (optional)"
```

### Step 7: Start Server

```bash
# From project root with venv activated:
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Visit: **http://127.0.0.1:8000**

---

## Troubleshooting

### `ModuleNotFoundError: No module named 'app'`
**Fix:** Make sure you're in the project root directory and venv is activated
```bash
cd /Users/eric/GitHub/live-bot-its
source venv/bin/activate
```

### `ModuleNotFoundError: No module named 'torch'`
**Fix:** Install full requirements (torch is needed for embeddings)
```bash
pip install torch
# or
pip install -r requirements-full.txt
```

### `ImportError: cannot import name 'InferenceClient'`
**Fix:** Upgrade huggingface-hub
```bash
pip install --upgrade huggingface-hub
```

### Slow/Hanging on Import
**Likely cause:** faiss-cpu downloading/compiling for the first time
**Solution:** Wait ~2 minutes, or install minimal requirements and skip RAG:
```bash
pip install -r requirements.txt  # No faiss
# RAG will be disabled but bot still works
```

### On Apple Silicon (M1/M2/M3)
Some packages may need architecture-specific builds:
```bash
# Install torch for Apple Silicon
pip install torch --index-url https://download.pytorch.org/whl/cpu

# Or let pip handle it automatically
pip install torch  # Should auto-detect M1/M2/M3
```

### Virtual Environment Won't Activate
```bash
# Try explicit path
source /Users/eric/GitHub/live-bot-its/venv/bin/activate

# Or use absolute path in bash_profile/zshrc:
alias bot-env="source /Users/eric/GitHub/live-bot-its/venv/bin/activate"
```

---

## Development Setup

If you plan to modify code, also install development tools:

```bash
pip install -r requirements.txt  # Core
pip install -r requirements-full.txt  # Full
pip install pytest black pylint  # Dev tools
```

### Run tests:
```bash
python -m unittest tests.test_remote_stt -v
```

### Format code:
```bash
black app/
```

### Lint code:
```bash
pylint app/
```

---

## Environment Variables Reference

Key `.env` variables:

```bash
# Required for HuggingFace API
HF_TOKEN=hf_your_token_here

# LLM Configuration
OLLAMA_MODEL=llama3.1:8b          # Local model
OLLAMA_LLM_NUM_PREDICT=120         # Max tokens
OLLAMA_TEMPERATURE=0.15            # 0=deterministic, 1=random

# Speech Recognition
WHISPER_MODEL_SIZE=base.en         # tiny/base/small/medium/large
WHISPER_DEVICE=cpu                 # cpu or cuda

# Speech Synthesis
TTS_VOICE=en-US-GuyNeural          # Microsoft voice
TTS_RATE=+15%                      # Speaking speed

# RAG
RAG_TOP_K=5                        # Chunks to retrieve
RAG_MIN_SCORE=0.35                 # Relevance threshold

# Server
HOST=0.0.0.0
PORT=8000
```

---

## Deactivating Virtual Environment

```bash
deactivate
```

Your prompt should return to normal (no longer showing `(venv)`).

---

## Next Steps

1. **Activate environment:** `source venv/bin/activate`
2. **Start server:** `python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload`
3. **Open browser:** http://127.0.0.1:8000
4. **Ask a question!**

---

## Optional: Using in IDE

### VS Code
Create `.vscode/settings.json`:
```json
{
  "python.defaultInterpreterPath": "${workspaceFolder}/venv/bin/python",
  "python.linting.enabled": true,
  "python.linting.pylintEnabled": true
}
```

### PyCharm
1. Open project
2. Project Settings → Python Interpreter
3. Add Interpreter → Existing Environment
4. Select `/Users/eric/GitHub/live-bot-its/venv/bin/python`

---

## Common Commands

```bash
# Activate
source venv/bin/activate

# Install package
pip install package_name

# List installed
pip list

# Freeze requirements
pip freeze > requirements.txt

# Deactivate
deactivate

# Remove venv
rm -rf venv
```

---

## Performance Notes

**Lightweight mode** (requirements.txt):
- Fast startup (~2s)
- Relies on HuggingFace API & local Ollama
- No local models/embeddings
- ~80MB disk space

**Full mode** (requirements-full.txt):
- Slower startup (~10s, torch loads)
- Can run everything locally
- Embeddings + Whisper + models cached
- ~2GB disk space (models)

**Recommended:** Use **lightweight** by default, install full if you want complete offline capability.
