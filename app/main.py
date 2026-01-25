from __future__ import annotations

import base64
import json
import uuid

from fastapi import FastAPI, WebSocket
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from app.conversation.controller import handle_user_text
from app.conversation.state import ConversationState
from app.rag.retriever import Retriever
from app.voice.stt_vosk import VoskSTT
from app.voice.tts_piper import PiperTTS

app = FastAPI(title="ITS Voice RAG Bot PoC")

app.mount("/static", StaticFiles(directory="app/web/static"), name="static")


@app.get("/")
async def index() -> HTMLResponse:
    with open("app/web/static/index.html", "r", encoding="utf-8") as f:
        return HTMLResponse(f.read())


@app.websocket("/ws/audio")
async def ws_audio(websocket: WebSocket) -> None:
    await websocket.accept()

    session_id = str(uuid.uuid4())
    state = ConversationState(session_id=session_id)
    retriever = Retriever()
    stt = VoskSTT()
    tts = PiperTTS()

    speaking = False

    await websocket.send_json({"type": "status", "message": "connected"})

    while True:
        msg = await websocket.receive_text()
        payload = json.loads(msg)
        msg_type = payload.get("type")

        if msg_type == "audio":
            b64_audio = payload.get("data", "")
            if not b64_audio:
                continue
            pcm_bytes = base64.b64decode(b64_audio)
            result = stt.accept_audio(pcm_bytes)
            text = result.get("text", "").strip()

            if text:
                await websocket.send_json({"type": "partial" if not result["final"] else "final_text", "text": text})

            if speaking and text:
                await websocket.send_json({"type": "barge_in"})
                speaking = False

            if result["final"] and text:
                response = handle_user_text(state, text, retriever)
                await websocket.send_json({
                    "type": "final",
                    "text": text,
                    "response": response["response"],
                    "sources": response["sources"],
                })

                speaking = True
                wav_bytes, sample_rate = tts.synthesize_wav(response["response"])
                audio_b64 = base64.b64encode(wav_bytes).decode("utf-8")
                await websocket.send_json({
                    "type": "tts",
                    "audio": audio_b64,
                    "sample_rate": sample_rate,
                })
                speaking = False

        if msg_type == "text":
            text = payload.get("text", "").strip()
            if not text:
                continue
            response = handle_user_text(state, text, retriever)
            await websocket.send_json({
                "type": "final",
                "text": text,
                "response": response["response"],
                "sources": response["sources"],
            })
            wav_bytes, sample_rate = tts.synthesize_wav(response["response"])
            audio_b64 = base64.b64encode(wav_bytes).decode("utf-8")
            await websocket.send_json({
                "type": "tts",
                "audio": audio_b64,
                "sample_rate": sample_rate,
            })
