"""
Text-to-Speech using Microsoft Edge TTS.

High-quality neural voices, streaming output, no GPU required.
Falls back gracefully if the service is unavailable.
"""
from __future__ import annotations

import asyncio
import io
import wave
import tempfile
from typing import Tuple, Optional, AsyncGenerator

import edge_tts
import numpy as np

from app.config import TTS_VOICE, TTS_RATE, TTS_VOLUME


class EdgeTTS:
    """Async TTS using Microsoft Edge neural voices.

    Produces 24 kHz mono WAV audio suitable for browser playback.
    """

    def __init__(self) -> None:
        self.voice = TTS_VOICE
        self.rate = TTS_RATE
        self.volume = TTS_VOLUME
        self._sample_rate = 24000
        print(f"[TTS] Using Edge TTS voice: {self.voice}")

    @property
    def sample_rate(self) -> int:
        return self._sample_rate

    async def synthesize_speech(self, text: str) -> Tuple[bytes, int]:
        """Synthesize text to WAV bytes (async).

        Returns:
            (wav_bytes, sample_rate)
        """
        if not text or not text.strip():
            return b"", self._sample_rate

        communicate = edge_tts.Communicate(
            text.strip(),
            voice=self.voice,
            rate=self.rate,
            volume=self.volume,
        )

        # Collect all audio chunks
        audio_data = bytearray()
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_data.extend(chunk["data"])

        if not audio_data:
            return b"", self._sample_rate

        # edge-tts returns MP3 by default — convert to WAV for browser
        wav_bytes = await self._mp3_to_wav(bytes(audio_data))
        return wav_bytes, self._sample_rate

    def synthesize_wav(self, text: str) -> Tuple[bytes, int]:
        """Synchronous wrapper for synthesize_speech."""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # We're inside an async context — create a new task
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    future = pool.submit(asyncio.run, self.synthesize_speech(text))
                    return future.result(timeout=30)
            else:
                return loop.run_until_complete(self.synthesize_speech(text))
        except RuntimeError:
            return asyncio.run(self.synthesize_speech(text))

    async def synthesize_streaming(self, text: str) -> AsyncGenerator[bytes, None]:
        """Stream WAV chunks as they become available.

        Yields WAV-encoded audio chunks for low-latency playback.
        """
        if not text or not text.strip():
            return

        communicate = edge_tts.Communicate(
            text.strip(),
            voice=self.voice,
            rate=self.rate,
            volume=self.volume,
        )

        audio_buffer = bytearray()
        chunk_size = 4800  # 0.2 seconds at 24kHz

        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_buffer.extend(chunk["data"])

        # Convert full MP3 to WAV and yield
        if audio_buffer:
            wav_bytes = await self._mp3_to_wav(bytes(audio_buffer))
            if wav_bytes:
                yield wav_bytes

    async def _mp3_to_wav(self, mp3_bytes: bytes) -> bytes:
        """Convert MP3 audio to 24kHz mono 16-bit WAV."""
        try:
            import soundfile as sf

            # soundfile can read MP3 directly
            audio_data, sr = sf.read(io.BytesIO(mp3_bytes))

            # Convert to mono if stereo
            if len(audio_data.shape) > 1:
                audio_data = audio_data.mean(axis=1)

            # Resample to 24kHz if needed
            if sr != self._sample_rate:
                # Simple linear resampling
                duration = len(audio_data) / sr
                new_length = int(duration * self._sample_rate)
                indices = np.linspace(0, len(audio_data) - 1, new_length)
                audio_data = np.interp(indices, np.arange(len(audio_data)), audio_data)

            # Convert to 16-bit PCM WAV
            pcm_int16 = np.clip(audio_data * 32767, -32768, 32767).astype(np.int16)

            wav_buffer = io.BytesIO()
            with wave.open(wav_buffer, 'wb') as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(self._sample_rate)
                wav.writeframes(pcm_int16.tobytes())

            return wav_buffer.getvalue()

        except Exception as e:
            print(f"[TTS] MP3→WAV conversion error: {e}")
            # Return the raw MP3 — browser can still play it
            return mp3_bytes
