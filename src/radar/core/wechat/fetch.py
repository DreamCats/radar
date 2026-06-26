from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Iterable

import httpx

from radar.core.models import MessageSource, RawMessage, WechatApiMessage

WECHAT_TIME_FORMAT = "%Y-%m-%d %H:%M:%S"
WINDOW_TIME_FORMAT = "%Y%m%d%H%M%S"


def fetch_messages(
    base_url: str,
    *,
    source: MessageSource,
    start_time: datetime,
    end_time: datetime,
    timeout: float = 20.0,
) -> list[RawMessage]:
    """拉取一个时间窗的微信消息，并立即标准化为 core 模型。"""

    response = httpx.get(
        base_url,
        params={
            "name": source,
            "starttime": start_time.strftime(WINDOW_TIME_FORMAT),
            "endtime": end_time.strftime(WINDOW_TIME_FORMAT),
        },
        timeout=timeout,
    )
    response.raise_for_status()
    return normalize_messages(response.json(), source=source, start_time=start_time, end_time=end_time)


def normalize_messages(
    rows: Iterable[dict],
    *,
    source: MessageSource,
    start_time: datetime,
    end_time: datetime,
) -> list[RawMessage]:
    """把中文原始字段收敛到 RawMessage，后续层不再接触外部字段名。"""

    fetch_time = datetime.now()
    fetch_window = f"{start_time.strftime(WINDOW_TIME_FORMAT)}-{end_time.strftime(WINDOW_TIME_FORMAT)}"
    messages: list[RawMessage] = []
    for row in rows:
        item = WechatApiMessage.model_validate(row)
        message_time = datetime.strptime(item.time, WECHAT_TIME_FORMAT)
        messages.append(
            RawMessage(
                message_id=_message_id(source, item, message_time),
                source=source,
                sender=item.sender,
                message_time=message_time,
                raw_content=item.content,
                group_name=item.group_name,
                fetch_time=fetch_time,
                fetch_window=fetch_window,
            )
        )
    return messages


def _message_id(source: MessageSource, item: WechatApiMessage, message_time: datetime) -> str:
    """API 没有稳定 ID 时，用关键字段生成去重 ID。"""

    raw = "\n".join(
        [
            source,
            message_time.isoformat(),
            item.sender,
            item.group_name or "",
            item.content,
        ]
    )
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]
