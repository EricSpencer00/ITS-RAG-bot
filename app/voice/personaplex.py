"""
PersonaPlex Voice Module - Full Duplex Speech-to-Speech

This module implements NVIDIA's PersonaPlex model for real-time
conversational AI with simultaneous listening and speaking.

Based on: https://github.com/NVIDIA/personaplex
"""
from __future__ import annotations

import asyncio
import os
import tarfile
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Callable, Awaitable, Literal

import numpy as np
import sentencepiece
import sphn
import torch
from huggingface_hub import hf_hub_download

from app.config import (
    HF_TOKEN,
    HF_REPO,
    PERSONAPLEX_DEVICE,
    PERSONAPLEX_CPU_OFFLOAD,
    VOICE_PROMPT_DIR,
    DEFAULT_VOICE_PROMPT,
    DEFAULT_TEXT_PROMPT,
)


# Type definitions
DeviceString = Literal["cuda", "cpu"]


def seed_all(seed: int) -> None:
    """Set all random seeds for reproducibility."""
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed(seed)
        torch.cuda.manual_seed_all(seed)
    random.seed(seed)
    np.random.seed(seed)


def torch_auto_device(requested: Optional[DeviceString] = None) -> torch.device:
    """Return a torch.device based on the requested string or availability."""
    if requested is not None:
        return torch.device(requested)
    if torch.cuda.is_available():
        return torch.device("cuda")
    return torch.device("cpu")


def wrap_with_system_tags(text: str) -> str:
    """Add system tags as the model expects if they are missing."""
    cleaned = text.strip()
    if cleaned.startswith("<system>") and cleaned.endswith("<system>"):
        return cleaned
    return f"<system> {cleaned} <system>"


class PersonaPlexLoader:
    """Handles loading PersonaPlex model components from HuggingFace."""
    
    DEFAULT_REPO = "nvidia/personaplex-7b-v1"
    MIMI_NAME = "tokenizer-e351c8d8-checkpoint125.safetensors"
    MOSHI_NAME = "model.safetensors"
    TEXT_TOKENIZER_NAME = "tokenizer_spm_32k_3.model"
    
    def __init__(self, hf_repo: str = DEFAULT_REPO, hf_token: Optional[str] = None):
        self.hf_repo = hf_repo
        self.hf_token = hf_token or os.environ.get("HF_TOKEN")
        
    def download_file(self, filename: str) -> str:
        """Download a file from HuggingFace hub."""
        return hf_hub_download(
            self.hf_repo, 
            filename,
            token=self.hf_token,
        )
    
    def get_mimi(self, weight_path: Optional[str], device: torch.device):
        """Load the Mimi speech encoder/decoder model."""
        # Import here to avoid circular imports
        from moshi.models import loaders as moshi_loaders
        
        if weight_path is None:
            weight_path = self.download_file(self.MIMI_NAME)
        return moshi_loaders.get_mimi(weight_path, device)
    
    def get_moshi_lm(self, weight_path: Optional[str], device: torch.device, cpu_offload: bool = False):
        """Load the Moshi language model."""
        from moshi.models import loaders as moshi_loaders
        
        if weight_path is None:
            weight_path = self.download_file(self.MOSHI_NAME)
        return moshi_loaders.get_moshi_lm(weight_path, device=device, cpu_offload=cpu_offload)
    
    def get_text_tokenizer(self, tokenizer_path: Optional[str] = None) -> sentencepiece.SentencePieceProcessor:
        """Load the text tokenizer."""
        if tokenizer_path is None:
            tokenizer_path = self.download_file(self.TEXT_TOKENIZER_NAME)
        return sentencepiece.SentencePieceProcessor(tokenizer_path)
    
    def get_voice_prompts_dir(self, voice_prompt_dir: Optional[str] = None) -> str:
        """Get or download voice prompts directory."""
        if voice_prompt_dir is not None:
            return voice_prompt_dir
            
        voices_tgz = self.download_file("voices.tgz")
        voices_tgz = Path(voices_tgz)
        voices_dir = voices_tgz.parent / "voices"
        
        if not voices_dir.exists():
            with tarfile.open(voices_tgz, "r:gz") as tar:
                tar.extractall(path=voices_tgz.parent)
                
        if not voices_dir.exists():
            raise RuntimeError("voices.tgz did not contain a 'voices/' directory")
            
        return str(voices_dir)


