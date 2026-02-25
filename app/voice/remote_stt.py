from __future__ import annotations
import os
import requests

HF_API_URL = os.getenv("HF_API_URL", "https://api-inference.huggingface.co/models")
HF_TOKEN = os.getenv("HF_TOKEN", "")
OPENAI_KEY = os.getenv("OPENAI_API_KEY", "")

class RemoteSTT:
    def __init__(self):
        # provider string determines which API to call. 'hf' for HuggingFace
        # inference, 'openai' for OpenAI's Whisper endpoint.
        self.provider = os.getenv("STT_API", "hf").lower()

    def transcribe(self, wav_bytes: bytes) -> str:
        if self.provider == "hf":
            headers = {"Authorization": f"Bearer {HF_TOKEN}"} if HF_TOKEN else {}
            files = {"file": ("audio.wav", wav_bytes)}
            resp = requests.post(f"{HF_API_URL}/openai/whisper-1", headers=headers, files=files)
            resp.raise_for_status()
            return resp.json().get("text", "")
        elif self.provider == "openai":
            headers = {"Authorization": f"Bearer {OPENAI_KEY}"}
            files = {"file": ("audio.wav", wav_bytes)}
            resp = requests.post("https://api.openai.com/v1/audio/transcriptions",
                                 headers=headers, files=files,
                                 data={"model": "whisper-1"})
            resp.raise_for_status()
            return resp.json().get("text", "")
        else:
            raise RuntimeError(f"unknown STT provider: {self.provider}")
