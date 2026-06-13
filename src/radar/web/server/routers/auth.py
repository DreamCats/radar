from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from radar.core.config import RadarConfig
from radar.web.server.auth import (
    authenticate,
    auth_required,
    clear_auth_cookie,
    current_username,
    set_auth_cookie,
)
from radar.web.server.deps import get_config
from radar.web.server.schemas import AuthLoginRequest, AuthStatusResponse

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.get("/status", response_model=AuthStatusResponse)
def status(request: Request, config: RadarConfig = Depends(get_config)) -> AuthStatusResponse:
    required = auth_required(config)
    username = current_username(config, request)
    return AuthStatusResponse(
        auth_required=required,
        authenticated=not required or username is not None,
        username=username,
    )


@router.post("/login", response_model=AuthStatusResponse)
def login(
    payload: AuthLoginRequest,
    response: Response,
    config: RadarConfig = Depends(get_config),
) -> AuthStatusResponse:
    if not auth_required(config):
        return AuthStatusResponse(auth_required=False, authenticated=True, username=None)
    if not authenticate(config, payload.username, payload.password):
        raise HTTPException(status_code=401, detail="账号或密码不正确")
    set_auth_cookie(config, response, payload.username)
    return AuthStatusResponse(auth_required=True, authenticated=True, username=payload.username)


@router.post("/logout", response_model=AuthStatusResponse)
def logout(response: Response, config: RadarConfig = Depends(get_config)) -> AuthStatusResponse:
    clear_auth_cookie(response)
    return AuthStatusResponse(
        auth_required=auth_required(config),
        authenticated=not auth_required(config),
        username=None,
    )
