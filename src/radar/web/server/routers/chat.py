from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from radar.core.chat import ChatAgent
from radar.core.config import RadarConfig
from radar.web.server.deps import get_config
from radar.web.server.schemas import ChatMessageResponse, ChatTurnRequest, ChatTurnResponse

router = APIRouter(prefix="/api", tags=["chat"])


@router.post("/chat/turn", response_model=ChatTurnResponse)
def chat_turn(
    request: ChatTurnRequest,
    config: RadarConfig = Depends(get_config),
) -> ChatTurnResponse:
    agent = ChatAgent(config)
    try:
        session_id = request.session_id
        if not session_id:
            session = agent.create_session(title=request.title, metadata=request.metadata)
            session_id = session.session_id
        result = agent.run_turn(session_id, _content_with_context(request.content, request.context))
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error)[:1000]) from error

    return ChatTurnResponse(
        session_id=result.session_id,
        user_message=ChatMessageResponse(**result.user_message.model_dump()),
        assistant_message=ChatMessageResponse(**result.assistant_message.model_dump()),
        tool_messages=[ChatMessageResponse(**message.model_dump()) for message in result.tool_messages],
    )


def _content_with_context(content: str, context: dict[str, Any]) -> str:
    if not context:
        return content
    return (
        f"{content.strip()}\n\n"
        "页面上下文：\n"
        f"{json.dumps(context, ensure_ascii=False, separators=(',', ':'))}"
    )
