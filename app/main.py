from __future__ import annotations

import base64
import json
import uuid
import re

from fastapi import FastAPI, WebSocket
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from app.conversation.controller import handle_user_text, handle_user_text_stream
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

    # Regex for sentence splitting (simple version)
    sentence_end_re = re.compile(r'(?<=[.!?])\s+')

    audio_enabled = True

    async def process_response_stream(text_input: str):
        nonlocal speaking, audio_enabled
        speaking = True
        
        full_response = ""
        buffer = ""
        sources = []
        
        # Determine intent & sources first
        # We use an async generator now, so we iterate with async for
        stream = handle_user_text_stream(state, text_input, retriever)
        
        try:
            async for chunk in stream:
                if chunk["type"] == "meta":
                    sources = chunk.get("sources", [])
                    # Send sources immediately
                    await websocket.send_json({
                        "type": "meta",
                        "sources": sources,
                    })
                    
                    if "response" in chunk:
                        # Static response
                        full_response = chunk["response"]
                        # Send token for UI
                        await websocket.send_json({
                            "type": "token",
                            "content": full_response
                        })
                        
                        if audio_enabled:
                            wav_bytes, sample_rate = tts.synthesize_wav(full_response)
                            audio_b64 = base64.b64encode(wav_bytes).decode("utf-8")
                            await websocket.send_json({
                                "type": "tts",
                                "audio": audio_b64,
                                "sample_rate": sample_rate,
                            })
                        
                        # Also send final text for log sync
                        await websocket.send_json({
                            "type": "final",
                            "response": full_response
                        })
                        return

                elif chunk["type"] == "token":
                    token = chunk["content"]
                    full_response += token
                    buffer += token
                    
                    # Send token to UI immediately for streaming text
                    await websocket.send_json({
                        "type": "token",
                        "content": token
                    })
                    
                    # Split sentences if audio is enabled
                    if audio_enabled:
                        splits = sentence_end_re.split(buffer)
                        if len(splits) > 1:
                            # We have at least one complete sentence
                            to_speak = splits[0]
                            buffer = splits[1] # Keep the rest (could be '' or partial sentence)
                            
                            if to_speak.strip():
                                wav_bytes, sample_rate = tts.synthesize_wav(to_speak)
                                audio_b64 = base64.b64encode(wav_bytes).decode("utf-8")
                                await websocket.send_json({
                                    "type": "tts",
                                    "audio": audio_b64,
                                    "sample_rate": sample_rate,
                                })
            
            # Flush remaining buffer
            if audio_enabled and buffer.strip():
                wav_bytes, sample_rate = tts.synthesize_wav(buffer)
                audio_b64 = base64.b64encode(wav_bytes).decode("utf-8")
                await websocket.send_json({
                    "type": "tts",
                    "audio": audio_b64,
                    "sample_rate": sample_rate,
                })
                
            # Update UI with full text
            await websocket.send_json({
                "type": "final",
                "response": full_response,
                "sources": sources
            })
            
        except Exception as e:
            await websocket.send_json({"type": "error", "message": str(e)})
        finally:
            speaking = False

    while True:
        msg = await websocket.receive_text()
        payload = json.loads(msg)
        msg_type = payload.get("type")

        if msg_type == "config":
             if "audio_enabled" in payload:
                 audio_enabled = payload["audio_enabled"]
                 # If turned off while speaking, stop speaking?
                 # Logic handled in frontend mostly, but good for next turn

        elif msg_type == "text":
            text = payload.get("text", "").strip()
            if text:
                 # Don't echo back text input (frontend already displayed it optimistically)
                 # Just process the response
                 await process_response_stream(text)

        elif msg_type == "audio":
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
                await process_response_stream(text)

