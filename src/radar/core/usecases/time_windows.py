from __future__ import annotations

from datetime import datetime, timedelta


def time_chunks(
    start_time: datetime,
    end_time: datetime,
    step: timedelta,
) -> list[tuple[datetime, datetime]]:
    """生成左闭右开时间切片，供拉取和离线任务编排复用。"""

    chunks: list[tuple[datetime, datetime]] = []
    current = start_time
    while current < end_time:
        next_time = min(current + step, end_time)
        chunks.append((current, next_time))
        current = next_time
    return chunks
