from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from radar.core.config import RadarConfig, load_config
from radar.web.server.auth import auth_required, request_authenticated
from radar.web.server.routers import (
    auth,
    backtest,
    catalyst_valuation_report,
    chat,
    health,
    ingest,
    industry_chains,
    market,
    messages,
    premarket,
    runs,
    schedules,
)
from radar.web.server.read_through import ReadRequestCoordinator
from radar.web.server.scheduler import SchedulerLoop


def create_app(config: RadarConfig | None = None) -> FastAPI:
    """创建 Web API；业务逻辑仍由 core/usecases 承担。"""

    app = FastAPI(title="radar dashboard", version="0.1.0", lifespan=_lifespan)
    app.state.radar_config = config or load_config()
    app.state.read_coordinator = ReadRequestCoordinator()
    app.state.scheduler_loop = SchedulerLoop(app.state.radar_config)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://127.0.0.1:5173",
            "http://localhost:5173",
        ],
        allow_origin_regex=r"http://(127\.0\.0\.1|localhost):\d+",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    _install_auth_middleware(app)
    app.include_router(auth.router)
    app.include_router(health.router)
    app.include_router(chat.router)
    app.include_router(messages.router)
    app.include_router(premarket.router)
    app.include_router(runs.router)
    app.include_router(schedules.router)
    app.include_router(ingest.router)
    app.include_router(catalyst_valuation_report.router)
    app.include_router(market.router)
    app.include_router(industry_chains.router)
    app.include_router(backtest.router)

    @app.get("/")
    def root() -> dict[str, str]:
        return {
            "detail": (
                "请打开 radar dashboard 命令输出的 dashboard 地址；"
                "API 健康检查见 /api/health"
            ),
        }

    return app


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    app.state.scheduler_loop.start()
    try:
        yield
    finally:
        app.state.scheduler_loop.stop()


def _install_auth_middleware(app: FastAPI) -> None:
    @app.middleware("http")
    async def require_login(request, call_next):
        config = request.app.state.radar_config
        if request.method == "OPTIONS":
            # CORS 预检不依赖登录 cookie，交给 CORSMiddleware 返回允许头。
            return await call_next(request)
        if _is_public_path(request.url.path) or not auth_required(config):
            return await call_next(request)
        if request_authenticated(config, request):
            return await call_next(request)
        return JSONResponse({"detail": "缺少或无效的访问密钥"}, status_code=401)


def _is_public_path(path: str) -> bool:
    return path == "/" or path.startswith("/api/auth/")
