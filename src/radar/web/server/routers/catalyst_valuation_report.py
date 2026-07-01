from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query

from radar.core.channel import BarkError
from radar.core.chat import ChatRun, ChatRunStore
from radar.core.config import RadarConfig
from radar.core.storage.report_store import (
    CatalystValuationReportArchiveDetail,
    CatalystValuationReportArchiveItem,
    get_catalyst_valuation_report,
    list_catalyst_valuation_reports,
    record_report_notification,
)
from radar.core.usecases.catalyst_valuation_report.publish import notify_report
from radar.web.server.catalyst_valuation_report_jobs import submit_catalyst_valuation_report_job
from radar.web.server.deps import get_config
from radar.web.server.schemas import (
    CatalystValuationReportDetailResponse,
    CatalystValuationReportJobRequest,
    CatalystValuationReportListResponse,
    CatalystValuationReportNotifyResponse,
    DerivedJobResponse,
)

router = APIRouter(prefix="/api", tags=["catalyst-valuation-report"])


@router.post("/catalyst-valuation-report/jobs", response_model=DerivedJobResponse)
def start_catalyst_valuation_report_job(
    request: CatalystValuationReportJobRequest,
    config: RadarConfig = Depends(get_config),
) -> DerivedJobResponse:
    if request.end_time <= request.start_time:
        raise HTTPException(status_code=400, detail="end_time 必须晚于 start_time")
    return DerivedJobResponse(items=[submit_catalyst_valuation_report_job(config, request)])


@router.get("/catalyst-valuation-reports", response_model=CatalystValuationReportListResponse)
def list_report_archives(
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    granularity_minutes: int | None = Query(default=None, ge=1, le=24 * 60),
    limit: int = Query(default=50, ge=1, le=200),
    config: RadarConfig = Depends(get_config),
) -> CatalystValuationReportListResponse:
    return _list_report_archives(
        config,
        start_time=start_time,
        end_time=end_time,
        granularity_minutes=granularity_minutes,
        limit=limit,
    )


@router.get("/catalyst-valuation-reports/{report_id}", response_model=CatalystValuationReportDetailResponse)
def get_report_archive(
    report_id: str,
    config: RadarConfig = Depends(get_config),
) -> CatalystValuationReportDetailResponse:
    return _get_report_archive(config, report_id)


@router.post("/catalyst-valuation-reports/{report_id}/bark", response_model=CatalystValuationReportNotifyResponse)
def send_report_bark(
    report_id: str,
    config: RadarConfig = Depends(get_config),
) -> CatalystValuationReportNotifyResponse:
    detail = get_catalyst_valuation_report(config.reports_database_path, report_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="报告不存在")
    if not detail.published_url:
        raise HTTPException(status_code=400, detail="报告没有公网 HTML URL，无法发送 Bark")

    try:
        notify_report(config, detail.report, detail.published_url)
    except BarkError as exc:
        record_report_notification(
            config.reports_database_path,
            report_id=report_id,
            channel="bark",
            status="failed",
            error_message=str(exc),
        )
        raise HTTPException(status_code=502, detail=f"Bark 发送失败: {exc}") from exc

    notification = record_report_notification(
        config.reports_database_path,
        report_id=report_id,
        channel="bark",
        status="succeeded",
    )
    updated = get_catalyst_valuation_report(config.reports_database_path, report_id)
    if updated is None:
        raise HTTPException(status_code=404, detail="报告不存在")
    return CatalystValuationReportNotifyResponse(
        item=_enrich_report_upside_runs(config, [updated])[0],
        notification=notification,
    )


@router.get("/external/catalyst-valuation-reports", response_model=CatalystValuationReportListResponse)
def list_external_report_archives(
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    granularity_minutes: int | None = Query(default=None, ge=1, le=24 * 60),
    limit: int = Query(default=50, ge=1, le=200),
    config: RadarConfig = Depends(get_config),
) -> CatalystValuationReportListResponse:
    return _list_report_archives(
        config,
        start_time=start_time,
        end_time=end_time,
        granularity_minutes=granularity_minutes,
        limit=limit,
    )


@router.get("/external/catalyst-valuation-reports/{report_id}", response_model=CatalystValuationReportDetailResponse)
def get_external_report_archive(
    report_id: str,
    config: RadarConfig = Depends(get_config),
) -> CatalystValuationReportDetailResponse:
    return _get_report_archive(config, report_id)


def _list_report_archives(
    config: RadarConfig,
    *,
    start_time: datetime | None,
    end_time: datetime | None,
    granularity_minutes: int | None,
    limit: int,
) -> CatalystValuationReportListResponse:
    if start_time is not None and end_time is not None and end_time <= start_time:
        raise HTTPException(status_code=400, detail="end_time 必须晚于 start_time")
    items = list_catalyst_valuation_reports(
        config.reports_database_path,
        start_time=start_time,
        end_time=end_time,
        granularity_minutes=granularity_minutes,
        limit=limit,
    )
    return CatalystValuationReportListResponse(items=_enrich_report_upside_runs(config, items))


def _get_report_archive(config: RadarConfig, report_id: str) -> CatalystValuationReportDetailResponse:
    detail = get_catalyst_valuation_report(config.reports_database_path, report_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="报告不存在")
    return CatalystValuationReportDetailResponse(item=_enrich_report_upside_runs(config, [detail])[0])


def _enrich_report_upside_runs(
    config: RadarConfig,
    items: list[CatalystValuationReportArchiveItem],
) -> list[CatalystValuationReportArchiveItem]:
    if not items:
        return items
    report_ids = {item.report_id for item in items}
    runs_by_report = _latest_upside_runs_by_report(config, report_ids)
    enriched: list[CatalystValuationReportArchiveItem] = []
    for item in items:
        run = runs_by_report.get(item.report_id)
        if run is None:
            enriched.append(item)
            continue
        enriched.append(
            item.model_copy(
                update={
                    "upside_chat_run_id": run.run_id,
                    "upside_chat_session_id": run.session_id,
                    "upside_chat_status": run.status,
                    "upside_chat_updated_at": datetime.fromisoformat(run.updated_at),
                    "upside_chat_error": run.error,
                }
            )
        )
    return enriched


def _latest_upside_runs_by_report(config: RadarConfig, report_ids: set[str]) -> dict[str, ChatRun]:
    if not report_ids:
        return {}
    result: dict[str, ChatRun] = {}
    try:
        runs = ChatRunStore.from_config(config).list_runs()
    except Exception:
        return result
    for run in runs:
        report_id = _upside_report_id(run)
        if report_id is None or report_id not in report_ids or report_id in result:
            continue
        result[report_id] = run
    return result


def _upside_report_id(run: ChatRun) -> str | None:
    source_report_id = run.metadata.get("source_report_id")
    if isinstance(source_report_id, str) and source_report_id:
        return source_report_id
    if run.metadata.get("surface") != "估值线索":
        return None
    if run.metadata.get("title") != "估值线索空间测算":
        return None
    entity_id = run.metadata.get("entity_id")
    return entity_id if isinstance(entity_id, str) and entity_id else None
