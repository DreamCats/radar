from __future__ import annotations

from fastapi import Request

from radar.core.config import RadarConfig


def get_config(request: Request) -> RadarConfig:
    return request.app.state.radar_config

