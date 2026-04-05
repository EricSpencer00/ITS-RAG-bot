from __future__ import annotations
import os
import requests

HF_API_URL = os.getenv("HF_API_URL", "https://api-inference.huggingface.co/models")
HF_TOKEN = os.getenv("HF_TOKEN", "")
OPENAI_KEY = os.getenv("OPENAI_API_KEY", "")

from huggingface_hub import InferenceClient


class RemoteSTT:
    def __init__(self):
        # provider string determines which API to call. 'hf' for HuggingFace
        # inference, 'openai' for OpenAI's Whisper endpoint.
        self.provider = os.getenv("STT_API", "hf").lower()

        # lazily create HF client if needed
        self._hf_client: InferenceClient | None = None

    def _get_hf_client(self) -> InferenceClient:
        if self._hf_client is None:
            self._hf_client = InferenceClient(token=HF_TOKEN) if HF_TOKEN else InferenceClient()
        return self._hf_client

    def transcribe(self, wav_bytes: bytes) -> str:
        if self.provider == "hf":
            # use the SDK rather than raw HTTP; it handles router/headers for us
            client = self._get_hf_client()
            model = os.getenv("HF_STT_MODEL", "openai/whisper-1")
            try:
                output = client.automatic_speech_recognition(wav_bytes, model=model)
            except StopIteration as exc:
                # SDK uses StopIteration to signal an empty/closed stream when
                # no provider responded, which is currently the case for every
                # ASR model on the router.  Surface a clearer error message.
                raise RuntimeError(
                    "HuggingFace currently has no active providers for speech-"
                    "to-text models. Remote STT via `STT_API=hf` will always fail. "
                    "Either install a local model (leave STT_API unset) or set "
                    "`STT_API=openai` to use OpenAI's Whisper service."
                ) from exc
            except Exception as exc:
                # map common HF SDK errors to a friendlier message
                msg = str(exc)
                if "404" in msg or "not found" in msg.lower():
                    raise RuntimeError(
                        f"HF model '{model}' not available (404). "
                        "This usually means no provider is currently hosting it; "
                        "try a different `HF_STT_MODEL` or verify your token."
                    ) from exc
                # let other exceptions bubble up normally
                raise
            # the returned object behaves like a dict with a 'text' key
            if isinstance(output, dict):
                return output.get("text", "")
            return getattr(output, "text", "") or ""

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
