from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Dict


@dataclass
class ConversationState:
    session_id: str
    history: List[Dict[str, str]] = field(default_factory=list)
    issue_summary: str | None = None
    environment: str | None = None
    attempted_steps: List[str] = field(default_factory=list)

    def add_turn(self, role: str, content: str) -> None:
        self.history.append({"role": role, "content": content})

    def update_from_user(self, text: str) -> None:
        if self.issue_summary is None:
            self.issue_summary = text
        else:
            self.issue_summary = self.issue_summary + " " + text
