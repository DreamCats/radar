from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from radar.core.chat.tools import ChatTool
from radar.core.config import RadarConfig
from radar.core.tushare import (
    get_billboard_trading,
    get_limit_pool,
    get_sector_moneyflow,
    get_stock_factor,
    get_stock_limit,
    get_stock_moneyflow,
    resolve_stock,
)
from radar.core.tushare import call as tushare_call


TUSHARE_PRICE_FIELDS = {
    "daily": "ts_code,trade_date,open,high,low,close,pre_close,change,pct_chg,vol,amount",
    "daily_basic": "ts_code,trade_date,turnover_rate,volume_ratio,pe,pb,ps,total_mv,circ_mv",
    "adj_factor": "ts_code,trade_date,adj_factor",
}
FINANCIAL_FIELDS = {
    "income": (
        "ts_code,ann_date,f_ann_date,end_date,report_type,total_revenue,revenue,"
        "operate_profit,total_profit,n_income,n_income_attr_p,ebit,ebitda,basic_eps,"
        "diluted_eps,rd_exp,update_flag"
    ),
    "balancesheet": (
        "ts_code,ann_date,f_ann_date,end_date,report_type,total_assets,total_liab,"
        "total_hldr_eqy_exc_min_int,total_cur_assets,total_cur_liab,money_cap,"
        "accounts_receiv,inventories,fix_assets,st_borr,lt_borr,update_flag"
    ),
    "cashflow": (
        "ts_code,ann_date,f_ann_date,end_date,report_type,net_profit,c_fr_sale_sg,"
        "c_paid_goods_s,n_cashflow_act,n_cashflow_inv_act,n_cash_flows_fnc_act,"
        "free_cashflow,end_bal_cash,update_flag"
    ),
    "fina_indicator": (
        "ts_code,ann_date,end_date,eps,dt_eps,total_revenue_ps,revenue_ps,profit_dedt,"
        "gross_margin,netprofit_margin,grossprofit_margin,roe,roe_dt,roe_waa,roa,"
        "debt_to_assets,ocfps,ocf_to_or,ocf_to_profit,tr_yoy,or_yoy,netprofit_yoy,"
        "dt_netprofit_yoy,ocf_yoy,rd_exp,update_flag"
    ),
}
FORECAST_FIELDS = (
    "ts_code,ann_date,end_date,type,p_change_min,p_change_max,net_profit_min,"
    "net_profit_max,last_parent_net,first_ann_date,summary,change_reason"
)
EXPRESS_FIELDS = (
    "ts_code,ann_date,end_date,revenue,operate_profit,total_profit,n_income,"
    "total_assets,total_hldr_eqy_exc_min_int,diluted_eps,diluted_roe,yoy_sales,"
    "yoy_net_profit,bps,perf_summary,is_audit,remark"
)
SEGMENT_FIELDS = (
    "ts_code,end_date,bz_item,bz_code,bz_sales,bz_profit,bz_cost,curr_type,update_flag"
)


