from __future__ import annotations

from typing import cast

import click

from radar.cli.context import load_cli_config, parse_datetime
from radar.core.models import MessageCategory, MessageSource
from radar.core.usecases.aggregation import (
    AggregateTopicsResult,
    RefineAggregateTopicsResult,
    aggregate_topics,
    refine_aggregate_topics,
)
from radar.core.usecases.anchoring import ANCHOR_EXTRACTOR_VERSION, DEFAULT_ANCHOR_CATEGORIES

_SOURCE_MAP: dict[str, MessageSource | None] = {
    "all": None,
    "personal_message": "个人消息",
    "group_message": "个人群",
}
_CATEGORY_CHOICES = ["research", "recommendation", "industry", "tool_ad", "chat", "unknown"]


@click.group()
def aggregate() -> None:
    """聚合消息 anchor。"""


@aggregate.command("topics")
@click.option("--trade-date", required=True, help="anchor 词库交易日，格式 YYYYMMDD。")
@click.option("--extractor-version", default=ANCHOR_EXTRACTOR_VERSION, show_default=True)
@click.option(
    "--source",
    "source_key",
    type=click.Choice(["all", "personal_message", "group_message"]),
    default="all",
    show_default=True,
    help="消息来源。",
)
@click.option(
    "--category",
    "categories",
    type=click.Choice(_CATEGORY_CHOICES),
    multiple=True,
    help=f"分类，可重复；不传默认 {','.join(DEFAULT_ANCHOR_CATEGORIES)}。",
)
@click.option("--min-classification-confidence", type=click.FloatRange(0, 1), default=0.7, show_default=True)
@click.option("--min-messages", type=click.IntRange(1, 100), default=2, show_default=True)
@click.option("--limit", type=click.IntRange(1, 100), default=20, show_default=True)
@click.option("--evidence-limit", type=click.IntRange(0, 10), default=2, show_default=True)
@click.option("--start", "start_text", required=True, help="开始时间。")
@click.option("--end", "end_text", required=True, help="结束时间。")
@click.pass_context
def aggregate_topics_command(
    ctx: click.Context,
    trade_date: str,
    extractor_version: str,
    source_key: str,
    categories: tuple[str, ...],
    min_classification_confidence: float,
    min_messages: int,
    limit: int,
    evidence_limit: int,
    start_text: str,
    end_text: str,
) -> None:
    """按 topic anchor 聚合主题，并展示相关个股和证据。"""

    start_time = parse_datetime(start_text)
    end_time = parse_datetime(end_text)
    if end_time <= start_time:
        raise click.ClickException("--end 必须晚于 --start")

    result = aggregate_topics(
        load_cli_config(ctx),
        trade_date=trade_date,
        extractor_version=extractor_version,
        source=_SOURCE_MAP[source_key],
        categories=[cast(MessageCategory, item) for item in categories] or DEFAULT_ANCHOR_CATEGORIES,
        min_classification_confidence=min_classification_confidence,
        min_messages=min_messages,
        limit=limit,
        evidence_limit=evidence_limit,
        start_time=start_time,
        end_time=end_time,
    )
    _echo_topics(result)


