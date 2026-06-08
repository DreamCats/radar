from __future__ import annotations

from typing import Any

from radar.core.config import RadarConfig
from radar.core.tushare import cache, history
from radar.core.tushare.exceptions import TushareConfigError
from radar.core.tushare.http import post_tushare
from radar.core.tushare.models import HistorySpec, RuntimeTushareProvider


def resolve_provider(config: RadarConfig) -> RuntimeTushareProvider:
    """把 radar 配置解析成 Tushare 运行期 provider。"""

    if config.market.provider != "tushare":
        raise TushareConfigError("market.provider 未配置为 tushare")
    if not config.market.secret_ref:
        raise TushareConfigError("market.secret_ref 未配置")

    secret = config.secrets.market.get(config.market.secret_ref)
    if secret is None or not secret.token:
        raise TushareConfigError(f"未配置 Tushare token: {config.market.secret_ref}")

    return RuntimeTushareProvider(
        api_url=config.market.api_url,
        token=secret.token,
        timeout=config.market.timeout,
        request_delay_ms=config.market.request_delay_ms,
        database=config.market_database_path,
    )


def call(
    config: RadarConfig,
    api_name: str,
    params: dict[str, Any] | None = None,
    fields: str | list[str] | None = None,
    *,
    cache_ttl: int | None = None,
    use_cache: bool = True,
) -> list[dict[str, Any]]:
    """调用 Tushare；历史型接口走行缓存，其余接口走短期 KV 缓存。"""

    provider = resolve_provider(config)
    clean_params = {key: value for key, value in (params or {}).items() if value is not None}
    spec = history.spec_for(api_name)
    if use_cache and spec is not None and fields is None:
        return _call_history(provider, spec, clean_params, fields)
    return _call_kv(provider, api_name, clean_params, fields, cache_ttl, use_cache=use_cache)


def _call_kv(
    provider: RuntimeTushareProvider,
    api_name: str,
    params: dict[str, Any],
    fields: str | list[str] | None,
    cache_ttl: int | None,
    *,
    use_cache: bool,
) -> list[dict[str, Any]]:
    ttl = cache.ttl_for(api_name) if cache_ttl is None else cache_ttl
    if use_cache:
        cached = cache.get(provider.database, api_name, params, fields=fields, ttl=ttl)
        if cached is not None:
            return cached

    rows = post_tushare(provider, api_name, params, fields)
    if use_cache:
        cache.put(provider.database, api_name, params, rows, fields=fields)
    return rows


def _call_history(
    provider: RuntimeTushareProvider,
    spec: HistorySpec,
    params: dict[str, Any],
    fields: str | list[str] | None,
) -> list[dict[str, Any]]:
    start = params.get(spec.req_start_param)
    end = params.get(spec.req_end_param)
    ts_code = params.get(spec.req_ts_code_param) if spec.req_ts_code_param else None

    # 点查不适合行缓存区间补全，退回 KV，保持调用语义简单。
    if not start and not end and not _is_pure_range_query(params):
        return _call_kv(provider, spec.api_name, params, fields, None, use_cache=True)

    for seg_start, seg_end in history.missing_segments(provider.database, spec, ts_code, start, end):
        seg_params = _segment_params(spec, params, seg_start, seg_end)
        rows = post_tushare(provider, spec.api_name, seg_params, fields)
        history.put_rows(provider.database, spec, rows, ts_code_override=ts_code)

    historical = history.query(provider.database, spec, ts_code, start, end)
    today_rows = _today_rows(provider, spec, params, start, end, fields)
    return today_rows + historical


def _today_rows(
    provider: RuntimeTushareProvider,
    spec: HistorySpec,
    params: dict[str, Any],
    start: str | None,
    end: str | None,
    fields: str | list[str] | None,
) -> list[dict[str, Any]]:
    today = history.today_key(spec.date_kind)
    if today <= history.cacheable_end_key(spec.date_kind):
        return []
    if end is not None and end < today:
        return []
    if start is not None and start > today:
        return []
    return post_tushare(provider, spec.api_name, _segment_params(spec, params, today, today), fields)


def _segment_params(
    spec: HistorySpec,
    base: dict[str, Any],
    start: str | None,
    end: str | None,
) -> dict[str, Any]:
    params = dict(base)
    if start is not None:
        params[spec.req_start_param] = start
    if end is not None:
        params[spec.req_end_param] = end
    return params


def _is_pure_range_query(params: dict[str, Any]) -> bool:
    return not ({"trade_date", "ann_date", "period", "date"} & params.keys())
