from __future__ import annotations

import hashlib
import re


_WECHAT_DECORATIVE_TOKEN_RE = re.compile(
    r"\[(?:玫瑰|礼物|强|握手|抱拳|合十|爱心|太阳|咖啡|庆祝|鼓掌|胜利|OK|ok)\]"
)
_UNICODE_EMOJI_RE = re.compile(r"[\ufe0e\ufe0f\U0001f300-\U0001faff]")
_LONG_CLUSTER_MESSAGE_MIN_CHARS = 40


def content_hash(content: str) -> str:
    normalized = normalize_content(content)
    return hashlib.sha1(normalized.encode("utf-8")).hexdigest()


def cluster_content_hash(contents: list[str]) -> str:
    # 同一组内容在不同群里可能先后顺序略有差异；排序后再哈希，避免重复来源分裂。
    parts = sorted(content_hash(content) for content in contents)
    return hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()


def cluster_dedupe_hash(contents: list[str]) -> str:
    if len(contents) == 1:
        return content_hash(contents[0])
    # 转发同一长正文时，有人会在 30 秒内补一句短评论；去重以最长正文为主。
    longest = max(contents, key=lambda content: len(normalize_content(content)))
    normalized = normalize_content(longest)
    if len(normalized) >= _LONG_CLUSTER_MESSAGE_MIN_CHARS:
        return content_hash(longest)
    return cluster_content_hash(contents)


def normalize_content(content: str) -> str:
    text = _WECHAT_DECORATIVE_TOKEN_RE.sub("", content)
    text = _UNICODE_EMOJI_RE.sub("", text)
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"\s+", "", text)
    text = re.sub(r"[，。！？!?,；;：:、…·~～_\-—=+*#@（）()\[\]【】\"'“”‘’]+", "", text)
    return text.lower()
