"""Model selection and management for conversation LLM."""

from typing import Optional, List


# Recommended HuggingFace models for ITS support chatbot
RECOMMENDED_MODELS = {
    "qwen2-0.5b": {
        "repo": "Qwen/Qwen2-0.5B-Instruct",
        "size": "0.5B",
        "speed": "⚡ Ultra-fast",
        "quality": "Basic Q&A",
    },
    "qwen2-1.5b": {
        "repo": "Qwen/Qwen2-1.5B-Instruct",
        "size": "1.5B",
        "speed": "⚡ Fast",
        "quality": "Good balance",
    },
    "qwen2-7b": {
        "repo": "Qwen/Qwen2-7B-Instruct",
        "size": "7B",
        "speed": "🔥 Medium",
        "quality": "Best quality",
    },
    "mistral-7b": {
        "repo": "mistralai/Mistral-7B-Instruct-v0.2",
        "size": "7B",
        "speed": "🔥 Medium",
        "quality": "Best for instructions",
    },
    "phi-2": {
        "repo": "microsoft/phi-2",
        "size": "2.7B",
        "speed": "⚡ Fast",
        "quality": "Very capable",
    },
    "zephyr-7b": {
        "repo": "tiiuae/zephyr-7b-instruct",
        "size": "7B",
        "speed": "🔥 Medium",
        "quality": "Great for chat",
    },
    "falcon-7b": {
        "repo": "tiiuae/falcon-7b-instruct",
        "size": "7B",
        "speed": "🔥 Medium",
        "quality": "Instruction-tuned",
    },
}


class ModelManager:
    """Manages LLM model selection and switching."""

    def __init__(self, initial_model: str = "zephyr-7b"):
        self.current_model = self._resolve_model(initial_model)
        self._initialization_in_progress = False
        self._personaplex_available = False

    def _resolve_model(self, model_key: str) -> str:
        """Resolve short name or full repo path to full HF repo path."""
        if model_key in RECOMMENDED_MODELS:
            return RECOMMENDED_MODELS[model_key]["repo"]
        # Check if it matches a repo path in RECOMMENDED_MODELS
        for short, info in RECOMMENDED_MODELS.items():
            if info["repo"] == model_key:
                return model_key
        # Assume it's already a full repo path and trust it
        return model_key

    def get_current_model(self) -> str:
        """Get the currently selected model repository."""
        return self.current_model

    def list_available_models(self) -> dict:
        """Return available models with metadata."""
        return RECOMMENDED_MODELS.copy()

    def set_current_model(self, model_key: str) -> bool:
        """Switch to a different model. Returns True if successful."""
        resolved = self._resolve_model(model_key)
        self.current_model = resolved
        return True

    def get_model_info(self, model_key: str) -> Optional[dict]:
        """Get info about a specific model."""
        if model_key in RECOMMENDED_MODELS:
            info = RECOMMENDED_MODELS[model_key].copy()
            info["id"] = model_key
            return info
        return None

    def set_personaplex_available(self, available: bool) -> None:
        """Mark PersonaPlex as available after initialization."""
        self._personaplex_available = available

    def is_personaplex_available(self) -> bool:
        """Check if PersonaPlex is ready."""
        return self._personaplex_available

    def set_initialization_in_progress(self, in_progress: bool) -> None:
        """Track if PersonaPlex is initializing."""
        self._initialization_in_progress = in_progress

    def is_initialization_in_progress(self) -> bool:
        """Check if initialization is happening."""
        return self._initialization_in_progress


# Global instance
_model_manager: Optional[ModelManager] = None


def get_model_manager() -> ModelManager:
    """Get or create the global model manager."""
    global _model_manager
    if _model_manager is None:
        from app.config import HF_CHAT_MODEL
        # Strip down to short name if it's a full repo
        model_name = HF_CHAT_MODEL
        for short, info in RECOMMENDED_MODELS.items():
            if info["repo"] == HF_CHAT_MODEL:
                model_name = short
                break
        _model_manager = ModelManager(model_name)
    return _model_manager
