from __future__ import annotations

from typing import Any

from radar.core.chat.tools import ChatTool
from radar.core.config import RadarConfig
from radar.core.tushare import resolve_stock
from radar.core.usecases.stock_evidence_chain import (
    get_stock_evidence_stock_chart,
    latest_stock_evidence_chain,
)
from radar.core.usecases.stock_evidence_chain.view_models import StockEvidenceChainItem


STAGE_VALUES = ["lead", "seed", "formed", "spreading", "pricing", "crowded"]


class RadarStockEvidenceTools:
    """Small stock-evidence tools for chat agent drill-down."""

    def __init__(self, config: RadarConfig):
        self.config = config

    def tools(self) -> list[ChatTool]:
        return [
            self.strategy_candidates_tool(),
            self.stock_evidence_detail_tool(),
            self.theme_candidates_tool(),
            self.stock_evidence_chart_tool(),
        ]

    def strategy_candidates_tool(self) -> ChatTool:
        return ChatTool(
            name="radar_strategy_candidates",
            description=(
                "读取个股证据链策略的紧凑候选列表。用于回答“推几个股票”“今天看什么”，"
                "只返回排序、阶段、主题、市场确认、核心理由和风险摘要。"
            ),
            input_schema=_object_schema(
                {
                    "stage": {"type": "string", "enum": STAGE_VALUES},
                    "theme": {"type": "string"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 30},
                }
            ),
            handler=self.strategy_candidates,
        )

    def stock_evidence_detail_tool(self) -> ChatTool:
        return ChatTool(
            name="radar_stock_evidence_detail",
            description="按股票名、6 位代码或 ts_code 读取单股证据链详情，用于解释为什么选它、风险和后续验证点。",
            input_schema=_object_schema(
                {"stock": {"type": "string"}, "limit": {"type": "integer", "minimum": 1, "maximum": 5}},
                required=["stock"],
            ),
            handler=self.stock_evidence_detail,
        )

    def theme_candidates_tool(self) -> ChatTool:
        return ChatTool(
            name="radar_theme_candidates",
            description="按主线/主题聚合个股证据链候选，用于回答当前主线、某主题里哪些股票更值得跟踪。",
            input_schema=_object_schema(
                {
                    "theme": {"type": "string"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 12},
                    "stocks_per_theme": {"type": "integer", "minimum": 1, "maximum": 8},
                }
            ),
            handler=self.theme_candidates,
        )

    def stock_evidence_chart_tool(self) -> ChatTool:
        return ChatTool(
            name="radar_stock_evidence_chart",
            description="读取个股证据链策略同源的本地日 K 线和成交额证据，返回 candles 及价格/成交额摘要。",
            input_schema=_object_schema(
                {
                    "stock": {"type": "string"},
                    "days": {"type": "integer", "minimum": 1, "maximum": 260},
                },
                required=["stock"],
            ),
            handler=self.stock_evidence_chart,
        )

    def strategy_candidates(self, args: dict[str, Any]) -> dict[str, Any]:
        limit = _bounded_int(args.get("limit"), default=10, maximum=30)
        stage = _optional_str(args.get("stage"))
        theme = _optional_str(args.get("theme"))
        items = self._items(limit=120 if stage or theme else limit)
        if stage:
            items = [item for item in items if item.stage == stage]
        if theme:
            items = [item for item in items if _item_theme_name(item) and theme in _item_theme_name(item)]
        limited_items = items[:limit]
        return {
            "item_count": len(limited_items),
            "stage_counts": _stock_stage_counts(limited_items),
            "items": [_candidate_summary(item) for item in limited_items],
        }

    def stock_evidence_detail(self, args: dict[str, Any]) -> dict[str, Any]:
        stock = str(args["stock"]).strip()
        limit = _bounded_int(args.get("limit"), default=1, maximum=5)
        matches = _match_stock_items(self._items(limit=500), stock)[:limit]
        return {
            "found": bool(matches),
            "query": stock,
            "item_count": len(matches),
            "items": [_stock_detail(item) for item in matches],
        }

    def theme_candidates(self, args: dict[str, Any]) -> dict[str, Any]:
        theme_filter = _optional_str(args.get("theme"))
        theme_limit = _bounded_int(args.get("limit"), default=8, maximum=12)
        stocks_per_theme = _bounded_int(args.get("stocks_per_theme"), default=5, maximum=8)
        groups: dict[str, dict[str, Any]] = {}
        for item in self._items(limit=120):
            theme = _item_theme(item)
            if theme is None:
                continue
            if theme_filter and theme_filter not in theme.theme_name:
                continue
            group = groups.setdefault(
                theme.theme_name,
                {
                    "theme_name": theme.theme_name,
                    "theme_type": theme.theme_type,
                    "quality_label": theme.quality_label,
                    "source_count": theme.source_count,
                    "candidate_count": 0,
                    "candidates": [],
                },
            )
            group["candidate_count"] += 1
            if len(group["candidates"]) < stocks_per_theme:
                group["candidates"].append(_candidate_summary(item))
        themes = sorted(groups.values(), key=lambda item: (-item["candidate_count"], item["theme_name"]))
        return {"theme_count": len(themes[:theme_limit]), "themes": themes[:theme_limit]}

    def stock_evidence_chart(self, args: dict[str, Any]) -> dict[str, Any]:
        stock = str(args["stock"]).strip()
        ts_code = resolve_stock(self.config, stock)
        chart = get_stock_evidence_stock_chart(
            self.config,
            ts_code=ts_code,
            days=_bounded_int(args.get("days"), default=120, maximum=260),
        )
        result = chart.model_dump(mode="json")
        result.update(
            {
                "found": bool(chart.candles),
                "stock": stock,
                "summary": _stock_chart_summary(chart.candles),
            }
        )
        return result

    def _items(self, *, limit: int) -> list[StockEvidenceChainItem]:
        return latest_stock_evidence_chain(self.config, limit=limit).items


