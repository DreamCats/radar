from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from threading import Lock

from radar.core.chat import ChatAgent, ChatRunStore, build_chat_system_prompt
from radar.core.config import RadarConfig
from radar.core.storage import fail_run, fail_stale_runs, finish_run, get_running_run, start_run
from radar.core.storage.report_store import save_catalyst_valuation_report
from radar.core.usecases.catalyst_valuation_report.models import CatalystValuationReport, CatalystValuationStockContext
from radar.core.usecases.catalyst_valuation_report import run_catalyst_valuation_report
from radar.web.server.chat_run_worker import start_chat_run_worker
from radar.web.server.schemas import CatalystValuationReportJobRequest, DerivedJobItem

CATALYST_VALUATION_REPORT_RUN_KIND = "catalyst_valuation_report"
STALE_AFTER = timedelta(hours=3)
UPSIDE_EVIDENCE_PER_STOCK = 2
UPSIDE_EVIDENCE_TEXT_LIMIT = 500

_EXECUTOR = ThreadPoolExecutor(
    max_workers=1,
    thread_name_prefix="radar-catalyst-valuation-report",
)
_SUBMIT_LOCK = Lock()


def submit_catalyst_valuation_report_job(
    config: RadarConfig,
    request: CatalystValuationReportJobRequest,
) -> DerivedJobItem:
    with _SUBMIT_LOCK:
        mark_stale_catalyst_valuation_report_runs(config)
        target = _target(request)
        running = get_running_run(config.database_path, kind=CATALYST_VALUATION_REPORT_RUN_KIND, target=target)
        if running is not None:
            return DerivedJobItem(
                job_type="catalyst_valuation_report",
                run_id=running.run_id,
                reused_existing=True,
                status="running",
            )

        run_id = start_run(
            config.database_path,
            kind=CATALYST_VALUATION_REPORT_RUN_KIND,
            target=target,
            metadata=_metadata(request) | {"stage": "生成催化估值线索报告"},
        )
        _EXECUTOR.submit(_run_catalyst_valuation_report_job, config, request, run_id)
        return DerivedJobItem(
            job_type="catalyst_valuation_report",
            run_id=run_id,
            reused_existing=False,
            status="running",
        )


def mark_stale_catalyst_valuation_report_runs(config: RadarConfig) -> int:
    return fail_stale_runs(
        config.database_path,
        older_than=datetime.now() - STALE_AFTER,
        kind=CATALYST_VALUATION_REPORT_RUN_KIND,
    )


def _run_catalyst_valuation_report_job(
    config: RadarConfig,
    request: CatalystValuationReportJobRequest,
    run_id: str,
) -> None:
    try:
        result = run_catalyst_valuation_report(
            config,
            start_time=request.start_time,
            end_time=request.end_time,
            limit=request.limit,
            max_stocks=request.max_stocks,
            publish=request.publish,
            notify=False,
        )
        report = result.report
        status = "skipped" if report.total_stocks == 0 else "succeeded"
        if result.bark_error and status == "succeeded":
            status = "partial_failed"
        archived = save_catalyst_valuation_report(
            config.reports_database_path,
            request=_metadata(request),
            result=result,
            run_id=run_id,
            status=status,
        )
        auto_upside_run_id = None
        auto_upside_error = None
        if request.auto_upside and status == "succeeded":
            try:
                auto_upside_run_id = submit_catalyst_valuation_upside_chat_run(
                    config,
                    report=report,
                    report_id=archived.report_id,
                    parent_run_id=run_id,
                    published_url=result.published_url,
                )
            except Exception as exc:
                auto_upside_error = str(exc)[:1000]
                status = "partial_failed"
        error_message = None
        if result.bark_error:
            error_message = f"Bark 通知失败: {result.bark_error}"
        elif auto_upside_error:
            error_message = f"自动空间测算提交失败: {auto_upside_error}"
        finish_run(
            config.database_path,
            run_id,
            status=status,
            raw_count=report.total_feed_items,
            stored_count=report.total_stocks,
            filtered_count=max(report.total_candidate_stocks - report.total_stocks, 0),
            error_message=error_message,
            metadata=_metadata(request)
            | {
                "stage": "完成",
                "total_feed_items": report.total_feed_items,
                "total_candidate_stocks": report.total_candidate_stocks,
                "total_stocks": report.total_stocks,
                "local_html_path": str(result.local_html_path),
                "published_url": result.published_url,
                "report_id": archived.report_id,
                "bark_sent": result.bark_sent,
                "bark_error": result.bark_error,
                "auto_upside": request.auto_upside,
                "auto_upside_chat_run_id": auto_upside_run_id,
                "auto_upside_error": auto_upside_error,
            },
        )
    except BaseException as exc:
        fail_run(config.database_path, run_id, exc)


def _target(request: CatalystValuationReportJobRequest) -> str:
    publish = "publish" if request.publish else "local"
    notify = "notify" if request.notify else "silent"
    upside = "upside" if request.auto_upside else "no-upside"
    return f"{request.start_time.isoformat()}..{request.end_time.isoformat()}:{publish}:{notify}:{upside}"


def _metadata(request: CatalystValuationReportJobRequest) -> dict[str, object]:
    return request.model_dump(mode="json", exclude_none=True)


