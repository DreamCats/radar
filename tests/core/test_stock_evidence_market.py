from __future__ import annotations

from radar.core.usecases.stock_evidence_chain.market import _DailyRow, _selected_trade_dates


def test_selected_trade_dates_use_next_trade_day_for_non_trading_evidence_date():
    rows = [
        _DailyRow(trade_date="20260508", close=101.35, pct_chg=None, amount=None),
        _DailyRow(trade_date="20260511", close=115.57, pct_chg=None, amount=None),
        _DailyRow(trade_date="20260617", close=105.56, pct_chg=None, amount=None),
    ]

    assert _selected_trade_dates(rows, ["20260510"], "20260617") == ["20260511", "20260617"]


def test_selected_trade_dates_keep_latest_on_or_before_as_of_date():
    rows = [
        _DailyRow(trade_date="20260511", close=115.57, pct_chg=None, amount=None),
        _DailyRow(trade_date="20260617", close=105.56, pct_chg=None, amount=None),
    ]

    assert _selected_trade_dates(rows, ["20260511"], "20260618") == ["20260511", "20260617"]
