from __future__ import annotations

import hashlib
import json
from typing import Any

from radar.core.usecases.stock_evidence_chain.lifecycle_models import LifecycleDigestHashes

HASH_CHANGE_LABELS = {
    "message_hash": "消息变了",
    "market_hash": "市场变了",
    "theme_hash": "主题变了",
    "recognition_hash": "阶段/认可变了",
    "backtest_hash": "回测变了",
    "lifecycle_package_hash": "证据包变了",
    "force": "强制重跑",
    "missing": "缺少生命周期摘要",
}
PART_HASH_KEYS = ("message_hash", "market_hash", "theme_hash", "recognition_hash", "backtest_hash")


def evidence_signature(package: dict[str, Any]) -> str:
    raw = json.dumps(package, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def evidence_hashes(package: dict[str, Any]) -> LifecycleDigestHashes:
    return LifecycleDigestHashes(
        message_hash=hash_part(package.get("message_evidence")),
        market_hash=hash_part(package.get("market_evidence")),
        theme_hash=hash_part({"primary": package.get("theme"), "candidates": package.get("theme_candidates")}),
        recognition_hash=hash_part(
            {
                "stage": package.get("stage"),
                "recognition": package.get("recognition"),
                "review": package.get("review"),
                "risks": package.get("risks"),
            }
        ),
        backtest_hash=hash_part(None),
        lifecycle_package_hash=evidence_signature(package),
    )


def hash_part(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def current_package_hash(current: dict[str, Any]) -> str | None:
    return optional_hash(current.get("lifecycle_package_hash")) or optional_hash(current.get("evidence_signature"))


def changed_hashes(current: dict[str, Any] | None, hashes: LifecycleDigestHashes) -> tuple[str, ...]:
    if current is None:
        return ()
    current_hashes = hashes.model_dump()
    changed = [
        key
        for key in PART_HASH_KEYS
        if optional_hash(current.get(key)) is not None and optional_hash(current.get(key)) != current_hashes[key]
    ]
    if changed:
        return tuple(changed)
    if current_package_hash(current) != hashes.lifecycle_package_hash:
        return ("lifecycle_package_hash",)
    return ()


def change_reason(changed_keys: tuple[str, ...]) -> str:
    if not changed_keys:
        return "证据包变了"
    return " / ".join(HASH_CHANGE_LABELS.get(key, key) for key in changed_keys)


def optional_hash(value: object) -> str | None:
    text = str(value or "").strip()
    return text or None
