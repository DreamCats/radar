from __future__ import annotations

import posixpath
import subprocess
from pathlib import Path

from pydantic import BaseModel

from radar.core.cloud.upload import (
    CloudUploadError,
    CloudUploadResult,
    clean_remote_relative_path,
    public_url,
)
from radar.core.config import RadarConfig

ALY_CONFIG_HINT = (
    "Aly 静态上传未配置：请在 config.yaml 设置 cloud.aly.enabled=true、"
    "cloud.aly.host/user/remote_dir/url_prefix；如使用密码登录，"
    "在 secrets.yaml 配置 secrets.cloud.aly.<name>.password"
)


class AlyUploadError(CloudUploadError):
    pass


class RuntimeAlyCloud(BaseModel):
    host: str
    user: str
    port: int = 22
    remote_dir: str
    url_prefix: str
    password: str | None = None
    sshpass_path: str = "sshpass"


def resolve_aly_cloud(config: RadarConfig) -> RuntimeAlyCloud:
    aly = config.cloud.aly
    if not aly.enabled:
        raise AlyUploadError(ALY_CONFIG_HINT)
    if not aly.host or not aly.user or not aly.remote_dir or not aly.url_prefix:
        raise AlyUploadError(ALY_CONFIG_HINT)

    secret = config.secrets.cloud.aly.get(aly.secret_ref) if aly.secret_ref else None
    return RuntimeAlyCloud(
        host=aly.host,
        user=aly.user,
        port=aly.port,
        remote_dir=aly.remote_dir,
        url_prefix=aly.url_prefix,
        password=secret.password if secret else None,
        sshpass_path=aly.sshpass_path,
    )


def upload_aly(
    config: RadarConfig,
    local_path: Path,
    remote_relative_path: str,
) -> CloudUploadResult:
    return upload_file(resolve_aly_cloud(config), local_path, remote_relative_path)


def upload_file(
    cloud: RuntimeAlyCloud,
    local_path: Path,
    remote_relative_path: str,
) -> CloudUploadResult:
    local = local_path.expanduser()
    if not local.exists():
        raise AlyUploadError(f"本地文件不存在: {local}")
    if cloud.password and not cloud.sshpass_path:
        raise AlyUploadError("Aly password 已配置，但 sshpass_path 为空")

    try:
        relative = clean_remote_relative_path(remote_relative_path)
    except CloudUploadError as exc:
        raise AlyUploadError(str(exc)) from exc
    remote_path = posixpath.join(cloud.remote_dir.rstrip("/"), relative)
    target = f"{cloud.user}@{cloud.host}"

    _run(
        _auth_prefix(cloud)
        + [
            "ssh",
            "-p",
            str(cloud.port),
            "-o",
            "StrictHostKeyChecking=no",
            target,
            "mkdir",
            "-p",
            posixpath.dirname(remote_path),
        ]
    )
    _run(
        _auth_prefix(cloud)
        + [
            "scp",
            "-P",
            str(cloud.port),
            "-o",
            "StrictHostKeyChecking=no",
            str(local),
            f"{target}:{remote_path}",
        ]
    )
    return CloudUploadResult(
        local_path=local,
        remote_path=remote_path,
        url=public_url(cloud.url_prefix, relative),
    )


def _auth_prefix(cloud: RuntimeAlyCloud) -> list[str]:
    if not cloud.password:
        return []
    return [cloud.sshpass_path, "-p", cloud.password]


def _run(command: list[str]) -> None:
    try:
        subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as exc:
        raise AlyUploadError(f"上传命令不存在: {command[0]}") from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "").strip()
        raise AlyUploadError(f"上传命令失败: {detail}") from exc
