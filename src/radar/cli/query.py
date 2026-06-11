from __future__ import annotations

import json

import click

from radar.cli.context import load_cli_config, parse_optional_datetime
from radar.core.messages import MessageFilters, list_messages
from radar.core.models import MessageSource
from radar.core.storage import connect, init_db

SOURCE_LABELS: dict[str, MessageSource] = {
    "personal_message": "个人消息",
    "group_message": "个人群",
    "个人消息": "个人消息",
    "个人群": "个人群",
}


@click.command("query")
@click.option(
    "--source",
    type=click.Choice(list(SOURCE_LABELS)),
    help="来源：personal_message/group_message/个人消息/个人群。",
)
@click.option("--group-name", help="按群名精确筛选。")
@click.option("--keyword", help="按正文、发送人、群名搜索。")
@click.option("--start", "start_text", help="开始时间。")
@click.option("--end", "end_text", help="结束时间。")
@click.option(
    "--limit",
    type=click.IntRange(1, 200),
    default=20,
    show_default=True,
    help="返回条数。",
)
@click.option("--cursor-time", help="下一页游标时间。")
@click.option("--cursor-id", help="下一页游标 message_id。")
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["text", "json"]),
    default="text",
    show_default=True,
    help="输出格式。",
)
@click.pass_context
def query_messages(
    ctx: click.Context,
    source: str | None,
    group_name: str | None,
    keyword: str | None,
    start_text: str | None,
    end_text: str | None,
    limit: int,
    cursor_time: str | None,
    cursor_id: str | None,
    output_format: str,
) -> None:
    """查询已写入 SQLite 的消息。"""

    config = load_cli_config(ctx)
    if bool(cursor_time) != bool(cursor_id):
        raise click.ClickException("--cursor-time 和 --cursor-id 必须一起传")

    filters = MessageFilters(
        source=SOURCE_LABELS[source] if source else None,
        group_name=group_name,
        keyword=keyword,
        start_time=parse_optional_datetime(start_text),
        end_time=parse_optional_datetime(end_text),
        cursor_time=parse_optional_datetime(cursor_time),
        cursor_id=cursor_id,
        limit=limit,
    )

    conn = connect(config.database_path)
    try:
        init_db(conn)
        page = list_messages(conn, filters)
    finally:
        conn.close()

    if output_format == "json":
        click.echo(json.dumps(page.model_dump(mode="json"), ensure_ascii=False, indent=2))
        return

    for item in page.items:
        group = item.group_name or "-"
        content = _clip(item.raw_content)
        click.echo(f"{item.message_time.isoformat()} | {item.source} | {group} | {item.sender} | {content}")
    if page.next_cursor_time and page.next_cursor_id:
        click.echo(
            "下一页: "
            f"--cursor-time {page.next_cursor_time.isoformat()} --cursor-id {page.next_cursor_id}"
        )


def _clip(value: str, limit: int = 120) -> str:
    text = " ".join(value.split())
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "..."
