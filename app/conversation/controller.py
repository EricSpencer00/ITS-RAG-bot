from __future__ import annotations

import json
from typing import Dict, List

import requests

from app.config import OLLAMA_BASE_URL, OLLAMA_MODEL
from app.conversation.state import ConversationState
from app.rag.prompt import SYSTEM_PROMPT
from app.rag.retriever import Retriever


INTENT_TICKET = "ticket_draft"
INTENT_TROUBLESHOOT = "troubleshoot"
INTENT_UNKNOWN = "unknown"


def detect_intent(text: str) -> str:
    lowered = text.lower()
    if any(k in lowered for k in ["ticket", "help request", "support request", "case", "submit"]):
        return INTENT_TICKET
    if any(k in lowered for k in ["how do i", "fix", "error", "issue", "problem", "trouble", "vpn", "wifi", "email", "mfa"]):
        return INTENT_TROUBLESHOOT
    return INTENT_TROUBLESHOOT


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
        parts.append(f"Source {idx}: {doc['source']}\n{doc['content']}")
    return "\n\n".join(parts)


def _ollama_chat(messages: List[Dict[str, str]]) -> str:
    payload = {
        "model": OLLAMA_MODEL,
        "messages": messages,
        "stream": False,
        "options": {"temperature": 0.2},
    }
    resp = requests.post(f"{OLLAMA_BASE_URL}/api/chat", json=payload, timeout=120)
    resp.raise_for_status()
    data = resp.json()
    return data.get("message", {}).get("content", "")


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

    docs = retriever.query(text)
    if not docs:
        fallback = "I don't have a public source for that yet. Please contact the ITS Service Desk or provide more details."
        state.add_turn("assistant", fallback)
        return {"response": fallback, "intent": INTENT_UNKNOWN, "sources": []}

    context = _format_context(docs)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"Question: {text}\n\nContext:\n{context}"},
    ]
    answer = _ollama_chat(messages)
    response = answer.strip()
    state.add_turn("assistant", response)
    return {"response": response, "intent": intent, "sources": docs}
