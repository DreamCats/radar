from __future__ import annotations

from fastapi.testclient import TestClient

from radar.web.server.app import create_app

from tests.web.test_server import _config


def test_industry_chains_endpoint_lists_content_assets(tmp_path):
    client = TestClient(create_app(_config(tmp_path)))

    response = client.get("/api/industry-chains")

    assert response.status_code == 200
    data = response.json()
    assert data["items"][0]["chain_id"] == "ai-liquid-cooling"
    assert data["items"][0]["data_path"] == "chains/ai-liquid-cooling.json"


def test_industry_chain_detail_endpoint_returns_markdown_and_graph(tmp_path):
    client = TestClient(create_app(_config(tmp_path)))

    response = client.get("/api/industry-chains/ai-liquid-cooling")

    assert response.status_code == 200
    data = response.json()
    assert data["item"]["chain_id"] == "ai-liquid-cooling"
    assert "AI 算力液冷产业链样板页" in data["content_markdown"]
    assert data["data"]["learning_steps"][0]["id"] == "why-now"
    assert data["data"]["nodes"][0]["id"] == "demand-ai-compute"
    assert data["data"]["companies"][0]["ts_code"] == "002837.SZ"


def test_industry_chain_detail_endpoint_returns_404_for_unknown_chain(tmp_path):
    client = TestClient(create_app(_config(tmp_path)))

    response = client.get("/api/industry-chains/unknown")

    assert response.status_code == 404
