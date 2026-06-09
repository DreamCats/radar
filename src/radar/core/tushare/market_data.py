from __future__ import annotations

from typing import Any

from radar.core.config import RadarConfig
from radar.core.tushare.client import call


STOCK_MONEYFLOW_APIS = {
    "tushare": "moneyflow",
    "dc": "moneyflow_dc",
    "ths": "moneyflow_ths",
}

SECTOR_MONEYFLOW_APIS = {
    "dc": "moneyflow_ind_dc",
    "ths": "moneyflow_ind_ths",
}

LIMIT_POOL_APIS = {"limit_list_d", "limit_step", "limit_strongest"}
BILLBOARD_APIS = {"top_list", "top_inst"}


def get_stock_moneyflow(
    config: RadarConfig,
    *,
    ts_code: str,
    source: str = "dc",
    start_date: str | None = None,
    end_date: str | None = None,
    trade_date: str | None = None,
    use_cache: bool = True,
) -> list[dict[str, Any]]:
    api_name = _api_from_source(STOCK_MONEYFLOW_APIS, source)
    return call(
        config,
        api_name,
        _stock_date_params(ts_code, start_date=start_date, end_date=end_date, trade_date=trade_date),
        use_cache=use_cache,
    )


def get_stock_factor(
    config: RadarConfig,
    *,
    ts_code: str,
    start_date: str | None = None,
    end_date: str | None = None,
    trade_date: str | None = None,
    use_cache: bool = True,
) -> list[dict[str, Any]]:
    return call(
        config,
        "stk_factor",
        _stock_date_params(ts_code, start_date=start_date, end_date=end_date, trade_date=trade_date),
        use_cache=use_cache,
    )


def get_stock_limit(
    config: RadarConfig,
    *,
    ts_code: str,
    start_date: str | None = None,
    end_date: str | None = None,
    trade_date: str | None = None,
    use_cache: bool = True,
) -> list[dict[str, Any]]:
    return call(
        config,
        "stk_limit",
        _stock_date_params(ts_code, start_date=start_date, end_date=end_date, trade_date=trade_date),
        use_cache=use_cache,
    )


def get_sector_moneyflow(
    config: RadarConfig,
    *,
    source: str = "dc",
    trade_date: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    use_cache: bool = True,
) -> list[dict[str, Any]]:
    api_name = _api_from_source(SECTOR_MONEYFLOW_APIS, source)
    return call(config, api_name, _date_params(start_date=start_date, end_date=end_date, trade_date=trade_date), use_cache=use_cache)


def get_limit_pool(
    config: RadarConfig,
    *,
    api_name: str = "limit_list_d",
    trade_date: str | None = None,
    limit_type: str | None = None,
    use_cache: bool = True,
) -> list[dict[str, Any]]:
    if api_name not in LIMIT_POOL_APIS:
        raise ValueError(f"不支持的涨停池接口: {api_name}")
    params = _date_params(trade_date=trade_date)
    if limit_type:
        params["limit_type"] = limit_type
    return call(config, api_name, params, use_cache=use_cache)


def get_billboard_trading(
    config: RadarConfig,
    *,
    api_name: str = "top_list",
    trade_date: str | None = None,
    ts_code: str | None = None,
    use_cache: bool = True,
) -> list[dict[str, Any]]:
    if api_name not in BILLBOARD_APIS:
        raise ValueError(f"不支持的龙虎榜接口: {api_name}")
    params = _date_params(trade_date=trade_date)
    if ts_code:
        params["ts_code"] = ts_code
    return call(config, api_name, params, use_cache=use_cache)


def _api_from_source(allowed: dict[str, str], source: str) -> str:
    try:
        return allowed[source]
    except KeyError as exc:
        raise ValueError(f"不支持的数据源: {source}") from exc


def _stock_date_params(
    ts_code: str,
    *,
    start_date: str | None = None,
    end_date: str | None = None,
    trade_date: str | None = None,
) -> dict[str, Any]:
    params = _date_params(start_date=start_date, end_date=end_date, trade_date=trade_date)
    params["ts_code"] = ts_code.strip().upper()
    return params


def _date_params(
    *,
    start_date: str | None = None,
    end_date: str | None = None,
    trade_date: str | None = None,
) -> dict[str, Any]:
    if trade_date:
        return {"trade_date": trade_date}
    params: dict[str, Any] = {}
    if start_date:
        params["start_date"] = start_date
    if end_date:
        params["end_date"] = end_date
    return params
