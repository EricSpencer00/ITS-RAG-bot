#!/bin/bash
# ITS Voice RAG Bot - Setup Verification Checklist
# Run this to verify all components are working

set -e

echo "========================================"
echo "ITS VOICE RAG BOT - SETUP VERIFICATION"
echo "========================================"
echo

PROJECT_ROOT="/Users/eric/GitHub/live-bot-its"
cd "$PROJECT_ROOT"

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

check() {
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✓${NC} $1"
    else
        echo -e "${RED}✗${NC} $1"
        return 1
    fi
}

echo "1. Checking directory structure..."
[ -d "app" ] && check "app/ directory exists" || echo -e "${RED}✗${NC} app/ missing"
[ -d "data/faiss" ] && check "FAISS index exists" || echo -e "${RED}✗${NC} FAISS index missing"
[ -d "models/vosk-model-small-en-us-0.15" ] && check "Vosk model exists" || echo -e "${RED}✗${NC} Vosk model missing"
[ -f ".env" ] && check ".env configuration exists" || echo -e "${RED}✗${NC} .env missing"
echo

echo "2. Checking Python dependencies..."
python3 -c "import faiss" && check "FAISS installed" || echo -e "${RED}✗${NC} FAISS not installed"
python3 -c "import vosk" && check "Vosk installed" || echo -e "${RED}✗${NC} Vosk not installed"
python3 -c "import pyttsx3" && check "pyttsx3 installed" || echo -e "${RED}✗${NC} pyttsx3 not installed"
python3 -c "import sentence_transformers" && check "sentence-transformers installed" || echo -e "${RED}✗${NC} sentence-transformers not installed"
python3 -c "import fastapi" && check "FastAPI installed" || echo -e "${RED}✗${NC} FastAPI not installed"
echo

echo "3. Checking Ollama..."
curl -s http://localhost:11434/api/tags > /dev/null && check "Ollama is running" || echo -e "${YELLOW}!${NC} Ollama not responding (start with: ollama serve)"
echo

echo "4. Checking FAISS index..."
python3 << 'PYTHON'
import sys
sys.path.insert(0, '.')
try:
    from app.rag.retriever import Retriever
    r = Retriever()
    print(f"\033[0;32m✓\033[0m FAISS index loaded ({r.index.ntotal} vectors)")
except Exception as e:
    print(f"\033[0;31m✗\033[0m FAISS error: {e}")
PYTHON
echo

echo "5. Checking voice components..."
python3 << 'PYTHON'
import sys
sys.path.insert(0, '.')
try:
    from app.voice.stt_vosk import VoskSTT
    stt = VoskSTT()
    print(f"\033[0;32m✓\033[0m Vosk STT ready")
except Exception as e:
    print(f"\033[0;31m✗\033[0m Vosk error: {e}")

try:
    from app.voice.tts_piper import PiperTTS
    tts = PiperTTS()
    print(f"\033[0;32m✓\033[0m pyttsx3 TTS ready")
except Exception as e:
    print(f"\033[0;31m✗\033[0m TTS error: {e}")
PYTHON
echo

echo "6. Checking web server..."
if [ -f "app/web/server.py" ]; then
    echo -e "${GREEN}✓${NC} Server module exists"
else
    echo -e "${RED}✗${NC} Server module missing"
fi

if [ -f "app/web/static/index.html" ]; then
    echo -e "${GREEN}✓${NC} Web UI exists"
else
    echo -e "${RED}✗${NC} Web UI missing"
fi
echo

echo "========================================"
echo "SETUP VERIFICATION COMPLETE"
echo "========================================"
echo
echo "To start the voice bot server:"
echo "  cd $PROJECT_ROOT"
echo "  source .venv/bin/activate"
echo "  python -m uvicorn app.web.server:app --host 127.0.0.1 --port 8000"
echo
echo "Then open: http://127.0.0.1:8000"
echo