def _candidate_summary(item: StockEvidenceChainItem) -> dict[str, Any]:
    theme = _item_theme(item)
    return {
        "ts_code": item.ts_code,
        "stock_name": item.stock_name,
        "stage": item.stage,
        "stage_label": item.stage_label,
        "confidence": item.confidence,
        "rank": item.rank,
        "theme": _theme_summary(theme),
        "market_recognition": item.recognition.state_label,
        "review_label": item.review.label,
        "summary": _clip(item.summary, 180),
        "key_reasons": _clip_list([*item.why, *item.incremental_points], 3, 160),
        "pricing_risk": _clip(item.pricing_risk, 160),
        "crowding_risk": _clip(item.crowding_risk, 160),
        "watch_next": _clip_list(item.watch_next, 3, 120),
    }


def _stock_detail(item: StockEvidenceChainItem) -> dict[str, Any]:
    result = _candidate_summary(item)
    result.update(
        {
            "trigger_count": item.trigger_count,
            "unique_trigger_count": item.unique_trigger_count,
            "sender_count": item.sender_count,
            "conversation_count": item.conversation_count,
            "evidence_count": item.evidence_count,
            "channels": item.channels[:8],
            "family_counts": item.family_counts,
            "market_summary": item.market_summary,
            "market_points": [point.model_dump(mode="json") for point in item.market_points[-8:]],
            "themes": [_theme_summary(theme) for theme in item.themes[:5]],
            "recognition_reasons": _clip_list(item.recognition.reasons, 4, 160),
            "recognition_missing": _clip_list(item.recognition.missing_evidence, 4, 160),
            "review": item.review.model_dump(mode="json"),
            "evidence_chain": [
                {
                    "message_id": evidence.message_id,
                    "time": evidence.time,
                    "type": evidence.type,
                    "sender": evidence.sender,
                    "group_name": evidence.group_name,
                    "evidence": _clip(evidence.evidence, 220),
                }
                for evidence in item.evidence_chain[:8]
            ],
        }
    )
    return result


def _theme_summary(theme: Any | None) -> dict[str, Any] | None:
    if theme is None:
        return None
    return {
        "theme_name": theme.theme_name,
        "theme_type": theme.theme_type,
        "role": theme.role,
        "quality_label": theme.quality_label,
        "confidence": theme.confidence,
        "source_count": theme.source_count,
        "stock_return_5d": theme.stock_return_5d,
        "stock_return_20d": theme.stock_return_20d,
        "amount_ratio_5d": theme.amount_ratio_5d,
        "is_theme_leader": theme.is_theme_leader,
        "quality_reasons": _clip_list(theme.quality_reasons, 3, 120),
    }


def _item_theme(item: StockEvidenceChainItem) -> Any | None:
    return item.primary_theme or (item.themes[0] if item.themes else None)


def _item_theme_name(item: StockEvidenceChainItem) -> str | None:
    theme = _item_theme(item)
    return theme.theme_name if theme else None


def _match_stock_items(items: list[StockEvidenceChainItem], stock: str) -> list[StockEvidenceChainItem]:
    stock_key = stock.upper()
    return [item for item in items if stock_key in item.ts_code.upper() or stock in item.stock_name]


def _stock_stage_counts(items: list[StockEvidenceChainItem]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        counts[item.stage] = counts.get(item.stage, 0) + 1
    return counts


def _stock_chart_summary(candles: list[Any]) -> dict[str, Any]:
    if not candles:
        return {}
    first = candles[0]
    latest = candles[-1]
    high_close = max(candles, key=lambda item: item.close)
    low_close = min(candles, key=lambda item: item.close)
    latest_amount = getattr(latest, "amount", None)
    avg5_amount = _average_amount(candles[-5:])
    avg20_amount = _average_amount(candles[-20:])
    return {
        "first_trade_date": first.trade_date,
        "latest_trade_date": latest.trade_date,
        "latest_close": latest.close,
        "latest_pct_chg": getattr(latest, "pct_chg", None),
        "return_from_first": _rate(latest.close, first.close),
        "return_from_low_close": _rate(latest.close, low_close.close),
        "drawdown_from_high_close": _rate(latest.close, high_close.close),
        "high_close_trade_date": high_close.trade_date,
        "high_close": high_close.close,
        "low_close_trade_date": low_close.trade_date,
        "low_close": low_close.close,
        "latest_amount": latest_amount,
        "avg5_amount": avg5_amount,
        "avg20_amount": avg20_amount,
        "latest_amount_vs_avg20": _rate(latest_amount, avg20_amount),
    }


def _average_amount(candles: list[Any]) -> float | None:
    values = [float(item.amount) for item in candles if getattr(item, "amount", None) is not None]
    if not values:
        return None
    return round(sum(values) / len(values), 4)


def _rate(current: float | None, base: float | None) -> float | None:
    if current is None or base is None or base == 0:
        return None
    return round((current - base) / base, 4)


def _clip(value: str | None, limit: int) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if len(text) <= limit:
        return text
    return f"{text[:limit].rstrip()}..."


def _clip_list(values: list[str], count: int, limit: int) -> list[str]:
    return [item for item in (_clip(value, limit) for value in values[:count]) if item]


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


def _object_schema(properties: dict[str, Any], *, required: list[str] | None = None) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": required or [],
        "additionalProperties": False,
    }
