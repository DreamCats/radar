from __future__ import annotations

from datetime import datetime, timezone

from radar.core.channel import BarkError, BarkMessage, push_bark
from radar.core.chat import ChatRun, ChatSessionStore
from radar.core.cloud import CloudUploadError
from radar.core.config import RadarConfig
from radar.core.storage.report_store import get_catalyst_valuation_report
from radar.core.storage.valuation_store import (
    ValuationMeasurement,
    record_valuation_publication,
    record_valuation_notification,
    save_valuation_measurement,
)
from radar.core.valuation.report import publish_valuation_measurement_html, write_valuation_measurement_html
from radar.core.valuation.upside_parser import parse_upside_measurement_items


def project_completed_valuation_run(config: RadarConfig, run: ChatRun) -> ValuationMeasurement | None:
    report_id = _upside_report_id(run)
    if report_id is None:
        return None

    report_detail = get_catalyst_valuation_report(config.reports_database_path, report_id)
    measured_at = _parse_time(run.updated_at) or datetime.now(timezone.utc).astimezone()
    assistant_content = _latest_assistant_content(config, run.session_id)
    if assistant_content is None:
        measurement = save_valuation_measurement(
            config.valuation_database_path,
            report_id=report_id,
            chat_run_id=run.run_id,
            session_id=run.session_id,
            source_generated_at=report_detail.generated_at if report_detail else None,
            measured_at=measured_at,
            parse_status="missing_message",
            parse_error="未找到 assistant 消息",
            items=[],
        )
        return measurement

    try:
        items, parse_error = parse_upside_measurement_items(assistant_content)
        parse_status = "ready" if items else "missing_table"
    except Exception as exc:
        items = []
        parse_status = "failed"
        parse_error = str(exc)[:1000]

    measurement = save_valuation_measurement(
        config.valuation_database_path,
        report_id=report_id,
        chat_run_id=run.run_id,
        session_id=run.session_id,
        source_generated_at=report_detail.generated_at if report_detail else None,
        measured_at=measured_at,
        parse_status=parse_status,
        parse_error=parse_error,
        items=items,
    )
    if measurement.parse_status == "ready" and measurement.positive_count > 0:
        measurement = _publish_positive_measurement(
            config,
            measurement,
            session_markdown=assistant_content,
            source_report_url=report_detail.published_url if report_detail else None,
        )
        if _structured_bark_enabled(report_detail):
            if measurement.published_url:
                measurement = _notify_positive_measurement(config, measurement, report_url=measurement.published_url)
            else:
                measurement = record_valuation_notification(
                    config.valuation_database_path,
                    measurement_id=measurement.measurement_id,
                    status="failed",
                    error_message=f"估值测算报告上传失败: {measurement.publish_error or '未生成公网 URL'}"[:1000],
                )
        else:
            measurement = record_valuation_notification(
                config.valuation_database_path,
                measurement_id=measurement.measurement_id,
                status="skipped",
                error_message="测算 Bark 未开启",
            )
    return measurement


def _publish_positive_measurement(
    config: RadarConfig,
    measurement: ValuationMeasurement,
    *,
    session_markdown: str,
    source_report_url: str | None,
) -> ValuationMeasurement:
    if not measurement.published_url:
        try:
            local_path = write_valuation_measurement_html(
                config,
                measurement,
                session_markdown=session_markdown,
                source_report_url=source_report_url,
            )
            published_url = publish_valuation_measurement_html(config, local_path, measurement=measurement)
        except CloudUploadError as exc:
            return record_valuation_publication(
                config.valuation_database_path,
                measurement_id=measurement.measurement_id,
                error_message=str(exc)[:1000],
            )
        measurement = record_valuation_publication(
            config.valuation_database_path,
            measurement_id=measurement.measurement_id,
            published_url=published_url,
        )
    return measurement


def _structured_bark_enabled(report_detail) -> bool:
    return bool(report_detail and report_detail.request.get("notify") is True)


def _notify_positive_measurement(
    config: RadarConfig,
    measurement: ValuationMeasurement,
    *,
    report_url: str | None,
) -> ValuationMeasurement:
    if measurement.notification_status == "succeeded":
        return measurement
    try:
        push_bark(
            config,
            BarkMessage(
                title=_positive_bark_title(measurement),
                subtitle=_positive_bark_subtitle(measurement),
                body=_positive_bark_body(measurement),
                url=report_url,
                group="radar-valuation",
                level="timeSensitive",
            ),
        )
    except BarkError as exc:
        return record_valuation_notification(
            config.valuation_database_path,
            measurement_id=measurement.measurement_id,
            status="failed",
            error_message=str(exc)[:1000],
        )
    return record_valuation_notification(
        config.valuation_database_path,
        measurement_id=measurement.measurement_id,
        status="succeeded",
    )


def _positive_bark_body(measurement: ValuationMeasurement) -> str:
    positives = [item for item in measurement.items if item.is_positive]
    if len(positives) == 1:
        item = positives[0]
        lines = [_item_label(item)]
        if item.key_validation:
            lines.append(f"验证：{_compact_text(item.key_validation, 72)}")
        return "\n".join(lines)
    lines = []
    for index, item in enumerate(positives[:3], start=1):
        parts = [_item_label(item)]
        if item.upside_text:
            parts.append(item.upside_text)
        if item.confidence:
            parts.append(f"确定性{item.confidence}")
        lines.append(f"{index}. {'｜'.join(parts)}")
    if len(positives) > 3:
        lines.append(f"另有 {len(positives) - 3} 个，点击查看完整测算报告")
    else:
        lines.append("点击查看完整测算报告")
    return "\n".join(lines)


def _positive_bark_title(measurement: ValuationMeasurement) -> str:
    positives = [item for item in measurement.items if item.is_positive]
    if len(positives) == 1:
        return f"Radar 估值测算｜{positives[0].name}"
    return f"Radar 估值测算｜{len(positives)} 个正向"


def _positive_bark_subtitle(measurement: ValuationMeasurement) -> str:
    positives = [item for item in measurement.items if item.is_positive]
    if not positives:
        return "无正向空间"
    first = positives[0]
    if len(positives) == 1:
        parts = []
        if first.upside_text:
            parts.append(first.upside_text)
        if first.valuation_status:
            parts.append(first.valuation_status)
        if first.confidence:
            parts.append(f"确定性{first.confidence}")
        return " · ".join(parts) or "正向空间"
    names = "、".join(item.name for item in positives[:3])
    return f"{names}{' 等' if len(positives) > 3 else ''}"


def _item_label(item) -> str:
    return f"{item.ts_code}｜{item.name}" if item.ts_code else item.name


def _compact_text(value: str, limit: int) -> str:
    text = " ".join(value.split())
    return text if len(text) <= limit else f"{text[:limit - 1]}…"


def _latest_assistant_content(config: RadarConfig, session_id: str) -> str | None:
    messages = ChatSessionStore.from_config(config).load_messages(session_id)
    for message in reversed(messages):
        if message.role == "assistant" and message.content.strip():
            return message.content
    return None


def _upside_report_id(run: ChatRun) -> str | None:
    if run.status != "completed":
        return None
    source_report_id = run.metadata.get("source_report_id")
    if isinstance(source_report_id, str) and source_report_id:
        return source_report_id
    if run.metadata.get("surface") != "估值线索":
        return None
    if run.metadata.get("title") != "估值线索空间测算":
        return None
    entity_id = run.metadata.get("entity_id")
    return entity_id if isinstance(entity_id, str) and entity_id else None


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None