@dataclass
class PersonaPlexSession:
    """Represents a single PersonaPlex conversation session."""
    
    session_id: str
    voice_prompt: str
    text_prompt: str
    seed: int = 42424242
    
    # Streaming state
    is_active: bool = False
    close_requested: bool = False
    ready_for_audio: bool = False  # True when session is ready to receive audio


class PersonaPlexEngine:
    """
    Main PersonaPlex engine for full-duplex speech-to-speech conversations.
    
    This class manages:
    - Model loading and initialization
    - Concurrent audio encoding/decoding
    - Streaming WebSocket communication
    - Voice and text prompt handling
    """
    
    def __init__(
        self,
        device: Optional[str] = None,
        hf_repo: str = PersonaPlexLoader.DEFAULT_REPO,
        hf_token: Optional[str] = None,
        cpu_offload: bool = False,
        voice_prompt_dir: Optional[str] = None,
    ):
        self.device = torch_auto_device(device)
        self.cpu_offload = cpu_offload
        self.loader = PersonaPlexLoader(hf_repo, hf_token)
        self.voice_prompt_dir = voice_prompt_dir
        
        # Models (loaded lazily)
        self._mimi = None
        self._other_mimi = None  # For encoding user audio
        self._lm = None
        self._lm_gen = None
        self._text_tokenizer = None
        
        # Streaming state
        self._lock = asyncio.Lock()
        self._initialized = False
        
    async def initialize(self) -> None:
        """Load all models (call once at startup)."""
        if self._initialized:
            return
            
        print("[PersonaPlex] Loading Mimi speech codec...")
        mimi_weight = self.loader.download_file(PersonaPlexLoader.MIMI_NAME)
        self._mimi = self.loader.get_mimi(mimi_weight, self.device)
        self._other_mimi = self.loader.get_mimi(mimi_weight, self.device)
        
        print("[PersonaPlex] Loading text tokenizer...")
        self._text_tokenizer = self.loader.get_text_tokenizer()
        
        # Get voice prompts BEFORE loading the large LM model
        print("[PersonaPlex] Loading voice prompts...")
        try:
            self.voice_prompt_dir = self.loader.get_voice_prompts_dir(self.voice_prompt_dir)
            print(f"[PersonaPlex] Voice prompts directory: {self.voice_prompt_dir}")
            
            # Verify voices directory exists and has files
            voices_path = Path(self.voice_prompt_dir)
            if not voices_path.exists():
                raise RuntimeError(f"Voice prompts directory does not exist: {self.voice_prompt_dir}")
            
            voice_files = list(voices_path.glob("*.pt"))
            if not voice_files:
                raise RuntimeError(f"No .pt files found in voice prompts directory: {self.voice_prompt_dir}")
            
            print(f"[PersonaPlex] Found {len(voice_files)} voice prompts")
        except Exception as e:
            print(f"[PersonaPlex] Error loading voice prompts: {e}")
            raise
        
        print("[PersonaPlex] Loading PersonaPlex LM (this may take a while)...")
        moshi_weight = self.loader.download_file(PersonaPlexLoader.MOSHI_NAME)
        self._lm = self.loader.get_moshi_lm(moshi_weight, self.device, self.cpu_offload)
        self._lm.eval()
        
        # Initialize LMGen
        from moshi.models import LMGen
        self.frame_size = int(self._mimi.sample_rate / self._mimi.frame_rate)
        self._lm_gen = LMGen(
            self._lm,
            audio_silence_frame_cnt=int(0.5 * self._mimi.frame_rate),
            sample_rate=self._mimi.sample_rate,
            device=self.device,
            frame_rate=self._mimi.frame_rate,
            save_voice_prompt_embeddings=False,
        )
        
        # Set up streaming mode
        self._mimi.streaming_forever(1)
        self._other_mimi.streaming_forever(1)
        self._lm_gen.streaming_forever(1)
        
        # Warmup
        print("[PersonaPlex] Warming up model...")
        self._warmup()
        
        self._initialized = True
        print("[PersonaPlex] Ready for conversations!")
        
    def _warmup(self) -> None:
        """Warm up the model with dummy data."""
        for _ in range(4):
            chunk = torch.zeros(1, 1, self.frame_size, dtype=torch.float32, device=self.device)
            codes = self._mimi.encode(chunk)
            _ = self._other_mimi.encode(chunk)
            for c in range(codes.shape[-1]):
                tokens = self._lm_gen.step(codes[:, :, c: c + 1])
                if tokens is None:
                    continue
                _ = self._mimi.decode(tokens[:, 1:9])
                _ = self._other_mimi.decode(tokens[:, 1:9])
                
        if self.device.type == 'cuda':
            torch.cuda.synchronize()
            
    @property
    def sample_rate(self) -> int:
        """Audio sample rate (24kHz for PersonaPlex)."""
        return self._mimi.sample_rate if self._mimi else 24000
    
    def get_voice_prompt_path(self, voice_name: str) -> Optional[str]:
        """Get full path for a voice prompt file, or None if voice prompts not available."""
        if self.voice_prompt_dir is None:
            print(f"[PersonaPlex] Warning: Voice prompts not loaded, skipping voice prompt")
            return None
            
        # Add .pt extension if not present
        if not voice_name.endswith('.pt'):
            voice_name = f"{voice_name}.pt"
            
        path = os.path.join(self.voice_prompt_dir, voice_name)
        if not os.path.exists(path):
            print(f"[PersonaPlex] Warning: Voice prompt not found: {path}, skipping voice prompt")
            return None
        return path
    
    def list_voices(self) -> list[str]:
        """List available voice prompts."""
        if self.voice_prompt_dir is None:
            return []
        voices = []
        for f in os.listdir(self.voice_prompt_dir):
            if f.endswith('.pt'):
                voices.append(f.replace('.pt', ''))
        return sorted(voices)
    
    async def handle_conversation(
        self,
        session: PersonaPlexSession,
        send_audio: Callable[[bytes], Awaitable[None]],
        send_text: Callable[[str], Awaitable[None]],
        receive_audio: Callable[[], Awaitable[Optional[bytes]]],
        is_alive: Callable[[], Awaitable[bool]],
    ) -> None:
        """
        Handle a full-duplex conversation session.
        
        This is the main conversation loop that:
        1. Receives user audio via Opus codec
        2. Encodes audio to tokens with Mimi
        3. Generates response tokens with PersonaPlex LM
        4. Decodes tokens to audio with Mimi
        5. Sends audio back via Opus codec
        
        All of this happens concurrently in a streaming fashion.
        """
        # Wait for engine to be fully initialized
        max_wait = 300  # 5 minutes timeout
        waited = 0
        while not self._initialized and waited < max_wait:
            await asyncio.sleep(1)
            waited += 1
        
        if not self._initialized:
            raise RuntimeError("PersonaPlex engine failed to initialize within timeout")
        
        if self._lm_gen is None:
            raise RuntimeError("PersonaPlex LM generation model is not initialized")
        
        async with self._lock:
            seed_all(session.seed)
            
            # Set up voice prompt (optional - can be None)
            voice_prompt_path = self.get_voice_prompt_path(session.voice_prompt)
            if voice_prompt_path and self._lm_gen.voice_prompt != voice_prompt_path:
                try:
                    if voice_prompt_path.endswith('.pt'):
                        # Load voice prompt embeddings with device mapping
                        state_dict = torch.load(voice_prompt_path, map_location=self.device)
                        self._lm_gen.audio_prompts = state_dict
                        self._lm_gen.voice_prompt = voice_prompt_path
                    else:
                        self._lm_gen.load_voice_prompt(voice_prompt_path)
                except RuntimeError as e:
                    if "CUDA device" in str(e) or "cuda" in str(e).lower():
                        print(f"[Session {session.session_id[:8]}] Note: Voice prompt requires {self.device}, skipping")
                    else:
                        print(f"[Session {session.session_id[:8]}] Warning: Failed to load voice prompt: {e}")
                except Exception as e:
                    print(f"[Session {session.session_id[:8]}] Warning: Failed to load voice prompt: {e}")
                    
            # Set up text prompt
            if session.text_prompt:
                self._lm_gen.text_prompt_tokens = self._text_tokenizer.encode(
                    wrap_with_system_tags(session.text_prompt)
                )
            else:
                self._lm_gen.text_prompt_tokens = None
                
            # Create Opus streams
            opus_writer = sphn.OpusStreamWriter(self._mimi.sample_rate)
            opus_reader = sphn.OpusStreamReader(self._mimi.sample_rate)
            
            # Reset streaming state
            self._mimi.reset_streaming()
            self._other_mimi.reset_streaming()
            self._lm_gen.reset_streaming()
            
            # Process system prompts (voice conditioning)
            await self._lm_gen.step_system_prompts_async(self._mimi, is_alive=is_alive)
            self._mimi.reset_streaming()
            
            session.is_active = True
            session.ready_for_audio = True  # Signal that we're ready to receive
            all_pcm_data = None
            
            async def process_incoming_audio():
                """Receive and buffer incoming audio."""
                nonlocal all_pcm_data
                
                print(f"[Session {session.session_id[:8]}] - Starting incoming audio processor")
                frames_received = 0
                silence_count = 0  
                # Wait for up to 10 seconds of silence before giving up
                # Loop runs at ~100-200Hz depending on sleep
                MAX_SILENCE_LOOPS = 5000  
                
                while session.is_active and not session.close_requested:
                    audio_data = await receive_audio()
                    if audio_data is None:
                        silence_count += 1
                        if silence_count > MAX_SILENCE_LOOPS:
                            print(f"[Session {session.session_id[:8]}] - No audio for {MAX_SILENCE_LOOPS} loops, stopping input")
                            session.close_requested = True
                            break
                        await asyncio.sleep(0.005) # Sleep 5ms to avoid CPU spinning
                        continue
                    
                    silence_count = 0  # Reset silence counter on data
                    frames_received += 1
                    print(f"[Session {session.session_id[:8]}] - Received frame #{frames_received}: {len(audio_data)} bytes")
                    if frames_received % 10 == 0:
                        print(f"[Session {session.session_id[:8]}] - Total received: {frames_received} frames")
                    
                    try:
                        opus_reader.append_bytes(audio_data)
                        pcm = opus_reader.read_pcm()
                        
                        if pcm.shape[-1] == 0:
                            continue
                        
                        # Debug: Log audio ingress
                        if frames_received % 10 == 0:
                            print(f"[Session {session.session_id[:8]}] - Decoded PCM: {pcm.shape[-1]} samples")
                            
                        if all_pcm_data is None:
                            all_pcm_data = pcm
                        else:
                            all_pcm_data = np.concatenate((all_pcm_data, pcm))
                    except Exception as e:
                        error_msg = str(e)
                        # If decoder dies, stop processing input
                        if "channel" in error_msg.lower() or "closed" in error_msg.lower():
                            print(f"[Session {session.session_id[:8]}] - Opus decoder channel error at frame {frames_received}, stopping input ({error_msg})")
                            session.close_requested = True
                            break
                        else:
                            print(f"[Session {session.session_id[:8]}] - Opus decode error: {e}")
                        
            async def process_audio_loop():
                """Main audio processing loop - encode/generate/decode."""
                nonlocal all_pcm_data
                
                print(f"[Session {session.session_id[:8]}] - Starting generation loop")
                frames_processed = 0
                
                while session.is_active and not session.close_requested:
                    if not await is_alive():
                        session.close_requested = True
                        break
                    
                    # We MUST sleep to avoid 100% CPU lock in a no-yield loop
                    await asyncio.sleep(0.001)

                    if all_pcm_data is not None and all_pcm_data.shape[-1] > self.frame_size * 50:
                        print(f"[Session {session.session_id[:8]}] - Dropping old audio frames (buffer too large: {all_pcm_data.shape[-1]})")
                        all_pcm_data = all_pcm_data[-self.frame_size * 10:]

                    if all_pcm_data is None or all_pcm_data.shape[-1] < self.frame_size:
                        await asyncio.sleep(0.001)
                        continue

                    # Process ONE frame at a time for real-time response
                    frames_processed += 1
                    if frames_processed % 10 == 0:
                        print(f"[Session {session.session_id[:8]}] - Processing frame {frames_processed}")
                        
                    chunk = all_pcm_data[:self.frame_size]
                    all_pcm_data = all_pcm_data[self.frame_size:]
                    chunk = torch.from_numpy(chunk).to(device=self.device)[None, None]
                
                    try:
                        # Encode user audio
                        codes = self._mimi.encode(chunk)
                        _ = self._other_mimi.encode(chunk)
                        
                        # Generate response tokens
                        for c in range(codes.shape[-1]):
                            tokens = self._lm_gen.step(codes[:, :, c: c + 1])
                            if tokens is None:
                                continue
                                
                            assert tokens.shape[1] == self._lm_gen.lm_model.dep_q + 1
                            
                            # Decode response audio
                            main_pcm = self._mimi.decode(tokens[:, 1:9])
                            _ = self._other_mimi.decode(tokens[:, 1:9])
                            main_pcm = main_pcm.cpu().detach()
                            
                            # Send audio via Opus
                            pcm_out = main_pcm[0, 0].numpy()
                            opus_writer.append_pcm(pcm_out)
                            
                            # Debug: Log output
                            if frames_processed % 10 == 0:
                                print(f"[Session {session.session_id[:8]}] - Generated response audio (frame {frames_processed})")
                            
                            # Extract and send text token
                            text_token = tokens[0, 0, 0].item()
                            if text_token not in (0, 3):  # Not padding tokens
                                text = self._text_tokenizer.id_to_piece(text_token)
                                text = text.replace("▁", " ")
                                await send_text(text)
                    except Exception as e:
                        print(f"[Session {session.session_id[:8]}] - Generation error: {e}")
                        await asyncio.sleep(0.001)
                                
            async def send_audio_loop():
                """Send generated audio to client as WAV."""
                import wave
                import io
                
                print(f"[Session {session.session_id[:8]}] - Starting output transmitter")
                frames_sent = 0
                pcm_buffer = []
                
                while session.is_active and not session.close_requested:
                    await asyncio.sleep(0.005) # 5ms pacing
                    opus_data = opus_writer.read_bytes()
                    
                    if len(opus_data) > 0:
                        try:
                            # Decode Opus to PCM
                            temp_reader = sphn.OpusStreamReader(self._mimi.sample_rate)
                            temp_reader.append_bytes(opus_data)
                            pcm = temp_reader.read_pcm()
                            
                            if pcm.shape[-1] > 0:
                                pcm_buffer.append(pcm)
                                frames_sent += 1
                                
                                # Send as WAV every 0.3 seconds (good latency/efficiency balance)
                                total_samples = sum(p.shape[-1] for p in pcm_buffer)
                                if total_samples >= int(self._mimi.sample_rate * 0.3):
                                    # Concatenate and convert to WAV
                                    pcm_concat = np.concatenate(pcm_buffer, axis=-1)
                                    
                                    # Convert float32 to int16 for WAV
                                    pcm_int16 = np.clip(pcm_concat[0, 0] * 32767, -32768, 32767).astype(np.int16)
                                    
                                    # Write WAV
                                    wav_buffer = io.BytesIO()
                                    with wave.open(wav_buffer, 'wb') as wav:
                                        wav.setnchannels(1)
                                        wav.setsampwidth(2)
                                        wav.setframerate(self._mimi.sample_rate)
                                        wav.writeframes(pcm_int16.tobytes())
                                    
                                    wav_bytes = wav_buffer.getvalue()
                                    await send_audio(wav_bytes)
                                    
                                    if frames_sent % 10 == 0:
                                        print(f"[Session {session.session_id[:8]}] - Sent WAV chunk ({len(wav_bytes)} bytes, {total_samples} PCM samples)")
                                    
                                    pcm_buffer = []
                        except Exception as e:
                            print(f"[Session {session.session_id[:8]}] - Output audio error: {e}")
                        
            # Run all loops concurrently
            tasks = [
                asyncio.create_task(process_incoming_audio()),
                asyncio.create_task(process_audio_loop()),
                asyncio.create_task(send_audio_loop()),
            ]
            
            try:
                done, pending = await asyncio.wait(
                    tasks, 
                    return_when=asyncio.FIRST_COMPLETED
                )
                
                # Cancel remaining tasks
                for task in pending:
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass
            finally:
                session.is_active = False


# Singleton instance
_engine: Optional[PersonaPlexEngine] = None


async def get_engine() -> PersonaPlexEngine:
    """Get or create the PersonaPlex engine singleton."""
    global _engine
    
    if _engine is None:
        _engine = PersonaPlexEngine(
            device=PERSONAPLEX_DEVICE,
            hf_repo=HF_REPO,
            hf_token=HF_TOKEN,
            cpu_offload=PERSONAPLEX_CPU_OFFLOAD,
            voice_prompt_dir=VOICE_PROMPT_DIR,
        )
        await _engine.initialize()
        
    return _engine
