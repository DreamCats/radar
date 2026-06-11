from __future__ import annotations

import json
import re
import sqlite3
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from radar.core.config import RadarConfig
from radar.core.llm import chat
from radar.core.storage import connect, init_db
from radar.core.usecases.stock_evidence_chain.lifecycle_hashes import (
    HASH_CHANGE_LABELS,
    change_reason,
    changed_hashes,
    current_package_hash,
    evidence_hashes,
    optional_hash,
)
from radar.core.usecases.stock_evidence_chain.lifecycle_models import (
    LIFECYCLE_DIGEST_SCOPE_TYPE,
    LifecycleDigestHashes,
    LifecycleDigestPreview,
    LifecycleDigestPreviewItem,
    LifecycleDigestRunResult,
)
from radar.core.usecases.stock_evidence_chain.lifecycle_package import PROMPT_VERSION, evidence_package
from radar.core.usecases.stock_evidence_chain.views import StockEvidenceChainItem, latest_stock_evidence_chain

DEFAULT_LIMIT = 120
DEFAULT_SCAN_LIMIT = 120


@dataclass(frozen=True)
class _DigestTask:
    item: StockEvidenceChainItem
    scope_key: str
    package: dict[str, Any]
    evidence_signature: str
    hashes: LifecycleDigestHashes
    changed_hashes: tuple[str, ...]
    action: str
    reason: str
    reusable: dict[str, Any] | None


@dataclass(frozen=True)
class _TaskSet:
    as_of_time: datetime | None
    scanned_count: int
    processable_count: int
    skipped_count: int
    tasks: list[_DigestTask]


def preview_lifecycle_digests(
    config: RadarConfig,
    *,
    limit: int = DEFAULT_LIMIT,
    force: bool = False,
) -> LifecycleDigestPreview:
    task_set = _load_tasks(config, limit=limit, force=force)
    items = [_preview_item(task) for task in task_set.tasks]
    pending = len([task for task in task_set.tasks if task.action == "generate"])
    skipped = task_set.skipped_count + len([task for task in task_set.tasks if task.action == "skip"])
    return LifecycleDigestPreview(
        as_of_time=task_set.as_of_time,
        scanned_count=task_set.scanned_count,
        processable_count=task_set.processable_count,
        pending_count=pending,
        skipped_count=skipped,
        estimated_llm_calls=pending,
        items=items,
    )


def refresh_lifecycle_digests(
    config: RadarConfig,
    *,
    limit: int = DEFAULT_LIMIT,
    force: bool = False,
    provider_names: list[str | None] | None = None,
    model: str | None = None,
    llm_workers: int = 16,
    llm_max_tokens: int = 1600,
    llm_temperature: float = 0.2,
) -> LifecycleDigestRunResult:
    task_set = _load_tasks(config, limit=limit, force=force)
    conn = connect(config.database_path)
    try:
        init_db(conn)
        providers = provider_names or [None]
        generated = 0
        reused = 0
        failed = 0
        skipped = task_set.skipped_count
        futures = {}
        with ThreadPoolExecutor(max_workers=max(llm_workers, 1)) as pool:
            for index, task in enumerate(task_set.tasks):
                if task.action == "skip":
                    skipped += 1
                    continue
                if task.action == "reuse" and task.reusable is not None:
                    _save_digest(conn, task=task, digest=task.reusable, provider=None, model=None)
                    reused += 1
                    continue
                provider = providers[index % len(providers)]
                futures[
                    pool.submit(
                        _generate_digest,
                        config,
                        task.package,
                        provider,
                        model,
                        llm_max_tokens,
                        llm_temperature,
                    )
                ] = (task, provider)
            for future in as_completed(futures):
                task, provider = futures[future]
                try:
                    digest = future.result()
                    _save_digest(conn, task=task, digest=digest, provider=provider, model=model)
                    generated += 1
                except Exception:
                    failed += 1
        return LifecycleDigestRunResult(
            as_of_time=task_set.as_of_time,
            scanned_count=task_set.scanned_count,
            processable_count=task_set.processable_count,
            pending_count=len([task for task in task_set.tasks if task.action == "generate"]),
            generated_count=generated,
            reused_count=reused,
            skipped_count=skipped,
            failed_count=failed,
            rerun_reason_counts=_rerun_reason_counts(task_set.tasks),
        )
    finally:
        conn.close()


