from __future__ import annotations

import json

from radar.core.chat.skills import ChatSkillLibrary
from radar.core.config import RadarConfig
from radar.core.llm import chat_json
from radar.core.usecases.catalyst_strategy.models import CatalystStockAnalysis, CatalystStockContext

VALUATION_TERMS = (
    "订单",
    "签单",
    "合同",
    "收入",
    "营收",
    "利润",
    "净利率",
    "毛利率",
    "产能",
    "交付",
    "客户",
    "pe",
    "PE",
    "估值",
    "目标价",
    "市值",
    "亿",
)


def analyze_stock_context(
    config: RadarConfig,
    context: CatalystStockContext,
    *,
    provider_name: str | None = None,
    model: str | None = None,
) -> CatalystStockAnalysis:
    valuation_allowed = _has_valuation_clues(context)
    messages = [
        {"role": "system", "content": _system_prompt(config, valuation_allowed=valuation_allowed)},
        {"role": "user", "content": _user_prompt(context, valuation_allowed=valuation_allowed)},
    ]
    try:
        raw = chat_json(
            config,
            messages,
            provider_name=provider_name,
            task="chat",
            model=model,
            disable_thinking=True,
        )
    except Exception as error:
        return CatalystStockAnalysis(
            stock_key=context.stock_key,
            ts_code=context.ts_code,
            stock_name=context.stock_name,
            summary=[f"AI 分析失败：{str(error)[:160]}"],
            valuation_status="error",
            valuation_text="",
        )
    return _analysis_from_json(context, raw, valuation_allowed=valuation_allowed)


def _system_prompt(config: RadarConfig, *, valuation_allowed: bool) -> str:
    skill = ChatSkillLibrary.from_config(config).get("investment-valuation")
    skill_text = skill.instructions if skill else ""
    valuation_rule = (
        "原文包含经营或估值数字；足够支撑利润预测和 PE 锚定时返回 provided，只有单票强数字时返回 scenario。"
        if valuation_allowed
        else "原文缺少可量化经营/估值数据，valuation_status 必须返回 skipped，不得硬凑目标价。"
    )
    return f"""你是 radar 的催化词策略分析器。只基于用户提供的本地消息证据和市场快照回答。

要求：
- 输出 JSON object，不要输出 Markdown。
- summary 固定为 3 句中文短句，每句不超过 60 字。
- summary 第 1 句写该标的是谁提出的、因什么事件被提出。
- summary 第 2 句写核心催化和产业链位置，避免泛泛说“受益行业景气”。
- summary 第 3 句写最需要验证的事实或最关键市场快照；不要把“缺少可量化数据/无法估值”放进 summary。
- 不要输出买卖建议或仓位建议。
- 区分原文事实、市场数据和推断。
- 原文经常只是会议、推荐列表或单点催化；先给证据评级和验证缺口，再决定是否进入估值。
- scenario 只用于明确归属于该公司的单票强数字，例如订单/合同/中标金额、利润/业绩预告、产能/出货、价格涨幅、客户金额。
- 数字若只是会议号、日期、行业规模、板块总 capex、股价涨幅、市值口号或推荐名单，不得 scenario，必须 skipped。
- scenario 的 valuation_text 必须按顺序写：已知事实；市场底稿；假设桥；反推验证；待补证据。
- 假设桥要给区间，不给单点，例如订单转收入比例、净利率、收入确认周期；如果没有订单金额，就只写反推验证，不编数字。
- 反推验证要引用 market_snapshot 的估算市值、PE TTM、隐含 TTM 利润、最近财报营收/净利，判断当前估值需要多少利润支撑。
- scenario 不得给目标价、目标市值、上涨空间，target_market_cap_yi/target_price/upside_pct 必须为 null。
- skipped 不是不分析；skipped 时 valuation_text 用 investment-valuation skill 写清已知事实、缺失字段、下一步验证，不给目标价。
- {valuation_rule}

JSON schema:
{{
  "summary": ["句子1", "句子2", "句子3"],
  "valuation_status": "provided|scenario|skipped",
  "valuation_text": "provided 写估值推演；scenario 写情景推演和反推验证；skipped 写明缺什么",
  "target_market_cap_yi": 123.4,
  "target_price": 12.3,
  "upside_pct": 25.6,
  "confidence": "高|中|低",
  "risks": ["风险1", "风险2"]
}}

investment-valuation skill:
{skill_text}
"""


def _user_prompt(context: CatalystStockContext, *, valuation_allowed: bool) -> str:
    payload = {
        "stock": {
            "stock_key": context.stock_key,
            "ts_code": context.ts_code,
            "stock_name": context.stock_name,
        },
        "valuation_allowed": valuation_allowed,
        "market_snapshot": context.market_snapshot.model_dump(mode="json") if context.market_snapshot else None,
        "evidence": [item.model_dump(mode="json") for item in context.evidence[:12]],
    }
    return "请分析下面这个由催化词筛选出的股票上下文：\n" + json.dumps(
        payload,
        ensure_ascii=False,
        indent=2,
    )


def _analysis_from_json(
    context: CatalystStockContext,
    raw: dict[str, object],
    *,
    valuation_allowed: bool,
) -> CatalystStockAnalysis:
    summary = [_clip(item, 80) for item in _string_list(raw.get("summary"))[:3]]
    status = str(raw.get("valuation_status") or "skipped").strip()
    if status not in {"provided", "scenario", "skipped"}:
        status = "skipped"
    if not valuation_allowed:
        status = "skipped"
    return CatalystStockAnalysis(
        stock_key=context.stock_key,
        ts_code=context.ts_code,
        stock_name=context.stock_name,
        summary=summary or ["未生成有效总结。"],
        valuation_status=status,
        valuation_text=_clip(raw.get("valuation_text"), 1200),
        target_market_cap_yi=_float(raw.get("target_market_cap_yi")) if status == "provided" else None,
        target_price=_float(raw.get("target_price")) if status == "provided" else None,
        upside_pct=_float(raw.get("upside_pct")) if status == "provided" else None,
        confidence=_optional_str(raw.get("confidence")),
        risks=[_clip(item, 80) for item in _string_list(raw.get("risks"))[:5]],
        raw_response=raw,
    )


def _has_valuation_clues(context: CatalystStockContext) -> bool:
    text = "\n".join(item.content for item in context.evidence)
    has_number = any(char.isdigit() for char in text)
    return has_number and any(term in text for term in VALUATION_TERMS)


def _string_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _clip(value: object, limit: int) -> str:
    text = "" if value is None else " ".join(str(value).split())
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "..."


def _float(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
