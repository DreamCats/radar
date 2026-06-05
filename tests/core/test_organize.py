from __future__ import annotations

from datetime import datetime

from radar.core.config import RadarConfig
from radar.core.models import MessageClassification, RawMessage
from radar.core.organize import (
    OrganizeClassificationFilters,
    OrganizeEvidenceFilters,
    list_classification_clusters,
    list_classification_evidence,
)
from radar.core.organize_aggregates import (
    OrganizeAggregateEvidenceFilters,
    OrganizeAggregateFilters,
    list_aggregate_evidence,
    list_aggregate_themes,
)
from radar.core.store import connect, init_db, upsert_message_classifications, upsert_messages
from radar.core.usecases.aggregation.models import (
    AggregateTopicsResult,
    RefinedTheme,
    RefinedThemeStock,
    RefineAggregateTopicsResult,
)
from radar.core.usecases.aggregation.storage import store_refine_result


def test_list_classification_clusters_groups_with_evidence(tmp_path):
    config = _config(tmp_path)
    messages = [
        _message("m1", "2026-06-04T10:00:00", "玻璃基板研究观点"),
        _message("m2", "2026-06-04T10:05:00", "电话会报名"),
        _message("m3", "2026-06-04T10:10:00", "继续推荐玻璃基板"),
    ]
    _seed(config, messages)
    _seed_classifications(
        config,
        [
            _classification(messages[0], "research", 0.90, "研究观点"),
            _classification(messages[1], "event", 0.88, "会议通知"),
            _classification(messages[2], "tool_ad", 0.60, "历史工具分类", status="needs_review"),
        ],
    )

    conn = connect(config.database_path)
    try:
        page = list_classification_clusters(conn, OrganizeClassificationFilters(keyword="玻璃", evidence_limit=5))
    finally:
        conn.close()

    assert page.summary.classified_count == 2
    assert page.summary.total_count == 1
    assert page.summary.cluster_count == 1
    assert page.summary.low_confidence_count == 1
    assert page.summary.hidden_count == 1
    assert page.clusters[0].category == "research"
    assert page.clusters[0].label == "研究观点"
    assert page.clusters[0].count == 1
    assert [item.message_id for item in page.clusters[0].evidence] == ["m1"]
    assert page.clusters[0].evidence[0].category == "research"


def test_list_classification_clusters_can_skip_evidence(tmp_path):
    config = _config(tmp_path)
    message = _message("m1", "2026-06-04T10:00:00", "玻璃基板研究观点")
    _seed(config, [message])
    _seed_classifications(config, [_classification(message, "research", 0.90, "研究观点")])

    conn = connect(config.database_path)
    try:
        page = list_classification_clusters(conn, OrganizeClassificationFilters(evidence_limit=0))
    finally:
        conn.close()

    assert page.summary.total_count == 1
    assert page.clusters[0].count == 1
    assert page.clusters[0].evidence == []


def test_list_classification_clusters_orders_by_value_and_hides_low_value_rows(tmp_path):
    config = _config(tmp_path)
    messages = [
        _message("m1", "2026-06-04T10:00:00", "研究观点"),
        _message("m2", "2026-06-04T10:01:00", "会议报名"),
        _message("m3", "2026-06-04T10:02:00", "继续重点推荐"),
        _message("m4", "2026-06-04T10:03:00", "信息残缺"),
        _message("m5", "2026-06-04T10:04:00", "产能变化"),
        _message("m6", "2026-06-04T10:05:00", "收到"),
        _message("m7", "2026-06-04T10:06:00", "低置信研究"),
        _message("m8", "2026-06-04T10:07:00", "基本确定研究"),
    ]
    _seed(config, messages)
    _seed_classifications(
        config,
            [
                _classification(messages[0], "research", 0.90, "研究观点"),
                _classification(messages[1], "event", 0.90, "会议活动"),
                _classification(messages[2], "recommendation", 0.90, "投资推荐"),
                _classification(messages[3], "unknown", 0.40, "信息不足", status="needs_review"),
                _classification(messages[4], "industry", 0.90, "产业变化"),
                _classification(messages[5], "chat", 0.90, "闲聊", status="ignored"),
                _classification(messages[6], "research", 0.50, "低置信", status="needs_review"),
                _classification(messages[7], "research", 0.70, "基本确定"),
            ],
        )

    conn = connect(config.database_path)
    try:
        page = list_classification_clusters(conn, OrganizeClassificationFilters())
        hidden = list_classification_clusters(conn, OrganizeClassificationFilters(category="unknown"))
    finally:
        conn.close()

    assert page.summary.classified_count == 8
    assert page.summary.total_count == 4
    assert page.summary.cluster_count == 4
    assert page.summary.low_confidence_count == 3
    assert page.summary.noise_count == 1
    assert page.summary.hidden_count == 4
    assert [cluster.category for cluster in page.clusters] == ["recommendation", "research", "industry", "event"]
    assert [cluster.low_confidence_count for cluster in page.clusters] == [0, 0, 0, 0]
    assert hidden.summary.classified_count == 1
    assert hidden.summary.total_count == 0
    assert hidden.summary.low_confidence_count == 1
    assert hidden.clusters == []


