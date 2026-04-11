"""
ITS Voice RAG Bot — Main Application

Cascaded voice pipeline:
    Browser Mic → WebSocket → Whisper STT → Ollama LLM (+ RAG) → Edge TTS → WebSocket → Browser Speaker
"""
from __future__ import annotations

import asyncio
import base64
import json
import re
import uuid

from typing import Dict, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from app.config import (
    STT_SILENCE_CHUNKS,
    TTS_CHUNK_MIN_CHARS,
    STT_API,
    PERSONAPLEX_ENABLED,
    DEFAULT_VOICE_PROMPT,
    DEFAULT_TEXT_PROMPT,
)
from app.conversation.controller import handle_user_text_stream, handle_user_text
from app.conversation.state import ConversationState
from app.rag.retriever import Retriever
from app.rag.prompt import SYSTEM_PROMPT

# STT classes; remote_stt imported lazily if required
from app.voice.stt_whisper import WhisperSTT
from app.voice.tts_edge import EdgeTTS

app = FastAPI(title="ITS Voice RAG Bot")

app.mount("/static", StaticFiles(directory="app/web/static"), name="static")


# ── Singletons (load once at startup, shared across all sessions) ──────
_stt: WhisperSTT | None = None
# if faster-whisper isn't installed (minimal slug), get_stt will return None
_retriever: Retriever | None = None


def get_stt():
    global _stt
    if _stt is None:
        # choose remote provider if configured
        if STT_API:
            from app.voice.remote_stt import RemoteSTT
            print(f"[Server] using remote STT provider={STT_API}")
            _stt = RemoteSTT()
        else:
            try:
                _stt = WhisperSTT()
            except Exception as exc:  # WhisperSTT raises RuntimeError if unavailable
                print(f"[Server] local STT disabled: {exc}")
                _stt = None
    return _stt


def get_retriever() -> Retriever | None:
    global _retriever
    if _retriever is None:
        try:
            print("[Server] Loading RAG retriever + embeddings...")
            _retriever = Retriever()
            print("[Server] RAG retriever ready.")
        except Exception as exc:  # may be RuntimeError from missing libs
            print(f"[Server] RAG disabled: {exc}")
            _retriever = None
    return _retriever


@app.on_event("startup")
async def startup() -> None:
    """Pre-load heavy models at startup so first request has no latency."""
    # STT may be disabled in core demo; it's okay if get_stt() returns None.
    _ = get_stt()
    # RAG may be disabled too; we call get_retriever() to trigger its initialization
    # but treat a None value as acceptable.
    _ = get_retriever()
    print("[Server] ITS Voice RAG Bot ready at http://127.0.0.1:8000")


@app.get("/")
async def index() -> HTMLResponse:
    with open("app/web/static/index.html", "r", encoding="utf-8") as f:
        return HTMLResponse(f.read())


@app.get("/health")
async def health():
    from app.model_manager import get_model_manager
    model_manager = get_model_manager()
    return {
        "status": "ok",
        "stt": "whisper",
        "tts": "edge-tts",
        "llm_model": model_manager.get_current_model(),
        "personaplex_available": model_manager.is_personaplex_available(),
    }


@app.get("/api/models")
async def get_models():
    """List available models and current selection."""
    from app.model_manager import get_model_manager
    model_manager = get_model_manager()
    return {
        "current": model_manager.get_current_model(),
        "available": model_manager.list_available_models(),
        "personaplex_available": model_manager.is_personaplex_available(),
        "initialization_in_progress": model_manager.is_initialization_in_progress(),
    }


@app.get("/api/voice/engines")
async def list_voice_engines():
    """List voice pipeline options available to the UI."""
    engines = [
        {
            "id": "cascaded",
            "label": "Cascaded (Whisper + LLM + Edge TTS)",
            "description": "Browser mic → STT → LLM → TTS. Works anywhere.",
            "ws": "/ws/audio",
            "available": True,
        },
    ]
    if PERSONAPLEX_ENABLED:
        engines.append({
            "id": "personaplex",
            "label": "PersonaPlex (local, full-duplex)",
            "description": "Speech-to-speech 7B model. Requires GPU for real-time; first load downloads ~15GB.",
            "ws": "/ws/personaplex",
            "available": True,
        })
    return {"engines": engines, "default": "cascaded"}


@app.post("/api/models/select")
async def select_model(body: dict):
    """Switch to a different model."""
    from app.model_manager import get_model_manager
    model_manager = get_model_manager()
    model_key = body.get("model", "zephyr-7b")
    success = model_manager.set_current_model(model_key)
    if success:
        return {
            "status": "ok",
            "current": model_manager.get_current_model(),
            "info": model_manager.get_model_info(model_key),
        }
    return {"status": "error", "message": "Failed to select model"}


# ── Helpers ────────────────────────────────────────────────────────────

_url_re = re.compile(r'https?://\S+')