@aggregate.command("refine")
@click.option("--trade-date", required=True, help="anchor 词库交易日，格式 YYYYMMDD。")
@click.option("--extractor-version", default=ANCHOR_EXTRACTOR_VERSION, show_default=True)
@click.option(
    "--source",
    "source_key",
    type=click.Choice(["all", "personal_message", "group_message"]),
    default="all",
    show_default=True,
    help="消息来源。",
)
@click.option(
    "--category",
    "categories",
    type=click.Choice(_CATEGORY_CHOICES),
    multiple=True,
    help=f"分类，可重复；不传默认 {','.join(DEFAULT_ANCHOR_CATEGORIES)}。",
)
@click.option("--min-classification-confidence", type=click.FloatRange(0, 1), default=0.7, show_default=True)
@click.option("--min-messages", type=click.IntRange(1, 100), default=2, show_default=True)
@click.option("--candidate-limit", type=click.IntRange(1, 100), default=50, show_default=True)
@click.option("--evidence-limit", type=click.IntRange(0, 10), default=3, show_default=True)
@click.option("--batch-size", type=click.IntRange(1, 30), default=5, show_default=True)
@click.option("--max-concurrency", type=click.IntRange(1, 16), default=10, show_default=True)
@click.option("--provider", "provider_name", help="指定单个 LLM provider。")
@click.option("--provider-pool", "provider_pool", multiple=True, help="可重复传入多个 provider。")
@click.option("--force", is_flag=True, help="忽略缓存，重新调用 LLM refine。")
@click.option("--start", "start_text", required=True, help="开始时间。")
@click.option("--end", "end_text", required=True, help="结束时间。")
@click.pass_context
def aggregate_refine_command(
    ctx: click.Context,
    trade_date: str,
    extractor_version: str,
    source_key: str,
    categories: tuple[str, ...],
    min_classification_confidence: float,
    min_messages: int,
    candidate_limit: int,
    evidence_limit: int,
    batch_size: int,
    max_concurrency: int,
    provider_name: str | None,
    provider_pool: tuple[str, ...],
    force: bool,
    start_text: str,
    end_text: str,
) -> None:
    """用 LLM 对本地聚合候选做投资视角 refinement。"""

    if provider_name and provider_pool:
        raise click.ClickException("--provider 和 --provider-pool 只能二选一")
    start_time = parse_datetime(start_text)
    end_time = parse_datetime(end_text)
    if end_time <= start_time:
        raise click.ClickException("--end 必须晚于 --start")

    result = refine_aggregate_topics(
        load_cli_config(ctx),
        trade_date=trade_date,
        extractor_version=extractor_version,
        source=_SOURCE_MAP[source_key],
        categories=[cast(MessageCategory, item) for item in categories] or DEFAULT_ANCHOR_CATEGORIES,
        min_classification_confidence=min_classification_confidence,
        min_messages=min_messages,
        candidate_limit=candidate_limit,
        evidence_limit=evidence_limit,
        batch_size=batch_size,
        max_concurrency=max_concurrency,
        provider_name=provider_name,
        provider_names=list(provider_pool) or None,
        force=force,
        start_time=start_time,
        end_time=end_time,
    )
    _echo_refine(result)


def _echo_topics(result: AggregateTopicsResult) -> None:
    click.echo(
        f"aggregate/topics: topics={result.topic_count} scoped={result.scoped_message_count} "
        f"anchored={result.anchored_message_count} extractor={result.extractor_version}"
    )
    for index, topic in enumerate(result.topics, start=1):
        stocks = ", ".join(f"{item.name}({item.count})" for item in topic.related_stocks[:5]) or "-"
        categories = " ".join(f"{key}={value}" for key, value in sorted(topic.category_distribution.items()))
        click.echo(
            f"{index}. {topic.name} score={topic.score} messages={topic.message_count} "
            f"anchors={topic.anchor_count} categories={categories} stocks={stocks}"
        )
        for evidence in topic.evidence:
            text = _compact_text(evidence.raw_content)
            click.echo(f"   - {evidence.message_time.isoformat()} {evidence.category} {text}")


def _echo_refine(result: RefineAggregateTopicsResult) -> None:
    click.echo(
        f"aggregate/refine: status={result.status} themes={result.theme_count} "
        f"candidates={result.candidate_count} batches={result.llm_batch_count} "
        f"failed_batches={result.failed_llm_batches} run_id={result.run_id}"
    )
    for index, theme in enumerate(result.themes, start=1):
        stocks = ", ".join(item.name for item in theme.related_stocks[:5]) or "-"
        evidence = ",".join(theme.evidence_message_ids[:5]) or "-"
        click.echo(
            f"{index}. {theme.theme_name} action={theme.actionability_score} "
            f"confidence={theme.confidence} novelty={theme.novelty} stocks={stocks} evidence={evidence}"
        )
        if theme.summary:
            click.echo(f"   {theme.summary}")


def _compact_text(value: str, limit: int = 90) -> str:
    text = " ".join(value.split())
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "..."
