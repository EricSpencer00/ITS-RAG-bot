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
)
from app.conversation.state import ConversationState
from app.rag.prompt import SYSTEM_PROMPT
from app.rag.retriever import Retriever


INTENT_TICKET = "ticket_draft"
INTENT_TROUBLESHOOT = "troubleshoot"
INTENT_UNKNOWN = "unknown"

# ── confidence thresholds ──────────────────────────────────────────────
# These control when Lu answers vs. asks a clarifying question.
# HIGH_CONFIDENCE: top RAG hit score above this → answer directly
# LOW_CONFIDENCE:  top RAG hit score below this → definitely ask
# Between the two: answer if the user already gave details, else ask.
HIGH_CONFIDENCE_SCORE = 0.55
LOW_CONFIDENCE_SCORE = 0.40
# After this many clarifications, answer with whatever we have
MAX_CLARIFICATIONS = 3

# Keywords for topic continuity detection
TROUBLESHOOTING_KEYWORDS = ["how do i", "fix", "error", "issue", "problem", "trouble", "vpn", "wifi", "email", "mfa", "password", "account", "login", "access", "network", "printer", "software"]
TOPIC_KEYWORDS = ["reset", "change", "configure", "set up", "install", "update", "connect", "enable", "disable"]


def detect_intent(text: str) -> str:
    lowered = text.lower()
    if any(k in lowered for k in ["ticket", "help request", "support request", "case", "submit"]):
        return INTENT_TICKET
    return INTENT_TROUBLESHOOT


def is_related_to_context(text: str, history: List[Dict[str, str]]) -> bool:
    """
    Determine if the current message is related to the conversation context.
    Uses keyword matching and continuity markers.
    """
    if not history or len(history) < 2:
        return True

    lowered_text = text.lower()

    user_messages = [h["content"] for h in history if h["role"] == "user"]
    if not user_messages:
        return True

    last_user_text = user_messages[-1].lower()

    # Direct topic continuity markers
    continuity_markers = ["also", "and", "another", "same", "still", "again", "what about", "how about", "more on"]
    if any(marker in lowered_text for marker in continuity_markers):
        return True

    # Keyword overlap
    text_keywords = set(lowered_text.split())
    last_keywords = set(last_user_text.split())
    common_keywords = text_keywords & last_keywords
    important_words = [kw for kw in common_keywords if len(kw) > 3 and kw not in {"that", "this", "have", "with", "from", "what", "help", "need"}]
    if len(important_words) >= 2:
        return True

    # Short responses (likely answering Lu's clarifying question) are related
    if len(text.split()) <= 8:
        return True

    # Both messages have troubleshooting keywords
    both_troubleshooting = (
        any(k in lowered_text for k in TROUBLESHOOTING_KEYWORDS) and
        any(k in last_user_text for k in TROUBLESHOOTING_KEYWORDS)
    )
    if both_troubleshooting:
        return True

    return False


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

        if source.startswith('http'):
            source_line = f"Source {idx}: {title} ({source})"
        else:
            source_line = f"Source {idx}: {title}"

        parts.append(f"{source_line}\n{content}")
    return "\n\n".join(parts)


def _assess_confidence(docs: List[Dict[str, str]], state: ConversationState) -> str:
    """Decide whether to answer or ask a clarifying question.

    Returns:
        "answer"  – enough confidence to give a solution
        "clarify" – should ask a diagnostic question first
    """
    # After MAX_CLARIFICATIONS rounds, just answer with best effort
    if state.clarifications_asked >= MAX_CLARIFICATIONS:
        return "answer"

    if not docs:
        return "clarify"

    top_score = float(docs[0].get("score", 0))

    # Strong match → answer
    if top_score >= HIGH_CONFIDENCE_SCORE:
        return "answer"

    # Weak match → clarify
    if top_score < LOW_CONFIDENCE_SCORE:
        return "clarify"

    # Middle ground: answer if the user has already provided some detail
    # (multiple turns or a longer message), otherwise clarify
    if state.turns >= 3 or (state.issue_summary and len(state.issue_summary.split()) > 20):
        return "answer"

    return "clarify"


# ── LLM backends ──────────────────────────────────────────────────────

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
    """Send a conversation to HuggingFace inference API.

    Tries chat_completion first, falls back to text_generation with formatted prompt.
    """
    from app.config import HF_TOKEN
    from app.model_manager import get_model_manager
    from huggingface_hub import InferenceClient

    model_manager = get_model_manager()
    model = model_manager.get_current_model()

    client = InferenceClient(token=HF_TOKEN) if HF_TOKEN else InferenceClient()

    # Try chat_completion first (newer, better structured)
    try:
        response = client.chat_completion(
            messages=messages,
            model=model,
            max_tokens=OLLAMA_LLM_NUM_PREDICT,
            temperature=OLLAMA_TEMPERATURE,
        )
        if response and hasattr(response, 'choices') and len(response.choices) > 0:
            choice = response.choices[0]
            if hasattr(choice, 'message') and hasattr(choice.message, 'content'):
                result = choice.message.content.strip()
                return result if result else "I couldn't generate a response. Please try again."
        result = str(response).strip() if response else ""
        return result if result else "I couldn't generate a response. Please try again."
    except Exception as e:
        chat_error = str(e).lower()
        # If chat fails, try text_generation with formatted prompt
        if "not supported" in chat_error or "supported task" in chat_error or "404" not in chat_error:
            try:
                # Format messages as a simple prompt for text_generation
                prompt_lines = []
                for m in messages:
                    role = m.get("role", "user")
                    content = m.get("content", "")
                    prompt_lines.append(f"{role}: {content}")
                prompt = "\n".join(prompt_lines)

                generated = client.text_generation(
                    prompt,
                    model=model,
                    max_new_tokens=OLLAMA_LLM_NUM_PREDICT,
                    temperature=OLLAMA_TEMPERATURE,
                )
                result = str(generated).strip() if generated else ""
                return result if result else "I couldn't generate a response. Please try again."
            except Exception as e2:
                print(f"[HF Chat Fallback Error] {str(e2)}")
                return f"I encountered an error. Please try a different model or try again."

        # If both fail, raise the original error
        if "404" in chat_error or "not found" in chat_error:
            raise RuntimeError(
                f"HF chat model '{model}' not available; received 404. "
                "Check HF_TOKEN or try another model."
            ) from e

        print(f"[HF Chat Error] {chat_error}")
        return "I encountered an error. Please try a different model or try again."


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
    """Wrapper — yields a single chunk since HF doesn't stream easily."""
    try:
        text = _hf_chat(messages)
        if text:
            yield text
    except StopIteration:
        # HF client may raise StopIteration; convert to proper error handling
        yield "I encountered an issue processing that request. Please try again."
    except Exception as e:
        yield f"Error: {str(e)}"


