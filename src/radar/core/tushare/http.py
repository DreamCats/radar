from __future__ import annotations

from typing import Any

import httpx

from radar.core.tushare.exceptions import TushareApiError, TushareHttpError
from radar.core.tushare.models import RuntimeTushareProvider


def post_tushare(
    provider: RuntimeTushareProvider,
    api_name: str,
    params: dict[str, Any],
    fields: str | list[str] | None = None,
) -> list[dict[str, Any]]:
    """调用 Tushare Pro HTTP API，返回行字典。"""

    payload: dict[str, Any] = {
        "api_name": api_name,
        "token": provider.token,
        "params": {key: value for key, value in params.items() if value is not None},
    }
    if fields:
        payload["fields"] = ",".join(fields) if isinstance(fields, list) else fields

    try:
        with httpx.Client(timeout=provider.timeout) as client:
            response = client.post(provider.api_url, json=payload)
            response.raise_for_status()
    except httpx.TimeoutException as exc:
        raise TushareHttpError(
            f"调用 Tushare {api_name} 超时: url={_safe_url(provider.api_url)} "
            f"timeout={provider.timeout}s，请检查 market.api_url 或代理服务"
        ) from exc
    except httpx.HTTPError as exc:
        raise TushareHttpError(
            f"调用 Tushare {api_name} 失败: url={_safe_url(provider.api_url)} error={exc}"
        ) from exc

    body = response.json()
    if body.get("code") != 0:
        raise TushareApiError(f"{api_name}: {body.get('msg')}")

    data = body.get("data") or {}
    columns: list[str] = data.get("fields") or []
    items: list[list[Any]] = data.get("items") or []
    return [dict(zip(columns, item, strict=False)) for item in items]


def _safe_url(url: str) -> str:
    return url.split("?", 1)[0]
