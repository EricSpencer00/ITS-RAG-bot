"""Kyutai moshi-mlx engine adapter — real-time speech-to-speech on Apple Silicon.

This is the Apple-Silicon-friendly replacement for ``personaplex.py``.
PersonaPlex is NVIDIA's fine-tune of moshi and only loads cleanly on CUDA;
moshi-mlx is Kyutai's *official* MLX/Metal port of the same architecture
and runs natively on M1/M2/M3.

Architecture notes (read this before changing anything):

* The model lives in a **child process** spawned with ``multiprocessing``
  using the ``"spawn"`` context. The child is the only place that imports
  ``mlx`` / ``moshi_mlx``. Reasons:

  - Subprocess isolation sidesteps the OpenMP runtime conflict between
    ``libtorch`` (loaded by faster-whisper in our main process) and the
    moshi backend, which previously segfaulted the uvicorn worker on the
    very first ``mimi`` load.
  - A crash inside the model process can't take the FastAPI server down.
  - We can use spawn (not fork) so the child gets a clean Python with no
    inherited torch / Whisper state.

* The parent process only loads ``rustymimi`` (the small Rust mimi codec)
  for encoding incoming PCM and decoding outgoing audio tokens. We never
  import ``moshi_mlx.local_web`` or ``mlx`` in the parent.

* Communication with the child is the same protocol moshi-mlx's own
  reference server uses:

  - parent → child via ``client_to_server`` queue: numpy arrays of mimi
    audio tokens (shape ``(num_codebooks, n)``)
  - child → parent via ``server_to_client`` queue:

    * the literal string ``"start"`` once, on handshake
    * tuples ``(0, audio_tokens_uint32)`` for generated audio
    * tuples ``(1, "<text piece>")`` for emitted text tokens
"""
from __future__ import annotations

import asyncio
import io
import multiprocessing as mp
import queue
import time
import wave
from dataclasses import dataclass
from typing import Awaitable, Callable, Optional

import numpy as np


# moshi sample rate / frame size are fixed by the mimi codec.
SAMPLE_RATE = 24000
FRAME_SIZE = 1920  # 80 ms per frame at 24 kHz
NUM_CODEBOOKS = 8  # config_v0_1 default — kept in sync with the child

# HF repo and quantization. q4 ≈ 4 GB on disk, fits comfortably on M1/M2/M3.
DEFAULT_HF_REPO = "kyutai/moshiko-mlx-q4"  # male voice
DEFAULT_QUANTIZED = 4


# ─── Child process entry point ────────────────────────────────────────
#
# Defined at module level so the ``"spawn"`` multiprocessing context can
# pickle a reference to it. The child re-imports moshi_mlx fresh — none of
# the parent's torch / Whisper state is inherited because we use spawn.
def _child_main(c2s: "mp.Queue", s2c: "mp.Queue", hf_repo: str, quantized: int) -> None:
    import argparse
    import json
    import sys
    import faulthandler

    # Surface any native crash inside the child as a Python traceback.
    faulthandler.enable(file=sys.stderr, all_threads=True)

    import huggingface_hub
    from moshi_mlx import models
    from moshi_mlx.local_web import model_server  # noqa: WPS433

    args = argparse.Namespace(
        hf_repo=hf_repo,
        quantized=quantized,
        moshi_weight=None,
        tokenizer=None,
        steps=4000,
        lm_config=None,
    )

    # local_web.model_server expects ``lm_config`` either as a dict (parsed
    # from config.json) or as an LmConfig instance. moshiko-mlx-q4 has no
    # config.json in the repo, so we fall back to the default v0_1 layout
    # (same behavior as moshi_mlx.local_web.main).
    lm_config = None
    try:
        cfg_path = huggingface_hub.hf_hub_download(hf_repo, "config.json")
        with open(cfg_path, "r") as f:
            lm_config = json.load(f)
    except Exception:
        lm_config = models.config_v0_1()

    print(f"[moshi-mlx child] starting model_server with {hf_repo} q{quantized}", flush=True)
    model_server(c2s, s2c, lm_config, args)