def test_list_classification_evidence_pages_by_time_and_message_id(tmp_path):
    config = _config(tmp_path)
    messages = [
        _message("m1", "2026-06-04T10:00:00", "第一条研究"),
        _message("m2", "2026-06-04T10:01:00", "第二条研究"),
        _message("m3", "2026-06-04T10:02:00", "第三条研究"),
    ]
    _seed(config, messages)
    _seed_classifications(
        config,
        [
            _classification(messages[0], "research", 0.90, "研究观点"),
            _classification(messages[1], "research", 0.90, "研究观点"),
            _classification(messages[2], "research", 0.90, "研究观点"),
        ],
    )

    conn = connect(config.database_path)
    try:
        first = list_classification_evidence(conn, OrganizeEvidenceFilters(category="research", limit=2))
        second = list_classification_evidence(
            conn,
            OrganizeEvidenceFilters(
                category="research",
                limit=2,
                cursor_time=first.next_cursor_time,
                cursor_id=first.next_cursor_id,
            ),
        )
    finally:
        conn.close()

    assert [item.message_id for item in first.items] == ["m3", "m2"]
    assert first.next_cursor_id == "m2"
    assert [item.message_id for item in second.items] == ["m1"]
    assert second.next_cursor_id is None


def test_list_aggregate_themes_reads_latest_refine_result_with_evidence(tmp_path):
    config = _config(tmp_path)
    messages = [
        _message("m1", "2026-06-04T10:00:00", "玻璃基板订单更新"),
        _message("m2", "2026-06-04T10:05:00", "玻璃基板设备推荐"),
        _message("m3", "2026-06-04T10:10:00", "光模块景气更新"),
    ]
    _seed(config, messages)
    _seed_classifications(
        config,
        [
            _classification(messages[0], "research", 0.90, "研究观点"),
            _classification(messages[1], "recommendation", 0.92, "投资推荐"),
            _classification(messages[2], "research", 0.88, "研究观点"),
        ],
    )

    conn = connect(config.database_path)
    try:
        init_db(conn)
        store_refine_result(conn, _refine_result("old-run", "2026-06-03T00:00:00", "2026-06-03T23:00:00", ["m3"]))
        store_refine_result(conn, _refine_result("new-run", "2026-06-04T00:00:00", "2026-06-04T23:00:00", ["m1", "m2"]))
        page = list_aggregate_themes(
            conn,
            OrganizeAggregateFilters(
                keyword="玻璃",
                start_time=datetime.fromisoformat("2026-06-04T09:00:00"),
                end_time=datetime.fromisoformat("2026-06-04T12:00:00"),
                evidence_limit=1,
            ),
        )
    finally:
        conn.close()

    assert page.result is not None
    assert page.result.run_id == "new-run"
    assert page.result.theme_count == 1
    assert page.result.evidence_message_count == 2
    assert page.themes[0].theme_name == "玻璃基板投资线索"
    assert page.themes[0].priority_score > 0
    assert [item.message_id for item in page.themes[0].evidence] == ["m2"]


def test_list_aggregate_themes_orders_by_priority_score(tmp_path):
    config = _config(tmp_path)
    messages = [
        _message("old", "2026-06-04T09:00:00", "旧主题高行动分"),
        _message("new-1", "2026-06-04T11:50:00", "新主题证据一"),
        _message("new-2", "2026-06-04T11:55:00", "新主题证据二"),
    ]
    _seed(config, messages)
    themes = [
        RefinedTheme(
            theme_name="旧高行动分",
            evidence_message_ids=["old"],
            novelty="continuing",
            confidence=0.90,
            actionability_score=90,
        ),
        RefinedTheme(
            theme_name="新证据增强",
            evidence_message_ids=["new-1", "new-2"],
            novelty="new",
            confidence=0.82,
            actionability_score=78,
        ),
    ]
    result = _refine_result("run-priority", "2026-06-04T09:00:00", "2026-06-04T12:00:00", ["old"]).model_copy(
        update={"themes": themes}
    )

    conn = connect(config.database_path)
    try:
        init_db(conn)
        store_refine_result(conn, result)
        page = list_aggregate_themes(
            conn,
            OrganizeAggregateFilters(
                start_time=datetime.fromisoformat("2026-06-04T09:00:00"),
                end_time=datetime.fromisoformat("2026-06-04T12:00:00"),
                evidence_limit=0,
            ),
        )
    finally:
        conn.close()

    assert [theme.theme_name for theme in page.themes] == ["新证据增强", "旧高行动分"]
    assert page.themes[0].priority_score > page.themes[1].priority_score
    assert page.themes[0].actionability_score < page.themes[1].actionability_score


