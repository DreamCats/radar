from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from radar.core.config import RadarConfig, load_config
from radar.web.server.routers import health, ingest, messages, runs


def create_app(config: RadarConfig | None = None) -> FastAPI:
    """创建 Web API；业务逻辑仍由 core/usecases 承担。"""

    app = FastAPI(title="radar dashboard", version="0.1.0")
    app.state.radar_config = config or load_config()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://127.0.0.1:5173",
            "http://localhost:5173",
        ],
        allow_origin_regex=r"http://(127\.0\.0\.1|localhost):\d+",
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(health.router)
    app.include_router(messages.router)
    app.include_router(runs.router)
    app.include_router(ingest.router)

    @app.get("/")
    def root() -> dict[str, str]:
        return {
            "detail": "请打开 radar dashboard 命令输出的 dashboard 地址；API 健康检查见 /api/health",
        }

    return app
