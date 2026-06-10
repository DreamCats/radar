from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class RuntimeBraveSearchProvider(BaseModel):
    api_key: str
    base_url: str
    timeout: float


class BraveSearchContextItem(BaseModel):
    url: str
    title: str | None = None
    snippets: list[str] = Field(default_factory=list)


class BraveSearchContextResult(BaseModel):
    query: str
    items: list[BraveSearchContextItem] = Field(default_factory=list)
    raw: dict[str, Any] = Field(default_factory=dict)