def test_list_aggregate_evidence_pages_by_theme_message_ids(tmp_path):
    config = _config(tmp_path)
    messages = [
        _message("m1", "2026-06-04T10:00:00", "第一条玻璃基板"),
        _message("m2", "2026-06-04T10:01:00", "第二条玻璃基板"),
        _message("m3", "2026-06-04T10:02:00", "第三条玻璃基板"),
    ]
    _seed(config, messages)
    _seed_classifications(
        config,
        [
            _classification(messages[0], "research", 0.90, "研究观点"),
            _classification(messages[1], "research", 0.91, "研究观点"),
            _classification(messages[2], "research", 0.92, "研究观点"),
        ],
    )

    conn = connect(config.database_path)
    try:
        init_db(conn)
        store_refine_result(conn, _refine_result("run-1", "2026-06-04T00:00:00", "2026-06-04T23:00:00", ["m1", "m2", "m3"]))
        first = list_aggregate_evidence(conn, OrganizeAggregateEvidenceFilters(run_id="run-1", theme_index=0, limit=2))
        second = list_aggregate_evidence(
            conn,
            OrganizeAggregateEvidenceFilters(
                run_id="run-1",
                theme_index=0,
                limit=2,
                cursor_time=first.next_cursor_time,
                cursor_id=first.next_cursor_id,
            ),
        )
    finally:
        conn.close()

    assert [item.message_id for item in first.items] == ["m3", "m2"]
    assert first.next_cursor_id == "m2"
    assert [item.message_id for item in second.items] == ["m1"]
    assert second.next_cursor_id is None


def _config(tmp_path) -> RadarConfig:
    return RadarConfig(storage={"data_dir": tmp_path, "database": tmp_path / "radar.sqlite3"})


def _seed(config: RadarConfig, messages: list[RawMessage]) -> None:
    conn = connect(config.database_path)
    try:
        init_db(conn)
        upsert_messages(conn, messages)
    finally:
        conn.close()


def _seed_classifications(config: RadarConfig, classifications: list[MessageClassification]) -> None:
    conn = connect(config.database_path)
    try:
        init_db(conn)
        upsert_message_classifications(conn, classifications)
    finally:
        conn.close()


def _message(message_id: str, message_time: str, content: str) -> RawMessage:
    return RawMessage(
        message_id=message_id,
        source="个人群",
        sender="tester",
        message_time=datetime.fromisoformat(message_time),
        raw_content=content,
        group_name="测试群",
        fetch_time=datetime.fromisoformat("2026-06-04T11:00:00"),
        fetch_window="20260604100000-20260604110000",
    )


def _classification(
    message: RawMessage,
    category: str,
    confidence: float,
    reason: str,
    *,
    status: str = "auto",
) -> MessageClassification:
    now = datetime.fromisoformat("2026-06-04T12:00:00")
    return MessageClassification(
        message_id=message.message_id,
        category=category,
        confidence=confidence,
        reason=reason,
        status=status,
        classifier_type="llm",
        llm_provider="test-provider",
        prompt_version="test",
        classifier_version="test",
        created_at=now,
        updated_at=now,
    )


def _refine_result(run_id: str, start_time: str, end_time: str, evidence_ids: list[str]) -> RefineAggregateTopicsResult:
    local_result = AggregateTopicsResult(
        trade_date="20260604",
        extractor_version="test-anchor",
        start_time=datetime.fromisoformat(start_time),
        end_time=datetime.fromisoformat(end_time),
        categories=["research", "recommendation"],
        min_classification_confidence=0.7,
        scoped_message_count=len(evidence_ids),
        anchored_message_count=len(evidence_ids),
        topic_count=1,
        topics=[],
    )
    return RefineAggregateTopicsResult(
        run_id=run_id,
        input_hash=f"hash-{run_id}",
        status="succeeded",
        trade_date="20260604",
        extractor_version="test-anchor",
        prompt_version="test-refine",
        candidate_count=1,
        theme_count=1,
        llm_batch_count=1,
        failed_llm_batches=0,
        max_concurrency=2,
        local_result=local_result,
        themes=[
            RefinedTheme(
                theme_name="玻璃基板投资线索",
                aliases=["玻璃基板"],
                summary="玻璃基板订单和设备线索集中出现",
                investment_logic="供需边际变化带来投资关注度提升",
                catalysts=["订单更新"],
                related_stocks=[RefinedThemeStock(name="测试股份", reason="设备受益", confidence=0.8)],
                evidence_message_ids=evidence_ids,
                novelty="medium",
                confidence=0.82,
                actionability_score=78,
                risk_notes=["验证不足"],
                merge_from_candidate_ids=["candidate-1"],
            )
        ],
    )
