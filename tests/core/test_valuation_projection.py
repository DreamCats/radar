from __future__ import annotations

from datetime import datetime

from radar.core.cloud import CloudUploadError, CloudUploadResult
from radar.core.chat import ChatMessage, ChatRunStore, ChatSessionStore
from radar.core.chat.events import now_iso
from radar.core.config import RadarConfig
from radar.core.storage.report_store import save_catalyst_valuation_report
from radar.core.storage.valuation_store import get_valuation_measurement_by_run
from radar.core.usecases.catalyst_valuation_report.models import (
    CatalystValuationReport,
    CatalystValuationReportRunResult,
)
from radar.core.valuation import parse_upside_measurement_items, project_completed_valuation_run
from radar.web.server.chat_run_worker import _mark_completed_and_project


def test_parse_upside_measurement_table():
    items, error = parse_upside_measurement_items(
        """
## 空间测算总表
| 排名 | 标的 | 当前市值 | 目标市值 | 剩余空间 | 状态 | 确定性 | 关键验证 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 胜宏科技 300476.SZ | 500亿 | 900-1100亿 | 80%-120% | 显著空间 | 高 | 订单兑现 |
| 2 | 已反映股份 600000.SH | 300亿 | 320亿 | 6% | 基本反映 | 中 | 业绩验证 |
"""
    )

    assert error is None
    assert [item.name for item in items] == ["胜宏科技", "已反映股份"]
    assert items[0].ts_code == "300476.SZ"
    assert items[0].is_positive is True
    assert items[1].is_positive is False


def test_project_completed_valuation_run_saves_items_and_sends_structured_bark(monkeypatch, tmp_path):
    config = _config(tmp_path)
    saved_report = save_catalyst_valuation_report(
        config.reports_database_path,
        request={"limit": 200, "publish": True, "notify": False},
        result=_report_result(tmp_path),
        run_id="report-run",
        status="succeeded",
    )
    run = _completed_run(
        config,
        report_id=saved_report.report_id,
        assistant_content="""
结论：1 个标的有显著空间。

## 空间测算总表
| 排名 | 标的 | 当前市值 | 目标市值 | 剩余空间 | 状态 | 确定性 | 关键验证 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 胜宏科技 300476.SZ | 500亿 | 900-1100亿 | 80%-120% | 显著空间 | 高 | 订单兑现 |
| 2 | 已反映股份 600000.SH | 300亿 | 320亿 | 6% | 基本反映 | 中 | 业绩验证 |
""",
    )
    captured = {}

    def fake_upload_aly(config, local_path, remote_path):
        html = local_path.read_text(encoding="utf-8")
        assert "Radar 估值测算报告" in html
        assert "完整 Session Markdown" in html
        assert "来源估值线索报告" in html
        assert "胜宏科技 300476.SZ" in html
        captured["remote_path"] = remote_path
        return CloudUploadResult(
            local_path=local_path,
            remote_path=remote_path,
            url="https://example.com/valuation-measurement.html",
        )

    def fake_push_bark(config, message):
        captured["message"] = message

    monkeypatch.setattr("radar.core.valuation.report.upload_aly", fake_upload_aly)
    monkeypatch.setattr("radar.core.valuation.projector.push_bark", fake_push_bark)

    measurement = project_completed_valuation_run(config, run)

    assert measurement is not None
    assert measurement.report_id == saved_report.report_id
    assert measurement.parse_status == "ready"
    assert measurement.total_items == 2
    assert measurement.positive_count == 1
    assert measurement.published_url == "https://example.com/valuation-measurement.html"
    assert measurement.notification_status == "succeeded"
    assert measurement.items[0].name == "胜宏科技"
    assert measurement.items[0].is_positive is True
    assert captured["remote_path"].startswith("valuation-measurement/")
    assert captured["message"].title == "Radar 估值测算｜胜宏科技"
    assert captured["message"].subtitle == "80%-120% · 显著空间 · 确定性高"
    assert "300476.SZ｜胜宏科技" in captured["message"].body
    assert "验证：订单兑现" in captured["message"].body
    assert captured["message"].url == "https://example.com/valuation-measurement.html"
    assert captured["message"].group == "radar-valuation"

    saved = get_valuation_measurement_by_run(config.valuation_database_path, run.run_id)
    assert saved is not None
    assert saved.measurement_id == measurement.measurement_id
    assert saved.published_url == "https://example.com/valuation-measurement.html"
    assert saved.notification_status == "succeeded"


def test_project_completed_valuation_run_skips_bark_without_positive_items(monkeypatch, tmp_path):
    config = _config(tmp_path)
    saved_report = save_catalyst_valuation_report(
        config.reports_database_path,
        request={"limit": 200, "publish": True, "notify": False},
        result=_report_result(tmp_path),
        run_id="report-run",
        status="succeeded",
    )
    run = _completed_run(
        config,
        report_id=saved_report.report_id,
        assistant_content="""
## 空间测算总表
| 排名 | 标的 | 当前市值 | 目标市值 | 剩余空间 | 状态 | 确定性 | 关键验证 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 已反映股份 600000.SH | 300亿 | 320亿 | 6% | 基本反映 | 中 | 业绩验证 |
""",
    )

    def fail_push_bark(config, message):
        raise AssertionError("不应发送 Bark")

    monkeypatch.setattr("radar.core.valuation.projector.push_bark", fail_push_bark)

    measurement = project_completed_valuation_run(config, run)

    assert measurement is not None
    assert measurement.parse_status == "ready"
    assert measurement.positive_count == 0
    assert measurement.notification_status is None


