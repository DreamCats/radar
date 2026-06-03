from __future__ import annotations

import argparse
from pathlib import Path

from radar.core.config import load_config
from radar.core.filtering import group_blacklist_sql
from radar.core.store import connect


def main() -> None:
    args = parse_args()
    config = load_config(args.config_dir)
    database_path = (args.database or config.database_path).expanduser()
    patterns = config.filters.group_blacklist_patterns
    where_sql, params = group_blacklist_sql(patterns)

    conn = connect(database_path)
    try:
        count = conn.execute(f"SELECT COUNT(*) FROM messages WHERE {where_sql}", params).fetchone()[0]
        print(f"database={database_path}")
        print(f"group_blacklist_patterns={len(patterns)}")
        print(f"matched_messages={count}")
        if not args.execute:
            print("not_deleted=true")
            return

        # 先删 FTS，再删主表，避免残留全文索引记录。
        conn.execute(
            f"""
            DELETE FROM messages_fts
            WHERE message_id IN (SELECT message_id FROM messages WHERE {where_sql})
            """,
            params,
        )
        conn.execute(f"DELETE FROM messages WHERE {where_sql}", params)
        conn.commit()
        print(f"deleted={count}")
    finally:
        conn.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="按 config.yaml 的群黑名单清理 radar SQLite。默认 dry-run。"
    )
    parser.add_argument("--config-dir", type=Path, default=None)
    parser.add_argument("--database", type=Path, default=None)
    parser.add_argument("--execute", action="store_true", help="真实删除黑名单群消息")
    return parser.parse_args()


if __name__ == "__main__":
    main()