def _strip_urls(text: str) -> str:
    """Remove raw URLs before TTS — they can't be spoken sensibly."""
    return _url_re.sub('', text).strip()


def _should_flush_tts(buffer: str) -> tuple[str, str] | None:
    """Return (to_speak, remainder) if buffer has a good TTS break point,
    or None if we should keep accumulating.

    Strategy:
    - Wait until buffer has TTS_CHUNK_MIN_CHARS characters
    - Then split on the nearest sentence end (.!?) first
    - Fall back to comma-break
    - Force-flush at 3x TTS_CHUNK_MIN_CHARS regardless
    """
    if len(buffer) < TTS_CHUNK_MIN_CHARS:
        return None

    # Try sentence end break
    m = re.search(r'(?<=[.!?])\s+', buffer)
    if m:
        return buffer[:m.start() + 1], buffer[m.end():]

    # Try comma break after enough chars
    if len(buffer) >= TTS_CHUNK_MIN_CHARS * 1.5:
        m = re.search(r'(?<=,)\s+', buffer)
        if m:
            return buffer[:m.start() + 1], buffer[m.end():]

    # Force flush if buffer is getting too long
    if len(buffer) >= TTS_CHUNK_MIN_CHARS * 3:
        return buffer, ""

    return None


# ── WebSocket voice pipeline ───────────────────────────────────────────


@app.post("/api/text")
async def http_chat(body: dict) -> Dict[str, object]:
    """Simple HTTP endpoint for text-only clients or when WS fails."""
    text = body.get("text", "")
    state = ConversationState(session_id=str(uuid.uuid4()))
    retriever = get_retriever()
    return handle_user_text(state, text, retriever)


@app.websocket("/ws/audio")
async def ws_audio(websocket: WebSocket) -> None:
    await websocket.accept()

    session_id = str(uuid.uuid4())
    state = ConversationState(session_id=session_id)
    retriever = get_retriever()  # singleton — no load delay

    # Initialize STT handler.  We prefer a remote provider (STT_API) if
    # configured; otherwise we attempt to reuse the singleton Whisper model.
    stt = None
    if STT_API:
        from app.voice.remote_stt import RemoteSTT
        stt = RemoteSTT()
    else:
        stt_model = get_stt()
        if stt_model is not None:
            stt = WhisperSTT.__new__(WhisperSTT)
            stt.model = stt_model.model
            stt._buffer = bytearray()
            stt._sample_rate = 16000
            stt._min_duration = 0.5
            stt._max_duration = 12.0
            stt._silence_threshold = 250
            stt._silence_chunks_needed = STT_SILENCE_CHUNKS
            stt._silent_chunks = 0
            stt._has_speech = False
    # if stt is still None, we'll refuse audio messages later

    tts = EdgeTTS()

    speaking = False
    audio_enabled = True

    await websocket.send_json({"type": "status", "message": "connected"})

    async def send_tts(text: str) -> None:
        """Synthesize text and send audio chunk — strips URLs first."""
        clean = _strip_urls(text)
        if not clean:
            return
        wav_bytes, sr = await tts.synthesize_speech(clean)
        if wav_bytes:
            audio_b64 = base64.b64encode(wav_bytes).decode("utf-8")
            await websocket.send_json({
                "type": "tts",
                "audio": audio_b64,
                "sample_rate": sr,
                "format": "wav",
            })

    async def process_response_stream(text_input: str) -> None:
        nonlocal speaking, audio_enabled
        speaking = True

        full_response = ""
        buffer = ""
        sources = []

        stream = handle_user_text_stream(state, text_input, retriever)

        try:
            async for chunk in stream:
                if chunk["type"] == "meta":
                    sources = chunk.get("sources", [])
                    await websocket.send_json({
                        "type": "meta",
                        "sources": sources,
                    })


                    if "response" in chunk:
                        full_response = chunk["response"]
                        await websocket.send_json({
                            "type": "token",
                            "content": full_response,
                        })
                        if audio_enabled:
                            await send_tts(full_response)
                        await websocket.send_json({
                            "type": "final",
                            "response": full_response,
                        })
                        return

                elif chunk["type"] == "token":
                    token = chunk["content"]
                    full_response += token
                    buffer += token

                    await websocket.send_json({
                        "type": "token",
                        "content": token,
                    })

                    # Stream TTS chunk-by-chunk for low latency
                    if audio_enabled:
                        result = _should_flush_tts(buffer)
                        if result is not None:
                            to_speak, buffer = result
                            if to_speak.strip():
                                await send_tts(to_speak)

            # Flush remaining buffer
            if audio_enabled and buffer.strip():
                await send_tts(buffer)

            await websocket.send_json({
                "type": "final",
                "response": full_response,
                "sources": sources,
            })

        except Exception as e:
            await websocket.send_json({"type": "error", "message": str(e)})
        finally:
            speaking = False

    try:
        while True:
            msg = await websocket.receive_text()
            payload = json.loads(msg)
            msg_type = payload.get("type")

            if msg_type == "config":
                if "audio_enabled" in payload:
                    audio_enabled = payload["audio_enabled"]

            elif msg_type == "text":
                text = payload.get("text", "").strip()
                if text:
                    await process_response_stream(text)

            elif msg_type == "audio":
                # Legacy: server-side STT for clients that still send PCM chunks.
                # The web UI now uses the browser's Web Speech API instead.
                if stt is None:
                    continue
                b64_audio = payload.get("data", "")
                if not b64_audio:
                    continue
                pcm_bytes = base64.b64decode(b64_audio)
                result = stt.accept_audio(pcm_bytes)

                partial = result.get("partial", "")
                text = result.get("text", "").strip()

                if partial:
                    await websocket.send_json({"type": "partial", "text": partial})

                if result["final"] and text:
                    await websocket.send_json({"type": "final_text", "text": text})
                    stt.reset()
                    await process_response_stream(text)

    except WebSocketDisconnect:
        print(f"[WS] Session {session_id[:8]} disconnected")
    except Exception as e:
        print(f"[WS] Session {session_id[:8]} error: {e}")


