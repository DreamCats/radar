from __future__ import annotations

from radar.core.brave_search import BraveSearchContextItem, BraveSearchContextResult
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
