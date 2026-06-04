from __future__ import annotations

import threading
import time

from radar.core.work_pool import run_work_pool


def test_run_work_pool_limits_concurrency():
    active_count = 0
    max_active_count = 0
    lock = threading.Lock()
    results: list[int] = []

    def worker(_index: int, item: int) -> int:
        nonlocal active_count, max_active_count
        with lock:
            active_count += 1
            max_active_count = max(max_active_count, active_count)
        time.sleep(0.02)
        with lock:
            active_count -= 1
        return item * 2

    def on_result(_index: int, _item: int, result: int) -> None:
        results.append(result)

    stats = run_work_pool(
        [1, 2, 3, 4, 5],
        max_workers=2,
        worker=worker,
        on_result=on_result,
        on_error=lambda _index, _item, error: (_ for _ in ()).throw(error),
    )

    assert stats.actual_workers == 2
    assert stats.completed_count == 5
    assert stats.failed_count == 0
    assert max_active_count <= 2
    assert sorted(results) == [2, 4, 6, 8, 10]


def test_run_work_pool_calls_result_before_submitting_next_item():
    completed: list[int] = []

    def worker(index: int, item: int) -> int:
        if index == 1:
            assert completed == [0]
        return item

    def on_result(index: int, _item: int, _result: int) -> None:
        completed.append(index)

    stats = run_work_pool(
        [10, 20],
        max_workers=1,
        worker=worker,
        on_result=on_result,
        on_error=lambda _index, _item, error: (_ for _ in ()).throw(error),
    )

    assert stats.completed_count == 2
    assert completed == [0, 1]


def test_run_work_pool_reports_errors_and_continues():
    errors: list[str] = []
    results: list[int] = []

    def worker(_index: int, item: int) -> int:
        if item == 2:
            raise RuntimeError("failed")
        return item

    def on_error(_index: int, _item: int, error: BaseException) -> None:
        errors.append(str(error))

    stats = run_work_pool(
        [1, 2, 3],
        max_workers=2,
        worker=worker,
        on_result=lambda _index, _item, result: results.append(result),
        on_error=on_error,
    )

    assert stats.completed_count == 2
    assert stats.failed_count == 1
    assert errors == ["failed"]
    assert sorted(results) == [1, 3]
