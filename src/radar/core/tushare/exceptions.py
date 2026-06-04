from __future__ import annotations


class TushareError(RuntimeError):
    """Tushare core 基础异常。"""


class TushareConfigError(TushareError):
    """Tushare 配置错误。"""


class TushareApiError(TushareError):
    """Tushare API 返回业务错误。"""


class TushareHttpError(TushareError):
    """Tushare HTTP 通信错误。"""
