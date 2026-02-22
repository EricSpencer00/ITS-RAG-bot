"""
ITS Voice RAG Bot — Main Application

Cascaded voice pipeline:
    Browser Mic → WebSocket → Whisper STT → Ollama LLM (+ RAG) → Edge TTS → WebSocket → Browser Speaker
"""
from __future__ import annotations

import base64
import json
import uuid
import re

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from app.conversation.controller import handle_user_text_stream
from app.conversation.state import ConversationState
from app.rag.retriever import Retriever
from app.voice.stt_whisper import WhisperSTT
from app.voice.tts_edge import EdgeTTS

app = FastAPI(title="ITS Voice RAG Bot")

app.mount("/static", StaticFiles(directory="app/web/static"), name="static")


# ── Shared singleton STT model (heavy, load once) ──────────────────────
_stt: WhisperSTT | None = None


def get_stt() -> WhisperSTT:
    global _stt
    if _stt is None:
        _stt = WhisperSTT()
    return _stt


@app.on_event("startup")
async def startup() -> None:
    """Pre-load the Whisper model at startup so first request isn't slow."""
    get_stt()
    print("[Server] ITS Voice RAG Bot ready at http://127.0.0.1:8000")


@app.get("/")
async def index() -> HTMLResponse:
    with open("app/web/static/index.html", "r", encoding="utf-8") as f:
        return HTMLResponse(f.read())


@app.get("/health")
async def health():
    return {"status": "ok", "stt": "whisper", "tts": "edge-tts"}


# ── WebSocket voice pipeline ───────────────────────────────────────────

sentence_end_re = re.compile(r'(?<=[.!?])\s+')


@app.websocket("/ws/audio")
async def ws_audio(websocket: WebSocket) -> None:
    await websocket.accept()

    session_id = str(uuid.uuid4())
    state = ConversationState(session_id=session_id)
    retriever = Retriever()

    # Each connection gets its own STT buffer but shares the heavy model
    stt_model = get_stt()
    stt = WhisperSTT.__new__(WhisperSTT)
    stt.model = stt_model.model
    stt._buffer = bytearray()
    stt._sample_rate = 16000
    stt._min_duration = 0.8
    stt._max_duration = 15.0
    stt._silence_threshold = 300
    stt._silence_chunks_needed = 8
    stt._silent_chunks = 0
    stt._has_speech = False

    tts = EdgeTTS()

    speaking = False
    audio_enabled = True

    await websocket.send_json({"type": "status", "message": "connected"})

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
                            wav_bytes, sr = await tts.synthesize_speech(full_response)
                            if wav_bytes:
                                audio_b64 = base64.b64encode(wav_bytes).decode("utf-8")
                                await websocket.send_json({
                                    "type": "tts",
                                    "audio": audio_b64,
                                    "sample_rate": sr,
                                    "format": "wav",
                                })

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

                    # Stream TTS sentence by sentence for low latency
                    if audio_enabled:
                        splits = sentence_end_re.split(buffer)
                        if len(splits) > 1:
                            to_speak = splits[0]
                            buffer = splits[-1]

                            if to_speak.strip():
                                wav_bytes, sr = await tts.synthesize_speech(to_speak)
                                if wav_bytes:
                                    audio_b64 = base64.b64encode(wav_bytes).decode("utf-8")
                                    await websocket.send_json({
                                        "type": "tts",
                                        "audio": audio_b64,
                                        "sample_rate": sr,
                                        "format": "wav",
                                    })

            # Flush remaining text
            if audio_enabled and buffer.strip():
                wav_bytes, sr = await tts.synthesize_speech(buffer)
                if wav_bytes:
                    audio_b64 = base64.b64encode(wav_bytes).decode("utf-8")
                    await websocket.send_json({
                        "type": "tts",
                        "audio": audio_b64,
                        "sample_rate": sr,
                        "format": "wav",
                    })

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

