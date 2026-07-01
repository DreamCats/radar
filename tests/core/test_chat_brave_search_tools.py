from __future__ import annotations

from radar.core.brave_search import (
    BraveSearchConfigError,
    BraveSearchContextItem,
    BraveSearchContextResult,
)
from radar.core.chat.brave_search_tools import RadarBraveSearchTools
from radar.core.config import RadarConfig


def test_brave_search_tool_calls_context_helper(tmp_path, monkeypatch):
    config = RadarConfig(storage={"data_dir": tmp_path})
    captured = {}

    def fake_search_context(
        config,
        query,
        *,
        count,
        max_tokens,
        max_tokens_per_url,
        threshold,
        include_sites,
        exclude_sites,
    ):
        captured.update(
            {
                "query": query,
                "count": count,
                "max_tokens": max_tokens,
                "max_tokens_per_url": max_tokens_per_url,
                "threshold": threshold,
                "include_sites": include_sites,
                "exclude_sites": exclude_sites,
            }
        )
        return BraveSearchContextResult(
            query=query,
            items=[
                BraveSearchContextItem(
                    title="OpenAI Docs",
                    url="https://platform.openai.com/docs",
                    snippets=["structured output docs"],
                )
            ],
        )

    monkeypatch.setattr(
        "radar.core.chat.brave_search_tools.search_context",
        fake_search_context,
    )

    result = RadarBraveSearchTools(config).search_web(
        {
            "query": "OpenAI structured outputs",
            "count": 2,
            "max_tokens": 2048,
            "max_tokens_per_url": 512,
            "threshold": "strict",
            "include_sites": ["platform.openai.com"],
        }
    )

    assert captured == {
        "query": "OpenAI structured outputs",
        "count": 2,
        "max_tokens": 2048,
        "max_tokens_per_url": 512,
        "threshold": "strict",
        "include_sites": ["platform.openai.com"],
        "exclude_sites": None,
    }
    assert result == {
        "source": "brave_search",
        "query": "OpenAI structured outputs",
        "item_count": 1,
        "items": [
            {
                "title": "OpenAI Docs",
                "url": "https://platform.openai.com/docs",
                "snippets": ["structured output docs"],
            }
        ],
    }


def test_stock_disclosure_search_prefers_official_sites(tmp_path, monkeypatch):
    config = RadarConfig(storage={"data_dir": tmp_path})

    monkeypatch.setattr(
        "radar.core.chat.brave_search_tools.resolve_stock",
        lambda config, stock: "600233.SH",
    )

    captured = {}

    def fake_search_cninfo_disclosures(**kwargs):
        captured.update(kwargs)
        return {
            "source": "cninfo",
            "scope": "cninfo_disclosure_list",
            "stock": kwargs["stock"],
            "code": "600233",
            "name": "圆通速递",
            "org_id": "gssh0600233",
            "category": "业绩预告",
            "keywords": kwargs["keywords"],
            "start_date": "2026-06-01",
            "end_date": "2026-07-01",
            "query_attempts": [{"category": "业绩预告", "keyword": "", "total": 1}],
            "item_count": 1,
            "items": [
                {
                    "code": "600233",
                    "name": "圆通速递",
                    "title": "圆通速递股份有限公司关于2026年半年度业绩预增的公告",
                    "announcement_time": "2026-07-01 08:00:00",
                    "url": "http://www.cninfo.com.cn/new/disclosure/detail?announcementId=1",
                }
            ],
        }

    def fake_search_context(*args, **kwargs):
        raise AssertionError("cninfo 命中时不应调用 Brave")

    monkeypatch.setattr(
        "radar.core.chat.brave_search_tools.search_cninfo_disclosures",
        fake_search_cninfo_disclosures,
    )
    monkeypatch.setattr(
        "radar.core.chat.brave_search_tools.search_context",
        fake_search_context,
    )

    result = RadarBraveSearchTools(config).search_stock_disclosures(
        {
            "stock": "圆通速递",
            "keywords": ["业绩预告", "净利润"],
            "category": "业绩预告",
            "start_date": "2026-06-01",
            "end_date": "2026-07-01",
            "count": 3,
        }
    )

    assert captured["stock"] == "圆通速递"
    assert captured["ts_code"] == "600233.SH"
    assert captured["keywords"] == ["业绩预告", "净利润"]
    assert captured["category"] == "业绩预告"
    assert captured["limit"] == 3
    assert result["source"] == "cninfo"
    assert result["scope"] == "cninfo_disclosure_list"
    assert result["ts_code"] == "600233.SH"
    assert result["item_count"] == 1
    assert "半年度业绩预增" in result["items"][0]["title"]


