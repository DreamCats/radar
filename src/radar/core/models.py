from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

MessageSource = Literal["个人消息", "个人群"]


class RawMessage(BaseModel):
    """标准化后的微信消息，是 core 内部和 SQLite 的基础数据单元。"""

    message_id: str
    source: MessageSource
    sender: str
    message_time: datetime
    raw_content: str
    fetch_time: datetime
    fetch_window: str
    group_name: str | None = None


class WechatApiMessage(BaseModel):
    """微信 API 原始字段是中文，单独建模便于隔离外部格式变化。"""

    sender: str = Field(alias="发送人")
    time: str = Field(alias="时间")
    content: str = Field(alias="内容")
    group_name: str | None = Field(default=None, alias="群名称")
