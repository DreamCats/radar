from __future__ import annotations

import secrets

from fastapi import Request

from radar.core.config import RadarConfig

AUTH_SCHEME = "Bearer"


def auth_required(config: RadarConfig) -> bool:
    return config.web.auth.enabled


def authenticate(config: RadarConfig, token: str) -> bool:
    expected = _configured_token(config)
    if not auth_required(config) or expected is None:
        return False
    return secrets.compare_digest(token, expected)


def request_authenticated(config: RadarConfig, request: Request) -> bool:
    if not auth_required(config):
        return True
    token = _bearer_token(request)
    return token is not None and authenticate(config, token)


def _bearer_token(request: Request) -> str | None:
    header = request.headers.get("authorization")
    if not header:
        return None
    scheme, _, token = header.partition(" ")
    if scheme.lower() != AUTH_SCHEME.lower() or not token.strip():
        return None
    return token.strip()


def _configured_token(config: RadarConfig) -> str | None:
    return config.secrets.web.auth.token
