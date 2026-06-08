from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from radar.core.config import RadarConfig
from radar.core.chat.events import ChatEvent, ChatMessage, ChatSession, new_id, now_iso


class ChatSessionStore:
    """Append-only file store for local chat sessions.

    每个 session 一个目录，消息和运行事件统一追加到 events.jsonl。
    这样保持可审计、易复制，也避免把个人对话写进 SQLite 主库。
    """

    def __init__(self, root: Path):
        self.root = root.expanduser()

    @classmethod
    def from_config(cls, config: RadarConfig) -> "ChatSessionStore":
        return cls(config.data_dir / "chat")

    def create_session(
        self,
        *,
        title: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ChatSession:
        session = ChatSession(
            session_id=new_id(),
            created_at=now_iso(),
            title=title,
            metadata=metadata or {},
        )
        session_dir = self.session_dir(session.session_id)
        session_dir.mkdir(parents=True, exist_ok=False)
        (session_dir / "session.json").write_text(
            session.model_dump_json(indent=2),
            encoding="utf-8",
        )
        self.append_event(
            ChatEvent(
                event_id=new_id(),
                session_id=session.session_id,
                type="session_created",
                created_at=session.created_at,
                payload={"session": session.model_dump()},
            )
        )
        return session

    def get_session(self, session_id: str) -> ChatSession:
        path = self.session_dir(session_id) / "session.json"
        if not path.exists():
            raise FileNotFoundError(f"chat session 不存在: {session_id}")
        return ChatSession.model_validate_json(path.read_text(encoding="utf-8"))

    def list_sessions(self) -> list[ChatSession]:
        sessions_dir = self.root / "sessions"
        if not sessions_dir.exists():
            return []
        sessions: list[ChatSession] = []
        for path in sorted(sessions_dir.iterdir(), reverse=True):
            session_file = path / "session.json"
            if session_file.exists():
                sessions.append(ChatSession.model_validate_json(session_file.read_text(encoding="utf-8")))
        return sorted(sessions, key=lambda session: session.created_at, reverse=True)

    def append_message(self, session_id: str, message: ChatMessage) -> ChatEvent:
        self.get_session(session_id)
        event = ChatEvent(
            event_id=new_id(),
            session_id=session_id,
            type="message_appended",
            created_at=message.created_at,
            payload={"message": message.model_dump()},
        )
        self.append_event(event)
        return event

    def append_event(self, event: ChatEvent) -> None:
        self.get_session(event.session_id)
        session_dir = self.session_dir(event.session_id)
        with (session_dir / "events.jsonl").open("a", encoding="utf-8") as file:
            file.write(json.dumps(event.model_dump(), ensure_ascii=False, separators=(",", ":")))
            file.write("\n")

    def load_events(self, session_id: str) -> list[ChatEvent]:
        self.get_session(session_id)
        path = self.session_dir(session_id) / "events.jsonl"
        if not path.exists():
            return []
        events: list[ChatEvent] = []
        with path.open(encoding="utf-8") as file:
            for line in file:
                if line.strip():
                    events.append(ChatEvent.model_validate_json(line))
        return events

    def load_messages(self, session_id: str) -> list[ChatMessage]:
        messages: list[ChatMessage] = []
        for event in self.load_events(session_id):
            if event.type != "message_appended":
                continue
            raw = event.payload.get("message")
            if isinstance(raw, dict):
                messages.append(ChatMessage.model_validate(raw))
        return messages

    def session_dir(self, session_id: str) -> Path:
        if "/" in session_id or "\\" in session_id:
            raise ValueError("session_id 不能包含路径分隔符")
        return self.root / "sessions" / session_id
