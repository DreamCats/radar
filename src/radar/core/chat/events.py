from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field

ChatRole = Literal["system", "user", "assistant", "tool"]
ChatEventType = Literal[
    "session_created",
    "message_appended",
    "turn_started",
    "turn_completed",
    "turn_failed",
    "tool_execution_started",
    "tool_execution_completed",
]


def now_iso() -> str:
    return datetime.now().isoformat()


def new_id() -> str:
    return uuid4().hex


class ChatSession(BaseModel):
    session_id: str
    created_at: str
    title: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ChatMessage(BaseModel):
    message_id: str
    role: ChatRole
    content: str
    created_at: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class ChatEvent(BaseModel):
    event_id: str
    session_id: str
    type: ChatEventType
    created_at: str
    payload: dict[str, Any] = Field(default_factory=dict)
