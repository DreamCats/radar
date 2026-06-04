from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RuntimeTushareProvider:
    """一次 Tushare 调用需要的运行期配置。"""

    api_url: str
    token: str
    timeout: float
    database: Path


@dataclass(frozen=True)
class HistorySpec:
    """可长期行缓存的 Tushare 接口规约。"""

    api_name: str
    date_field: str
    date_kind: str
    ts_code_field: str | None = "ts_code"
    req_start_param: str = "start_date"
    req_end_param: str = "end_date"
    req_ts_code_param: str | None = "ts_code"
