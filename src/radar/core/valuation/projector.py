from __future__ import annotations

from datetime import datetime, timezone

from radar.core.channel import BarkError, BarkMessage, push_bark
from radar.core.chat import ChatRun, ChatSessionStore
from radar.core.config import RadarConfig
from radar.core.storage.report_store import get_catalyst_valuation_report
from radar.core.storage.valuation_store import (
    ValuationMeasurement,
    record_valuation_notification,
    save_valuation_measurement,
)
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
        measurement = _notify_positive_measurement(config, measurement, report_url=report_detail.published_url if report_detail else None)
    return measurement


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
                title="Radar 估值测算",
                subtitle=f"{measurement.positive_count} 个有上涨空间",
                body=_positive_bark_body(measurement),
                url=report_url,
                group="radar",
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
    lines = [f"估值测算：{len(positives)} 个有上涨空间标的"]
    for index, item in enumerate(positives[:5], start=1):
        code = f" {item.ts_code}" if item.ts_code else ""
        upside = f" {item.upside_text}" if item.upside_text else ""
        status = f" {item.valuation_status}" if item.valuation_status else ""
        confidence = f" {item.confidence}" if item.confidence else ""
        lines.append(f"{index}. {item.name}{code}{upside}{status}{confidence}".strip())
        if item.key_validation:
            lines.append(f"   验证：{item.key_validation}")
    if len(positives) > 5:
        lines.append(f"... 另有 {len(positives) - 5} 个")
    if measurement.source_generated_at:
        lines.append(f"报告：{measurement.source_generated_at:%Y-%m-%d %H:%M}")
    return "\n".join(lines)


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
