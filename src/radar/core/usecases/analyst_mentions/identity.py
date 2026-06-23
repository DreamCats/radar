from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass

_EMOJI_RE = re.compile("[\U0001f300-\U0001faff\u2600-\u27bf\ufe0f]")
_ZERO_WIDTH_RE = re.compile("[\u200b-\u200f\u202a-\u202e]")


@dataclass(frozen=True)
class AnalystIdentity:
    analyst_id: str
    display_name: str
    alias_key: str


def source_candidate(sender: str) -> str:
    value = " ".join(sender.split())
    return value or "未知来源"


def analyst_identity(source_name: str) -> AnalystIdentity:
    alias_key = alias_key_for(source_name)
    raw = f"analyst|{alias_key}"
    return AnalystIdentity(
        analyst_id="an_" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16],
        display_name=source_name,
        alias_key=alias_key,
    )


def alias_key_for(source_name: str) -> str:
    value = unicodedata.normalize("NFKC", source_name)
    value = _EMOJI_RE.sub("", value)
    value = _ZERO_WIDTH_RE.sub("", value)
    value = "".join(value.split())
    return value or "未知来源"


def mention_id(message_id: str, ts_code: str, extractor_version: str) -> str:
    raw = f"{message_id}|{ts_code}|{extractor_version}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()
