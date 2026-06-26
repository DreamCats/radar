from __future__ import annotations

from radar.core.wechat.filtering import group_blacklist_sql, is_group_blacklisted


def test_is_group_blacklisted_by_name_contains():
    patterns = ["小学", "寝室"]

    assert is_group_blacklisted("汇师小学二年级（1）班", patterns)
    assert is_group_blacklisted("3007寝室", patterns)
    assert not is_group_blacklisted("东财策略", patterns)
    assert not is_group_blacklisted(None, patterns)


def test_group_blacklist_sql_empty_patterns():
    sql, params = group_blacklist_sql([])

    assert sql == "0"
    assert params == []
