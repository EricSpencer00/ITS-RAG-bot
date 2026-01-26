"""
Voice module - PersonaPlex full-duplex speech-to-speech

This module provides real-time conversational AI using NVIDIA PersonaPlex.
"""
from app.voice.personaplex import (
    PersonaPlexEngine,
    PersonaPlexSession,
    get_engine,
)

__all__ = [
    "PersonaPlexEngine",
    "PersonaPlexSession",
    "get_engine",
]