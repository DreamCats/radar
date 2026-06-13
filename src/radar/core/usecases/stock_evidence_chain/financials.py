from __future__ import annotations

import datetime as dt
from typing import Any, Literal

from pydantic import BaseModel, Field

from radar.core.config import RadarConfig
from radar.core.tushare import client as tushare_client
from radar.core.tushare import history
from radar.core.tushare.exceptions import TushareError


FinancialTone = Literal["ready", "watch", "risk", "missing"]


class StockEvidenceFinancialMetric(BaseModel):
    label: str
    value: str
    tone: Literal["up", "down", "flat"] | None = None


class StockEvidenceFinancials(BaseModel):
    ts_code: str
    status: str
    tone: FinancialTone = "missing"
    latest_period: str | None = None
    latest_ann_date: str | None = None
    metrics: list[StockEvidenceFinancialMetric] = Field(default_factory=list)
    lines: list[str] = Field(default_factory=list)
    missing_reason: str | None = None
    source: str = "tushare"


def get_stock_evidence_financials(
    config: RadarConfig,
    *,
    ts_code: str,
    years: int = 5,
) -> StockEvidenceFinancials:
    code = ts_code.strip().upper()
    if not code:
        raise ValueError("ts_code 不能为空")

    start = _lookback_start(years)
    end = history.cacheable_end_key("day")
    sources = {
        "income": _rows(config, "income", code, start, end),
        "balancesheet": _rows(config, "balancesheet", code, start, end),
        "cashflow": _rows(config, "cashflow", code, start, end),
        "fina_indicator": _rows(config, "fina_indicator", code, start, end),
    }
    latest_period = _latest_period(sources)
    if latest_period is None:
        return StockEvidenceFinancials(
            ts_code=code,
            status="暂无财报",
            tone="missing",
            missing_reason="Tushare 暂无该股票近年财报数据或本地配置暂不可用。",
            lines=[
                "已接入 Tushare 财务接口，但当前没有可展示的 income / balancesheet / cashflow / fina_indicator 数据。",
                "财务核查仍缺收入、利润、现金流和资产质量，不输出完整结论。",
            ],
        )

    income = _row_for_period(sources["income"], latest_period)
    balance = _row_for_period(sources["balancesheet"], latest_period)
    cashflow = _row_for_period(sources["cashflow"], latest_period)
    indicator = _row_for_period(sources["fina_indicator"], latest_period)
    ann_date = _latest_ann_date(income, balance, cashflow, indicator)
    revenue = _first_number(income, "revenue", "total_revenue")
    net_profit = _first_number(income, "n_income_attr_p", "n_income")
    operating_cashflow = _number(cashflow.get("n_cashflow_act"))
    gross_margin = _number(indicator.get("grossprofit_margin"))
    roe = _first_number(indicator, "roe", "roe_waa")
    debt_to_assets = _number(indicator.get("debt_to_assets"))
    accounts_receiv = _first_number(balance, "accounts_receiv", "accounts_receiv_bill")
    inventories = _number(balance.get("inventories"))

    metrics = [
        StockEvidenceFinancialMetric(label="报告期", value=_format_period(latest_period)),
        StockEvidenceFinancialMetric(label="营收", value=_format_amount(revenue)),
        StockEvidenceFinancialMetric(label="归母净利", value=_format_amount(net_profit), tone=_tone(net_profit)),
        StockEvidenceFinancialMetric(label="ROE", value=_format_ratio(roe), tone=_tone(roe)),
    ]
    lines = _dedupe(
        [
            f"最近报告期 {_format_period(latest_period)}，公告日 {ann_date or '-'}。",
            f"营业收入 {_format_amount(revenue)}，同比 {_format_ratio(_number(indicator.get('or_yoy')))}；归母净利 {_format_amount(net_profit)}，同比 {_format_ratio(_number(indicator.get('netprofit_yoy')))}。",
            f"销售毛利率 {_format_ratio(gross_margin)}，ROE {_format_ratio(roe)}，资产负债率 {_format_ratio(debt_to_assets)}。",
            f"经营现金流 {_format_amount(operating_cashflow)}，经营现金流/归母净利 {_format_multiple(_divide(operating_cashflow, net_profit))}。",
            f"应收账款 {_format_amount(accounts_receiv)}，存货 {_format_amount(inventories)}。",
        ]
    )

    return StockEvidenceFinancials(
        ts_code=code,
        status="已接 Tushare",
        tone="ready",
        latest_period=latest_period,
        latest_ann_date=ann_date,
        metrics=metrics,
        lines=lines,
    )


def _rows(config: RadarConfig, api_name: str, ts_code: str, start: str, end: str) -> list[dict[str, Any]]:
    try:
        return tushare_client.call(
            config,
            api_name,
            {"ts_code": ts_code, "start_date": start, "end_date": end},
            use_cache=True,
        )
    except TushareError:
        spec = history.spec_for(api_name)
        if spec is None:
            return []
        return history.query(config.market_database_path, spec, ts_code, start=start, end=end)


def _latest_period(sources: dict[str, list[dict[str, Any]]]) -> str | None:
    periods = [str(row.get("end_date") or "") for rows in sources.values() for row in rows]
    return max((period for period in periods if period), default=None)


def _row_for_period(rows: list[dict[str, Any]], period: str) -> dict[str, Any]:
    candidates = [row for row in rows if str(row.get("end_date") or "") == period]
    if not candidates:
        return {}
    candidates.sort(key=_row_sort_key, reverse=True)
    consolidated = [row for row in candidates if str(row.get("report_type") or "") == "1"]
    return consolidated[0] if consolidated else candidates[0]


def _row_sort_key(row: dict[str, Any]) -> tuple[str, int, str]:
    return (
        str(row.get("end_date") or ""),
        1 if str(row.get("report_type") or "") == "1" else 0,
        str(row.get("f_ann_date") or row.get("ann_date") or ""),
    )


def _latest_ann_date(*rows: dict[str, Any]) -> str | None:
    values = [str(row.get("f_ann_date") or row.get("ann_date") or "") for row in rows]
    return max((value for value in values if value), default=None)


def _lookback_start(years: int) -> str:
    lookback_years = min(max(years, 1), 10)
    return (dt.date.today() - dt.timedelta(days=lookback_years * 370)).strftime("%Y%m%d")


def _number(value: object) -> float | None:
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number else None


def _first_number(row: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        value = _number(row.get(key))
        if value is not None:
            return value
    return None


def _format_period(value: str | None) -> str:
    if not value or len(value) != 8:
        return value or "-"
    return f"{value[:4]}-{value[4:6]}-{value[6:]}"


def _format_amount(value: float | None) -> str:
    if value is None:
        return "-"
    amount = value / 100_000_000
    return f"{amount:.2f}亿"


def _format_ratio(value: float | None) -> str:
    return "-" if value is None else f"{value:.1f}%"


def _format_multiple(value: float | None) -> str:
    return "-" if value is None else f"{value:.2f}x"


def _divide(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator is None or denominator == 0:
        return None
    return numerator / denominator


def _tone(value: float | None) -> Literal["up", "down", "flat"]:
    if value is None or value == 0:
        return "flat"
    return "up" if value > 0 else "down"


def _dedupe(items: list[str]) -> list[str]:
    return list(dict.fromkeys(item for item in items if item))
