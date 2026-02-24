# ITS Voice Bot

Voice-first RAG chatbot for Loyola ITS support.

## Setup

```bash
# 1. Create virtual environment
python3 -m venv .venv311
source .venv311/bin/activate

# 2. Install dependencies
#
# The repo maintains two sets of requirements:
#   * requirements.txt      – minimal set used for lightweight/demo
#    deployments (Heroku slug friendly).
#   * requirements-full.txt – full set including ML/RAG/LLM libs for
#    local development or if running everything on the same host.
#
# To install the full set, run `pip install -r requirements-full.txt`.
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

---

## Deployment 📦

The app is container‑friendly. two primary paths to the internet:

1. **Heroku (containers)**
   ```bash
   # login and create app
   heroku login
   heroku create my-its-voice-bot

   # set any env vars you need, e.g.:
   heroku config:set HF_CHAT_MODEL="gpt2" HF_TOKEN="$(cat ~/.hf_token)"
   heroku config:set OLLAMA_BASE_URL="http://somehost:11434" \
        OLLAMA_MODEL="llama3.1:8b"

   # push container
   heroku container:push web --app my-its-voice-bot
   heroku container:release web --app my-its-voice-bot

   # view logs
   heroku logs --tail --app my-its-voice-bot
   ```
   The `heroku.yml` in the repo makes this a straight Docker build; the
   included `Dockerfile` installs dependencies and runs `uvicorn` on
   `$PORT`.

2. **Any other host** – you can use the same Dockerfile or run `uvicorn`
   directly on a VM.  Make sure to copy the `models/vosk*` directory and
   `data/faiss/faiss.index` (or re-run `scripts/ingest_docs.py`).  Set
   environment variables for `HF_CHAT_MODEL`/`HF_TOKEN` (to call public
   HuggingFace inference) or `OLLAMA_BASE_URL`/`OLLAMA_MODEL` if using a
   local Ollama server.

### HuggingFace inference

To avoid running a local LLM you can configure the voice bot to hit the
HuggingFace Hosted Inference API by setting `HF_CHAT_MODEL` (e.g.
`"tiiuae/falcon-7b-instruct"`) and `HF_TOKEN`.
The controller concatenates conversation history into a single prompt and
sends it to `https://api-inference.huggingface.co/models/<model>`.
Streaming responses are emulated by returning the complete answer as one
chunk.

Leave `HF_CHAT_MODEL` empty to fall back to the Ollama URL defined above.
