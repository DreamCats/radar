from __future__ import annotations

import json

from radar.core.market.quotes import (
    from_public_quote_code,
    parse_sina_realtime_response,
    parse_tencent_minute_response,
    parse_tencent_realtime_response,
    tencent_minute_url,
    to_public_quote_code,
)


def test_public_quote_code_converts_tushare_symbols():
    assert to_public_quote_code("000811.SZ") == "sz000811"
    assert to_public_quote_code("600519.SH") == "sh600519"
    assert to_public_quote_code("300750") == "sz300750"
    assert from_public_quote_code("sz000811") == "000811.SZ"


def test_tencent_minute_parser_calculates_incremental_volume_and_amount():
    payload = {
        "data": {
            "sz000811": {
                "data": {
                    "data": [
                        "0930 31.80 1689 5371020.00",
                        "0931 31.70 14768 46853143.93",
                    ]
                }
            }
        }
    }

    points = parse_tencent_minute_response(json.dumps(payload), ts_code="000811.SZ")

    assert tencent_minute_url("000811.SZ").endswith("?code=sz000811")
    assert [point.time for point in points] == ["09:30", "09:31"]
    assert points[0].cum_volume_shares == 168900
    assert points[0].minute_volume_shares == 168900
    assert points[1].cum_volume_shares == 1476800
    assert points[1].minute_volume_shares == 1307900
    assert round(points[1].minute_amount_yuan, 2) == 41482123.93


def test_tencent_realtime_parser_reads_core_quote_fields():
    values = [""] * 49
    values[1] = "冰轮环境"
    values[2] = "000811"
    values[3] = "33.85"
    values[4] = "30.77"
    values[5] = "31.80"
    values[9] = "33.85"
    values[10] = "721100"
    values[19] = "0.00"
    values[20] = "0"
    values[30] = "20260615150000"
    values[33] = "33.85"
    values[34] = "31.06"
    values[36] = "457234"
    values[37] = "151500"

    quote = parse_tencent_realtime_response(
        f'v_sz000811="{"~".join(values)}";',
        ts_code="000811.SZ",
    )

    assert quote is not None
    assert quote.source == "tencent"
    assert quote.name == "冰轮环境"
    assert quote.close == 33.85
    assert quote.volume_shares == 45_723_400
    assert quote.amount_yuan == 1_515_000_000
    assert quote.bid1_volume_lots == 721100


def test_sina_realtime_parser_reads_core_quote_fields():
    values = [""] * 33
    values[0] = "冰轮环境"
    values[1] = "31.800"
    values[2] = "30.770"
    values[3] = "33.850"
    values[4] = "33.850"
    values[5] = "31.060"
    values[8] = "45723400"
    values[9] = "1515000000.00"
    values[10] = "72110000"
    values[11] = "33.850"
    values[20] = "0"
    values[21] = "0.000"
    values[30] = "2026-06-15"
    values[31] = "15:00:00"

    quote = parse_sina_realtime_response(
        f'var hq_str_sz000811="{",".join(values)}";',
        ts_code="000811.SZ",
    )

    assert quote is not None
    assert quote.source == "sina"
    assert quote.open == 31.8
    assert quote.pre_close == 30.77
    assert quote.close == 33.85
    assert quote.volume_shares == 45_723_400
    assert quote.amount_yuan == 1_515_000_000
    assert quote.bid1_volume_lots == 721100
    assert quote.timestamp == "2026-06-15 15:00:00"
