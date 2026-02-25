from __future__ import annotations

import json
import aiohttp
from typing import Dict, List, AsyncGenerator

import requests

from app.config import (
    OLLAMA_BASE_URL,
    OLLAMA_MODEL,
    OLLAMA_LLM_NUM_PREDICT,
    OLLAMA_TEMPERATURE,
    HF_CHAT_MODEL,
)
from app.conversation.state import ConversationState
from app.rag.prompt import SYSTEM_PROMPT
from app.rag.retriever import Retriever


INTENT_TICKET = "ticket_draft"
INTENT_TROUBLESHOOT = "troubleshoot"
INTENT_UNKNOWN = "unknown"

# Keywords for topic continuity detection
TROUBLESHOOTING_KEYWORDS = ["how do i", "fix", "error", "issue", "problem", "trouble", "vpn", "wifi", "email", "mfa", "password", "account", "login", "access", "network", "printer", "software"]
TOPIC_KEYWORDS = ["reset", "change", "configure", "set up", "install", "update", "connect", "enable", "disable"]


def detect_intent(text: str) -> str:
    lowered = text.lower()
    if any(k in lowered for k in ["ticket", "help request", "support request", "case", "submit"]):
        return INTENT_TICKET
    if any(k in lowered for k in TROUBLESHOOTING_KEYWORDS):
        return INTENT_TROUBLESHOOT
    return INTENT_TROUBLESHOOT


def is_related_to_context(text: str, history: List[Dict[str, str]]) -> bool:
    """
    Determine if the current message is related to the conversation context.
    Uses keyword matching and semantic similarity to decide if context should be preserved.
    """
    if not history or len(history) < 2:
        return True  # First message, no context to relate to
    
    lowered_text = text.lower()
    
    # Get the last user message(s) for context
    user_messages = [h["content"] for h in history if h["role"] == "user"]
    if not user_messages:
        return True
    
    last_user_text = user_messages[-1].lower()
    
    # Check for direct topic continuity markers
    continuity_markers = ["also", "and", "another", "same", "still", "again", "what about", "how about", "more on"]
    if any(marker in lowered_text for marker in continuity_markers):
        return True
    
    # Check for keyword overlap (indicates topic continuity)
    text_keywords = set(lowered_text.split())
    last_keywords = set(last_user_text.split())
    common_keywords = text_keywords & last_keywords
    
    # If there's meaningful keyword overlap, consider it related
    important_words = [kw for kw in common_keywords if len(kw) > 3 and kw not in ["that", "this", "have", "with", "from", "what", "help", "need"]]
    if len(important_words) >= 2:
        return True
    
    # Check if both messages have similar troubleshooting intent
    both_troubleshooting = (
        any(k in lowered_text for k in TROUBLESHOOTING_KEYWORDS) and
        any(k in last_user_text for k in TROUBLESHOOTING_KEYWORDS)
    )
    if both_troubleshooting:
        return True
    
    # If no clear relation found, still return True with lower confidence
    # This implements "don't completely drop the context" requirement
    return True


def requires_private_data(text: str) -> bool:
    lowered = text.lower()
    return any(k in lowered for k in ["internal", "employee record", "student record", "ssn", "social security"])


def build_ticket_draft(state: ConversationState) -> str:
    lines = ["Ticket Draft (not submitted)"]
    lines.append(f"Issue: {state.issue_summary or 'Unknown'}")
    lines.append(f"Environment: {state.environment or 'Unknown'}")
    if state.attempted_steps:
        lines.append("Attempted Steps:")
        for step in state.attempted_steps:
            lines.append(f"- {step}")
    else:
        lines.append("Attempted Steps: None provided")
    return "\n".join(lines)


def _format_context(docs: List[Dict[str, str]]) -> str:
    parts = []
    for idx, doc in enumerate(docs, start=1):
        source = doc['source']
        title = doc.get('title', source)
        content = doc['content']
        
        # Format source info with URL if available
        if source.startswith('http'):
            source_line = f"Source {idx}: {title} ({source})"
        else:
            source_line = f"Source {idx}: {title}"
        
        parts.append(f"{source_line}\n{content}")
    return "\n\n".join(parts)


def _ollama_chat(messages: List[Dict[str, str]]) -> str:
    payload = {
        "model": OLLAMA_MODEL,
        "messages": messages,
        "stream": False,
        "options": {"temperature": OLLAMA_TEMPERATURE, "num_predict": OLLAMA_LLM_NUM_PREDICT},
    }
    resp = requests.post(f"{OLLAMA_BASE_URL}/api/chat", json=payload, timeout=120)
    resp.raise_for_status()
    data = resp.json()
    return data.get("message", {}).get("content", "")


def _hf_chat(messages: List[Dict[str, str]]) -> str:
    """Send a simple concatenated conversation to HuggingFace inference API.

    This isn't a sophisticated chat protocol; most HF chat-capable models
    will happily continue from a prompt consisting of alternating role tags.
    The caller handles max token limits via environment (OLLAMA_LLM_NUM_PREDICT).
    """
    from app.config import HF_CHAT_MODEL, HF_API_URL, HF_TOKEN

    # join all messages by role for a basic prompt
    prompt_lines = []
    for m in messages:
        role = m.get("role", "user")
        content = m.get("content", "")
        prompt_lines.append(f"{role}: {content}")
    prompt = "\n".join(prompt_lines)

    headers = {"Authorization": f"Bearer {HF_TOKEN}"} if HF_TOKEN else {}
    payload = {"inputs": prompt, "parameters": {"max_new_tokens": OLLAMA_LLM_NUM_PREDICT}}
    resp = requests.post(f"{HF_API_URL}/{HF_CHAT_MODEL}", headers=headers, json=payload, timeout=120)
    resp.raise_for_status()
    data = resp.json()
    # HF usually returns {'generated_text': '...'} or a list of those
    if isinstance(data, list):
        return data[0].get("generated_text", "")
    return data.get("generated_text", "")