def _load_tasks(config: RadarConfig, *, limit: int, force: bool) -> _TaskSet:
    scan_limit = max(DEFAULT_SCAN_LIMIT, limit * 4)
    dashboard = latest_stock_evidence_chain(config, limit=scan_limit)
    conn = connect(config.database_path)
    try:
        init_db(conn)
        tasks: list[_DigestTask] = []
        skipped_count = 0
        processable_count = 0
        for item in dashboard.items:
            theme = item.primary_theme
            if processable_count >= limit:
                break
            processable_count += 1
            package = evidence_package(item, as_of_time=dashboard.as_of_time)
            hashes = evidence_hashes(package)
            signature = hashes.lifecycle_package_hash
            scope_key = f"{theme.theme_id}:{item.ts_code}" if theme is not None else f"stock:{item.ts_code}"
            current = _current_digest(conn, dashboard.as_of_time, scope_key)
            reusable = None if force else _reusable_digest(conn, scope_key, signature)
            changed = changed_hashes(current, hashes) if current else ()
            if force:
                action = "generate"
                reason = "强制重跑"
                changed = ("force",)
            elif current and current_package_hash(current) == signature:
                action = "skip"
                reason = "证据未变化"
            elif reusable is not None:
                action = "reuse"
                reason = "复用相同证据摘要"
            else:
                action = "generate"
                if current is not None:
                    reason = change_reason(changed)
                else:
                    changed = ("missing",)
                    reason = "缺少生命周期摘要"
            tasks.append(
                _DigestTask(
                    item=item,
                    scope_key=scope_key,
                    package=package,
                    evidence_signature=signature,
                    hashes=hashes,
                    changed_hashes=changed,
                    action=action,
                    reason=reason,
                    reusable=reusable,
                )
            )
        return _TaskSet(
            as_of_time=dashboard.as_of_time,
            scanned_count=len(dashboard.items),
            processable_count=processable_count,
            skipped_count=skipped_count,
            tasks=tasks,
        )
    finally:
        conn.close()


def _preview_item(task: _DigestTask) -> LifecycleDigestPreviewItem:
    theme = task.item.primary_theme
    return LifecycleDigestPreviewItem(
        scope_key=task.scope_key,
        ts_code=task.item.ts_code,
        stock_name=task.item.stock_name,
        theme_id=theme.theme_id if theme else None,
        theme_name=theme.theme_name if theme else None,
        stage_label=task.item.stage_label,
        recognition_label=task.item.recognition.state_label,
        action=task.action,
        reason=task.reason,
        evidence_signature=task.evidence_signature,
        hashes=task.hashes,
        changed_hashes=list(task.changed_hashes),
    )