class RadarTushareTools:
    def __init__(self, config: RadarConfig):
        self.config = config

    def tools(self) -> list[ChatTool]:
        return [
            self.resolve_stock_tool(),
            self.stock_price_history_tool(),
            self.stock_financials_tool(),
            self.stock_forecast_or_segments_tool(),
            self.stock_moneyflow_tool(),
            self.sector_moneyflow_tool(),
            self.stock_factor_tool(),
            self.stock_limit_tool(),
            self.limit_pool_tool(),
            self.billboard_tool(),
        ]

    def resolve_stock_tool(self) -> ChatTool:
        return ChatTool(
            name="radar_resolve_stock",
            description="把股票中文名、6 位代码或 ts_code 解析为唯一 Tushare ts_code。",
            input_schema=_object_schema({"value": {"type": "string"}}, required=["value"]),
            handler=self.resolve_stock,
        )

    def stock_price_history_tool(self) -> ChatTool:
        return ChatTool(
            name="radar_get_stock_price_history",
            description="读取受控 Tushare 日线/基础/复权历史数据，支持 daily、daily_basic、adj_factor；用于已收盘或已落库交易日，不承诺盘中实时数据。",
            input_schema=_object_schema(
                {
                    "stock": {"type": "string"},
                    "api_name": {"type": "string", "enum": list(TUSHARE_PRICE_FIELDS)},
                    "start_date": {"type": "string"},
                    "end_date": {"type": "string"},
                    "days": {"type": "integer", "minimum": 1, "maximum": 365},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 240},
                },
                required=["stock"],
            ),
            handler=self.stock_price_history,
        )

    def stock_financials_tool(self) -> ChatTool:
        return ChatTool(
            name="radar_get_stock_financials",
            description=(
                "读取单股核心财务报表和财务指标，支持 income、balancesheet、cashflow、fina_indicator。"
                "用于验证收入、归母净利、现金流、资产负债、ROE、毛利率和增长质量。"
            ),
            input_schema=_object_schema(
                {
                    "stock": {"type": "string"},
                    "api_names": {
                        "type": "array",
                        "items": {"type": "string", "enum": list(FINANCIAL_FIELDS)},
                    },
                    "start_date": {"type": "string"},
                    "end_date": {"type": "string"},
                    "period": {"type": "string"},
                    "days": {"type": "integer", "minimum": 1, "maximum": 3650},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 100},
                },
                required=["stock"],
            ),
            handler=self.stock_financials,
        )

    def stock_forecast_or_segments_tool(self) -> ChatTool:
        return ChatTool(
            name="radar_get_stock_forecast_or_segments",
            description=(
                "读取单股业绩预告、业绩快报和主营业务构成，返回 forecast、express、fina_mainbz。"
                "用于把催化线索转译成利润预测、分部收入和业务暴露。"
            ),
            input_schema=_object_schema(
                {
                    "stock": {"type": "string"},
                    "include": {
                        "type": "array",
                        "items": {"type": "string", "enum": ["forecast", "express", "segments"]},
                    },
                    "start_date": {"type": "string"},
                    "end_date": {"type": "string"},
                    "period": {"type": "string"},
                    "segment_type": {"type": "string", "enum": ["P", "D", "I"]},
                    "days": {"type": "integer", "minimum": 1, "maximum": 3650},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 100},
                },
                required=["stock"],
            ),
            handler=self.stock_forecast_or_segments,
        )

    def stock_moneyflow_tool(self) -> ChatTool:
        return ChatTool(
            name="radar_get_stock_moneyflow",
            description="读取个股资金流，支持 tushare、东财 dc、同花顺 ths 数据源。",
            input_schema=_object_schema(
                {
                    "stock": {"type": "string"},
                    "source": {"type": "string", "enum": ["dc", "ths", "tushare"]},
                    "start_date": {"type": "string"},
                    "end_date": {"type": "string"},
                    "trade_date": {"type": "string"},
                    "days": {"type": "integer", "minimum": 1, "maximum": 365},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 240},
                    "use_cache": {"type": "boolean"},
                },
                required=["stock"],
            ),
            handler=self.stock_moneyflow,
        )

    def sector_moneyflow_tool(self) -> ChatTool:
        return ChatTool(
            name="radar_get_sector_moneyflow",
            description="读取行业/板块资金流，支持东财 dc 和同花顺 ths 数据源。",
            input_schema=_object_schema(
                {
                    "source": {"type": "string", "enum": ["dc", "ths"]},
                    "trade_date": {"type": "string"},
                    "start_date": {"type": "string"},
                    "end_date": {"type": "string"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 200},
                    "use_cache": {"type": "boolean"},
                }
            ),
            handler=self.sector_moneyflow,
        )

    def stock_factor_tool(self) -> ChatTool:
        return ChatTool(
            name="radar_get_stock_technical_factors",
            description="读取 Tushare stk_factor 原始因子，仅在用户明确要求技术指标字段时使用；常规投研回答不要主动分析 KDJ、MACD、RSI、BOLL 或均线形态。",
            input_schema=_object_schema(
                {
                    "stock": {"type": "string"},
                    "start_date": {"type": "string"},
                    "end_date": {"type": "string"},
                    "trade_date": {"type": "string"},
                    "days": {"type": "integer", "minimum": 1, "maximum": 365},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 240},
                    "use_cache": {"type": "boolean"},
                },
                required=["stock"],
            ),
            handler=self.stock_factor,
        )

    def stock_limit_tool(self) -> ChatTool:
        return ChatTool(
            name="radar_get_stock_limit_context",
            description="读取个股涨跌停价 stk_limit，补充涨停价、跌停价和交易日期上下文。",
            input_schema=_object_schema(
                {
                    "stock": {"type": "string"},
                    "start_date": {"type": "string"},
                    "end_date": {"type": "string"},
                    "trade_date": {"type": "string"},
                    "days": {"type": "integer", "minimum": 1, "maximum": 365},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 240},
                    "use_cache": {"type": "boolean"},
                },
                required=["stock"],
            ),
            handler=self.stock_limit,
        )

    def limit_pool_tool(self) -> ChatTool:
        return ChatTool(
            name="radar_get_limit_pool",
            description="读取涨跌停池/连板梯队/最强涨停池，支持 limit_list_d、limit_step、limit_strongest。",
            input_schema=_object_schema(
                {
                    "api_name": {"type": "string", "enum": ["limit_list_d", "limit_step", "limit_strongest"]},
                    "trade_date": {"type": "string"},
                    "limit_type": {"type": "string"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 200},
                    "use_cache": {"type": "boolean"},
                }
            ),
            handler=self.limit_pool,
        )

    def billboard_tool(self) -> ChatTool:
        return ChatTool(
            name="radar_get_billboard_trading",
            description="读取龙虎榜 top_list/top_inst，可按交易日和股票过滤。",
            input_schema=_object_schema(
                {
                    "api_name": {"type": "string", "enum": ["top_list", "top_inst"]},
                    "trade_date": {"type": "string"},
                    "stock": {"type": "string"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 200},
                    "use_cache": {"type": "boolean"},
                }
            ),
            handler=self.billboard,
        )

    def resolve_stock(self, args: dict[str, Any]) -> dict[str, Any]:
        value = str(args["value"]).strip()
        return {"value": value, "ts_code": resolve_stock(self.config, value)}

    def stock_price_history(self, args: dict[str, Any]) -> dict[str, Any]:
        api_name = str(args.get("api_name") or "daily")
        if api_name not in TUSHARE_PRICE_FIELDS:
            raise ValueError(f"不支持的 Tushare 接口: {api_name}")
        stock, ts_code, start_date, end_date = self._stock_range(args)
        rows = tushare_call(
            self.config,
            api_name,
            {"ts_code": ts_code, "start_date": start_date, "end_date": end_date},
            fields=TUSHARE_PRICE_FIELDS[api_name],
        )
        return _stock_result(stock, ts_code, api_name, start_date, end_date, rows, args, maximum=240)

    def stock_financials(self, args: dict[str, Any]) -> dict[str, Any]:
        stock, ts_code, start_date, end_date = self._stock_range(
            args,
            default_days=1460,
            max_days=3650,
        )
        api_names = _enum_list(
            args.get("api_names"),
            allowed=set(FINANCIAL_FIELDS),
            default=list(FINANCIAL_FIELDS),
        )
        params = _financial_params(ts_code, args, start_date, end_date)
        return {
            "stock": stock,
            "ts_code": ts_code,
            "start_date": start_date,
            "end_date": end_date,
            "period": _optional_str(args.get("period")),
            "items": {
                api_name: tushare_call(self.config, api_name, params, fields=FINANCIAL_FIELDS[api_name])[
                    : _bounded_int(args.get("limit"), default=12, maximum=100)
                ]
                for api_name in api_names
            },
        }

    def stock_forecast_or_segments(self, args: dict[str, Any]) -> dict[str, Any]:
        stock, ts_code, start_date, end_date = self._stock_range(
            args,
            default_days=1460,
            max_days=3650,
        )
        includes = _enum_list(
            args.get("include"),
            allowed={"forecast", "express", "segments"},
            default=["forecast", "express", "segments"],
        )
        base_params = _financial_params(ts_code, args, start_date, end_date)
        limit = _bounded_int(args.get("limit"), default=20, maximum=100)
        items: dict[str, list[dict[str, Any]]] = {}
        if "forecast" in includes:
            items["forecast"] = tushare_call(
                self.config,
                "forecast",
                base_params,
                fields=FORECAST_FIELDS,
            )[:limit]
        if "express" in includes:
            items["express"] = tushare_call(
                self.config,
                "express",
                base_params,
                fields=EXPRESS_FIELDS,
            )[:limit]
        if "segments" in includes:
            segment_params = dict(base_params)
            segment_params["type"] = str(args.get("segment_type") or "P")
            items["segments"] = tushare_call(
                self.config,
                "fina_mainbz",
                segment_params,
                fields=SEGMENT_FIELDS,
            )[:limit]
        return {
            "stock": stock,
            "ts_code": ts_code,
            "start_date": start_date,
            "end_date": end_date,
            "period": _optional_str(args.get("period")),
            "segment_type": str(args.get("segment_type") or "P"),
            "items": items,
        }

    def stock_moneyflow(self, args: dict[str, Any]) -> dict[str, Any]:
        stock, ts_code, start_date, end_date = self._stock_range(args)
        source = str(args.get("source") or "dc")
        trade_date = _date_key(args.get("trade_date"))
        rows = get_stock_moneyflow(
            self.config,
            ts_code=ts_code,
            source=source,
            start_date=None if trade_date else start_date,
            end_date=None if trade_date else end_date,
            trade_date=trade_date,
            use_cache=bool(args.get("use_cache", True)),
        )
        return _stock_result(
            stock,
            ts_code,
            _source_api(source, "moneyflow"),
            trade_date or start_date,
            trade_date or end_date,
            rows,
            args,
            maximum=240,
        )

    def sector_moneyflow(self, args: dict[str, Any]) -> dict[str, Any]:
        source = str(args.get("source") or "dc")
        start_date, end_date = _range_from_args(args, default_days=7, max_days=365)
        trade_date = _date_key(args.get("trade_date"))
        rows = get_sector_moneyflow(
            self.config,
            source=source,
            trade_date=trade_date,
            start_date=None if trade_date else start_date,
            end_date=None if trade_date else end_date,
            use_cache=bool(args.get("use_cache", True)),
        )
        return _rows_result(
            _source_api(source, "sector_moneyflow"),
            rows,
            args,
            maximum=200,
            start_date=trade_date or start_date,
            end_date=trade_date or end_date,
        )

    def stock_factor(self, args: dict[str, Any]) -> dict[str, Any]:
        stock, ts_code, start_date, end_date = self._stock_range(args, default_days=30)
        trade_date = _date_key(args.get("trade_date"))
        rows = get_stock_factor(
            self.config,
            ts_code=ts_code,
            start_date=None if trade_date else start_date,
            end_date=None if trade_date else end_date,
            trade_date=trade_date,
            use_cache=bool(args.get("use_cache", True)),
        )
        return _stock_result(stock, ts_code, "stk_factor", trade_date or start_date, trade_date or end_date, rows, args, maximum=240)

    def stock_limit(self, args: dict[str, Any]) -> dict[str, Any]:
        stock, ts_code, start_date, end_date = self._stock_range(args, default_days=30)
        trade_date = _date_key(args.get("trade_date"))
        rows = get_stock_limit(
            self.config,
            ts_code=ts_code,
            start_date=None if trade_date else start_date,
            end_date=None if trade_date else end_date,
            trade_date=trade_date,
            use_cache=bool(args.get("use_cache", True)),
        )
        return _stock_result(stock, ts_code, "stk_limit", trade_date or start_date, trade_date or end_date, rows, args, maximum=240)

    def limit_pool(self, args: dict[str, Any]) -> dict[str, Any]:
        api_name = str(args.get("api_name") or "limit_list_d")
        rows = get_limit_pool(
            self.config,
            api_name=api_name,
            trade_date=_date_key(args.get("trade_date")),
            limit_type=_optional_str(args.get("limit_type")),
            use_cache=bool(args.get("use_cache", True)),
        )
        return _rows_result(api_name, rows, args, maximum=200)

    def billboard(self, args: dict[str, Any]) -> dict[str, Any]:
        stock = _optional_str(args.get("stock"))
        ts_code = resolve_stock(self.config, stock) if stock else None
        api_name = str(args.get("api_name") or "top_list")
        rows = get_billboard_trading(
            self.config,
            api_name=api_name,
            trade_date=_date_key(args.get("trade_date")),
            ts_code=ts_code,
            use_cache=bool(args.get("use_cache", True)),
        )
        result = _rows_result(api_name, rows, args, maximum=200)
        if ts_code:
            result["ts_code"] = ts_code
        return result

    def _stock_range(
        self,
        args: dict[str, Any],
        *,
        default_days: int = 90,
        max_days: int = 365,
    ) -> tuple[str, str, str, str]:
        stock = str(args["stock"]).strip()
        ts_code = resolve_stock(self.config, stock)
        start_date, end_date = _range_from_args(args, default_days=default_days, max_days=max_days)
        return stock, ts_code, start_date, end_date


