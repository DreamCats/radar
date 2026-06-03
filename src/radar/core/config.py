from __future__ import annotations

import os
from pathlib import Path

from pydantic import BaseModel, Field


class RadarConfig(BaseModel):
    """运行配置只放本地路径和入口，不承载业务规则。"""

    data_dir: Path = Field(default_factory=lambda: Path.home() / ".config" / "radar")
    wechat_base_url: str | None = None

    @property
    def database_path(self) -> Path:
        return self.data_dir / "radar.sqlite3"


def load_config() -> RadarConfig:
    """从环境变量读取最小配置，避免把个人数据入口写进代码。"""

    data_dir = os.getenv("RADAR_DATA_DIR")
    return RadarConfig(
        data_dir=Path(data_dir).expanduser() if data_dir else Path.home() / ".config" / "radar",
        wechat_base_url=os.getenv("RADAR_WECHAT_BASE_URL"),
    )
