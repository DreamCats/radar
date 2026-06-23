from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

TickStatus = Literal["planned", "running", "submitted", "skipped", "failed"]


class ScheduleRecord(BaseModel):
    schedule_id: str
    job_key: str
    title: str
    enabled: bool
    timezone: str
    cadence_kind: str
    cadence: dict[str, Any] = Field(default_factory=dict)
    window_preset: str | None = None
    request: dict[str, Any] = Field(default_factory=dict)
    catch_up_policy: str
    max_lag_minutes: int
    last_tick_at: datetime | None = None
    next_tick_at: datetime | None = None
    sort_order: int = 0
    created_at: datetime
    updated_at: datetime


class ScheduleTickRecord(BaseModel):
    tick_id: str
    schedule_id: str
    planned_at: datetime
    fired_at: datetime | None = None
    status: TickStatus
    run_ids: list[str] = Field(default_factory=list)
    request: dict[str, Any] = Field(default_factory=dict)
    skipped_reason: str | None = None
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime
