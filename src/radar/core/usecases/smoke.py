from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Any

from radar.core.config import RadarConfig
from radar.core.llm import LlmConfigError, chat, resolve_provider as resolve_llm_provider
from radar.core.tushare import call as call_tushare


@dataclass(frozen=True)
class SmokeResult:
    capability: str
    target: str
    detail: str
    sample: str | None = None
    row_count: int | None = None


def test_llm(
    config: RadarConfig,
    *,
    provider_name: str | None = None,
    task: str | None = None,
    model: str | None = None,
) -> SmokeResult:
    """用一次短请求验证 LLM provider 配置、鉴权和协议是否可用。"""

    selected_name, provider = resolve_llm_provider(config, provider_name=provider_name, task=task)
    content = chat(
        config,
        [{"role": "user", "content": "请只回复 ok。"}],
        provider_name=provider_name,
        task=task,
        model=model,
        temperature=0,
        max_tokens=16,
    ).strip()
    if not content:
        raise LlmConfigError("LLM 请求成功但返回文本为空，请检查 provider 协议配置")
    target = f"{selected_name}/{provider.protocol}/{model or provider.model}"
    return SmokeResult(
        capability="llm",
        target=target,
        detail="request ok",
        sample=_clip(content, 160),
    )


def test_market(
    config: RadarConfig,
    *,
    date_text: str | None = None,
    use_cache: bool = True,
) -> SmokeResult:
    """用交易日历接口验证 Tushare 配置、代理、鉴权和市场库缓存是否可用。"""

    cal_date = date_text or dt.date.today().strftime("%Y%m%d")
    rows = call_tushare(
        config,
        "trade_cal",
        params={"exchange": "SSE", "start_date": cal_date, "end_date": cal_date},
        fields=["exchange", "cal_date", "is_open", "pretrade_date"],
        cache_ttl=3600,
        use_cache=use_cache,
    )
    sample = rows[0] if rows else {}
    return SmokeResult(
        capability="market",
        target=f"tushare/trade_cal/{cal_date}",
        detail="request ok",
        sample=_format_sample(sample),
        row_count=len(rows),
    )


def _format_sample(value: dict[str, Any]) -> str:
    return ", ".join(f"{key}={item}" for key, item in value.items()) if value else None


def _clip(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return value[: limit - 1] + "..."
