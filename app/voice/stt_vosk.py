from __future__ import annotations

import json
from typing import Dict

from vosk import Model, KaldiRecognizer

from app.config import VOSK_MODEL_PATH, STT_SAMPLE_RATE


class VoskSTT:
    def __init__(self) -> None:
        self.model = Model(VOSK_MODEL_PATH)
        self.recognizer = KaldiRecognizer(self.model, STT_SAMPLE_RATE)
        self.recognizer.SetWords(True)

    def accept_audio(self, pcm_bytes: bytes) -> Dict[str, str | bool]:
        if self.recognizer.AcceptWaveform(pcm_bytes):
            result = json.loads(self.recognizer.Result())
            return {"final": True, "text": result.get("text", "")}
        partial = json.loads(self.recognizer.PartialResult())
        return {"final": False, "text": partial.get("partial", "")}

    def reset(self) -> None:
        self.recognizer.Reset()