# ── PersonaPlex full-duplex voice endpoint ─────────────────────────────


@app.websocket("/ws/personaplex")
async def ws_personaplex(websocket: WebSocket) -> None:
    """Full-duplex speech-to-speech via NVIDIA PersonaPlex.

    Protocol (JSON-over-WebSocket):
      Client → server:
        {"type": "audio", "data": "<base64 opus chunk>"}
        {"type": "stop"}
      Server → client:
        {"type": "status", "message": "loading" | "ready"}
        {"type": "audio", "data": "<base64 wav>", "format": "wav"}
        {"type": "token", "content": "<text>"}
        {"type": "error", "message": "..."}
    """
    await websocket.accept()
    session_id = str(uuid.uuid4())

    if not PERSONAPLEX_ENABLED:
        await websocket.send_json({"type": "error", "message": "PersonaPlex is disabled on this server."})
        await websocket.close()
        return

    # Lazy import — keeps startup cheap and surfaces missing deps cleanly
    try:
        from app.voice.personaplex import get_engine, PersonaPlexSession
    except Exception as e:
        await websocket.send_json({
            "type": "error",
            "message": f"PersonaPlex module unavailable: {e}. Check sphn / moshi / huggingface-hub versions.",
        })
        await websocket.close()
        return

    await websocket.send_json({"type": "status", "message": "loading"})

    try:
        engine = await get_engine()
    except Exception as e:
        await websocket.send_json({"type": "error", "message": f"PersonaPlex init failed: {e}"})
        await websocket.close()
        return

    await websocket.send_json({"type": "status", "message": "ready"})

    session = PersonaPlexSession(
        session_id=session_id,
        voice_prompt=DEFAULT_VOICE_PROMPT,
        text_prompt=SYSTEM_PROMPT or DEFAULT_TEXT_PROMPT,
    )

    incoming: asyncio.Queue = asyncio.Queue()
    alive = True

    async def is_alive() -> bool:
        return alive

    async def receive_audio() -> Optional[bytes]:
        try:
            return await asyncio.wait_for(incoming.get(), timeout=0.1)
        except asyncio.TimeoutError:
            return None

    async def send_audio(wav_bytes: bytes) -> None:
        await websocket.send_json({
            "type": "audio",
            "data": base64.b64encode(wav_bytes).decode("ascii"),
            "format": "wav",
        })

    async def send_text(text: str) -> None:
        await websocket.send_json({"type": "token", "content": text})

    async def read_loop() -> None:
        nonlocal alive
        try:
            while alive:
                msg = await websocket.receive_text()
                payload = json.loads(msg)
                mtype = payload.get("type")
                if mtype == "audio":
                    data = payload.get("data", "")
                    if data:
                        await incoming.put(base64.b64decode(data))
                elif mtype == "stop":
                    alive = False
                    break
        except WebSocketDisconnect:
            alive = False
        except Exception as e:
            print(f"[WS/personaplex {session_id[:8]}] read error: {e}")
            alive = False

    read_task = asyncio.create_task(read_loop())
    try:
        await engine.handle_conversation(
            session=session,
            send_audio=send_audio,
            send_text=send_text,
            receive_audio=receive_audio,
            is_alive=is_alive,
        )
    except Exception as e:
        try:
            await websocket.send_json({"type": "error", "message": str(e)})
        except Exception:
            pass
        print(f"[WS/personaplex {session_id[:8]}] error: {e}")
    finally:
        alive = False
        read_task.cancel()
        try:
            await read_task
        except (asyncio.CancelledError, Exception):
            pass
        print(f"[WS/personaplex {session_id[:8]}] closed")

