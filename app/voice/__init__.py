"""
Voice module — Cascaded STT/TTS pipeline

STT: faster-whisper (CTranslate2)
TTS: Edge TTS (Microsoft neural voices)
"""
from app.voice.stt_whisper import WhisperSTT
from app.voice.tts_edge import EdgeTTS

__all__ = [
    "WhisperSTT",
    "EdgeTTS",
]