def test_stock_disclosure_search_falls_back_to_brave_when_cninfo_empty(tmp_path, monkeypatch):
    config = RadarConfig(storage={"data_dir": tmp_path})
    captured = {}

    monkeypatch.setattr(
        "radar.core.chat.brave_search_tools.resolve_stock",
        lambda config, stock: "600233.SH",
    )

    def fake_search_cninfo_disclosures(**kwargs):
        return {
            "source": "cninfo",
            "scope": "cninfo_disclosure_list",
            "stock": kwargs["stock"],
            "code": "600233",
            "name": "圆通速递",
            "org_id": "gssh0600233",
            "category": kwargs["category"],
            "keywords": kwargs["keywords"],
            "start_date": kwargs["start_date"],
            "end_date": kwargs["end_date"],
            "query_attempts": [],
            "item_count": 0,
            "items": [],
        }

    def fake_search_context(
        config,
        query,
        *,
        count,
        max_tokens,
        max_tokens_per_url,
        threshold,
        include_sites,
        exclude_sites,
    ):
        captured.update(
            {
                "query": query,
                "count": count,
                "max_tokens": max_tokens,
                "max_tokens_per_url": max_tokens_per_url,
                "threshold": threshold,
                "include_sites": include_sites,
                "exclude_sites": exclude_sites,
            }
        )
        return BraveSearchContextResult(
            query=query,
            items=[
                BraveSearchContextItem(
                    title="圆通速递公告",
                    url="https://www.sse.com.cn/disclosure/listedinfo/announcement/",
                    snippets=["2026 半年度业绩预告"],
                )
            ],
        )

    monkeypatch.setattr(
        "radar.core.chat.brave_search_tools.search_cninfo_disclosures",
        fake_search_cninfo_disclosures,
    )
    monkeypatch.setattr(
        "radar.core.chat.brave_search_tools.search_context",
        fake_search_context,
    )

    result = RadarBraveSearchTools(config).search_stock_disclosures(
        {
            "stock": "圆通速递",
            "keywords": ["业绩预告", "净利润"],
            "category": "业绩预告",
            "start_date": "2026-06-01",
            "end_date": "2026-07-01",
            "count": 3,
        }
    )

    assert "圆通速递" in captured["query"]
    assert "600233" in captured["query"]
    assert "业绩预告" in captured["query"]
    assert captured["include_sites"] == ["cninfo.com.cn", "sse.com.cn", "szse.cn"]
    assert captured["threshold"] == "balanced"
    assert captured["exclude_sites"] is None
    assert result["scope"] == "official_disclosure_sites"
    assert result["ts_code"] == "600233.SH"
    assert result["cninfo"]["item_count"] == 0
    assert result["item_count"] == 1


def test_stock_disclosure_search_keeps_cninfo_empty_when_brave_unconfigured(tmp_path, monkeypatch):
    config = RadarConfig(storage={"data_dir": tmp_path})

    monkeypatch.setattr(
        "radar.core.chat.brave_search_tools.resolve_stock",
        lambda config, stock: "688376.SH",
    )
    monkeypatch.setattr(
        "radar.core.chat.brave_search_tools.search_cninfo_disclosures",
        lambda **kwargs: {
            "source": "cninfo",
            "scope": "cninfo_disclosure_list",
            "stock": kwargs["stock"],
            "code": "688376",
            "name": "美埃科技",
            "org_id": "gssh688376",
            "category": kwargs["category"],
            "keywords": kwargs["keywords"],
            "start_date": kwargs["start_date"],
            "end_date": kwargs["end_date"],
            "query_attempts": [],
            "item_count": 0,
            "items": [],
        },
    )

    def fake_search_context(*args, **kwargs):
        raise BraveSearchConfigError("Brave Search 未配置")

    monkeypatch.setattr(
        "radar.core.chat.brave_search_tools.search_context",
        fake_search_context,
    )

    result = RadarBraveSearchTools(config).search_stock_disclosures(
        {
            "stock": "美埃科技",
            "keywords": ["业绩预告"],
            "category": "业绩预告",
            "start_date": "2026-06-01",
            "end_date": "2026-07-01",
        }
    )

    assert result["source"] == "cninfo"
    assert result["code"] == "688376"
    assert result["name"] == "美埃科技"
    assert result["ts_code"] == "688376.SH"
    assert result["item_count"] == 0
    assert "Brave Search 未配置" in result["brave_error"]
