from __future__ import annotations

from threading import Event, Thread
from time import sleep

from radar.web.server.read_through import ReadRequestCoordinator


def test_read_request_coordinator_caches_result():
    coordinator = ReadRequestCoordinator(slow_threshold_seconds=999)
    calls = 0

    def compute() -> dict[str, int]:
        nonlocal calls
        calls += 1
        return {"value": calls}

    first = coordinator.get_or_compute(
        key="same",
        operation="/api/test",
        group="normal",
        ttl_seconds=60,
        compute=compute,
    )
    second = coordinator.get_or_compute(
        key="same",
        operation="/api/test",
        group="normal",
        ttl_seconds=60,
        compute=compute,
    )

    assert first == {"value": 1}
    assert second == {"value": 1}
    assert calls == 1


def test_read_request_coordinator_joins_inflight_request():
    coordinator = ReadRequestCoordinator(slow_threshold_seconds=999)
    started = Event()
    release = Event()
    calls = 0
    results: list[str] = []
    errors: list[BaseException] = []

    def compute() -> str:
        nonlocal calls
        calls += 1
        started.set()
        if not release.wait(timeout=2):
            raise TimeoutError("release not set")
        return "done"

    def worker() -> None:
        try:
            results.append(
                coordinator.get_or_compute(
                    key="same",
                    operation="/api/test",
                    group="normal",
                    ttl_seconds=60,
                    compute=compute,
                )
            )
        except BaseException as exc:
            errors.append(exc)

    first_thread = Thread(target=worker)
    first_thread.start()
    assert started.wait(timeout=2)

    second_thread = Thread(target=worker)
    second_thread.start()
    sleep(0.05)
    release.set()

    first_thread.join(timeout=2)
    second_thread.join(timeout=2)

    assert errors == []
    assert sorted(results) == ["done", "done"]
    assert calls == 1
