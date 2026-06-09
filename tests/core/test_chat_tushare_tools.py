from __future__ import annotations

from radar.core.chat.tushare_tools import RadarTushareTools
from radar.core.config import RadarConfig


def test_stock_moneyflow_tool_resolves_stock_and_calls_helper(tmp_path, monkeypatch):
    config = RadarConfig(storage={"data_dir": tmp_path})
    captured = {}

    monkeypatch.setattr("radar.core.chat.tushare_tools.resolve_stock", lambda config, value: "300503.SZ")

    def fake_moneyflow(config, *, ts_code, source, start_date, end_date, trade_date, use_cache):
        captured.update(
            {
                "ts_code": ts_code,
                "source": source,
                "start_date": start_date,
                "end_date": end_date,
                "trade_date": trade_date,
                "use_cache": use_cache,
            }
        )
        return [{"ts_code": ts_code, "trade_date": "20260609", "net_amount": 123.4}]

    monkeypatch.setattr("radar.core.chat.tushare_tools.get_stock_moneyflow", fake_moneyflow)

    result = RadarTushareTools(config).stock_moneyflow(
        {
            "stock": "昊志机电",
            "source": "ths",
            "start_date": "2026-06-01",
            "end_date": "2026-06-09",
            "limit": 5,
            "use_cache": False,
        }
    )

    assert result["api_name"] == "moneyflow_ths"
    assert result["stock"] == "昊志机电"
    assert result["ts_code"] == "300503.SZ"
    assert result["items"] == [{"ts_code": "300503.SZ", "trade_date": "20260609", "net_amount": 123.4}]
    assert captured == {
        "ts_code": "300503.SZ",
        "source": "ths",
        "start_date": "20260601",
        "end_date": "20260609",
        "trade_date": None,
        "use_cache": False,
    }


def test_stock_factor_and_limit_tools_call_helpers(tmp_path, monkeypatch):
    config = RadarConfig(storage={"data_dir": tmp_path})
    captured = []

    monkeypatch.setattr("radar.core.chat.tushare_tools.resolve_stock", lambda config, value: "300503.SZ")

    def fake_factor(config, *, ts_code, start_date, end_date, trade_date, use_cache):
        captured.append(("factor", ts_code, start_date, end_date, trade_date, use_cache))
        return [{"ma_qfq_5": 10.5}]

    def fake_limit(config, *, ts_code, start_date, end_date, trade_date, use_cache):
        captured.append(("limit", ts_code, start_date, end_date, trade_date, use_cache))
        return [{"up_limit": 95.71, "down_limit": 78.31}]

    monkeypatch.setattr("radar.core.chat.tushare_tools.get_stock_factor", fake_factor)
    monkeypatch.setattr("radar.core.chat.tushare_tools.get_stock_limit", fake_limit)

    tools = RadarTushareTools(config)
    factor = tools.stock_factor({"stock": "300503.SZ", "trade_date": "2026-06-09", "end_date": "2026-06-09", "limit": 1})
    limit = tools.stock_limit({"stock": "300503.SZ", "trade_date": "2026-06-09", "end_date": "2026-06-09", "limit": 1})

    assert factor["api_name"] == "stk_factor"
    assert factor["items"] == [{"ma_qfq_5": 10.5}]
    assert limit["api_name"] == "stk_limit"
    assert limit["items"] == [{"up_limit": 95.71, "down_limit": 78.31}]
    assert captured == [
        ("factor", "300503.SZ", None, None, "20260609", True),
        ("limit", "300503.SZ", None, None, "20260609", True),
    ]


def test_sector_limit_pool_and_billboard_tools_call_helpers(tmp_path, monkeypatch):
    config = RadarConfig(storage={"data_dir": tmp_path})
    captured = []

    monkeypatch.setattr("radar.core.chat.tushare_tools.resolve_stock", lambda config, value: "300503.SZ")

    def fake_sector(config, *, source, trade_date, start_date, end_date, use_cache):
        captured.append(("sector", source, trade_date, start_date, end_date, use_cache))
        return [{"name": "机器人"}]

    def fake_pool(config, *, api_name, trade_date, limit_type, use_cache):
        captured.append(("pool", api_name, trade_date, limit_type, use_cache))
        return [{"ts_code": "300503.SZ"}]

    def fake_billboard(config, *, api_name, trade_date, ts_code, use_cache):
        captured.append(("billboard", api_name, trade_date, ts_code, use_cache))
        return [{"exalter": "机构专用"}]

    monkeypatch.setattr("radar.core.chat.tushare_tools.get_sector_moneyflow", fake_sector)
    monkeypatch.setattr("radar.core.chat.tushare_tools.get_limit_pool", fake_pool)
    monkeypatch.setattr("radar.core.chat.tushare_tools.get_billboard_trading", fake_billboard)

    tools = RadarTushareTools(config)
    sector = tools.sector_moneyflow({"source": "dc", "trade_date": "2026-06-09", "end_date": "2026-06-09", "limit": 1})
    pool = tools.limit_pool({"api_name": "limit_step", "trade_date": "2026-06-09", "limit_type": "U", "limit": 1})
    billboard = tools.billboard({"api_name": "top_inst", "trade_date": "2026-06-09", "stock": "昊志机电"})

    assert sector["api_name"] == "moneyflow_ind_dc"
    assert pool["api_name"] == "limit_step"
    assert billboard["api_name"] == "top_inst"
    assert billboard["ts_code"] == "300503.SZ"
    assert captured == [
        ("sector", "dc", "20260609", None, None, True),
        ("pool", "limit_step", "20260609", "U", True),
        ("billboard", "top_inst", "20260609", "300503.SZ", True),
    ]
