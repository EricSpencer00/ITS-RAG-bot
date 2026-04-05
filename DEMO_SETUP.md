# Live Demo Setup — HuggingFace Model Selection

This guide gets you a **live demo in the browser in 5 minutes** using HuggingFace Inference API.

## Quick Start

### 1. Get a HuggingFace Token
- Go to https://huggingface.co/settings/tokens
- Create a **User Access Token** (read-only is fine)
- Copy it

### 2. Set Environment Variable
```bash
export HF_TOKEN="hf_xxxxxxxxxxxxx"  # Paste your token
```

### 3. Run the Server
```bash
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

### 4. Open in Browser
- Visit **http://127.0.0.1:8000**
- You should see the Loyola ITS Assistant UI

### 5. Test It Out
- Type "How do I reset my password?" in the text box
- Or click "Start Talk" to use voice input
- Use the **Model dropdown** in the top-left to switch between models

---

## Available Models

| Model | Size | Speed | Best For |
|-------|------|-------|----------|
| **Qwen 0.5B** ⚡ | 500M | Ultra-fast | Testing, simple Q&A |
| **Qwen 1.5B** ⚡ | 1.5B | Fast | Good balance |
| **Qwen 7B** 🔥 | 7B | Medium | Best quality answers |
| **Mistral 7B** 🔥 | 7B | Medium | Best for instructions |
| **Zephyr 7B** 🔥 | 7B | Medium | Great for chat (default) |
| **Falcon 7B** 🔥 | 7B | Medium | Instruction-tuned |

### Model Selection
- Click the dropdown in the header to switch models
- All models use the HuggingFace Inference API (free tier available)
- Switches are instant — no server restart needed

---

## What Changed

### ✅ Prompt Engineering
- System prompt rewritten to use **Akinator-style diagnostic flow**
- Bot asks clarifying questions instead of listing solutions
- High-confidence gating based on RAG retrieval scores
- Max 3 clarifications before giving best-effort answer

### ✅ Diagnostic Mode
- `controller.py` now has `_assess_confidence()` function
- Confidence thresholds: `HIGH_CONFIDENCE_SCORE=0.55`, `LOW_CONFIDENCE_SCORE=0.40`
- Context preservation improved for short replies (≤8 words)
- Tracks clarification count in `ConversationState`

### ✅ Model Selection
- `model_manager.py` — centralized model management
- `/api/models` endpoint — list available models
- `/api/models/select` endpoint — switch models at runtime
- Frontend dropdown in header for easy switching
- No reload needed

### ✅ Frontend
- Added model selector dropdown to header
- Clean styling with Loyola branding
- Real-time feedback on model switches

---

## Troubleshooting

### "404 not found" errors
- Verify `HF_TOKEN` is set: `echo $HF_TOKEN`
- Some free-tier models may be rate-limited
- Try a different model from the dropdown

### Slow responses
- **Qwen 0.5B** is fastest (500M parameters)
- **Zephyr 7B** is a good balance
- Wait 10-30 seconds for first inference (API startup)

### Voice not working
- Check browser permissions for microphone
- Toggle "Voice" switch off/on
- Make sure audio output is not muted

### RAG not working
- Make sure `data/faiss/faiss.index` exists
- If missing, run: `python app/rag/ingest.py`

---

## Next Steps: PersonaPlex (Optional)

For **full-duplex speech-to-speech** (listen while speaking):

```bash
# This requires GPU and 10+ min initialization
export PERSONAPLEX_DEVICE=cuda
python scripts/personaplex_demo.py
```

PersonaPlex will initialize in the background and become available after ~10 minutes.

---

## Architecture Overview

```
Browser (WebSocket)
    ↓
FastAPI Server
    ├─ Model Manager (tracks current LLM)
    ├─ Conversation Controller (RAG + diagnostic flow)
    ├─ Retriever (FAISS vector search)
    ├─ STT (Whisper or HF API)
    └─ TTS (Edge TTS)
    ↓
HuggingFace Inference API (selected model)
    ↓
Browser (audio + text response)
```

---

## Testing the Diagnostic Flow

Try these prompts to see the bot ask clarifying questions:

1. **Vague prompt:**
   > "VPN not working"
   
   → Bot might ask: "Are you on campus Wi-Fi or off-campus?"

2. **Ambiguous issue:**
   > "My email is broken"
   
   → Bot asks: "Are you using Outlook on your computer, or webmail in a browser?"

3. **Partial info:**
   > "Can't access OneDrive"
   
   → Bot: "Are you on a Mac or Windows?"

The bot will ask up to 3 questions before committing to an answer, ensuring high confidence in suggestions.
