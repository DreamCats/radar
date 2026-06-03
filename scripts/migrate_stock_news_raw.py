from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Iterable

from pydantic import ValidationError

from radar.core.config import load_config
from radar.core.filtering import is_group_blacklisted
from radar.core.models import RawMessage
from radar.core.store import connect, init_db, upsert_messages

DEFAULT_START_DATE = date(2026, 4, 1)
DEFAULT_END_DATE = date(2026, 6, 3)
DEFAULT_STOCK_NEWS_DATA_DIR = Path.home() / ".config" / "stock-news" / "data"


@dataclass
class MigrationStats:
    files_seen: int = 0
    files_missing: int = 0
    rows_seen: int = 0
    rows_in_range: int = 0
    rows_invalid: int = 0
    rows_blacklisted: int = 0
    inserted: int = 0
    skipped_existing: int = 0


def main() -> None:
    args = parse_args()
    start_date = parse_date(args.start_date)
    end_date = parse_date(args.end_date)
    if start_date > end_date:
        raise SystemExit("--start-date 不能晚于 --end-date")

    config = load_config(args.config_dir)
    database_path = args.database or config.database_path
    stats = migrate_raw_range(
        stock_news_data_dir=args.stock_news_data_dir.expanduser(),
        database_path=database_path.expanduser(),
        start_date=start_date,
        end_date=end_date,
        group_blacklist_patterns=[] if args.ignore_group_blacklist else config.filters.group_blacklist_patterns,
        execute=args.execute,
    )
    print_summary(stats, database_path.expanduser(), execute=args.execute)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="把 stock-news raw JSON 迁移到 radar SQLite。默认 dry-run，不写数据库。"
    )
    parser.add_argument("--start-date", default=DEFAULT_START_DATE.isoformat())
    parser.add_argument("--end-date", default=DEFAULT_END_DATE.isoformat())
    parser.add_argument("--stock-news-data-dir", type=Path, default=DEFAULT_STOCK_NEWS_DATA_DIR)
    parser.add_argument("--config-dir", type=Path, default=None)
    parser.add_argument("--database", type=Path, default=None)
    parser.add_argument("--ignore-group-blacklist", action="store_true", help="迁移时不应用群黑名单")
    parser.add_argument("--execute", action="store_true", help="真实写入 SQLite")
    return parser.parse_args()


def migrate_raw_range(
    *,
    stock_news_data_dir: Path,
    database_path: Path,
    start_date: date,
    end_date: date,
    group_blacklist_patterns: list[str],
    execute: bool,
) -> MigrationStats:
    stats = MigrationStats()
    conn = connect(database_path) if execute else None
    try:
        if conn is not None:
            init_db(conn)
        for day in date_range(start_date, end_date):
            raw_dir = stock_news_data_dir / day.isoformat() / "raw"
            if not raw_dir.exists():
                stats.files_missing += 1
                continue
            for raw_file in iter_raw_message_files(raw_dir):
                migrate_raw_file(
                    raw_file,
                    day,
                    stats,
                    group_blacklist_patterns=group_blacklist_patterns,
                    conn=conn,
                )
    finally:
        if conn is not None:
            conn.close()
    return stats


def migrate_raw_file(
    raw_file: Path,
    day: date,
    stats: MigrationStats,
    *,
    group_blacklist_patterns: list[str],
    conn,
) -> None:
    stats.files_seen += 1
    rows = load_json_list(raw_file)
    stats.rows_seen += len(rows)

    messages: list[RawMessage] = []
    for row in rows:
        try:
            message = RawMessage.model_validate(row)
        except ValidationError:
            stats.rows_invalid += 1
            continue
        # stock-news 有跨日窗口文件，迁移时按消息自身日期过滤，避免带入范围外数据。
        if message.message_time.date() != day:
            continue
        stats.rows_in_range += 1
        if is_group_blacklisted(message.group_name, group_blacklist_patterns):
            stats.rows_blacklisted += 1
            continue
        messages.append(message)

    if conn is None:
        return

    inserted = upsert_messages(conn, messages)
    stats.inserted += inserted
    stats.skipped_existing += len(messages) - inserted


def load_json_list(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"raw 文件根节点必须是 list: {path}")
    return data


def iter_raw_message_files(raw_dir: Path) -> Iterable[Path]:
    """只迁移消息文件，跳过 .fetched.json 等 stock-news 元数据。"""

    yield from sorted(raw_dir.glob("个人消息_*.json"))
    yield from sorted(raw_dir.glob("个人群_*.json"))


def date_range(start_date: date, end_date: date) -> Iterable[date]:
    current = start_date
    while current <= end_date:
        yield current
        current += timedelta(days=1)


def parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def print_summary(stats: MigrationStats, database_path: Path, *, execute: bool) -> None:
    mode = "execute" if execute else "dry-run"
    print(f"mode={mode}")
    print(f"database={database_path}")
    print(f"files_seen={stats.files_seen}")
    print(f"missing_raw_dirs={stats.files_missing}")
    print(f"rows_seen={stats.rows_seen}")
    print(f"rows_in_range={stats.rows_in_range}")
    print(f"rows_blacklisted={stats.rows_blacklisted}")
    print(f"rows_invalid={stats.rows_invalid}")
    if execute:
        print(f"inserted={stats.inserted}")
        print(f"skipped_existing={stats.skipped_existing}")
    else:
        print("not_written=true")


if __name__ == "__main__":
    main()
