from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from radar.core.usecases.stock_evidence_chain.recognition import (
    StockEvidenceRecognitionContext,
    StockEvidenceThemeContext,
)

ReviewTone = Literal["success", "warning", "danger", "info", "muted"]


class StockEvidenceReviewContext(BaseModel):
    state: str = "evidence_gap"
    label: str = "证据不足"
    tone: ReviewTone = "info"
    action_label: str = "补证据"
    headline: str = "当前判断仍需要更多交叉验证。"
    reasons: list[str] = Field(default_factory=list)


def build_review_context(
    *,
    stage: str,
    stage_label: str,
    confidence: float | None,
    summary: str,
    unique_trigger_count: int,
    market_summary: dict[str, Any],
    market_points: list[dict[str, Any]],
    primary_theme: StockEvidenceThemeContext | None,
    recognition: StockEvidenceRecognitionContext,
) -> StockEvidenceReviewContext:
    metrics = _market_metrics(market_summary, market_points)
    if is_llm_output_invalid(summary=summary, confidence=confidence):
        return _review(
            "llm_error",
            "LLM异常需重跑",
            "danger",
            "重跑",
            "这条判断不是正常投研结论，先不要纳入排序决策。",
            ["LLM 返回了拒答、代码块或空置信度，说明本次生成质量不合格。"],
        )
    if _is_market_first(stage, recognition.state, metrics):
        return _review(
            "market_first",
            "市场先行消息滞后",
            "warning",
            "追确认",
            "价格已经先动，消息证据偏少，别误判成早期线索。",
            ["当前阶段仍偏早，但价格/量能已经给出较强确认。", "重点看后续是否有更多机构和主题扩散跟上。"],
        )
    if _is_one_day_pulse(metrics):
        return _review(
            "one_day_pulse",
            "单日脉冲待验证",
            "warning",
            "等持续",
            "单日大涨不能直接等同于趋势确认。",
            ["最新交易日涨幅和量能较强，但区间表现仍弱或尚未脱离低位。", "需要继续观察 2-3 个交易日是否放量承接。"],
        )
    if _is_price_rejected_diffusion(stage, recognition.state, metrics):
        return _review(
            "price_rejected_diffusion",
            "消息扩散被价格否决",
            "danger",
            "降权",
            "大家在传，但价格和相对强度没有配合。",
            ["消息扩散已经不弱，但区间收益、回撤或主题内强弱表现偏差。", "这类更适合复盘为什么市场不买账。"],
        )
    if recognition.state == "rejected":
        return _review(
            "narrative_rejected",
            "逻辑强市场不认",
            "danger",
            "先观察",
            "叙事讲得通，但资金暂时没有认可。",
            ["消息热度不低，但价格或主题强弱没有跟上。", "继续跟踪前先找市场不认可的原因。"],
        )
    if recognition.state in {"overheated", "pullback_after_pricing"} or stage == "crowded":
        return _review(
            "overheated_review",
            "已过热偏复盘",
            "warning",
            "防追高",
            "市场已经明显反映，优先看风险而不是追新机会。",
            ["短期涨幅、拥挤或回撤风险已经变成主要矛盾。"],
        )
    if recognition.state in {"confirmed", "just_confirmed"} and primary_theme is not None:
        return _review(
            "mainline_confirmed",
            "主线明确且市场确认",
            "success",
            "重点跟踪",
            "主题、价格和消息证据基本能互相支撑。",
            [f"主叙事为「{primary_theme.theme_name}」，市场认可状态为「{recognition.state_label}」。"],
        )
    if primary_theme is None and stage in {"spreading", "pricing", "crowded"}:
        return _review(
            "theme_missing",
            "主线未确认",
            "warning",
            "补主题",
            "阶段看起来偏后，但还缺清晰主题归属。",
            ["没有稳定主主题时，先按个股事件观察，不要直接当作板块主线。"],
        )
    if unique_trigger_count >= 6 and recognition.state == "unknown":
        return _review(
            "needs_market_validation",
            "消息热需补市场验证",
            "info",
            "补市场",
            "消息已经不少，但还缺价格、量能或主题强弱确认。",
            ["下一步优先看市场是否持续确认，而不是继续堆同类消息。"],
        )
    return _review(
        "evidence_gap",
        "证据不足",
        "muted",
        "补证据",
        f"{stage_label}判断仍需要更多交叉验证。",
        ["继续补主题归属、价格量能和后续催化兑现证据。"],
    )


def is_llm_output_invalid(*, summary: str, confidence: float | None) -> bool:
    text = summary.strip()
    if confidence is None:
        return True
    if not text:
        return True
    lowered = text.lower()
    return lowered.startswith("the request was rejected") or "```json" in lowered


def _review(
    state: str,
    label: str,
    tone: ReviewTone,
    action_label: str,
    headline: str,
    reasons: list[str],
) -> StockEvidenceReviewContext:
    return StockEvidenceReviewContext(
        state=state,
        label=label,
        tone=tone,
        action_label=action_label,
        headline=headline,
        reasons=reasons,
    )


def _market_metrics(market_summary: dict[str, Any], market_points: list[dict[str, Any]]) -> dict[str, float | None]:
    latest = market_points[-1] if market_points else {}
    return {
        "return_since_first": _float(market_summary.get("return_since_first_point")),
        "drawdown": _float(market_summary.get("drawdown_from_selected_high")),
        "latest_pct": _float(latest.get("pct_chg")) if isinstance(latest, dict) else None,
        "latest_amount_ratio": _float(latest.get("amount_ratio_5d")) if isinstance(latest, dict) else None,
    }


def _is_market_first(stage: str, recognition_state: str, metrics: dict[str, float | None]) -> bool:
    if stage not in {"seed", "formed", "lead"} or recognition_state not in {"confirmed", "just_confirmed", "overheated"}:
        return False
    return_since_first = metrics["return_since_first"]
    return return_since_first is not None and return_since_first >= 0.18


def _is_one_day_pulse(metrics: dict[str, float | None]) -> bool:
    latest_pct = metrics["latest_pct"]
    latest_amount_ratio = metrics["latest_amount_ratio"]
    return_since_first = metrics["return_since_first"]
    return (
        latest_pct is not None
        and latest_pct >= 7
        and latest_amount_ratio is not None
        and latest_amount_ratio >= 1.5
        and (return_since_first is None or return_since_first < 0.05)
    )


def _is_price_rejected_diffusion(stage: str, recognition_state: str, metrics: dict[str, float | None]) -> bool:
    if stage not in {"spreading", "pricing", "crowded"} or recognition_state != "rejected":
        return False
    return_since_first = metrics["return_since_first"]
    drawdown = metrics["drawdown"]
    return (return_since_first is not None and return_since_first < 0.05) or (drawdown is not None and drawdown <= -0.12)


def _float(value: object) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None
