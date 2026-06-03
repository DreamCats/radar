from __future__ import annotations


def is_group_blacklisted(group_name: str | None, patterns: list[str]) -> bool:
    """按群名包含关系过滤明显非投研群；私聊不参与群黑名单。"""

    if not group_name:
        return False
    normalized = group_name.casefold()
    return any(pattern.casefold() in normalized for pattern in patterns if pattern)


def group_blacklist_sql(patterns: list[str]) -> tuple[str, list[str]]:
    """生成 SQLite LIKE 条件，用于批量清理或统计黑名单群消息。"""

    clean_patterns = [pattern for pattern in patterns if pattern]
    if not clean_patterns:
        return "0", []
    conditions = " OR ".join(["group_name LIKE ?" for _ in clean_patterns])
    params = [f"%{pattern}%" for pattern in clean_patterns]
    return f"group_name IS NOT NULL AND ({conditions})", params