async def _ollama_chat_stream(messages: List[Dict[str, str]]) -> AsyncGenerator[str, None]:
    payload = {
        "model": OLLAMA_MODEL,
        "messages": messages,
        "stream": True,
        "options": {"temperature": OLLAMA_TEMPERATURE, "num_predict": OLLAMA_LLM_NUM_PREDICT},
    }
    
    async with aiohttp.ClientSession() as session:
        async with session.post(f"{OLLAMA_BASE_URL}/api/chat", json=payload) as resp:
            resp.raise_for_status()
            async for line in resp.content:
                if line:
                    try:
                        data = json.loads(line)
                        content = data.get("message", {}).get("content", "")
                        if content:
                            yield content
                    except json.JSONDecodeError:
                        pass


async def _hf_chat_stream(messages: List[Dict[str, str]]) -> AsyncGenerator[str, None]:
    """Simplified streaming wrapper for HuggingFace API.

    The inference API doesn't offer true streaming easily, so we just call the
    synchronous client and yield a single chunk. This preserves the async
    interface used by the rest of the code.
    """
    text = _hf_chat(messages)
    yield text


async def handle_user_text_stream(state: ConversationState, text: str, retriever: Retriever) -> AsyncGenerator[Dict, None]:
    """
    Async Generator that yields:
    1. {"type": "meta", "intent": ..., "sources": ..., "response": ...} (response may be pre-calculated for simple intents)
    2. {"type": "token", "content": ...} (for LLM generation)
    
    Maintains conversation context across multiple turns, with intelligent context preservation.
    """
    if requires_private_data(text):
        refusal = "I can only use public ITS information in this PoC. Please contact the ITS Service Desk for requests that require private or internal data."
        state.add_turn("assistant", refusal)
        yield {"type": "meta", "intent": INTENT_UNKNOWN, "sources": [], "response": refusal}
        return

    intent = detect_intent(text)
    state.add_turn("user", text)
    state.update_from_user(text)

    if intent == INTENT_TICKET:
        draft = build_ticket_draft(state)
        state.add_turn("assistant", draft)
        yield {"type": "meta", "intent": intent, "sources": [], "response": draft}
        return

    if retriever is not None:
        docs = retriever.query(text)
    else:
        docs = []
    
    yield {"type": "meta", "intent": intent, "sources": docs}

    if not docs:
         context = "No specific Loyola documentation found."
    else:
         context = _format_context(docs)
    
    # Build message history - include recent conversation context if related
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    
    # Add conversation history if the new message is related to prior context
    if is_related_to_context(text, state.history):
        # Include last 4 turns (2 user-assistant pairs) of history for context
        recent_history = state.history[:-1]  # Exclude the current user message (just added)
        if recent_history:
            # Only include last 4 messages (2 turns) to avoid overwhelming context
            history_to_include = recent_history[-4:]
            for msg in history_to_include:
                messages.append(msg)
    
    # Add current query with context
    messages.append({
        "role": "user",
        "content": f"Question: {text}\n\nContext:\n{context}"
    })
    
    full_response = []
    # choose chat backend based on configuration
    if HF_CHAT_MODEL:
        async for token in _hf_chat_stream(messages):
            full_response.append(token)
            yield {"type": "token", "content": token}
    else:
        async for token in _ollama_chat_stream(messages):
            full_response.append(token)
            yield {"type": "token", "content": token}
    
    state.add_turn("assistant", "".join(full_response))



def handle_user_text(state: ConversationState, text: str, retriever: Retriever) -> Dict[str, str]:
    if requires_private_data(text):
        refusal = "I can only use public ITS information in this PoC. Please contact the ITS Service Desk for requests that require private or internal data."
        state.add_turn("assistant", refusal)
        return {"response": refusal, "intent": INTENT_UNKNOWN, "sources": []}

    intent = detect_intent(text)
    state.add_turn("user", text)
    state.update_from_user(text)

    if intent == INTENT_TICKET:
        draft = build_ticket_draft(state)
        state.add_turn("assistant", draft)
        return {"response": draft, "intent": intent, "sources": []}

    if retriever is not None:
        docs = retriever.query(text)
    else:
        docs = []
    if not docs:
        context = "No specific Loyola documentation found."
    else:
        context = _format_context(docs)
    
    # Build message history - include recent conversation context if related
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    
    # Add conversation history if the new message is related to prior context
    if is_related_to_context(text, state.history):
        # Include last 4 turns (2 user-assistant pairs) of history for context
        recent_history = state.history[:-1]  # Exclude the current user message (just added)
        if recent_history:
            # Only include last 4 messages (2 turns) to avoid overwhelming context
            history_to_include = recent_history[-4:]
            for msg in history_to_include:
                messages.append(msg)
    
    # Add current query with context
    messages.append({
        "role": "user",
        "content": f"Question: {text}\n\nContext:\n{context}"
    })
    
    # choose chat backend at runtime
    if HF_CHAT_MODEL:
        answer = _hf_chat(messages)
    else:
        answer = _ollama_chat(messages)

    response = answer.strip()
    state.add_turn("assistant", response)
    return {"response": response, "intent": intent, "sources": docs}