# ── Diagnostic hint injected when Lu should ask a question ────────────
_CLARIFY_HINT = (
    "\n\n[INSTRUCTION: The retrieved sources are not a strong match, or the user "
    "hasn't given enough detail yet. Ask ONE short clarifying question to narrow "
    "down the problem. Do NOT suggest a solution yet.]"
)


# ── Public handlers ───────────────────────────────────────────────────

async def handle_user_text_stream(state: ConversationState, text: str, retriever: Retriever) -> AsyncGenerator[Dict, None]:
    """Async generator that yields meta, token, and final chunks."""
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

    # ── RAG retrieval ─────────────────────────────────────────────────
    docs = retriever.query(text) if retriever is not None else []

    yield {"type": "meta", "intent": intent, "sources": docs}

    if not docs:
        context = "No specific Loyola documentation found."
    else:
        context = _format_context(docs)

    # ── Confidence gate ───────────────────────────────────────────────
    decision = _assess_confidence(docs, state)

    # ── Build messages ────────────────────────────────────────────────
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    # Include recent history if related
    if is_related_to_context(text, state.history):
        recent_history = state.history[:-1]  # exclude the just-added user msg
        if recent_history:
            for msg in recent_history[-4:]:
                messages.append(msg)

    # Build user message with context + optional clarify hint
    user_content = f"Question: {text}\n\nContext:\n{context}"
    if decision == "clarify":
        user_content += _CLARIFY_HINT
        state.clarifications_asked += 1

    messages.append({"role": "user", "content": user_content})

    # ── Stream LLM response ───────────────────────────────────────────
    from app.model_manager import get_model_manager
    model_manager = get_model_manager()
    use_hf = model_manager.get_current_model() != OLLAMA_MODEL

    full_response = []
    response_generated = False

    # Try HF first, fall back to Ollama
    if use_hf:
        try:
            async for token in _hf_chat_stream(messages):
                full_response.append(token)
                yield {"type": "token", "content": token}
            response_generated = True
        except Exception as e:
            print(f"[Controller Streaming] HF chat failed: {e}, falling back to Ollama")
            full_response = []  # Reset for Ollama attempt

    # Fall back to Ollama if HF failed or wasn't attempted
    if not response_generated:
        try:
            async for token in _ollama_chat_stream(messages):
                full_response.append(token)
                yield {"type": "token", "content": token}
            response_generated = True
        except Exception as e:
            error_msg = f"I'm having trouble with inference right now. Please try again."
            full_response.append(error_msg)
            yield {"type": "token", "content": error_msg}
            print(f"[Controller Streaming] Both HF and Ollama failed: {e}")

    state.add_turn("assistant", "".join(full_response))


def handle_user_text(state: ConversationState, text: str, retriever: Retriever) -> Dict[str, str]:
    """Synchronous (non-streaming) handler — used by POST /api/text."""
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

    docs = retriever.query(text) if retriever is not None else []
    if not docs:
        context = "No specific Loyola documentation found."
    else:
        context = _format_context(docs)

    # Confidence gate
    decision = _assess_confidence(docs, state)

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    if is_related_to_context(text, state.history):
        recent_history = state.history[:-1]
        if recent_history:
            for msg in recent_history[-4:]:
                messages.append(msg)

    user_content = f"Question: {text}\n\nContext:\n{context}"
    if decision == "clarify":
        user_content += _CLARIFY_HINT
        state.clarifications_asked += 1

    messages.append({"role": "user", "content": user_content})

    from app.model_manager import get_model_manager
    model_manager = get_model_manager()
    use_hf = model_manager.get_current_model() != OLLAMA_MODEL

    # Try HF first, fall back to Ollama
    answer = None
    if use_hf:
        try:
            answer = _hf_chat(messages)
        except Exception as e:
            print(f"[Controller] HF chat failed: {e}, falling back to Ollama")
            answer = None

    if not answer:
        try:
            answer = _ollama_chat(messages)
        except Exception as e:
            answer = f"I'm having trouble reaching both HF and local inference. Error: {str(e)[:50]}"

    response = answer.strip() if answer else "Sorry, I couldn't generate a response. Try again?"
    state.add_turn("assistant", response)
    return {"response": response, "intent": intent, "sources": docs}
