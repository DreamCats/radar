from __future__ import annotations

from datetime import datetime, timedelta

from radar.core.runs import fail_run, fail_stale_runs, finish_run, get_run, get_running_run, list_runs, start_run


def test_run_lifecycle_records_summary(tmp_path):
    db = tmp_path / "radar.sqlite3"

    run_id = start_run(
        db,
        kind="wechat_ingest_range",
        target="group_message:window",
        metadata={"source_key": "group_message"},
    )
    finish_run(
        db,
        run_id,
        raw_count=3,
        stored_count=2,
        filtered_count=1,
        metadata={"chunk_count": 1},
    )

    record = get_run(db, run_id)
    assert record is not None
    assert record.status == "succeeded"
    assert record.raw_count == 3
    assert record.stored_count == 2
    assert record.filtered_count == 1
    assert record.metadata == {"chunk_count": 1}
    assert record.finished_at is not None


def test_fail_run_records_error_summary(tmp_path):
    db = tmp_path / "radar.sqlite3"
    run_id = start_run(db, kind="wechat_ingest_range", target="group_message:window")

    fail_run(db, run_id, RuntimeError("接口超时"))

    record = get_run(db, run_id)
    assert record is not None
    assert record.status == "failed"
    assert record.error_message == "接口超时"


def test_list_runs_filters_recent_records(tmp_path):
    db = tmp_path / "radar.sqlite3"
    first = start_run(db, kind="wechat_ingest_range", target="group_message:first")
    second = start_run(db, kind="wechat_ingest_window", target="group_message:second")
    finish_run(db, first, status="skipped")
    fail_run(db, second, RuntimeError("接口超时"))

    records = list_runs(db, status="failed", limit=10)

    assert [record.run_id for record in records] == [second]
    assert records[0].kind == "wechat_ingest_window"


def test_get_running_run_and_fail_stale_runs(tmp_path):
    db = tmp_path / "radar.sqlite3"
    run_id = start_run(db, kind="wechat_ingest_range", target="group_message:day")

    running = get_running_run(db, kind="wechat_ingest_range", target="group_message:day")
    assert running is not None
    assert running.run_id == run_id

    stale_count = fail_stale_runs(db, older_than=datetime.now() + timedelta(seconds=1), kind="wechat_ingest_range")
    assert stale_count == 1

    record = get_run(db, run_id)
    assert record is not None
    assert record.status == "failed"
    assert get_running_run(db, kind="wechat_ingest_range", target="group_message:day") is None