def _rerun_reason_counts(tasks: list[_DigestTask]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for task in tasks:
        if task.action != "generate":
            continue
        keys = task.changed_hashes or ("lifecycle_package_hash",)
        for key in keys:
            label = HASH_CHANGE_LABELS.get(key, key)
            counts[label] = counts.get(label, 0) + 1
    return counts


def _current_digest(conn: sqlite3.Connection, as_of_time: datetime | None, scope_key: str) -> dict[str, Any] | None:
    if as_of_time is None:
        return None
    row = conn.execute(
        """
        SELECT
            evidence_signature, message_hash, market_hash, theme_hash,
            recognition_hash, backtest_hash, lifecycle_package_hash, digest_json
        FROM opportunity_lifecycle_digests
        WHERE as_of_time = ?
          AND scope_type = ?
          AND scope_key = ?
          AND prompt_version = ?
        ORDER BY updated_at DESC
        LIMIT 1
        """,
        (as_of_time.isoformat(), LIFECYCLE_DIGEST_SCOPE_TYPE, scope_key, PROMPT_VERSION),
    ).fetchone()
    if row is None:
        return None
    digest = _safe_json(row["digest_json"])
    digest["evidence_signature"] = str(row["evidence_signature"])
    digest["message_hash"] = optional_hash(row["message_hash"])
    digest["market_hash"] = optional_hash(row["market_hash"])
    digest["theme_hash"] = optional_hash(row["theme_hash"])
    digest["recognition_hash"] = optional_hash(row["recognition_hash"])
    digest["backtest_hash"] = optional_hash(row["backtest_hash"])
    digest["lifecycle_package_hash"] = optional_hash(row["lifecycle_package_hash"])
    return digest


def _reusable_digest(conn: sqlite3.Connection, scope_key: str, signature: str) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT digest_json
        FROM opportunity_lifecycle_digests
        WHERE scope_type = ?
          AND scope_key = ?
          AND prompt_version = ?
          AND (lifecycle_package_hash = ? OR evidence_signature = ?)
        ORDER BY updated_at DESC
        LIMIT 1
        """,
        (LIFECYCLE_DIGEST_SCOPE_TYPE, scope_key, PROMPT_VERSION, signature, signature),
    ).fetchone()
    return _safe_json(row["digest_json"]) if row is not None else None


def _generate_digest(
    config: RadarConfig,
    package: dict[str, Any],
    provider_name: str | None,
    model: str | None,
    max_tokens: int,
    temperature: float,
) -> dict[str, Any]:
    text = chat(
        config,
        [
            {"role": "system", "content": _system_prompt()},
            {"role": "user", "content": _user_prompt(package)},
        ],
        provider_name=provider_name,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        disable_thinking=True,
    )
    result = _parse_json(text)
    result["raw_text"] = text
    return result


def _system_prompt() -> str:
    return (
        "你是个人投资者的机会生命周期复盘助手。只能基于给定结构化证据梳理，"
        "不补外部新闻，不给买卖建议，不重新发明阶段。输出严格 JSON object。"
    )


def _user_prompt(package: dict[str, Any]) -> str:
    return "\n".join(
        [
            "请把下面证据包梳理成机会生命周期摘要。",
            "重点回答：这个个股机会走到哪一步、为什么、缺什么、下一步看什么；如果缺主题归属或 review 已标记风险，要显式写进缺口或风险。",
            "不要改变证据包里已有的阶段、市场认可和 review 结论，只解释它们之间的关系。",
            "",
            "输出 JSON schema：",
            "{",
            '  "one_line": "一句话机会生命周期判断",',
            '  "timeline": ["最多5条，按时间串起机会路径"],',
            '  "stage_reason": ["最多4条，解释为什么当前阶段成立或不充分"],',
            '  "missing_evidence": ["缺失证据或反证"],',
            '  "risk": ["追高、拥挤、主题不扩散、市场不认等风险"],',
            '  "next_watch": ["接下来应该观察的证据"]',
            "}",
            "",
            "证据包 JSON：",
            json.dumps(package, ensure_ascii=False, sort_keys=True),
        ]
    )


def _save_digest(
    conn: sqlite3.Connection,
    *,
    task: _DigestTask,
    digest: dict[str, Any],
    provider: str | None,
    model: str | None,
) -> None:
    now = datetime.now().isoformat()
    item = task.item
    theme = item.primary_theme
    payload = _normalized_digest(digest, item)
    conn.execute(
        """
        INSERT INTO opportunity_lifecycle_digests (
            digest_id, as_of_time, scope_type, scope_key, ts_code, stock_name,
            theme_id, theme_name, stage, recognition_state, evidence_signature,
            message_hash, market_hash, theme_hash, recognition_hash, backtest_hash,
            lifecycle_package_hash, prompt_version, llm_provider, model, digest_json,
            created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(as_of_time, scope_type, scope_key, prompt_version) DO UPDATE SET
            stock_name = excluded.stock_name,
            theme_id = excluded.theme_id,
            theme_name = excluded.theme_name,
            stage = excluded.stage,
            recognition_state = excluded.recognition_state,
            evidence_signature = excluded.evidence_signature,
            message_hash = excluded.message_hash,
            market_hash = excluded.market_hash,
            theme_hash = excluded.theme_hash,
            recognition_hash = excluded.recognition_hash,
            backtest_hash = excluded.backtest_hash,
            lifecycle_package_hash = excluded.lifecycle_package_hash,
            llm_provider = excluded.llm_provider,
            model = excluded.model,
            digest_json = excluded.digest_json,
            updated_at = excluded.updated_at
        """,
        (
            uuid.uuid4().hex,
            str(task.package.get("as_of_time") or ""),
            LIFECYCLE_DIGEST_SCOPE_TYPE,
            task.scope_key,
            item.ts_code,
            item.stock_name,
            theme.theme_id if theme else None,
            theme.theme_name if theme else None,
            item.stage,
            item.recognition.state,
            task.evidence_signature,
            task.hashes.message_hash,
            task.hashes.market_hash,
            task.hashes.theme_hash,
            task.hashes.recognition_hash,
            task.hashes.backtest_hash,
            task.hashes.lifecycle_package_hash,
            PROMPT_VERSION,
            provider,
            model,
            json.dumps(payload, ensure_ascii=False, sort_keys=True),
            now,
            now,
        ),
    )
    conn.commit()


def _normalized_digest(digest: dict[str, Any], item: StockEvidenceChainItem) -> dict[str, Any]:
    return {
        "one_line": _text(digest.get("one_line")) or item.summary,
        "timeline": _string_list(digest.get("timeline")),
        "stage_reason": _string_list(digest.get("stage_reason")) or item.why[:4],
        "missing_evidence": _string_list(digest.get("missing_evidence")) or item.recognition.missing_evidence[:4],
        "risk": _string_list(digest.get("risk")),
        "next_watch": _string_list(digest.get("next_watch")) or item.watch_next[:4],
        "raw_text": _text(digest.get("raw_text")),
    }


def _parse_json(text: str) -> dict[str, Any]:
    raw = _strip_json_fence(text.strip())
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if not match:
            return {}
        try:
            parsed = json.loads(match.group(0))
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}


def _strip_json_fence(text: str) -> str:
    if not text.startswith("```"):
        return text
    lines = text.splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _safe_json(text: object) -> dict[str, Any]:
    try:
        parsed = json.loads(str(text or "{}"))
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        return {}


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _text(value: object) -> str:
    return str(value).strip() if value is not None else ""
