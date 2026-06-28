from __future__ import annotations

import httpx
import pytest

from radar.core.channel import (
    BarkApiError,
    BarkConfigError,
    BarkMessage,
    push_bark,
    resolve_bark_channel,
)
from radar.core.config import RadarConfig


def test_resolve_bark_channel_requires_config(tmp_path):
    config = RadarConfig(storage={"data_dir": tmp_path})

    with pytest.raises(BarkConfigError, match="RADAR_BARK_DEVICE_KEY"):
        resolve_bark_channel(config)


def test_push_bark_posts_json(monkeypatch, tmp_path):
    config = _config(tmp_path)
    captured = {}

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self):
            return {"code": 200, "message": "success", "timestamp": 123}

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

    monkeypatch.setattr("radar.core.channel.bark.httpx.Client", FakeClient)

    result = push_bark(
        config,
        BarkMessage(
            title="消息面提醒",
            subtitle="氮化铝",
            body="2 条新消息",
            url="https://radar.example/catalyst",
            sound="minuet",
            badge=1,
            is_archive=True,
        ),
    )

    assert captured["url"] == "https://api.day.app/push"
    assert captured["timeout"] == 8
    assert captured["headers"]["Content-Type"] == "application/json; charset=utf-8"
    assert captured["json"] == {
        "device_key": "bark-key",
        "body": "2 条新消息",
        "title": "消息面提醒",
        "subtitle": "氮化铝",
        "url": "https://radar.example/catalyst",
        "group": "radar",
        "level": "timeSensitive",
        "sound": "minuet",
        "badge": 1,
        "isArchive": "1",
    }
    assert result.code == 200
    assert result.message == "success"
    assert result.timestamp == 123


def test_push_bark_posts_device_keys_for_multiple_devices(monkeypatch, tmp_path):
    config = RadarConfig(
        storage={"data_dir": tmp_path},
        channel={"bark": {"enabled": True, "secret_ref": "bark_main"}},
        secrets={
            "channel": {
                "bark": {
                    "bark_main": {
                        "device_key": "bark-key-a",
                        "device_keys": ["bark-key-b", "bark-key-c"],
                    }
                }
            }
        },
    )
    captured = {}

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self):
            return {"code": 200, "message": "success"}

    class FakeClient:
        def __init__(self, *, timeout):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def post(self, url, *, json, headers):
            captured["json"] = json
            return FakeResponse()

    monkeypatch.setattr("radar.core.channel.bark.httpx.Client", FakeClient)

    push_bark(config, BarkMessage(body="多设备"))

    assert captured["json"] == {
        "body": "多设备",
        "device_keys": ["bark-key-a", "bark-key-b", "bark-key-c"],
    }


def test_push_bark_rejects_empty_body(tmp_path):
    with pytest.raises(ValueError, match="body"):
        push_bark(_config(tmp_path), BarkMessage(body=" "))


def test_push_bark_maps_status_errors(monkeypatch, tmp_path):
    class FakeResponse:
        def raise_for_status(self) -> None:
            request = httpx.Request("POST", "https://api.day.app/push")
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

    monkeypatch.setattr("radar.core.channel.bark.httpx.Client", FakeClient)

    with pytest.raises(BarkApiError, match="status=401"):
        push_bark(_config(tmp_path), BarkMessage(body="测试"))


def test_push_bark_rejects_non_success_code(monkeypatch, tmp_path):
    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self):
            return {"code": 400, "message": "invalid key"}

    class FakeClient:
        def __init__(self, *, timeout):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def post(self, url, *, json, headers):
            return FakeResponse()

    monkeypatch.setattr("radar.core.channel.bark.httpx.Client", FakeClient)

    with pytest.raises(BarkApiError, match="code=400"):
        push_bark(_config(tmp_path), BarkMessage(body="测试"))


def _config(tmp_path) -> RadarConfig:
    return RadarConfig(
        storage={"data_dir": tmp_path},
        channel={
            "bark": {
                "enabled": True,
                "secret_ref": "bark_main",
                "timeout": 8,
                "default_group": "radar",
                "default_level": "timeSensitive",
            }
        },
        secrets={"channel": {"bark": {"bark_main": {"device_key": "bark-key"}}}},
    )
