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
    assert [item["chain_id"] for item in data["items"]] == [
        "ai-liquid-cooling",
        "solid-state-battery",
        "short-drama-entertainment",
        "humanoid-robotics",
        "low-altitude-economy",
        "innovative-drugs",
    ]


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


def test_industry_chain_detail_endpoint_returns_custom_flow_columns(tmp_path):
    client = TestClient(create_app(_config(tmp_path)))

    response = client.get("/api/industry-chains/solid-state-battery")

    assert response.status_code == 200
    data = response.json()
    assert data["item"]["chain_id"] == "solid-state-battery"
    assert "固态电池产业链学习页" in data["content_markdown"]
    assert data["data"]["flow_columns"][0]["node_ids"] == ["high-energy-demand"]
    assert data["data"]["nodes"][0]["id"] == "high-energy-demand"
    assert data["data"]["companies"][0]["ts_code"] == "300750.SZ"


def test_industry_chain_detail_endpoint_returns_commercial_model_chain(tmp_path):
    client = TestClient(create_app(_config(tmp_path)))

    response = client.get("/api/industry-chains/short-drama-entertainment")

    assert response.status_code == 200
    data = response.json()
    assert data["item"]["chain_id"] == "short-drama-entertainment"
    assert "微短剧 / 影视娱乐产业链学习页" in data["content_markdown"]
    assert data["data"]["flow_columns"][0]["node_ids"] == ["fragmented-attention-demand"]
    assert data["data"]["nodes"][0]["id"] == "fragmented-attention-demand"
    assert data["data"]["companies"][0]["ts_code"] == "603533.SH"


def test_industry_chain_detail_endpoint_returns_humanoid_robotics_chain(tmp_path):
    client = TestClient(create_app(_config(tmp_path)))

    response = client.get("/api/industry-chains/humanoid-robotics")

    assert response.status_code == 200
    data = response.json()
    assert data["item"]["chain_id"] == "humanoid-robotics"
    assert "人形机器人 / 具身智能产业链学习页" in data["content_markdown"]
    assert data["data"]["flow_columns"][0]["node_ids"] == ["embodied-ai-demand"]
    assert data["data"]["nodes"][0]["id"] == "embodied-ai-demand"
    assert data["data"]["companies"][0]["ts_code"] == "688017.SH"


def test_industry_chain_detail_endpoint_returns_low_altitude_economy_chain(tmp_path):
    client = TestClient(create_app(_config(tmp_path)))

    response = client.get("/api/industry-chains/low-altitude-economy")

    assert response.status_code == 200
    data = response.json()
    assert data["item"]["chain_id"] == "low-altitude-economy"
    assert "低空经济 / eVTOL产业链学习页" in data["content_markdown"]
    assert data["data"]["flow_columns"][0]["node_ids"] == [
        "policy-airspace-opening",
        "airworthiness-certification",
        "airspace-management",
    ]
    assert data["data"]["nodes"][0]["id"] == "policy-airspace-opening"
    assert data["data"]["companies"][0]["ts_code"] == "002085.SZ"


def test_industry_chain_detail_endpoint_returns_innovative_drugs_chain(tmp_path):
    client = TestClient(create_app(_config(tmp_path)))

    response = client.get("/api/industry-chains/innovative-drugs")

    assert response.status_code == 200
    data = response.json()
    assert data["item"]["chain_id"] == "innovative-drugs"
    assert "创新药 / ADC / 双抗出海产业链学习页" in data["content_markdown"]
    assert data["data"]["flow_columns"][0]["node_ids"] == [
        "unmet-clinical-need",
        "policy-payment-support",
    ]
    assert data["data"]["nodes"][0]["id"] == "unmet-clinical-need"
    assert data["data"]["companies"][0]["ts_code"] == "688235.SH"


def test_industry_chain_detail_endpoint_returns_404_for_unknown_chain(tmp_path):
    client = TestClient(create_app(_config(tmp_path)))

    response = client.get("/api/industry-chains/unknown")

    assert response.status_code == 404
