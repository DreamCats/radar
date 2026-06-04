from __future__ import annotations

from radar.core.runs import fail_run, finish_run, get_run, start_run


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
