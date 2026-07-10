from __future__ import annotations

from datetime import datetime

from fastapi.testclient import TestClient

from radar.core.config import RadarConfig
from radar.core.storage.valuation_store import ValuationMeasurementItemInput, save_valuation_measurement
from radar.web.server.app import create_app


def test_valuation_measurement_opportunities_endpoint(tmp_path):
    config = RadarConfig(storage={"data_dir": tmp_path / "data"})
    save_valuation_measurement(
        config.valuation_database_path,
        report_id="report-1",
        chat_run_id="run-1",
        session_id="session-1",
        source_generated_at=datetime.fromisoformat("2026-07-10T01:00:00"),
        measured_at=datetime.fromisoformat("2026-07-10T01:30:00"),
        parse_status="ready",
        parse_error=None,
        items=[
            ValuationMeasurementItemInput(
                rank=1,
                ts_code="300037.SZ",
                name="新宙邦",
                upside_text="+50%",
                valuation_status="显著空间",
                notification_level="可通知",
                anchor_type="券商目标价",
                evidence_level="中等证据",
                is_positive=True,
            )
        ],
    )

    response = TestClient(create_app(config)).get("/api/valuation-measurements/opportunities")

    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 1
    assert items[0]["stock_key"] == "300037.SZ"
    assert items[0]["latest"]["report_id"] == "report-1"
    assert items[0]["latest"]["notification_level"] == "可通知"