def test_project_completed_valuation_run_records_upload_failure_without_bark(monkeypatch, tmp_path):
    config = _config(tmp_path)
    saved_report = save_catalyst_valuation_report(
        config.reports_database_path,
        request={"limit": 200, "publish": True, "notify": False},
        result=_report_result(tmp_path),
        run_id="report-run",
        status="succeeded",
    )
    run = _completed_run(
        config,
        report_id=saved_report.report_id,
        assistant_content="""
## 空间测算总表
| 排名 | 标的 | 当前市值 | 目标市值 | 剩余空间 | 状态 | 确定性 | 关键验证 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 胜宏科技 300476.SZ | 500亿 | 900亿 | 80% | 显著空间 | 高 | 订单兑现 |
""",
    )

    def fail_upload(config, local_path, remote_path):
        raise CloudUploadError("upload failed")

    def fail_push_bark(config, message):
        raise AssertionError("测算报告上传失败时不应发送 Bark")

    monkeypatch.setattr("radar.core.valuation.report.upload_aly", fail_upload)
    monkeypatch.setattr("radar.core.valuation.projector.push_bark", fail_push_bark)

    measurement = project_completed_valuation_run(config, run)

    assert measurement is not None
    assert measurement.parse_status == "ready"
    assert measurement.positive_count == 1
    assert measurement.published_url is None
    assert measurement.publish_error == "upload failed"
    assert measurement.notification_status == "failed"
    assert measurement.notification_error == "估值测算报告上传失败: upload failed"


def test_completed_chat_run_hook_projects_valuation_result(monkeypatch, tmp_path):
    config = _config(tmp_path)
    saved_report = save_catalyst_valuation_report(
        config.reports_database_path,
        request={"limit": 200, "publish": True, "notify": False},
        result=_report_result(tmp_path),
        run_id="report-run",
        status="succeeded",
    )
    run_store = ChatRunStore.from_config(config)
    run = _running_run(
        config,
        report_id=saved_report.report_id,
        assistant_content="""
## 空间测算总表
| 排名 | 标的 | 当前市值 | 目标市值 | 剩余空间 | 状态 | 确定性 | 关键验证 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 胜宏科技 300476.SZ | 500亿 | 900亿 | 80% | 显著空间 | 高 | 订单兑现 |
""",
    )

    monkeypatch.setattr(
        "radar.core.valuation.report.upload_aly",
        lambda config, local_path, remote_path: CloudUploadResult(
            local_path=local_path,
            remote_path=remote_path,
            url="https://example.com/valuation-measurement.html",
        ),
    )
    monkeypatch.setattr("radar.core.valuation.projector.push_bark", lambda config, message: None)

    _mark_completed_and_project(run_store, run.run_id, config)

    assert run_store.get_run(run.run_id).status == "completed"
    measurement = get_valuation_measurement_by_run(config.valuation_database_path, run.run_id)
    assert measurement is not None
    assert measurement.positive_count == 1
    events = run_store.load_events(run.run_id)
    assert events[-1].event == "valuation_projection"
    assert events[-1].data["measurement_id"] == measurement.measurement_id


def _completed_run(config: RadarConfig, *, report_id: str, assistant_content: str):
    run = _running_run(config, report_id=report_id, assistant_content=assistant_content)
    return ChatRunStore.from_config(config).mark_completed(run.run_id)


def _running_run(config: RadarConfig, *, report_id: str, assistant_content: str):
    session_store = ChatSessionStore.from_config(config)
    session = session_store.create_session(
        title="估值线索空间测算",
        metadata={"source_report_id": report_id},
    )
    session_store.append_message(
        session.session_id,
        ChatMessage(
            message_id="assistant-message",
            role="assistant",
            content=assistant_content,
            created_at=now_iso(),
        ),
    )
    run_store = ChatRunStore.from_config(config)
    run = run_store.create_run(
        session.session_id,
        metadata={
            "surface": "估值线索",
            "title": "估值线索空间测算",
            "source_report_id": report_id,
        },
        request={"content": "测算", "llm_content": "测算"},
    )
    return run


def _report_result(tmp_path) -> CatalystValuationReportRunResult:
    report = CatalystValuationReport(
        generated_at=datetime.fromisoformat("2026-07-09T10:00:00"),
        start_time=datetime.fromisoformat("2026-07-09T09:00:00"),
        end_time=datetime.fromisoformat("2026-07-09T10:00:00"),
        total_feed_items=5,
        total_candidate_stocks=2,
        total_stocks=2,
    )
    return CatalystValuationReportRunResult(
        report=report,
        local_html_path=tmp_path / "report.html",
        published_url="https://example.com/report.html",
    )


def _config(tmp_path) -> RadarConfig:
    return RadarConfig(
        storage={"data_dir": tmp_path / "data"},
        channel={"bark": {"enabled": True, "secret_ref": "bark_main"}},
        secrets={"channel": {"bark": {"bark_main": {"device_key": "bark-key"}}}},
    )
