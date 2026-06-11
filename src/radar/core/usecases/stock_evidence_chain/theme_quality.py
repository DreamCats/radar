from __future__ import annotations

from datetime import datetime
from typing import Any

from radar.core.market_theme_rules import is_generic_theme_name, is_specific_theme_name

ROLE_PRIORITY = {"core": 3, "elastic": 2, "unknown": 1}
TYPE_PRIORITY = {"theme": 4, "concept": 3, "industry": 2, "stock": 1}

BROAD_THEME_MEMBERS = 180
VERY_BROAD_THEME_MEMBERS = 300
FRESH_DAYS = 7
STALE_DAYS = 45


def apply_theme_quality(
    selected: dict[str, list[Any]],
    *,
    as_of: datetime | None,
) -> None:
    for themes in selected.values():
        for item in themes:
            _apply_item_quality(item, as_of=as_of)
        themes.sort(key=theme_sort_key)


def theme_sort_key(item: Any) -> tuple[float, int, int, float, int, str]:
    return (
        -float(getattr(item, "quality_score", 0) or 0),
        -ROLE_PRIORITY.get(str(getattr(item, "role", "")), 0),
        -int(getattr(item, "source_count", 0) or 0),
        -float(getattr(item, "confidence", 0) or 0),
        -TYPE_PRIORITY.get(str(getattr(item, "theme_type", "")), 0),
        str(getattr(item, "theme_name", "")),
    )


def is_primary_theme_candidate(item: Any) -> bool:
    score = float(getattr(item, "quality_score", 0) or 0)
    source_count = int(getattr(item, "source_count", 0) or 0)
    confidence = float(getattr(item, "confidence", 0) or 0)
    theme_name = str(getattr(item, "theme_name", ""))
    is_broad = bool(getattr(item, "is_broad_theme", False))
    is_leader = bool(getattr(item, "is_theme_leader", False))
    if score >= 0.72:
        return True
    if score >= 0.62 and source_count >= 2 and (not is_broad or is_leader):
        return True
    if score >= 0.58 and is_specific_theme_name(theme_name) and is_leader and not is_broad:
        return True
    return score >= 0.58 and confidence >= 0.78 and is_leader


def theme_missing_summary(themes: list[Any]) -> str:
    if not themes:
        return "缺主题归属，无法判断是否处在市场主线里"
    parts: list[str] = []
    for item in themes[:3]:
        warnings = list(getattr(item, "quality_warnings", []) or [])
        label = str(getattr(item, "quality_label", "待确认"))
        reason = "、".join(warnings[:2]) if warnings else label
        parts.append(f"{getattr(item, 'theme_name', '主题')}：{reason}")
    return "主叙事暂不确定；" + "；".join(parts)


def _apply_item_quality(item: Any, *, as_of: datetime | None) -> None:
    score, reasons, warnings = _quality_parts(item, as_of=as_of)
    bounded = max(0.0, min(1.0, score))
    item.quality_score = round(bounded, 2)
    item.quality_label = _quality_label(bounded)
    item.quality_reasons = reasons[:4]
    item.quality_warnings = warnings[:4]
    item.is_broad_theme = _is_broad_theme(item)


def _quality_parts(item: Any, *, as_of: datetime | None) -> tuple[float, list[str], list[str]]:
    score = 0.0
    reasons: list[str] = []
    warnings: list[str] = []

    role = str(getattr(item, "role", "unknown"))
    source_count = int(getattr(item, "source_count", 0) or 0)
    confidence = float(getattr(item, "confidence", 0) or 0)
    theme_type = str(getattr(item, "theme_type", ""))
    theme_name = str(getattr(item, "theme_name", ""))
    member_count = _int_or_none(getattr(item, "member_count", None))
    covered_count = _int_or_none(getattr(item, "covered_member_count", None))
    return_rank = _int_or_none(getattr(item, "return_rank_5d", None))
    stock_return_5d = _float_or_none(getattr(item, "stock_return_5d", None))

    score += {"core": 0.28, "elastic": 0.18}.get(role, 0.04)
    score += min(source_count, 4) * 0.08
    score += min(confidence, 1.0) * 0.22
    score += {"theme": 0.08, "concept": 0.06, "industry": 0.04}.get(theme_type, 0.0)

    if is_specific_theme_name(theme_name):
        score += 0.08
        reasons.append("主题名是具体可投资叙事")
    elif is_generic_theme_name(theme_name):
        score -= 0.08
        warnings.append("主题名称偏泛，不能单独当主线")

    if source_count >= 2:
        reasons.append(f"跨来源归属：{source_count} 个来源")
    else:
        warnings.append("单来源归属，容易只是弱关联")

    recency = _days_since(getattr(item, "latest_trade_date", None), as_of=as_of)
    if recency is not None:
        if recency <= FRESH_DAYS:
            score += 0.08
            reasons.append("近期仍在市场 anchor 中出现")
        elif recency > STALE_DAYS:
            score -= 0.08
            warnings.append(f"主题归属已 {recency} 天未更新")

    if member_count is not None:
        if member_count >= VERY_BROAD_THEME_MEMBERS:
            score -= 0.14
            warnings.append(f"主题过宽：约 {member_count} 只成分")
        elif member_count >= BROAD_THEME_MEMBERS:
            score -= 0.08
            warnings.append(f"主题偏宽：约 {member_count} 只成分")
        elif 8 <= member_count <= 80:
            score += 0.08
            reasons.append(f"主题成分规模可比：{member_count} 只")
        elif member_count <= 160:
            score += 0.03
            reasons.append(f"主题成分规模可比：{member_count} 只")
        elif member_count <= 3:
            warnings.append("主题成分太少，可能只是临时组合")

    if member_count and covered_count is not None and covered_count / member_count < 0.35:
        warnings.append("主题内行情覆盖不足")

    if return_rank and member_count:
        if bool(getattr(item, "is_theme_leader", False)):
            score += 0.12
            reasons.append(f"该股处在主题 5 日强弱前列：{return_rank}/{member_count}")
        elif bool(getattr(item, "is_theme_laggard", False)):
            score -= 0.10
            warnings.append(f"主题内强弱偏后：{return_rank}/{member_count}")

    if stock_return_5d is not None:
        if stock_return_5d >= 0.05:
            score += 0.06
            reasons.append("个股 5 日表现开始配合主题")
        elif stock_return_5d <= -0.05:
            score -= 0.06
            warnings.append("个股 5 日表现拖累主题确认")

    if not reasons:
        warnings.append("缺少能支撑主线的强证据")
    return score, _dedupe(reasons), _dedupe(warnings)


def _quality_label(score: float) -> str:
    if score >= 0.72:
        return "主线候选"
    if score >= 0.58:
        return "可参考"
    if score >= 0.42:
        return "弱关联"
    return "待确认"


def _is_broad_theme(item: Any) -> bool:
    member_count = _int_or_none(getattr(item, "member_count", None))
    return member_count is not None and member_count >= BROAD_THEME_MEMBERS


def _days_since(value: Any, *, as_of: datetime | None) -> int | None:
    text = str(value or "").strip()
    if not text or as_of is None:
        return None
    try:
        if len(text) == 8 and text.isdigit():
            latest = datetime.strptime(text, "%Y%m%d")
        else:
            latest = datetime.fromisoformat(text)
    except ValueError:
        return None
    return max(0, (as_of.date() - latest.date()).days)


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _float_or_none(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(item for item in values if item))
