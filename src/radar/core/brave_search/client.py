from __future__ import annotations

from typing import Any

import httpx

from radar.core.brave_search.exceptions import (
    BraveSearchApiError,
    BraveSearchConfigError,
    BraveSearchHttpError,
)
from radar.core.brave_search.models import (
    BraveSearchContextItem,
    BraveSearchContextResult,
    RuntimeBraveSearchProvider,
)
from radar.core.config import RadarConfig

CONTEXT_ENDPOINT = "/res/v1/llm/context"
THRESHOLD_MODES = {"strict", "balanced", "lenient"}


def resolve_provider(config: RadarConfig) -> RuntimeBraveSearchProvider:
    """把 radar 配置解析成 Brave Search 运行期 provider。"""

    if config.brave_search.provider != "brave":
        raise BraveSearchConfigError("brave_search.provider 未配置为 brave")
    if not config.brave_search.secret_ref:
        raise BraveSearchConfigError("brave_search.secret_ref 未配置")

    secret = config.secrets.brave_search.get(config.brave_search.secret_ref)
    if secret is None or not secret.api_key:
        raise BraveSearchConfigError(
            f"未配置 Brave Search API key: {config.brave_search.secret_ref}"
        )

    return RuntimeBraveSearchProvider(
        api_key=secret.api_key,
        base_url=config.brave_search.base_url.rstrip("/"),
        timeout=config.brave_search.timeout,
    )


def search_context(
    config: RadarConfig,
    query: str,
    *,
    count: int | None = None,
    max_tokens: int | None = 4096,
    max_tokens_per_url: int | None = None,
    threshold: str | None = None,
    include_sites: list[str] | None = None,
    exclude_sites: list[str] | None = None,
) -> BraveSearchContextResult:
    """调用 Brave LLM context 接口，返回适合喂给 LLM 的来源片段。"""

    q = query.strip()
    if not q:
        raise ValueError("query 不能为空")
    provider = resolve_provider(config)
    body = _context_body(
        q,
        count=count,
        max_tokens=max_tokens,
        max_tokens_per_url=max_tokens_per_url,
        threshold=threshold,
        include_sites=include_sites,
        exclude_sites=exclude_sites,
    )
    raw = _post_json(provider, CONTEXT_ENDPOINT, body)
    return BraveSearchContextResult(query=q, items=_context_items(raw), raw=raw)


def _context_body(
    query: str,
    *,
    count: int | None,
    max_tokens: int | None,
    max_tokens_per_url: int | None,
    threshold: str | None,
    include_sites: list[str] | None,
    exclude_sites: list[str] | None,
) -> dict[str, Any]:
    body: dict[str, Any] = {"q": query}
    if count is not None:
        body["count"] = _positive_int(count, "count")
    if max_tokens is not None:
        body["maximum_number_of_tokens"] = _minimum_int(
            max_tokens,
            "max_tokens",
            minimum=1024,
        )
    if max_tokens_per_url is not None:
        body["maximum_number_of_tokens_per_url"] = _positive_int(
            max_tokens_per_url,
            "max_tokens_per_url",
        )
    if threshold is not None:
        if threshold not in THRESHOLD_MODES:
            raise ValueError("threshold 必须是 strict、balanced 或 lenient")
        body["context_threshold_mode"] = threshold
    goggles = _site_goggles(include_sites or [], exclude_sites or [])
    if goggles:
        body["goggles"] = goggles
    return body


def _post_json(
    provider: RuntimeBraveSearchProvider,
    path: str,
    body: dict[str, Any],
) -> dict[str, Any]:
    url = f"{provider.base_url}{path}"
    try:
        with httpx.Client(timeout=provider.timeout) as client:
            response = client.post(
                url,
                json=body,
                headers={
                    "X-Subscription-Token": provider.api_key,
                    "Content-Type": "application/json",
                },
            )
            response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise BraveSearchApiError(
            f"Brave Search API 返回错误: status={exc.response.status_code} url={_safe_url(url)}"
        ) from exc
    except httpx.TimeoutException as exc:
        raise BraveSearchHttpError(
            f"调用 Brave Search 超时: url={_safe_url(url)} timeout={provider.timeout}s"
        ) from exc
    except httpx.HTTPError as exc:
        raise BraveSearchHttpError(
            f"调用 Brave Search 失败: url={_safe_url(url)} error={exc}"
        ) from exc

    data = response.json()
    if not isinstance(data, dict):
        raise BraveSearchApiError("Brave Search 返回不是 JSON object")
    return data


def _context_items(raw: dict[str, Any]) -> list[BraveSearchContextItem]:
    grounding = raw.get("grounding")
    if not isinstance(grounding, dict):
        return []
    generic = grounding.get("generic")
    if not isinstance(generic, list):
        return []
    items: list[BraveSearchContextItem] = []
    for row in generic:
        if not isinstance(row, dict):
            continue
        url = row.get("url")
        if not isinstance(url, str) or not url:
            continue
        title = row.get("title") if isinstance(row.get("title"), str) else None
        snippets = [item for item in row.get("snippets", []) if isinstance(item, str)]
        items.append(BraveSearchContextItem(url=url, title=title, snippets=snippets))
    return items


def _site_goggles(include_sites: list[str], exclude_sites: list[str]) -> str | None:
    if include_sites and exclude_sites:
        raise ValueError("include_sites 和 exclude_sites 不能同时使用")
    if include_sites:
        rules = ["$discard"]
        rules.extend(f"$boost,site={_domain(site)}" for site in include_sites)
        return "\n".join(rules)
    if exclude_sites:
        return "\n".join(f"$discard,site={_domain(site)}" for site in exclude_sites)
    return None


def _domain(value: str) -> str:
    domain = value.strip()
    if domain and all(
        char.isascii() and (char.isalnum() or char in ".-_")
        for char in domain
    ):
        return domain
    raise ValueError(f"非法域名: {value}")


def _positive_int(value: int, name: str) -> int:
    return _minimum_int(value, name, minimum=1)


def _minimum_int(value: int, name: str, *, minimum: int) -> int:
    parsed = int(value)
    if parsed < minimum:
        raise ValueError(f"{name} 必须大于等于 {minimum}")
    return parsed


def _safe_url(url: str) -> str:
    return url.split("?", 1)[0]
