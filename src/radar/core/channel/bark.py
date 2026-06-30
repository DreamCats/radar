from __future__ import annotations

import time
from typing import Any, Literal

import httpx
from pydantic import BaseModel, Field

from radar.core.config import RadarConfig

BARK_CONFIG_HINT = (
    "Bark 未配置：请设置环境变量 RADAR_BARK_DEVICE_KEY，"
    "或在 radar secrets.yaml 配置 secrets.channel.bark.<name>.device_key/device_keys，"
    "并在 config.yaml 设置 channel.bark.enabled=true、channel.bark.secret_ref=<name>"
)
BarkLevel = Literal["critical", "active", "timeSensitive", "passive"]
_RETRY_DELAYS = (1.0, 3.0)


class BarkError(RuntimeError):
    pass


class BarkConfigError(BarkError):
    pass


class BarkHttpError(BarkError):
    pass


class BarkApiError(BarkError):
    pass


class RuntimeBarkChannel(BaseModel):
    device_keys: list[str]
    base_url: str
    timeout: float
    default_group: str | None = None
    default_level: BarkLevel | None = None


class BarkMessage(BaseModel):
    body: str
    title: str | None = None
    subtitle: str | None = None
    url: str | None = None
    group: str | None = None
    level: BarkLevel | None = None
    sound: str | None = None
    icon: str | None = None
    badge: int | None = Field(default=None, ge=0)
    is_archive: bool | None = None


class BarkPushResult(BaseModel):
    code: int | None = None
    message: str | None = None
    timestamp: int | None = None
    raw: dict[str, Any]


def resolve_bark_channel(config: RadarConfig) -> RuntimeBarkChannel:
    """把 radar 配置解析成 Bark 运行期 channel。"""

    bark_config = config.channel.bark
    if not bark_config.enabled:
        raise BarkConfigError(BARK_CONFIG_HINT)
    if not bark_config.secret_ref:
        raise BarkConfigError(BARK_CONFIG_HINT)

    secret = config.secrets.channel.bark.get(bark_config.secret_ref)
    if secret is None:
        raise BarkConfigError(
            f"未配置 Bark device_key/device_keys: {bark_config.secret_ref}。"
            f"{BARK_CONFIG_HINT}"
        )
    device_keys = _device_keys(secret.device_key, secret.device_keys)
    if not device_keys:
        raise BarkConfigError(
            f"未配置 Bark device_key/device_keys: {bark_config.secret_ref}。"
            f"{BARK_CONFIG_HINT}"
        )

    return RuntimeBarkChannel(
        device_keys=device_keys,
        base_url=bark_config.base_url.rstrip("/"),
        timeout=bark_config.timeout,
        default_group=bark_config.default_group,
        default_level=bark_config.default_level,
    )


def push_bark(config: RadarConfig, message: BarkMessage) -> BarkPushResult:
    """发送一条 Bark 通知；只负责 channel 投递，不负责筛选和去重。"""

    channel = resolve_bark_channel(config)
    body = _push_body(channel, message)
    raw = _post_json(channel, "/push", body)
    code = _optional_int(raw.get("code"))
    result = BarkPushResult(
        code=code,
        message=_optional_str(raw.get("message")),
        timestamp=_optional_int(raw.get("timestamp")),
        raw=raw,
    )
    if code is not None and code != 200:
        raise BarkApiError(f"Bark API 返回错误: code={code} message={result.message or ''}")
    return result


def _push_body(channel: RuntimeBarkChannel, message: BarkMessage) -> dict[str, Any]:
    body_text = message.body.strip()
    if not body_text:
        raise ValueError("Bark body 不能为空")

    body: dict[str, Any] = {"body": body_text}
    if len(channel.device_keys) == 1:
        body["device_key"] = channel.device_keys[0]
    else:
        body["device_keys"] = channel.device_keys
    _put_optional(body, "title", message.title)
    _put_optional(body, "subtitle", message.subtitle)
    _put_optional(body, "url", message.url)
    _put_optional(body, "group", message.group or channel.default_group)
    _put_optional(body, "level", message.level or channel.default_level)
    _put_optional(body, "sound", message.sound)
    _put_optional(body, "icon", message.icon)
    if message.badge is not None:
        body["badge"] = message.badge
    if message.is_archive:
        body["isArchive"] = "1"
    return body


def _post_json(
    channel: RuntimeBarkChannel,
    path: str,
    body: dict[str, Any],
) -> dict[str, Any]:
    url = f"{channel.base_url}{path}"
    timeout = _httpx_timeout(channel.timeout)
    retry_count = len(_RETRY_DELAYS)
    attempt = 0
    while True:
        try:
            with httpx.Client(timeout=timeout) as client:
                response = client.post(
                    url,
                    json=body,
                    headers={"Content-Type": "application/json; charset=utf-8"},
                )
                response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise BarkApiError(
                f"Bark API 返回错误: status={exc.response.status_code} url={_safe_url(url)}"
            ) from exc
        except httpx.TimeoutException as exc:
            if attempt < retry_count:
                time.sleep(_RETRY_DELAYS[attempt])
                attempt += 1
                continue
            raise BarkHttpError(
                f"调用 Bark 超时: url={_safe_url(url)} timeout={channel.timeout}s"
            ) from exc
        except httpx.NetworkError as exc:
            if attempt < retry_count:
                time.sleep(_RETRY_DELAYS[attempt])
                attempt += 1
                continue
            raise BarkHttpError(f"调用 Bark 失败: url={_safe_url(url)} error={exc}") from exc
        except httpx.HTTPError as exc:
            raise BarkHttpError(f"调用 Bark 失败: url={_safe_url(url)} error={exc}") from exc
        break

    data = response.json()
    if not isinstance(data, dict):
        raise BarkApiError("Bark 返回不是 JSON object")
    return data


def _httpx_timeout(timeout: float) -> httpx.Timeout:
    value = max(float(timeout), 0.1)
    short_timeout = min(3.0, value)
    return httpx.Timeout(
        value,
        connect=short_timeout,
        write=short_timeout,
        pool=short_timeout,
        read=min(8.0, value),
    )


def _put_optional(body: dict[str, Any], key: str, value: object) -> None:
    if value is None:
        return
    text = str(value).strip()
    if text:
        body[key] = text


def _device_keys(device_key: str | None, device_keys: list[str]) -> list[str]:
    keys = []
    for key in [device_key, *device_keys]:
        if key is None:
            continue
        text = key.strip()
        if text and text not in keys:
            keys.append(text)
    return keys


def _optional_str(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _safe_url(url: str) -> str:
    return url.split("?", 1)[0]
