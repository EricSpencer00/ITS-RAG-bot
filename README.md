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

### HuggingFace inference and remote STT

The demo can talk to free HuggingFace endpoints rather than running models
locally.  Set the following config vars on Heroku (or in your `.env`):

```bash
heroku config:set HF_CHAT_MODEL="tiiuae/zephyr-7b-instruct" \
                  HF_TOKEN="<your-hf-token>"
# note: many of the earlier free endpoints (falcon‑7b‑instruct, mistralai/7B,
# even the 7B‑Instruct-v0.2 release) now return HTTP 410.  `tiiuae/zephyr-7b-
# instruct` is a working fall‑back that is free to use; feel free to swap in
# another model of your choice.
# optional custom HF URL, e.g. for a self‑hosted API
# by default the code uses the new `router.huggingface.co` service
# heroku config:set HF_API_URL="https://my-hf-host/models"
```

With these variables present the bot uses `_hf_chat()` in
`app/conversation/controller.py` to send prompts and receive completions.
If `HF_CHAT_MODEL` is unset the code falls back to your local Ollama server.

#### Remote STT

You can also perform speech‑to‑text via an external service instead of
`faster-whisper`.  Use the `STT_API` var to choose the provider:

* `STT_API=hf` – call HuggingFace’s speech‑to‑text endpoint.  The
  specific model can be overridden with `HF_STT_MODEL` (default
  `openai/whisper-1`).  However, **as of early 2026 there are no free HF
  providers hosting any ASR models via the router**, so every attempt
  will fail with a 404/StopIteration error unless you host your own
  inference service or get special access to a gated model.  The code
  uses the official `huggingface_hub.InferenceClient` SDK; when remote
  STT fails it now surfaces a friendly message and suggests using a
  local model or switching to `STT_API=openai`.
  
  Suggested “safe picks” such as `openai/whisper-small`,
  `openai/whisper-base` or `openai/whisper-tiny` are **all in the same
  boat** – we tried them and the router immediately raised
  `StopIteration` (meaning no provider responded).  There’s nothing you
  can do in the client to make those start working until a vendor turns
  them on.
* `STT_API=openai` – call OpenAI’s Whisper API (`OPENAI_API_KEY` must be set).

No additional Python packages are required; the `RemoteSTT` helper lives in
`app/voice/remote_stt.py` and is selected automatically when `STT_API` is
nonempty.

Leave `STT_API` unset to attempt loading the local Whisper model (which will
fail gracefully on a minimal slug).

This configuration lets you deploy a fully functional demo on Heroku using
only free-tier cloud APIs.  The dyno remains small (< 60 MB) because none of
`torch`/`faiss`/`faster-whisper` is installed.
