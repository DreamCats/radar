from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass


@dataclass(frozen=True)
class ThemeNormalization:
    theme_key: str
    theme_name: str
    theme_type: str
    aliases: tuple[str, ...]


@dataclass(frozen=True)
class _ThemeRule:
    name: str
    keywords: tuple[str, ...]
    required_any: tuple[str, ...] = ()


SPECIFIC_THEME_RULES: tuple[_ThemeRule, ...] = (
    _ThemeRule("MLCC", ("mlcc", "钛酸钡", "配方粉")),
    _ThemeRule(
        "CPO/光通信",
        ("cpo", "光通信", "光通信设备", "光芯片", "硅光", "eml", "pam4", "cw-dfb", "cwdfb", "mpo"),
    ),
    _ThemeRule(
        "半导体设备",
        ("半导体设备", "设备零部件", "设备订单", "存储扩产", "晶圆厂扩产", "刻蚀", "薄膜沉积", "cmp设备", "清洗设备"),
    ),
    _ThemeRule(
        "半导体材料",
        (
            "半导体材料",
            "电子化学品",
            "湿电子化学品",
            "电子级",
            "光刻胶",
            "蚀刻液",
            "清洗剂",
            "显影液",
            "电子特气",
            "靶材",
            "硅片",
            "抛光液",
        ),
    ),
    _ThemeRule("PCB/先进封装", ("pcb", "ccl", "覆铜板", "玻璃基板", "先进封装", "abf", "载板")),
    _ThemeRule("算力电源", ("电源模块", "服务器电源", "数据中心供电", "巴拿马电源"), ("算力", "ai", "数据中心", "服务器", "阿里")),
    _ThemeRule("虚拟电厂", ("虚拟电厂",)),
    _ThemeRule("海风海缆", ("海风", "海缆", "海上风电")),
    _ThemeRule("锂矿/锂电材料", ("锂矿", "锂电池材料", "碳酸锂", "锂盐")),
    _ThemeRule("钨/小金属", ("金属钨", "钨钼", "仲钨酸铵", "钨粉", "小金属")),
)

GENERIC_THEME_NAMES = {
    "ai硬件",
    "半导体",
    "芯片",
    "国产芯片",
    "国产芯片概念",
    "中芯概念",
    "通信",
    "算力",
    "涨价",
    "涨价概念",
    "专用设备",
    "通用设备",
    "元件",
    "装饰材料",
}


def normalize_theme_anchor(name: str, anchor_type: str, reason: str | None = None) -> ThemeNormalization | None:
    raw_name = _clean_display_name(name)
    if not raw_name:
        return None
    specific_name = match_specific_theme(raw_name, reason)
    if specific_name:
        return ThemeNormalization(
            theme_key=canonical_theme_key(specific_name),
            theme_name=specific_name,
            theme_type="theme",
            aliases=(raw_name, specific_name),
        )
    return ThemeNormalization(
        theme_key=canonical_theme_key(raw_name),
        theme_name=raw_name,
        theme_type=anchor_type,
        aliases=(raw_name,),
    )


def match_specific_theme(name: str, reason: str | None = None) -> str | None:
    name_text = _compact_text(name)
    reason_text = _compact_text(reason or "")
    text = f"{name_text}{reason_text}"
    for rule in SPECIFIC_THEME_RULES:
        if rule.name == "CPO/光通信" and not _matches_cpo_rule(name_text, reason_text):
            continue
        if not any(_compact_text(keyword) in text for keyword in rule.keywords):
            continue
        if rule.required_any and not any(_compact_text(keyword) in text for keyword in rule.required_any):
            continue
        return rule.name
    return None


def is_generic_theme_name(name: str) -> bool:
    return canonical_theme_key(name) in {canonical_theme_key(item) for item in GENERIC_THEME_NAMES}


def is_specific_theme_name(name: str) -> bool:
    return canonical_theme_key(name) in {canonical_theme_key(rule.name) for rule in SPECIFIC_THEME_RULES}


def _matches_cpo_rule(name_text: str, reason_text: str) -> bool:
    if any(keyword in name_text for keyword in ("cpo", "mpo", "光通信", "光通信设备", "光芯片")):
        return True
    return any(keyword in reason_text for keyword in ("cpo", "eml", "pam4", "cwdfb", "硅光", "光芯片"))


def canonical_theme_key(name: str) -> str:
    text = unicodedata.normalize("NFKC", name).strip().lower()
    text = re.sub(r"[（(][^）)]*[）)]", "", text)
    parts = re.findall(r"[a-z0-9\u4e00-\u9fff]+", text)
    compact = "".join(parts)
    for suffix in ("概念板块", "行业板块", "概念", "板块", "指数"):
        if compact.endswith(suffix) and len(compact) > len(suffix):
            compact = compact[: -len(suffix)]
            break
    return compact


def _clean_display_name(name: str) -> str:
    text = unicodedata.normalize("NFKC", str(name or "")).strip()
    return re.sub(r"\s+", " ", text)


def _compact_text(value: str) -> str:
    return "".join(re.findall(r"[a-z0-9\u4e00-\u9fff]+", unicodedata.normalize("NFKC", value).lower()))
