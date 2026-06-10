from __future__ import annotations

import httpx
import pytest

from radar.core.brave_search import (
    BraveSearchApiError,
    BraveSearchConfigError,
    resolve_provider,
    search_context,
)
from radar.core.config import RadarConfig


def test_resolve_provider_requires_brave_search_config(tmp_path):
    config = RadarConfig(storage={"data_dir": tmp_path})

    with pytest.raises(BraveSearchConfigError, match="RADAR_BRAVE_SEARCH_API_KEY"):
        resolve_provider(config)


def test_search_context_posts_to_brave_llm_context(monkeypatch, tmp_path):
    config = _config(tmp_path)
    captured = {}

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self):
            return {
                "grounding": {
                    "generic": [
                        {
                            "url": "https://example.com/a",
                            "title": "Example A",
                            "snippets": ["alpha", "beta"],
                        }
                    ]
                }
            }

    class FakeClient:
        def __init__(self, *, timeout):
            captured["timeout"] = timeout

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def post(self, url, *, json, headers):
            captured.update({"url": url, "json": json, "headers": headers})
            return FakeResponse()

    monkeypatch.setattr("radar.core.brave_search.client.httpx.Client", FakeClient)

    result = search_context(
        config,
        "AI 投资",
        count=3,
        max_tokens=2048,
        max_tokens_per_url=512,
        threshold="strict",
        include_sites=["example.com"],
    )

    assert captured["url"] == "https://api.search.brave.com/res/v1/llm/context"
    assert captured["timeout"] == 10
    assert captured["headers"]["X-Subscription-Token"] == "brave-secret"
    assert captured["json"] == {
        "q": "AI 投资",
        "count": 3,
        "maximum_number_of_tokens": 2048,
        "maximum_number_of_tokens_per_url": 512,
        "context_threshold_mode": "strict",
        "goggles": "$discard\n$boost,site=example.com",
    }
    assert result.query == "AI 投资"
    assert result.items[0].url == "https://example.com/a"
    assert result.items[0].title == "Example A"
    assert result.items[0].snippets == ["alpha", "beta"]


def test_search_context_rejects_empty_query(tmp_path):
    with pytest.raises(ValueError, match="query"):
        search_context(_config(tmp_path), " ")


def test_search_context_rejects_too_small_token_budget(tmp_path):
    with pytest.raises(ValueError, match="1024"):
        search_context(_config(tmp_path), "AI", max_tokens=512)


def test_search_context_maps_status_errors(monkeypatch, tmp_path):
    class FakeResponse:
        status_code = 401

        def raise_for_status(self) -> None:
            request = httpx.Request(
                "POST",
                "https://api.search.brave.com/res/v1/llm/context",
            )
            response = httpx.Response(401, request=request)
            raise httpx.HTTPStatusError("unauthorized", request=request, response=response)

    class FakeClient:
        def __init__(self, *, timeout):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def post(self, url, *, json, headers):
            return FakeResponse()

    monkeypatch.setattr("radar.core.brave_search.client.httpx.Client", FakeClient)

    with pytest.raises(BraveSearchApiError, match="status=401"):
        search_context(_config(tmp_path), "AI")


def _config(tmp_path) -> RadarConfig:
    return RadarConfig(
        storage={"data_dir": tmp_path},
        brave_search={"provider": "brave", "secret_ref": "brave_main", "timeout": 10},
        secrets={"brave_search": {"brave_main": {"api_key": "brave-secret"}}},
    )
