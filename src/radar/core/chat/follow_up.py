from __future__ import annotations

import re

_STOCK_WITH_CODE_RE = re.compile(
    r"([\u4e00-\u9fffA-Za-z][\u4e00-\u9fffA-Za-z0-9]{1,9})"
    r"\s*[（(]\s*\d{6}\.(?:SH|SZ|BJ)\s*[）)]"
)
_WHITESPACE_RE = re.compile(r"\s+")
_SUGGESTION_MAX_LENGTH = 72

_THEME_KEYWORDS = (
    "半导体",
    "AI算力",
    "AI硬件",
    "光刻胶",
    "机器人",
    "PCB",
    "存储",
    "电力设备",
    "有色",
    "医药",
    "军工",
    "消费电子",
)


def build_follow_up_suggestion(user_content: str, assistant_content: str) -> str | None:
    """根据刚完成的一轮回答生成一条下一问建议。

    这里故意用轻量规则，不额外调用 LLM，避免每轮回复后增加延迟和成本。
    """
    answer = _clean_text(assistant_content)
    if len(answer) < 12:
        return None

    stocks = _extract_stock_names(answer)
    if stocks:
        target = "、".join(stocks[:2])
        if _contains_any(answer, ("风险", "暂缓", "排雷", "回调")):
            return _fit(f"继续验证{target}的反证、行情位置和暂缓跟踪条件。")
        if _contains_any(answer, ("需要验证", "订单", "IPO", "客户", "业绩", "验证")):
            return _fit(f"继续补{target}的原文证据、行情确认和关键验证点。")
        return _fit(f"继续深挖{target}：证据链、市场确认和风险条件。")

    themes = [theme for theme in _THEME_KEYWORDS if theme in answer]
    if themes:
        return _fit(f"继续把{themes[0]}主线按标的、证据强度和风险分层。")

    if _contains_any(user_content, ("风险", "排雷", "暂缓")) or _contains_any(
        answer,
        ("风险提示", "暂缓", "反证"),
    ):
        return "把上面的风险按“立即暂缓、继续观察、可忽略”分层。"
    if _contains_any(answer, ("需要验证", "下一步", "还缺", "缺口")):
        return "把还缺的证据整理成下一步验证清单。"
    if _contains_any(answer, ("跟踪清单", "优先级", "候选", "排序")) or "|" in answer:
        return "从上面的清单里挑 1 个最高优先级对象继续深挖。"
    return "把上面的结论拆成证据、反证和下一步验证清单。"


def _extract_stock_names(text: str) -> list[str]:
    names: list[str] = []
    for match in _STOCK_WITH_CODE_RE.finditer(text):
        name = match.group(1).strip(" -—、，。:：#0123456789.")
        if name and name not in names:
            names.append(name)
    return names


def _contains_any(text: str, keywords: tuple[str, ...]) -> bool:
    return any(keyword in text for keyword in keywords)


def _clean_text(text: str) -> str:
    return _WHITESPACE_RE.sub(" ", text).strip()


def _fit(text: str) -> str:
    if len(text) <= _SUGGESTION_MAX_LENGTH:
        return text
    return f"{text[: _SUGGESTION_MAX_LENGTH - 1]}…"
