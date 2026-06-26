from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, TypeVar, cast

from fastapi import Request

T = TypeVar("T")

logger = logging.getLogger(__name__)


@dataclass
class _CacheEntry:
    value: Any
    expires_at: float


@dataclass
class _InFlight:
    condition: threading.Condition
    done: bool = False
    value: Any = None
    error: BaseException | None = None


class ReadRequestCoordinator:
    """合并重复读请求，并对重读接口做短 TTL 缓存和并发控制。"""

    def __init__(
        self,
        *,
        normal_limit: int = 4,
        heavy_limit: int = 1,
        max_entries: int = 128,
        slow_threshold_seconds: float = 1.0,
    ) -> None:
        self._lock = threading.RLock()
        self._cache: dict[str, _CacheEntry] = {}
        self._inflight: dict[str, _InFlight] = {}
        self._semaphores = {
            "normal": threading.Semaphore(normal_limit),
            "heavy": threading.Semaphore(heavy_limit),
        }
        self._max_entries = max_entries
        self._slow_threshold_seconds = slow_threshold_seconds

    def get_or_compute(
        self,
        *,
        key: str,
        operation: str,
        group: str,
        ttl_seconds: float,
        compute: Callable[[], T],
    ) -> T:
        started_at = time.perf_counter()
        now = time.monotonic()
        with self._lock:
            entry = self._cache.get(key)
            if entry is not None and entry.expires_at > now:
                self._log_if_slow(
                    operation=operation,
                    group=group,
                    cache_state="hit",
                    singleflight_state="none",
                    queue_seconds=0.0,
                    compute_seconds=0.0,
                    total_seconds=time.perf_counter() - started_at,
                )
                return cast(T, entry.value)
            if entry is not None:
                self._cache.pop(key, None)

            inflight = self._inflight.get(key)
            if inflight is None:
                inflight = _InFlight(condition=threading.Condition(self._lock))
                self._inflight[key] = inflight
                leader = True
            else:
                leader = False

            if not leader:
                while not inflight.done:
                    inflight.condition.wait()
                total_seconds = time.perf_counter() - started_at
                self._log_if_slow(
                    operation=operation,
                    group=group,
                    cache_state="miss",
                    singleflight_state="joined",
                    queue_seconds=0.0,
                    compute_seconds=0.0,
                    total_seconds=total_seconds,
                )
                if inflight.error is not None:
                    raise inflight.error
                return cast(T, inflight.value)

        value: T | None = None
        error: BaseException | None = None
        queue_started_at = time.perf_counter()
        semaphore = self._semaphores.get(group, self._semaphores["normal"])
        semaphore.acquire()
        queue_seconds = time.perf_counter() - queue_started_at
        compute_started_at = time.perf_counter()
        try:
            value = compute()
            return value
        except BaseException as exc:
            error = exc
            raise
        finally:
            compute_seconds = time.perf_counter() - compute_started_at
            semaphore.release()
            total_seconds = time.perf_counter() - started_at
            with self._lock:
                inflight.value = value
                inflight.error = error
                inflight.done = True
                if error is None:
                    self._cache[key] = _CacheEntry(
                        value=value,
                        expires_at=time.monotonic() + ttl_seconds,
                    )
                    self._evict_locked()
                self._inflight.pop(key, None)
                inflight.condition.notify_all()
            self._log_if_slow(
                operation=operation,
                group=group,
                cache_state="miss",
                singleflight_state="new",
                queue_seconds=queue_seconds,
                compute_seconds=compute_seconds,
                total_seconds=total_seconds,
            )

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()

    def _evict_locked(self) -> None:
        now = time.monotonic()
        expired_keys = [key for key, entry in self._cache.items() if entry.expires_at <= now]
        for key in expired_keys:
            self._cache.pop(key, None)
        while len(self._cache) > self._max_entries:
            oldest_key = min(self._cache, key=lambda key: self._cache[key].expires_at)
            self._cache.pop(oldest_key, None)

    def _log_if_slow(
        self,
        *,
        operation: str,
        group: str,
        cache_state: str,
        singleflight_state: str,
        queue_seconds: float,
        compute_seconds: float,
        total_seconds: float,
    ) -> None:
        if total_seconds < self._slow_threshold_seconds and queue_seconds < 0.05:
            return
        logger.info(
            "read_request operation=%s group=%s cache=%s singleflight=%s queue_ms=%.1f "
            "compute_ms=%.1f total_ms=%.1f",
            operation,
            group,
            cache_state,
            singleflight_state,
            queue_seconds * 1000,
            compute_seconds * 1000,
            total_seconds * 1000,
        )


def request_cache_key(request: Request, *, scope: str) -> str:
    query = request.url.query
    return f"{scope}:{request.method}:{request.url.path}?{query}"


def request_operation(request: Request) -> str:
    query = request.url.query
    if not query:
        return request.url.path
    return f"{request.url.path}?{query}"