# ─── Parent-side audio codec warmup ───────────────────────────────────
#
# Reproduces moshi_mlx.local_web.full_warmup so we don't have to import
# local_web in the parent process (which would also pull in sphn etc.).
def _full_warmup(tokenizer, c2s: "mp.Queue", s2c: "mp.Queue", max_delay: int) -> None:
    for i in range(4):
        pcm = np.zeros(FRAME_SIZE, dtype=np.float32)
        tokenizer.encode(pcm)
        while True:
            time.sleep(0.01)
            data = tokenizer.get_encoded()
            if data is not None:
                break
        c2s.put_nowait(data)
        if i < max_delay:
            continue
        # Drain a generated frame from the model
        while True:
            kind, data = s2c.get()
            if kind == 0:
                tokenizer.decode(data)
                break
        while True:
            time.sleep(0.01)
            data = tokenizer.get_decoded()
            if data is not None:
                break


def _pcm_to_wav_bytes(pcm: np.ndarray, sample_rate: int = SAMPLE_RATE) -> bytes:
    """Pack a 1D float32 PCM array into a one-shot WAV blob."""
    pcm_int16 = np.clip(pcm * 32767.0, -32768, 32767).astype(np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(pcm_int16.tobytes())
    return buf.getvalue()


# ─── Public engine class ──────────────────────────────────────────────


class MoshiMlxEngine:
    """In-process facade for the moshi-mlx model running in a child."""

    def __init__(self, hf_repo: str = DEFAULT_HF_REPO, quantized: int = DEFAULT_QUANTIZED):
        self.hf_repo = hf_repo
        self.quantized = quantized
        self._proc: Optional[mp.Process] = None
        self._c2s: Optional[mp.Queue] = None
        self._s2c: Optional[mp.Queue] = None
        self._tokenizer = None  # rustymimi.StreamTokenizer (parent-side)
        self._initialized = False
        self._lock = asyncio.Lock()

    @property
    def sample_rate(self) -> int:
        return SAMPLE_RATE

    async def initialize(self) -> None:
        if self._initialized:
            return

        # Late imports — keep the parent process slim until PP is requested.
        import huggingface_hub
        import rustymimi

        loop = asyncio.get_running_loop()

        # Download the mimi codec safetensors so the parent can encode/decode
        # audio. The child also downloads its own copy on first run, but the
        # HF cache means the second download is a no-op.
        def _download_mimi() -> str:
            return huggingface_hub.hf_hub_download(
                self.hf_repo, "tokenizer-e351c8d8-checkpoint125.safetensors"
            )

        mimi_path = await loop.run_in_executor(None, _download_mimi)
        self._tokenizer = rustymimi.StreamTokenizer(mimi_path, num_codebooks=NUM_CODEBOOKS)

        # Spawn the model child. ``"spawn"`` is critical: ``"fork"`` would
        # inherit Whisper / torch state from the parent and re-trigger the
        # OpenMP segfault that this whole module exists to avoid.
        ctx = mp.get_context("spawn")
        self._c2s = ctx.Queue()
        self._s2c = ctx.Queue()
        self._proc = ctx.Process(
            target=_child_main,
            args=(self._c2s, self._s2c, self.hf_repo, self.quantized),
            daemon=True,
        )
        self._proc.start()

        # Wait for the "start" handshake from the child. The child loads
        # ~4 GB of weights and runs an internal warmup, so this can take
        # 30–90 s the first time.
        def _wait_for_start() -> str:
            return self._s2c.get()

        start_msg = await loop.run_in_executor(None, _wait_for_start)
        if start_msg != "start":
            raise RuntimeError(f"unexpected handshake from moshi-mlx child: {start_msg!r}")

        # Run the codec/model warmup loop (encode 4 silent frames, drain
        # 2 generated frames, makes sure both sides are primed).
        await loop.run_in_executor(
            None, _full_warmup, self._tokenizer, self._c2s, self._s2c, 2
        )

        self._initialized = True

    async def handle_conversation(
        self,
        send_audio: Callable[[bytes], Awaitable[None]],
        send_text: Callable[[str], Awaitable[None]],
        receive_pcm: Callable[[], Awaitable[Optional[np.ndarray]]],
        is_alive: Callable[[], Awaitable[bool]],
    ) -> None:
        """Run one moshi conversation. PCM in, WAV + text out.

        ``receive_pcm`` returns a 1D float32 numpy array at ``self.sample_rate``
        or ``None`` on timeout. ``send_audio`` is called with WAV bytes ready
        to push to the browser. ``send_text`` is called per emitted token.
        """
        if not self._initialized:
            await self.initialize()

        async with self._lock:  # one session at a time — moshi has shared LM state
            loop = asyncio.get_running_loop()
            in_buffer = np.zeros(0, dtype=np.float32)
            stop = asyncio.Event()

            async def input_loop() -> None:
                nonlocal in_buffer
                try:
                    while not stop.is_set() and await is_alive():
                        pcm = await receive_pcm()
                        if pcm is None:
                            await asyncio.sleep(0.005)
                            continue
                        if pcm.dtype != np.float32:
                            pcm = pcm.astype(np.float32)
                        in_buffer = np.concatenate((in_buffer, pcm))

                        while in_buffer.shape[-1] >= FRAME_SIZE:
                            chunk = in_buffer[:FRAME_SIZE]
                            in_buffer = in_buffer[FRAME_SIZE:]

                            # Encode this frame on a worker thread (mimi
                            # encode is a Rust call that releases the GIL).
                            await loop.run_in_executor(
                                None, self._tokenizer.encode, chunk
                            )
                            # Drain encoded tokens and forward to the model.
                            while True:
                                tokens = self._tokenizer.get_encoded()
                                if tokens is None:
                                    await asyncio.sleep(0.001)
                                    continue
                                self._c2s.put_nowait(tokens)
                                break
                finally:
                    stop.set()

            async def output_loop() -> None:
                try:
                    while not stop.is_set() and await is_alive():
                        try:
                            kind, data = await loop.run_in_executor(
                                None,
                                lambda: self._s2c.get(timeout=0.1),
                            )
                        except queue.Empty:
                            await asyncio.sleep(0.005)
                            continue
                        if kind == 1:  # text token
                            try:
                                await send_text(data)
                            except Exception:
                                pass
                        elif kind == 0:  # audio tokens
                            await loop.run_in_executor(
                                None, self._tokenizer.decode, data
                            )
                            while True:
                                pcm_out = self._tokenizer.get_decoded()
                                if pcm_out is None:
                                    await asyncio.sleep(0.001)
                                    continue
                                wav_bytes = _pcm_to_wav_bytes(pcm_out)
                                try:
                                    await send_audio(wav_bytes)
                                except Exception:
                                    pass
                                break
                finally:
                    stop.set()

            await asyncio.gather(input_loop(), output_loop())

    def shutdown(self) -> None:
        if self._proc is not None and self._proc.is_alive():
            self._proc.terminate()
            self._proc.join(timeout=5)
        self._proc = None
        # Explicitly close+join the queues so multiprocessing's resource
        # tracker doesn't complain about leaked semaphores on macOS.
        for q in (self._c2s, self._s2c):
            if q is not None:
                try:
                    q.close()
                    q.join_thread()
                except Exception:
                    pass
        self._c2s = None
        self._s2c = None
        self._initialized = False


# ─── Module-level singleton (matches the personaplex.py shape) ────────


_engine: Optional[MoshiMlxEngine] = None


async def get_engine() -> MoshiMlxEngine:
    global _engine
    if _engine is None:
        _engine = MoshiMlxEngine()
        await _engine.initialize()
    return _engine
