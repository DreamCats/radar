from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest
import httpx

from radar.core.config import RadarConfig, RadarSecrets
from radar.core.tushare import cache, history
from radar.core.tushare.client import call, resolve_provider
from radar.core.tushare.exceptions import TushareApiError, TushareConfigError, TushareHttpError
from radar.core.tushare.http import post_tushare
from radar.core.tushare.models import RuntimeTushareProvider
from radar.core.tushare.market_data import (
    get_billboard_trading,
    get_limit_pool,
    get_sector_moneyflow,
    get_stock_factor,
    get_stock_limit,
    get_stock_moneyflow,
)
from radar.core.tushare.realtime import get_realtime_daily_quote
from radar.core.tushare.resolver import resolve_stock


def test_resolve_provider_uses_market_secret(tmp_path: Path):
    provider = resolve_provider(_config(tmp_path))

    assert provider.api_url == "https://example.invalid/tushare"
    assert provider.token == "secret-token"
    assert provider.request_delay_ms == 150
    assert provider.database == tmp_path / "market.sqlite3"


def test_resolve_provider_requires_tushare_market(tmp_path: Path):
    with pytest.raises(TushareConfigError, match="provider"):
        resolve_provider(RadarConfig())


def test_http_post_flattens_tushare_rows(monkeypatch, tmp_path: Path):
    captured = {}

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "code": 0,
                "data": {
                    "fields": ["ts_code", "close"],
                    "items": [["600519.SH", 100.5]],
                },
            }

    class FakeClient:
        def __init__(self, timeout):
            captured["timeout"] = timeout

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def post(self, url, json):
            captured.update({"url": url, "json": json})
            return FakeResponse()

    monkeypatch.setattr("radar.core.tushare.http.httpx.Client", FakeClient)

    rows = post_tushare(
        _provider(tmp_path),
        "daily",
        {"ts_code": "600519.SH", "empty": None},
        ["ts_code", "close"],
    )

    assert rows == [{"ts_code": "600519.SH", "close": 100.5}]
    assert captured["url"] == "https://example.invalid/tushare"
    assert captured["json"]["fields"] == "ts_code,close"
    assert captured["json"]["params"] == {"ts_code": "600519.SH"}


def test_http_post_raises_api_error(monkeypatch, tmp_path: Path):
    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"code": 40001, "msg": "token 无效"}

    class FakeClient:
        def __init__(self, timeout):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def post(self, url, json):
            return FakeResponse()

    monkeypatch.setattr("radar.core.tushare.http.httpx.Client", FakeClient)

    with pytest.raises(TushareApiError, match="token 无效"):
        post_tushare(_provider(tmp_path), "stock_basic", {})


def test_http_post_timeout_message_includes_target(monkeypatch, tmp_path: Path):
    class FakeClient:
        def __init__(self, timeout):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def post(self, url, json):
            raise httpx.ConnectTimeout("timed out")

    monkeypatch.setattr("radar.core.tushare.http.httpx.Client", FakeClient)

    with pytest.raises(TushareHttpError, match="market.api_url"):
        post_tushare(_provider(tmp_path), "trade_cal", {})


def test_http_post_applies_request_delay(monkeypatch, tmp_path: Path):
    slept = []

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"code": 0, "data": {"fields": [], "items": []}}

    class FakeClient:
        def __init__(self, timeout):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def post(self, url, json):
            return FakeResponse()

    monkeypatch.setattr("radar.core.tushare.http.httpx.Client", FakeClient)
    monkeypatch.setattr("radar.core.tushare.http.time.sleep", lambda seconds: slept.append(seconds))

    post_tushare(_provider(tmp_path, request_delay_ms=150), "daily", {})

    assert slept == [0.15]


