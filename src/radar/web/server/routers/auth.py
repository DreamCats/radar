from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from radar.core.config import RadarConfig
from radar.web.server.auth import (
    authenticate,
    auth_required,
    request_authenticated,
)
from radar.web.server.deps import get_config
from radar.web.server.schemas import AuthLoginRequest, AuthStatusResponse

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.get("/status", response_model=AuthStatusResponse)
def status(request: Request, config: RadarConfig = Depends(get_config)) -> AuthStatusResponse:
    required = auth_required(config)
    return AuthStatusResponse(
        auth_required=required,
        authenticated=not required or request_authenticated(config, request),
        username=None,
    )


@router.post("/login", response_model=AuthStatusResponse)
def login(
    payload: AuthLoginRequest,
    config: RadarConfig = Depends(get_config),
) -> AuthStatusResponse:
    if not auth_required(config):
        return AuthStatusResponse(auth_required=False, authenticated=True, username=None)
    if not authenticate(config, payload.token):
        raise HTTPException(status_code=401, detail="访问密钥不正确")
    return AuthStatusResponse(auth_required=True, authenticated=True, username=None)


@router.post("/logout", response_model=AuthStatusResponse)
def logout(config: RadarConfig = Depends(get_config)) -> AuthStatusResponse:
    return AuthStatusResponse(
        auth_required=auth_required(config),
        authenticated=not auth_required(config),
        username=None,
    )
