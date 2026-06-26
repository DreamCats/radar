from __future__ import annotations

from collections.abc import Callable, Sequence
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import dataclass
from typing import Generic, TypeVar

T = TypeVar("T")
R = TypeVar("R")
U = TypeVar("U")


@dataclass(frozen=True)
class WorkPoolStats:
    actual_workers: int
    completed_count: int
    failed_count: int


def run_work_pool(
    items: Sequence[T],
    *,
    max_workers: int,
    worker: Callable[[int, T], R],
    on_result: Callable[[int, T, R], None],
    on_error: Callable[[int, T, BaseException], None],
) -> WorkPoolStats:
    """限制并发执行任务；完成一个回调一个，再补下一个。"""

    if max_workers < 1:
        raise ValueError("max_workers 必须大于 0")
    if not items:
        return WorkPoolStats(actual_workers=0, completed_count=0, failed_count=0)

    actual_workers = min(max_workers, len(items))
    completed_count = 0
    failed_count = 0
    next_index = 0

    with ThreadPoolExecutor(max_workers=actual_workers) as executor:
        pending: dict[Future[R], _PendingWork[T]] = {}
        for _ in range(actual_workers):
            next_index = _submit_next(executor, items, worker, pending, next_index)

        while pending:
            done, _ = wait(pending, return_when=FIRST_COMPLETED)
            for future in done:
                pending_work = pending.pop(future)
                try:
                    result = future.result()
                except BaseException as exc:
                    failed_count += 1
                    on_error(pending_work.index, pending_work.item, exc)
                else:
                    completed_count += 1
                    on_result(pending_work.index, pending_work.item, result)

                if next_index < len(items):
                    next_index = _submit_next(executor, items, worker, pending, next_index)

    return WorkPoolStats(
        actual_workers=actual_workers,
        completed_count=completed_count,
        failed_count=failed_count,
    )


def run_resource_work_pool(
    items: Sequence[T],
    *,
    resources: Sequence[U],
    max_workers: int,
    worker: Callable[[int, T, U], R],
    on_result: Callable[[int, T, R], None],
    on_error: Callable[[int, T, BaseException], None],
) -> WorkPoolStats:
    """限制并发执行任务，并按批次下标轮询分配外部资源。"""

    if not resources:
        raise ValueError("resources 不能为空")

    def resource_worker(index: int, item: T) -> R:
        return worker(index, item, resources[index % len(resources)])

    return run_work_pool(
        items,
        max_workers=max_workers,
        worker=resource_worker,
        on_result=on_result,
        on_error=on_error,
    )


@dataclass(frozen=True)
class _PendingWork(Generic[T]):
    index: int
    item: T


def _submit_next(
    executor: ThreadPoolExecutor,
    items: Sequence[T],
    worker: Callable[[int, T], R],
    pending: dict[Future[R], _PendingWork[T]],
    next_index: int,
) -> int:
    item = items[next_index]
    pending[executor.submit(worker, next_index, item)] = _PendingWork(index=next_index, item=item)
    return next_index + 1