def test_kv_cache_key_includes_param_order_and_fields(tmp_path: Path):
    db = tmp_path / "radar.sqlite3"
    rows = [{"ts_code": "600519.SH"}]

    cache.put(db, "stock_basic", {"b": 2, "a": 1}, rows, fields="ts_code")

    assert cache.get(db, "stock_basic", {"a": 1, "b": 2}, fields="ts_code") == rows
    assert cache.get(db, "stock_basic", {"a": 1, "b": 2}, fields="name") is None
    assert cache.get(db, "stock_basic", {"a": 1, "b": 2}, fields="ts_code", ttl=0) is None


def test_realtime_daily_quote_uses_short_cache_ttl():
    assert cache.ttl_for("rt_k") == 60


def test_high_value_stock_apis_are_history_specs():
    for api_name in ("moneyflow", "moneyflow_dc", "moneyflow_ths", "stk_factor", "stk_limit"):
        spec = history.SPECS[api_name]
        assert spec.date_field == "trade_date"
        assert spec.ts_code_field == "ts_code"


def test_sector_moneyflow_uses_short_kv_ttl():
    assert cache.ttl_for("moneyflow_ind_dc") == 3600
    assert cache.ttl_for("moneyflow_ind_ths") == 3600


def test_history_skips_today_before_close_and_queries_desc(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("radar.core.tushare.history._today_date", lambda: dt.date(2026, 6, 4))
    monkeypatch.setattr("radar.core.tushare.history._now_time", lambda: dt.time(14, 59))
    spec = history.SPECS["daily"]

    stored = history.put_rows(
        tmp_path / "radar.sqlite3",
        spec,
        [
            {"ts_code": "600519.SH", "trade_date": "20260603", "close": 2},
            {"ts_code": "600519.SH", "trade_date": "20260604", "close": 3},
            {"ts_code": "600519.SH", "trade_date": "20260602", "close": 1},
        ],
    )

    rows = history.query(tmp_path / "radar.sqlite3", spec, "600519.SH", "20260602", "20260604")
    assert stored == 2
    assert [row["trade_date"] for row in rows] == ["20260603", "20260602"]


def test_history_stores_today_after_close(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("radar.core.tushare.history._today_date", lambda: dt.date(2026, 6, 4))
    monkeypatch.setattr("radar.core.tushare.history._now_time", lambda: dt.time(15, 31))
    spec = history.SPECS["daily"]

    stored = history.put_rows(
        tmp_path / "radar.sqlite3",
        spec,
        [
            {"ts_code": "600519.SH", "trade_date": "20260604", "close": 3},
            {"ts_code": "600519.SH", "trade_date": "20260605", "close": 4},
        ],
    )

    rows = history.query(tmp_path / "radar.sqlite3", spec, "600519.SH", "20260604", "20260605")
    assert stored == 1
    assert [row["trade_date"] for row in rows] == ["20260604"]


def test_history_missing_segments_clamps_today_before_close(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("radar.core.tushare.history._today_date", lambda: dt.date(2026, 6, 4))
    monkeypatch.setattr("radar.core.tushare.history._now_time", lambda: dt.time(14, 59))

    assert history.missing_segments(
        tmp_path / "radar.sqlite3",
        history.SPECS["daily"],
        "600519.SH",
        "20260604",
        "20260604",
    ) == []


def test_history_missing_segments_allows_today_after_close(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("radar.core.tushare.history._today_date", lambda: dt.date(2026, 6, 4))
    monkeypatch.setattr("radar.core.tushare.history._now_time", lambda: dt.time(15, 31))

    assert history.missing_segments(
        tmp_path / "radar.sqlite3",
        history.SPECS["daily"],
        "600519.SH",
        "20260604",
        "20260604",
    ) == [("20260604", "20260604")]


def test_call_uses_kv_cache_for_static_api(monkeypatch, tmp_path: Path):
    config = _config(tmp_path)
    calls = []

    def fake_post(provider, api_name, params, fields):
        calls.append((api_name, params, fields))
        return [{"ts_code": "600519.SH"}]

    monkeypatch.setattr("radar.core.tushare.client.post_tushare", fake_post)

    first = call(config, "stock_basic", {"list_status": "L"})
    second = call(config, "stock_basic", {"list_status": "L"})

    assert first == second == [{"ts_code": "600519.SH"}]
    assert len(calls) == 1


def test_call_uses_history_cache_for_daily(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("radar.core.tushare.history._today_date", lambda: dt.date(2026, 6, 4))
    monkeypatch.setattr("radar.core.tushare.history._now_time", lambda: dt.time(14, 59))
    config = _config(tmp_path)
    calls = []

    def fake_post(provider, api_name, params, fields):
        calls.append(params)
        if params["start_date"] == "20260604":
            return []
        return [{"ts_code": "600519.SH", "trade_date": "20260603", "close": 100}]

    monkeypatch.setattr("radar.core.tushare.client.post_tushare", fake_post)

    rows = call(
        config,
        "daily",
        {"ts_code": "600519.SH", "start_date": "20260603", "end_date": "20260603"},
    )
    cached = call(
        config,
        "daily",
        {"ts_code": "600519.SH", "start_date": "20260603", "end_date": "20260603"},
    )

    assert rows == cached == [{"ts_code": "600519.SH", "trade_date": "20260603", "close": 100}]
    assert calls == [{"ts_code": "600519.SH", "start_date": "20260603", "end_date": "20260603"}]


def test_point_query_falls_back_to_kv(monkeypatch, tmp_path: Path):
    config = _config(tmp_path)
    calls = []

    def fake_post(provider, api_name, params, fields):
        calls.append(params)
        return [{"ts_code": "600519.SH", "trade_date": "20260603"}]

    monkeypatch.setattr("radar.core.tushare.client.post_tushare", fake_post)

    call(config, "daily", {"ts_code": "600519.SH", "trade_date": "20260603"})
    call(config, "daily", {"ts_code": "600519.SH", "trade_date": "20260603"})

    assert calls == [{"ts_code": "600519.SH", "trade_date": "20260603"}]


def test_history_api_with_fields_falls_back_to_kv(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("radar.core.tushare.history._today_date", lambda: dt.date(2026, 6, 4))
    config = _config(tmp_path)
    calls = []

    def fake_post(provider, api_name, params, fields):
        calls.append((params, fields))
        return [{"ts_code": "600519.SH", "trade_date": "20260603"}]

    monkeypatch.setattr("radar.core.tushare.client.post_tushare", fake_post)

    call(
        config,
        "daily",
        {"ts_code": "600519.SH", "start_date": "20260603", "end_date": "20260603"},
        fields="ts_code,trade_date",
    )
    call(
        config,
        "daily",
        {"ts_code": "600519.SH", "start_date": "20260603", "end_date": "20260603"},
        fields="ts_code,trade_date",
    )

    assert calls == [
        (
            {"ts_code": "600519.SH", "start_date": "20260603", "end_date": "20260603"},
            "ts_code,trade_date",
        )
    ]


def test_get_realtime_daily_quote_calls_rt_k_and_normalizes(monkeypatch, tmp_path: Path):
    captured = {}

    def fake_call(config, api_name, params, fields=None, *, use_cache=True, **kwargs):
        captured.update(
            {
                "config": config,
                "api_name": api_name,
                "params": params,
                "fields": fields,
                "use_cache": use_cache,
                "kwargs": kwargs,
            }
        )
        return [
            {
                "ts_code": "300503.SZ",
                "name": "昊志机电",
                "pre_close": "87.01",
                "open": "83.50",
                "high": 85.68,
                "low": 82.51,
                "close": "84.75",
                "vol": "16327661",
                "amount": "1374470949.46",
                "num": "47447",
            }
        ]

    monkeypatch.setattr("radar.core.tushare.realtime.call", fake_call)

    quote = get_realtime_daily_quote(_config(tmp_path), ts_code="300503.sz", use_cache=False)

    assert quote is not None
    assert captured["api_name"] == "rt_k"
    assert captured["params"] == {"ts_code": "300503.SZ"}
    assert captured["use_cache"] is False
    assert "open" in captured["fields"]
    assert captured["kwargs"] == {}
    assert quote.ts_code == "300503.SZ"
    assert quote.name == "昊志机电"
    assert quote.open == 83.5
    assert quote.close == 84.75
    assert quote.num == 47447


def test_get_realtime_daily_quote_returns_none_for_empty_rows(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("radar.core.tushare.realtime.call", lambda *args, **kwargs: [])

    assert get_realtime_daily_quote(_config(tmp_path), ts_code="300503.SZ") is None


def test_market_data_helpers_call_expected_apis(monkeypatch, tmp_path: Path):
    calls = []

    def fake_call(config, api_name, params=None, fields=None, *, use_cache=True, **kwargs):
        calls.append((api_name, params, fields, use_cache, kwargs))
        return [{"api_name": api_name}]

    monkeypatch.setattr("radar.core.tushare.market_data.call", fake_call)
    config = _config(tmp_path)

    assert get_stock_moneyflow(config, ts_code="300503.sz", source="dc", start_date="20260601", end_date="20260609") == [
        {"api_name": "moneyflow_dc"}
    ]
    assert get_stock_moneyflow(config, ts_code="300503.SZ", source="ths", trade_date="20260609", use_cache=False) == [
        {"api_name": "moneyflow_ths"}
    ]
    assert get_stock_moneyflow(config, ts_code="300503.SZ", source="tushare") == [{"api_name": "moneyflow"}]
    assert get_stock_factor(config, ts_code="300503.SZ", start_date="20260601") == [{"api_name": "stk_factor"}]
    assert get_stock_limit(config, ts_code="300503.SZ", trade_date="20260609") == [{"api_name": "stk_limit"}]
    assert get_sector_moneyflow(config, source="dc", trade_date="20260609") == [{"api_name": "moneyflow_ind_dc"}]
    assert get_limit_pool(config, api_name="limit_step", trade_date="20260609") == [{"api_name": "limit_step"}]
    assert get_billboard_trading(config, api_name="top_inst", trade_date="20260609", ts_code="300503.SZ") == [
        {"api_name": "top_inst"}
    ]

    assert calls[0] == (
        "moneyflow_dc",
        {"start_date": "20260601", "end_date": "20260609", "ts_code": "300503.SZ"},
        None,
        True,
        {},
    )
    assert calls[1] == ("moneyflow_ths", {"trade_date": "20260609", "ts_code": "300503.SZ"}, None, False, {})
    assert calls[-1] == ("top_inst", {"trade_date": "20260609", "ts_code": "300503.SZ"}, None, True, {})


def test_resolve_stock_supports_name_and_symbol(monkeypatch, tmp_path: Path):
    rows = (
        {"ts_code": "600519.SH", "symbol": "600519", "name": "贵州茅台"},
        {"ts_code": "000001.SZ", "symbol": "000001", "name": "平安银行"},
    )
    monkeypatch.setattr("radar.core.tushare.resolver._all_stocks", lambda config: rows)

    assert resolve_stock(_config(tmp_path), "600519") == "600519.SH"
    assert resolve_stock(_config(tmp_path), "贵州茅台") == "600519.SH"
    assert resolve_stock(_config(tmp_path), "000001.sz") == "000001.SZ"


def _config(tmp_path: Path) -> RadarConfig:
    return RadarConfig(
        storage={"data_dir": tmp_path},
        market={
            "provider": "tushare",
            "secret_ref": "tushare_main",
            "api_url": "https://example.invalid/tushare",
            "timeout": 12,
        },
        secrets=RadarSecrets(market={"tushare_main": {"token": "secret-token"}}),
    )


def _provider(tmp_path: Path, request_delay_ms: int = 0) -> RuntimeTushareProvider:
    return RuntimeTushareProvider(
        api_url="https://example.invalid/tushare",
        token="secret-token",
        timeout=12,
        request_delay_ms=request_delay_ms,
        database=tmp_path / "market.sqlite3",
    )
