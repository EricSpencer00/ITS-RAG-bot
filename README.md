# ITS Voice Bot

Voice-first RAG chatbot for Loyola ITS support.

## Setup

```bash
# 1. Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Download Vosk model
mkdir -p models
cd models
wget https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip
unzip vosk-model-small-en-us-0.15.zip
cd ..

# 4. Start Ollama (in separate terminal)
ollama serve
ollama pull llama3.2

# 5. Ingest documents (first time only)
python scripts/ingest_docs.py

# 6. Run server
python scripts/run_dev.py
```

## Usage

Open http://127.0.0.1:8000 in your browser.

- **Voice**: Click mic button, speak, click again to stop
- **Text**: Type in the input box and press Enter
- **Voice Output**: Toggle the speaker icon to enable/disable TTS