def submit_catalyst_valuation_upside_chat_run(
    config: RadarConfig,
    *,
    report: CatalystValuationReport,
    report_id: str,
    parent_run_id: str,
    published_url: str | None,
) -> str:
    title = "估值线索空间测算"
    subtitle = f"{_format_window_title(report)} · {report.total_stocks} 标的"
    context = _upside_context(report, report_id=report_id, published_url=published_url, title=title, subtitle=subtitle)
    content = _upside_prompt(report, report_id=report_id)
    metadata = {
        "surface": "估值线索",
        "entity_id": report_id,
        "title": title,
        "subtitle": subtitle,
        "source_report_id": report_id,
        "parent_run_id": parent_run_id,
        "stock_summary": _stock_summary(report.stocks),
        "auto_started_by": CATALYST_VALUATION_REPORT_RUN_KIND,
    }
    agent = ChatAgent(config)
    session = agent.create_session(title=title, metadata=metadata)
    run_store = ChatRunStore.from_config(config)
    run = run_store.create_run(
        session.session_id,
        metadata=metadata,
        request={
            "content": content,
            "llm_content": _content_with_context(content, context),
            "system_prompt": build_chat_system_prompt("估值线索"),
            "provider_name": None,
        },
    )
    run_store.append_event(run.run_id, "session", {"session_id": session.session_id})
    start_chat_run_worker(run.run_id, config)
    return run.run_id


def _upside_context(
    report: CatalystValuationReport,
    *,
    report_id: str,
    published_url: str | None,
    title: str,
    subtitle: str,
) -> dict[str, object]:
    return {
        "surface": "估值线索",
        "entity_id": report_id,
        "title": title,
        "subtitle": subtitle,
        "fields": [
            {"label": "报告", "value": report_id},
            {"label": "报告窗口", "value": f"{_format_time(report.start_time)} ~ {_format_time(report.end_time)}"},
            {"label": "生成时间", "value": _format_time(report.generated_at)},
            {"label": "HTML", "value": published_url or "未上传"},
            {"label": "标的", "value": _stock_summary(report.stocks) or "无"},
            {"label": "标的数量", "value": report.total_stocks},
            {"label": "催化词条目", "value": report.total_feed_items},
        ],
        "evidence": _upside_evidence(report),
    }


def _upside_prompt(report: CatalystValuationReport, *, report_id: str) -> str:
    stock_names = _stock_summary(report.stocks) or "无"
    return "\n".join(
        [
            "请先调用 radar_load_skill 读取 catalyst-valuation-upside，"
            "再调用 radar_get_catalyst_valuation_report 读取这份本地结构化报告，然后做空间测算。",
            "",
            "任务要求：",
            "1. 使用 report_id 读取报告数据，不要依赖公网报告 URL 抓网页正文。",
            "2. 对报告里的每个标的补当前市值：优先用 radar_get_stock_price_history 查询 "
            "daily_basic 最近交易日 total_mv；必要时用 radar_get_realtime_quote 补盘中价格/涨跌幅。",
            "3. 在“原文证据成立”的假设下，用第一性原理重算目标市值区间；不要只复述报告里的数字。",
            "4. 计算剩余空间，并标记：显著空间 / 有空间但需验证 / 基本反映 / 已超目标 / 严重透支。",
            "5. 把已确认事实、基于假设的推断、仍需验证条件分开写。",
            "6. 输出机会排序、追高风险、关键数据缺口；不要输出买卖建议、仓位或确定性收益。",
            "",
            f"report_id：{report_id}",
            f"报告窗口：{_format_time(report.start_time)} ~ {_format_time(report.end_time)}",
            f"报告标的：{stock_names}",
        ]
    )


def _content_with_context(content: str, context: dict[str, object]) -> str:
    return f"{content.strip()}\n\n页面上下文：\n{json.dumps(context, ensure_ascii=False, separators=(',', ':'))}"


def _upside_evidence(report: CatalystValuationReport) -> list[str]:
    lines: list[str] = []
    for stock in report.stocks:
        lines.extend(_stock_evidence(stock))
    return lines


def _stock_evidence(stock: CatalystValuationStockContext) -> list[str]:
    lines: list[str] = []
    for evidence in stock.evidence[:UPSIDE_EVIDENCE_PER_STOCK]:
        source = evidence.group_name or evidence.source
        terms = "、".join(dict.fromkeys([*evidence.valuation_terms, *evidence.matched_terms])) or "无"
        numbers = "、".join(evidence.valuation_numbers) or "无"
        content = evidence.content.strip()
        if len(content) > UPSIDE_EVIDENCE_TEXT_LIMIT:
            content = f"{content[:UPSIDE_EVIDENCE_TEXT_LIMIT]}..."
        lines.append(
            "\n".join(
                [
                    f"标的：{stock.stock_name} {stock.ts_code or stock.stock_key}",
                    f"时间：{_format_time(evidence.message_time)}；发送人：{evidence.sender}；来源：{source}",
                    f"命中词：{terms}；估值数字：{numbers}",
                    content,
                ]
            )
        )
    return lines


def _stock_summary(stocks: list[CatalystValuationStockContext]) -> str:
    return "、".join(f"{stock.stock_name}{f' {stock.ts_code}' if stock.ts_code else ''}" for stock in stocks)


def _format_window_title(report: CatalystValuationReport) -> str:
    return f"{_format_time(report.start_time)} ~ {_format_time(report.end_time)}"


def _format_time(value: datetime) -> str:
    return value.isoformat(sep=" ", timespec="minutes")
