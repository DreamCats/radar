from __future__ import annotations


class BraveSearchError(RuntimeError):
    """Brave Search core 基础异常。"""


class BraveSearchConfigError(BraveSearchError):
    """Brave Search 配置错误。"""


class BraveSearchApiError(BraveSearchError):
    """Brave Search API 返回业务错误。"""


class BraveSearchHttpError(BraveSearchError):
    """Brave Search HTTP 通信错误。"""
