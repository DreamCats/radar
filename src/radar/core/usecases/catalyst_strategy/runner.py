from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from radar.core.config import RadarConfig
from radar.core.runtime import run_work_pool
from radar.core.usecases.catalyst_strategy.analyze import analyze_stock_context
from radar.core.usecases.catalyst_strategy.collect import collect_catalyst_stock_contexts
from radar.core.usecases.catalyst_strategy.market import load_market_snapshot
from radar.core.usecases.catalyst_strategy.models import (
    CatalystStockAnalysis,
    CatalystStockContext,
    CatalystStrategyReport,
    CatalystStrategyRunResult,
)
from radar.core.usecases.catalyst_strategy.publish import notify_report, publish_report_html, write_report_html


def run_catalyst_strategy_report(
    config: RadarConfig,
    *,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    hours: int = 24,
    limit: int = 200,
    max_stocks: int = 12,
    llm_concurrency: int = 3,
    provider_name: str | None = None,
    model: str | None = None,
    output_path: Path | None = None,
    publish: bool = False,
    notify: bool = False,
) -> CatalystStrategyRunResult:
    end = end_time or datetime.now()
    start = start_time or (end - timedelta(hours=hours))
    contexts, total_feed_items = collect_catalyst_stock_contexts(
        config,
        start_time=start,
        end_time=end,
        limit=limit,
        max_stocks=max_stocks,
    )
    for context in contexts:
        context.market_snapshot = load_market_snapshot(config, context)

    analyses = _analyze_contexts(
        config,
        contexts,
        provider_name=provider_name,
        model=model,
        llm_concurrency=llm_concurrency,
    )
    report = CatalystStrategyReport(
        generated_at=datetime.now(),
        start_time=start,
        end_time=end,
        total_feed_items=total_feed_items,
        total_stocks=len(contexts),
        stocks=contexts,
        analyses=analyses,
    )
    local_path = write_report_html(config, report, output_path=output_path)
    should_publish = publish and report.total_stocks > 0
    should_notify = notify and report.total_stocks > 0
    url = publish_report_html(config, local_path, generated_at=report.generated_at) if should_publish else None
    if should_notify:
        if not url:
            raise ValueError("notify=true 需要同时 publish=true，确保 Bark 可以打开公网 URL")
        notify_report(config, report, url)
    return CatalystStrategyRunResult(
        report=report,
        local_html_path=local_path,
        published_url=url,
        bark_sent=should_notify,
    )


def _analyze_contexts(
    config: RadarConfig,
    contexts: list[CatalystStockContext],
    *,
    provider_name: str | None,
    model: str | None,
    llm_concurrency: int,
) -> list[CatalystStockAnalysis]:
    results: list[CatalystStockAnalysis | None] = [None] * len(contexts)

    def worker(_index: int, context: CatalystStockContext) -> CatalystStockAnalysis:
        return analyze_stock_context(config, context, provider_name=provider_name, model=model)

    def on_result(index: int, _context: CatalystStockContext, result: CatalystStockAnalysis) -> None:
        results[index] = result

    def on_error(index: int, context: CatalystStockContext, error: BaseException) -> None:
        results[index] = CatalystStockAnalysis(
            stock_key=context.stock_key,
            ts_code=context.ts_code,
            stock_name=context.stock_name,
            summary=[f"AI 分析失败：{str(error)[:160]}"],
            valuation_status="error",
            valuation_text="",
        )

    run_work_pool(
        contexts,
        max_workers=llm_concurrency,
        worker=worker,
        on_result=on_result,
        on_error=on_error,
    )
    return [
        result
        or CatalystStockAnalysis(
            stock_key=context.stock_key,
            ts_code=context.ts_code,
            stock_name=context.stock_name,
            summary=["AI 分析未返回结果。"],
            valuation_status="error",
            valuation_text="",
        )
        for context, result in zip(contexts, results, strict=True)
    ]