def _object_schema(properties: dict[str, Any], *, required: list[str] | None = None) -> dict[str, Any]:
    return {"type": "object", "properties": properties, "required": required or [], "additionalProperties": False}


def _range_from_args(args: dict[str, Any], *, default_days: int, max_days: int) -> tuple[str, str]:
    end_date = _date_key(args.get("end_date")) or datetime.now().strftime("%Y%m%d")
    start_date = _date_key(args.get("start_date"))
    if start_date is None:
        days = _bounded_int(args.get("days"), default=default_days, maximum=max_days)
        start_date = (datetime.strptime(end_date, "%Y%m%d") - timedelta(days=days)).strftime("%Y%m%d")
    return start_date, end_date


def _rows_result(
    api_name: str,
    rows: list[dict[str, Any]],
    args: dict[str, Any],
    *,
    maximum: int,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict[str, Any]:
    limit = _bounded_int(args.get("limit"), default=min(50, maximum), maximum=maximum)
    result: dict[str, Any] = {"api_name": api_name, "items": rows[:limit]}
    if start_date:
        result["start_date"] = start_date
    if end_date:
        result["end_date"] = end_date
    return result


def _financial_params(ts_code: str, args: dict[str, Any], start_date: str, end_date: str) -> dict[str, str]:
    params = {"ts_code": ts_code, "start_date": start_date, "end_date": end_date}
    period = _optional_str(args.get("period"))
    if period:
        params["period"] = period.replace("-", "")
    return params


def _stock_result(
    stock: str,
    ts_code: str,
    api_name: str,
    start_date: str,
    end_date: str,
    rows: list[dict[str, Any]],
    args: dict[str, Any],
    *,
    maximum: int,
) -> dict[str, Any]:
    result = _rows_result(api_name, rows, args, maximum=maximum, start_date=start_date, end_date=end_date)
    result.update({"stock": stock, "ts_code": ts_code})
    return result


def _source_api(source: str, prefix: str) -> str:
    if prefix == "moneyflow":
        return {"dc": "moneyflow_dc", "ths": "moneyflow_ths", "tushare": "moneyflow"}[source]
    return {"dc": "moneyflow_ind_dc", "ths": "moneyflow_ind_ths"}[source]


def _enum_list(value: object, *, allowed: set[str], default: list[str]) -> list[str]:
    if value is None:
        return default
    if not isinstance(value, list):
        raise ValueError("参数必须是字符串数组")
    items = [str(item).strip() for item in value if str(item).strip()]
    invalid = [item for item in items if item not in allowed]
    if invalid:
        raise ValueError(f"不支持的取值: {', '.join(invalid)}")
    return items or default


def _bounded_int(value: object, *, default: int, maximum: int) -> int:
    if value is None:
        return default
    parsed = int(value)
    if parsed < 1:
        return default
    return min(parsed, maximum)


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _date_key(value: object) -> str | None:
    text = _optional_str(value)
    if text is None:
        return None
    return text.replace("-", "")
