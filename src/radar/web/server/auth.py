from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import Request, Response

from radar.core.config import RadarConfig

AUTH_COOKIE = "radar_session"


def auth_required(config: RadarConfig) -> bool:
    secret = config.secrets.web.auth
    return bool(config.web.auth.enabled and secret.username and secret.password)


def authenticate(config: RadarConfig, username: str, password: str) -> bool:
    secret = config.secrets.web.auth
    if not auth_required(config) or secret.username is None or secret.password is None:
        return False
    return secrets.compare_digest(username, secret.username) and secrets.compare_digest(
        password,
        secret.password,
    )


def current_username(config: RadarConfig, request: Request) -> str | None:
    if not auth_required(config):
        return None
    token = request.cookies.get(AUTH_COOKIE)
    if not token:
        return None
    return _verify_token(config, token)


def set_auth_cookie(config: RadarConfig, response: Response, username: str) -> None:
    expires_at = datetime.now(timezone.utc) + timedelta(hours=config.web.auth.session_hours)
    response.set_cookie(
        AUTH_COOKIE,
        _sign_token(config, username, expires_at),
        max_age=config.web.auth.session_hours * 3600,
        httponly=True,
        samesite="lax",
    )


def clear_auth_cookie(response: Response) -> None:
    response.delete_cookie(AUTH_COOKIE, httponly=True, samesite="lax")


def _sign_token(config: RadarConfig, username: str, expires_at: datetime) -> str:
    payload = {"u": username, "exp": int(expires_at.timestamp())}
    body = _b64(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signature = hmac.new(_secret_key(config), body.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{body}.{signature}"


def _verify_token(config: RadarConfig, token: str) -> str | None:
    try:
        body, signature = token.split(".", 1)
        expected = hmac.new(_secret_key(config), body.encode("utf-8"), hashlib.sha256).hexdigest()
        if not secrets.compare_digest(signature, expected):
            return None
        payload = json.loads(_unb64(body))
        if int(payload.get("exp") or 0) < int(datetime.now(timezone.utc).timestamp()):
            return None
        username = payload.get("u")
        secret_username = config.secrets.web.auth.username
        if not isinstance(username, str) or username != secret_username:
            return None
        return username
    except (binascii.Error, ValueError, TypeError, json.JSONDecodeError, UnicodeDecodeError):
        return None


def _secret_key(config: RadarConfig) -> bytes:
    secret = config.secrets.web.auth
    key = secret.session_secret or secret.password or ""
    return key.encode("utf-8")


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _unb64(data: str) -> str:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(f"{data}{padding}").decode("utf-8")
