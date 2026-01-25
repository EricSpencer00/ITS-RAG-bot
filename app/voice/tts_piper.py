from __future__ import annotations

import io
from typing import Tuple

import pyttsx3
import wave
import numpy as np

from app.config import PIPER_SPEAKER_ID


class PiperTTS:
    def __init__(self) -> None:
        self.engine = pyttsx3.init()
        self.engine.setProperty('rate', 175)
        self.engine.setProperty('volume', 0.9)

    def synthesize_wav(self, text: str) -> Tuple[bytes, int]:
        # Save to temp file
        import tempfile
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp:
            tmp_path = tmp.name
        
        self.engine.save_to_file(text, tmp_path)
        self.engine.runAndWait()
        
        # Read back as bytes
        with open(tmp_path, 'rb') as f:
            wav_bytes = f.read()
        
        import os
        os.unlink(tmp_path)
        
        return wav_bytes, 22050
