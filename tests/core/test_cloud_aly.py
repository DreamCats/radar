from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from radar.core.cloud import AlyUploadError, RuntimeAlyCloud, upload_aly, upload_file
from radar.core.config import RadarConfig


def test_upload_file_uploads_to_remote_dir(monkeypatch, tmp_path: Path):
    local = tmp_path / "alert.html"
    local.write_text("<html></html>", encoding="utf-8")
    commands: list[list[str]] = []

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr("radar.core.cloud.aly.subprocess.run", fake_run)

    result = upload_file(
        RuntimeAlyCloud(
            host="39.106.190.32",
            user="root",
            password="secret",
            remote_dir="/usr/share/caddy/radar",
            url_prefix="http://39.106.190.32/radar",
        ),
        local,
        "messages/2026-06-28/alert.html",
    )

    assert result.remote_path == "/usr/share/caddy/radar/messages/2026-06-28/alert.html"
    assert result.url == "http://39.106.190.32/radar/messages/2026-06-28/alert.html"
    assert commands[0][:3] == ["sshpass", "-p", "secret"]
    assert commands[0][3:6] == ["ssh", "-p", "22"]
    assert commands[0][-3:] == [
        "mkdir",
        "-p",
        "/usr/share/caddy/radar/messages/2026-06-28",
    ]
    assert commands[1][:3] == ["sshpass", "-p", "secret"]
    assert commands[1][3:6] == ["scp", "-P", "22"]
    assert commands[1][-1] == (
        "root@39.106.190.32:/usr/share/caddy/radar/messages/2026-06-28/alert.html"
    )


def test_upload_aly_resolves_radar_config(monkeypatch, tmp_path: Path):
    local = tmp_path / "alert.html"
    local.write_text("<html></html>", encoding="utf-8")
    commands: list[list[str]] = []

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr("radar.core.cloud.aly.subprocess.run", fake_run)
    config = RadarConfig(
        storage={"data_dir": tmp_path},
        cloud={
            "aly": {
                "enabled": True,
                "secret_ref": "aly_main",
                "host": "39.106.190.32",
                "user": "root",
                "remote_dir": "/usr/share/caddy/radar",
                "url_prefix": "http://39.106.190.32/radar",
                "sshpass_path": "/opt/homebrew/bin/sshpass",
            }
        },
        secrets={"cloud": {"aly": {"aly_main": {"password": "secret"}}}},
    )

    result = upload_aly(config, local, "/messages/report.html")

    assert result.url == "http://39.106.190.32/radar/messages/report.html"
    assert commands[0][:3] == ["/opt/homebrew/bin/sshpass", "-p", "secret"]


def test_upload_file_rejects_invalid_relative_path(tmp_path: Path):
    local = tmp_path / "alert.html"
    local.write_text("<html></html>", encoding="utf-8")

    with pytest.raises(AlyUploadError, match="非法远程相对路径"):
        upload_file(
            RuntimeAlyCloud(
                host="39.106.190.32",
                user="root",
                remote_dir="/usr/share/caddy/radar",
                url_prefix="http://39.106.190.32/radar",
            ),
            local,
            "../alert.html",
        )


def test_upload_aly_requires_enabled_config(tmp_path: Path):
    local = tmp_path / "alert.html"
    local.write_text("<html></html>", encoding="utf-8")

    with pytest.raises(AlyUploadError, match="Aly 静态上传未配置"):
        upload_aly(RadarConfig(storage={"data_dir": tmp_path}), local, "alert.html")
