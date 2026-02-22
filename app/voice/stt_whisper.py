"""
Streaming Speech-to-Text using faster-whisper (CTranslate2).

Accumulates PCM audio chunks and transcribes when silence is detected
or enough audio has been buffered. Works great on Apple Silicon.
"""
from __future__ import annotations

import io
import wave
import time
import tempfile
from typing import Dict, Optional

import numpy as np
from faster_whisper import WhisperModel

from app.config import WHISPER_MODEL_SIZE, WHISPER_DEVICE, WHISPER_COMPUTE_TYPE


class WhisperSTT:
    """Streaming-friendly Whisper STT.

    Accepts raw PCM chunks (16-bit, 16 kHz, mono) and returns
    transcription results with voice-activity detection.
    """

    def __init__(self) -> None:
        print(f"[STT] Loading Whisper model '{WHISPER_MODEL_SIZE}' on {WHISPER_DEVICE}...")
        self.model = WhisperModel(
            WHISPER_MODEL_SIZE,
            device=WHISPER_DEVICE,
            compute_type=WHISPER_COMPUTE_TYPE,
        )
        print("[STT] Whisper model loaded.")

        self._buffer = bytearray()
        self._sample_rate = 16000
        # Minimum audio length (seconds) before attempting transcription
        self._min_duration = 0.8
        # Maximum audio length (seconds) before forcing transcription
        self._max_duration = 15.0
        # Silence threshold (RMS below this = silence)
        self._silence_threshold = 300
        # How many consecutive silent chunks before we consider it a pause
        self._silence_chunks_needed = 8
        self._silent_chunks = 0
        self._has_speech = False

    @property
    def sample_rate(self) -> int:
        return self._sample_rate

    def _rms(self, pcm_bytes: bytes) -> float:
        """Compute RMS energy of 16-bit PCM."""
        samples = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32)
        if len(samples) == 0:
            return 0.0
        return float(np.sqrt(np.mean(samples ** 2)))

    def accept_audio(self, pcm_bytes: bytes) -> Dict[str, object]:
        """Feed a chunk of 16-bit 16 kHz mono PCM.

        Returns:
            {"final": bool, "text": str, "partial": str}
        """
        rms = self._rms(pcm_bytes)
        self._buffer.extend(pcm_bytes)

        duration = len(self._buffer) / (self._sample_rate * 2)  # 2 bytes per sample

        if rms > self._silence_threshold:
            self._has_speech = True
            self._silent_chunks = 0
        else:
            self._silent_chunks += 1

        # Force transcription if buffer is too long
        if duration >= self._max_duration and self._has_speech:
            return self._transcribe(final=True)

        # Transcribe on silence after speech
        if (self._has_speech
                and self._silent_chunks >= self._silence_chunks_needed
                and duration >= self._min_duration):
            return self._transcribe(final=True)

        # Return partial indicator while collecting
        if self._has_speech and duration >= self._min_duration:
            return {"final": False, "text": "", "partial": "listening..."}

        return {"final": False, "text": "", "partial": ""}

    def _transcribe(self, final: bool = True) -> Dict[str, object]:
        """Run Whisper on the buffered audio."""
        if len(self._buffer) < self._sample_rate:  # Less than 0.5s
            self.reset()
            return {"final": True, "text": "", "partial": ""}

        # Convert buffer to float32 numpy array
        samples = np.frombuffer(bytes(self._buffer), dtype=np.int16).astype(np.float32) / 32768.0

        try:
            segments, info = self.model.transcribe(
                samples,
                beam_size=5,
                language="en",
                vad_filter=True,
                vad_parameters=dict(
                    min_silence_duration_ms=500,
                    speech_pad_ms=200,
                ),
            )
            text = " ".join(seg.text.strip() for seg in segments).strip()
        except Exception as e:
            print(f"[STT] Transcription error: {e}")
            text = ""

        self.reset()
        return {"final": final, "text": text, "partial": ""}

    def reset(self) -> None:
        """Clear the audio buffer."""
        self._buffer = bytearray()
        self._silent_chunks = 0
        self._has_speech = False
